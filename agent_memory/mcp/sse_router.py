"""FastAPI SSE & HTTP Transport Router for Remote Model Context Protocol (MCP) clients."""

import asyncio
import json
import uuid
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, Response, Depends, HTTPException, Query, Header
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session
from ..database import get_db_session
from ..auth.api_key_service import APIKeyService
from .server import MemoryBrainMCPServer

logger = logging.getLogger("memorybrain.mcp.sse")
router = APIRouter(prefix="/mcp", tags=["Model Context Protocol (MCP)"])

# Shared MCP engine instance
mcp_engine = MemoryBrainMCPServer()

# Active SSE sessions: session_id -> asyncio.Queue
active_sessions: Dict[str, asyncio.Queue] = {}


def authenticate_mcp_request(
    api_key: Optional[str] = Query(None, description="API key in query string"),
    authorization: Optional[str] = Header(None, description="Authorization Bearer header"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Authenticates the incoming MCP client connection using query param or Bearer token."""
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "").strip()
    elif api_key:
        token = api_key.strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail="MCP Authentication required. Provide ?api_key=mb_... or 'Authorization: Bearer mb_...'"
        )

    # Master dev key check
    if token == "mem_dev_master_key_123":
        return {"org_id": "org_default_dev", "role": "owner", "project_id": None}

    key_record = APIKeyService.verify_api_key(db, token)
    if not key_record:
        raise HTTPException(status_code=401, detail="Invalid, expired, or revoked API key.")

    return {
        "org_id": key_record.org_id,
        "project_id": key_record.project_id,
        "role": key_record.role
    }


@router.get("/sse", summary="Establish MCP SSE transport connection")
async def mcp_sse_endpoint(
    request: Request,
    api_key: Optional[str] = Query(None),
    auth_info: Dict[str, Any] = Depends(authenticate_mcp_request)
):
    """
    Standard SSE endpoint for Claude Desktop / Cursor remote connection.
    Sends an 'endpoint' event pointing to /mcp/messages?session_id=..., then streams responses.
    """
    session_id = f"mcpsess_{uuid.uuid4().hex[:16]}"
    queue = asyncio.Queue()
    active_sessions[session_id] = queue

    # Build messages endpoint URL (preserve api_key in query if provided)
    key_param = f"&api_key={api_key}" if api_key else ""
    post_endpoint = f"/mcp/messages?session_id={session_id}{key_param}"

    async def event_generator():
        try:
            # 1. Send endpoint event per MCP SSE specification
            yield f"event: endpoint\ndata: {post_endpoint}\n\n"

            # 2. Stream subsequent JSON-RPC message events
            while True:
                if await request.is_disconnected():
                    break
                try:
                    # Wait for next outgoing message with 15s heartbeat timeout
                    message = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: message\ndata: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat ping comment to keep connection alive
                    yield ": ping\n\n"
        finally:
            active_sessions.pop(session_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/messages", summary="Post JSON-RPC message to active MCP session")
async def mcp_messages_endpoint(
    request: Request,
    session_id: Optional[str] = Query(None),
    auth_info: Dict[str, Any] = Depends(authenticate_mcp_request),
    db: Session = Depends(get_db_session)
):
    """
    Receives JSON-RPC request from client, executes tool/method,
    and returns response (both direct HTTP and pushed to SSE stream if session exists).
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    org_id = auth_info["org_id"]
    project_id = auth_info.get("project_id")

    # Execute MCP protocol logic
    response_payload = mcp_engine.handle_request(
        db=db,
        org_id=org_id,
        request=body,
        project_id=project_id
    )

    # Push to SSE stream if session_id is active
    if session_id and session_id in active_sessions:
        await active_sessions[session_id].put(response_payload)

    return JSONResponse(content=response_payload)
