"""Automated Test Suite for Model Context Protocol (MCP) Server and Tool Registry."""

import sys
import json
from pathlib import Path
from fastapi.testclient import TestClient

# Windows console encoding fix
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from agent_memory.database import init_db, get_db
from agent_memory.models.db_models import Organization, Memory, MemoryStatus, UsageEvent, APIKey
from agent_memory.mcp.server import MemoryBrainMCPServer
from agent_memory.auth.api_key_service import APIKeyService
from agent_memory.api.server import app

client = TestClient(app)


def run_mcp_test_suite():
    print("\n" + "=" * 78)
    print(" 🔌 MODEL CONTEXT PROTOCOL (MCP) SERVER & CLAUDE INTEGRATION TEST SUITE")
    print("=" * 78)

    init_db()

    test_org_id = "org_mcp_test_corp"
    user_id = "claude_user_alex"

    # Setup test org and API key
    with get_db() as db:
        org = db.query(Organization).filter(Organization.id == test_org_id).first()
        if not org:
            org = Organization(
                id=test_org_id,
                name="MCP Robotics Inc",
                slug="mcp-robotics-corp",
                tier="growth",
                subscription_status="active"
            )
            db.add(org)
            db.commit()

        # Clean prior memories & usage
        db.query(Memory).filter(Memory.org_id == test_org_id).delete()
        db.query(UsageEvent).filter(UsageEvent.org_id == test_org_id).delete()
        db.commit()

        # Generate fresh project key
        key_data = APIKeyService.generate_api_key(
            db=db,
            org_id=test_org_id,
            name="Claude Desktop MCP Key",
            environment="prod",
            role="developer"
        )
        api_key = key_data["api_key"]

    server = MemoryBrainMCPServer()

    # -------------------------------------------------------------
    # Test 1: MCP JSON-RPC Initialize & Ping Handshake
    # -------------------------------------------------------------
    print("\n▶ [Test 1] MCP Initialize & Handshake Protocol...")
    with get_db() as db:
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "claude-desktop", "version": "1.0.0"}
            }
        }
        resp = server.handle_request(db, org_id=test_org_id, request=init_req)
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        result = resp["result"]
        assert result["protocolVersion"] == "2024-11-05"
        assert result["serverInfo"]["name"] == "memorybrain-mcp"
        assert "tools" in result["capabilities"]

        # Ping
        ping_resp = server.handle_request(db, org_id=test_org_id, request={"jsonrpc": "2.0", "id": 2, "method": "ping"})
        assert ping_resp["result"] == {}
    print("  ✅ MCP protocol handshake (initialize, ping) verified!")

    # -------------------------------------------------------------
    # Test 2: Tools Discovery (tools/list)
    # -------------------------------------------------------------
    print("\n▶ [Test 2] MCP Tools Discovery (tools/list)...")
    with get_db() as db:
        tools_req = {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}}
        tools_resp = server.handle_request(db, org_id=test_org_id, request=tools_req)
        tools = tools_resp["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        assert "recall_memories" in tool_names
        assert "save_memory" in tool_names
        assert "get_user_profile" in tool_names
        assert "forget_memory" in tool_names
    print(f"  ✅ Discovered {len(tools)} tools: {', '.join(tool_names)}")

    # -------------------------------------------------------------
    # Test 3: Tool Execution: save_memory
    # -------------------------------------------------------------
    print("\n▶ [Test 3] MCP Tool Execution: save_memory...")
    with get_db() as db:
        save_req = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "save_memory",
                "arguments": {
                    "user_id": user_id,
                    "statement": "Alex prefers writing frontend code in Next.js 14 and Tailwind CSS.",
                    "category": "PREFERENCE"
                }
            }
        }
        save_resp = server.handle_request(db, org_id=test_org_id, request=save_req)
        assert "result" in save_resp
        content = save_resp["result"]["content"][0]["text"]
        assert "Successfully remembered" in content
        assert "Next.js 14" in content

        # Also save a second memory
        save_req2 = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "save_memory",
                "arguments": {
                    "user_id": user_id,
                    "statement": "Alex decided the microservices architecture will use gRPC and PostgreSQL.",
                    "category": "DECISION"
                }
            }
        }
        server.handle_request(db, org_id=test_org_id, request=save_req2)

        # Verify usage event recorded
        events = db.query(UsageEvent).filter(
            UsageEvent.org_id == test_org_id,
            UsageEvent.endpoint == "/mcp/save_memory"
        ).all()
        assert len(events) >= 1
    print("  ✅ Memory securely ingested & usage event metered via MCP save_memory tool!")

    # -------------------------------------------------------------
    # Test 4: Tool Execution: recall_memories
    # -------------------------------------------------------------
    print("\n▶ [Test 4] MCP Tool Execution: recall_memories (Semantic Search)...")
    with get_db() as db:
        recall_req = {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "recall_memories",
                "arguments": {
                    "user_id": user_id,
                    "query": "Which frontend framework does Alex like to use?",
                    "limit": 3
                }
            }
        }
        recall_resp = server.handle_request(db, org_id=test_org_id, request=recall_req)
        recall_text = recall_resp["result"]["content"][0]["text"]
        assert "Next.js 14" in recall_text
        assert "PREFERENCE" in recall_text
    print("  ✅ Claude accurately recalled relevant context via MCP recall_memories tool!")

    # -------------------------------------------------------------
    # Test 5: Tool Execution: get_user_profile
    # -------------------------------------------------------------
    print("\n▶ [Test 5] MCP Tool Execution: get_user_profile...")
    with get_db() as db:
        profile_req = {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "get_user_profile",
                "arguments": {"user_id": user_id}
            }
        }
        profile_resp = server.handle_request(db, org_id=test_org_id, request=profile_req)
        profile_text = profile_resp["result"]["content"][0]["text"]
        assert "User Knowledge Profile: claude_user_alex" in profile_text
        assert "Next.js" in profile_text
        assert "gRPC" in profile_text
    print("  ✅ User profile summary assembled with full knowledge base!")

    # -------------------------------------------------------------
    # Test 6: Tool Execution: forget_memory (GDPR)
    # -------------------------------------------------------------
    print("\n▶ [Test 6] MCP Tool Execution: forget_memory...")
    with get_db() as db:
        forget_req = {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {
                "name": "forget_memory",
                "arguments": {"user_id": user_id}
            }
        }
        forget_resp = server.handle_request(db, org_id=test_org_id, request=forget_req)
        forget_text = forget_resp["result"]["content"][0]["text"]
        assert "GDPR Wipe complete" in forget_text

        # Verify memories are soft-deleted
        active_count = db.query(Memory).filter(
            Memory.org_id == test_org_id,
            Memory.user_id == user_id,
            Memory.status == MemoryStatus.ACTIVE.value
        ).count()
        assert active_count == 0
    print("  ✅ Memory wipe executed successfully via MCP forget_memory!")

    # -------------------------------------------------------------
    # Test 7: Remote HTTP Messages Endpoint Authentication & Execution
    # -------------------------------------------------------------
    print("\n▶ [Test 7] Remote HTTP /mcp/messages Endpoint...")
    # Unauthenticated request must fail with 401
    r_unauth = client.post(
        "/mcp/messages",
        json={"jsonrpc": "2.0", "id": 10, "method": "tools/list"}
    )
    assert r_unauth.status_code == 401, f"Expected 401: {r_unauth.text}"

    # Authenticated request with Bearer header
    r_auth = client.post(
        "/mcp/messages",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"jsonrpc": "2.0", "id": 11, "method": "tools/list"}
    )
    assert r_auth.status_code == 200, f"Authenticated MCP request failed: {r_auth.text}"
    mcp_data = r_auth.json()
    assert mcp_data["result"]["tools"][0]["name"] == "recall_memories"

    # Authenticated via query parameter (?api_key=...)
    r_query_auth = client.post(
        f"/mcp/messages?api_key={api_key}",
        json={"jsonrpc": "2.0", "id": 12, "method": "ping"}
    )
    assert r_query_auth.status_code == 200
    assert r_query_auth.json()["result"] == {}
    print("  ✅ Remote HTTP MCP endpoints authenticated via Bearer token and Query params!")

    print("\n" + "=" * 78)
    print(" 🌟 ALL 7 MCP SERVER & TOOL REGISTRY TESTS PASSED (100%)")
    print("=" * 78 + "\n")


if __name__ == "__main__":
    run_mcp_test_suite()
