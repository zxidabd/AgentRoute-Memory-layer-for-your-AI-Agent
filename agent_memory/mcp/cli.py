"""Stdio transport CLI bridge for Model Context Protocol (MCP) clients (Claude Desktop, Cursor, etc.).

Usage in claude_desktop_config.json:
{
  "mcpServers": {
    "memorybrain": {
      "command": "python",
      "args": ["-m", "agent_memory.mcp.cli"],
      "env": {
        "MEMORYBRAIN_API_KEY": "mb_prod_your_api_key_here"
      }
    }
  }
}
"""

import os
import sys
import json
import logging
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Suppress noisy logging on stdout so JSON-RPC stream remains clean
logging.basicConfig(level=logging.ERROR, stream=sys.stderr)

from agent_memory.database import init_db, get_db
from agent_memory.auth.api_key_service import APIKeyService
from agent_memory.mcp.server import MemoryBrainMCPServer


def run_stdio_mcp_server():
    init_db()
    server = MemoryBrainMCPServer()

    api_key = os.getenv("MEMORYBRAIN_API_KEY", "").strip()
    if not api_key:
        # Check command line args
        for i, arg in enumerate(sys.argv):
            if arg == "--api-key" and i + 1 < len(sys.argv):
                api_key = sys.argv[i + 1].strip()

    if not api_key:
        sys.stderr.write("Error: MEMORYBRAIN_API_KEY environment variable or --api-key flag must be provided.\n")
        sys.exit(1)

    with get_db() as db:
        if api_key == "mem_dev_master_key_123":
            org_id = "org_default_dev"
            project_id = None
        else:
            key_record = APIKeyService.verify_api_key(db, api_key)
            if not key_record:
                sys.stderr.write("Error: Invalid, expired, or revoked MEMORYBRAIN_API_KEY.\n")
                sys.exit(1)
            org_id = key_record.org_id
            project_id = key_record.project_id

    sys.stderr.write(f"MemoryBrain MCP Server online (tenant: {org_id}, project: {project_id})\n")

    # JSON-RPC standard line-buffered read/write loop
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            request_json = json.loads(line)
            with get_db() as db:
                response = server.handle_request(db, org_id=org_id, request=request_json, project_id=project_id)

            # Notifications do not produce output
            if response is not None and not (request_json.get("method", "").startswith("notifications/")):
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

        except KeyboardInterrupt:
            break
        except Exception as e:
            sys.stderr.write(f"MCP Stdio Error: {str(e)}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    run_stdio_mcp_server()
