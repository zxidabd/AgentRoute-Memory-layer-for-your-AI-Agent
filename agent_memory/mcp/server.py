"""Model Context Protocol (MCP) Protocol Engine & Tool Registry for MemoryBrain.

Implements JSON-RPC 2.0 MCP 2024-11-05 specification for Claude Desktop, Cursor, and Windsurf.
"""

import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from ..models.db_models import Memory, MemoryStatus, SourceType, Organization
from ..engine.embeddings import EmbeddingService
from ..engine.ranking import MemoryRanker
from ..security.encryption import encrypt_field, decrypt_field
from ..billing.usage_tracker import UsageTracker
from ..billing.plans import BillableEventType
from ..billing.plan_enforcer import PlanEnforcer

logger = logging.getLogger("memorybrain.mcp")


class MemoryBrainMCPServer:
    """Core MCP server executing tools/list, tools/call, initialize, and ping."""

    SERVER_INFO = {
        "name": "memorybrain-mcp",
        "version": "1.0.0"
    }

    CAPABILITIES = {
        "tools": {
            "listChanged": False
        },
        "resources": {},
        "prompts": {}
    }

    TOOLS_REGISTRY = [
        {
            "name": "recall_memories",
            "description": "Search long-term memory for relevant facts, user preferences, past project context, decisions, and instructions.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "Identifier of the user or agent context (e.g. 'alice', 'founder_123')."
                    },
                    "query": {
                        "type": "string",
                        "description": "Natural language question or search phrase (e.g. 'What is the design budget?')."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of memories to return (default: 5).",
                        "default": 5
                    }
                },
                "required": ["user_id", "query"]
            }
        },
        {
            "name": "save_memory",
            "description": "Store a new fact, instruction, preference, or project update to permanent memory. Automatically resolves contradictions and updates prior records.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "Identifier of the user or agent context."
                    },
                    "statement": {
                        "type": "string",
                        "description": "The exact fact or preference to remember (e.g. 'User prefers Next.js with TypeScript.')."
                    },
                    "category": {
                        "type": "string",
                        "enum": ["FACT", "PREFERENCE", "DECISION", "INSTRUCTION"],
                        "description": "Category of the memory.",
                        "default": "FACT"
                    }
                },
                "required": ["user_id", "statement"]
            }
        },
        {
            "name": "get_user_profile",
            "description": "Retrieve the complete active knowledge profile and list of all stored memories for a user.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "Identifier of the user."
                    }
                },
                "required": ["user_id"]
            }
        },
        {
            "name": "forget_memory",
            "description": "Purge specific memories or wipe all memories for a user under GDPR compliance.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "Identifier of the user."
                    },
                    "memory_id": {
                        "type": "string",
                        "description": "Optional specific memory ID to forget. If omitted, wipes all memories for the user."
                    }
                },
                "required": ["user_id"]
            }
        },
        {
            "name": "search_data_assets",
            "description": "Discover enterprise data assets (tables, views, pipelines) across Snowflake, BigQuery, Postgres using natural language. Returns certified badges, health alerts, and column schemas.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query (e.g. 'verified churn metrics', 'daily revenue table')."
                    },
                    "platform": {
                        "type": "string",
                        "description": "Optional platform filter (e.g. 'snowflake', 'bigquery', 'postgres')."
                    },
                    "certified_only": {
                        "type": "boolean",
                        "description": "Filter to only certified data assets.",
                        "default": False
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of assets to return (default: 5).",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        },
        {
            "name": "get_table_schema",
            "description": "Retrieve detailed schema, column data types, primary keys, and documentation for a specific table or view by its Fully Qualified Name (FQN).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "fqn": {
                        "type": "string",
                        "description": "Fully Qualified Name of the table (e.g. 'snowflake.analytics_prod.core.dim_customer_churn')."
                    }
                },
                "required": ["fqn"]
            }
        },
        {
            "name": "get_metric_definition",
            "description": "Retrieve the certified definition, calculation formula, canonical SQL expression, and required JOIN paths for an enterprise business KPI.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "metric_name": {
                        "type": "string",
                        "description": "Identifier of the metric (e.g. 'customer_churn_rate', 'net_revenue_retention')."
                    }
                },
                "required": ["metric_name"]
            }
        },
        {
            "name": "get_data_lineage",
            "description": "Trace data lineage for an asset. Can trace 'upstream' (data provenance & root sources) or 'downstream' (blast radius of broken pipelines).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "fqn": {
                        "type": "string",
                        "description": "Fully Qualified Name of the table or pipeline."
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["upstream", "downstream"],
                        "description": "Direction of lineage traversal ('upstream' for provenance, 'downstream' for impact analysis).",
                        "default": "upstream"
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum traversal depth (default: 5).",
                        "default": 5
                    }
                },
                "required": ["fqn"]
            }
        }
    ]

    def __init__(self, embeddings: Optional[EmbeddingService] = None, ranker: Optional[MemoryRanker] = None):
        self.embeddings = embeddings or EmbeddingService()
        self.ranker = ranker or MemoryRanker(self.embeddings)

    def handle_request(self, db: Session, org_id: str, request: Dict[str, Any], project_id: Optional[str] = None) -> Dict[str, Any]:
        """Dispatches incoming JSON-RPC 2.0 requests and returns response envelope."""
        req_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})

        try:
            if method == "initialize":
                return self._jsonrpc_response(req_id, {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": self.SERVER_INFO,
                    "capabilities": self.CAPABILITIES
                })

            elif method == "notifications/initialized" or method == "initialized":
                # Client acknowledgment, no response needed for notifications
                return {"jsonrpc": "2.0", "result": {}}

            elif method == "ping":
                return self._jsonrpc_response(req_id, {})

            elif method == "tools/list":
                return self._jsonrpc_response(req_id, {
                    "tools": self.TOOLS_REGISTRY
                })

            elif method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments", {})
                result = self._execute_tool(db, org_id, tool_name, tool_args, project_id=project_id)
                return self._jsonrpc_response(req_id, result)

            else:
                return self._jsonrpc_error(req_id, -32601, f"Method '{method}' not found.")

        except Exception as e:
            logger.exception(f"Error handling MCP request {method}: {str(e)}")
            return self._jsonrpc_error(req_id, -32000, str(e))

    def _execute_tool(self, db: Session, org_id: str, name: str, args: Dict[str, Any], project_id: Optional[str] = None) -> Dict[str, Any]:
        """Executes the specific MemoryBrain MCP tool."""
        if name == "recall_memories":
            user_id = args.get("user_id")
            query = args.get("query")
            limit = int(args.get("limit", 5))

            if not user_id or not query:
                return {"isError": True, "content": [{"type": "text", "text": "Both 'user_id' and 'query' are required."}]}

            # Track billable query event
            UsageTracker.record_event(
                db=db,
                org_id=org_id,
                endpoint="/mcp/recall_memories",
                event_type=BillableEventType.RECALL_QUERY,
                units_billed=1
            )

            # Query memories
            q = db.query(Memory).filter(
                Memory.org_id == org_id,
                Memory.user_id == user_id,
                Memory.status == MemoryStatus.ACTIVE.value
            )
            if project_id:
                q = q.filter((Memory.project_id == project_id) | (Memory.project_id.is_(None)))

            memories = q.all()
            if not memories:
                return {
                    "content": [{
                        "type": "text",
                        "text": f"No active memories found for user '{user_id}' matching query."
                    }]
                }

            # Decrypt statements & build MemoryRecord list for ranking
            from ..models.memory import MemoryRecord
            mem_models = []
            for m in memories:
                try:
                    stmt = decrypt_field(m.statement)
                except Exception:
                    stmt = m.statement

                embed = None
                if m.embedding_json:
                    try:
                        embed = json.loads(m.embedding_json)
                    except Exception:
                        embed = self.embeddings.embed_text(stmt)
                else:
                    embed = self.embeddings.embed_text(stmt)

                m_created_at = m.created_at
                if m_created_at and m_created_at.tzinfo is None:
                    m_created_at = m_created_at.replace(tzinfo=timezone.utc)
                elif not m_created_at:
                    m_created_at = datetime.now(timezone.utc)

                mem_models.append(
                    MemoryRecord(
                        id=m.id,
                        tenant_id=m.org_id,
                        user_id=m.user_id,
                        statement=stmt,
                        category=m.category,
                        importance=m.importance_score or 0.7,
                        access_count=m.access_count or 0,
                        is_active=(m.status == MemoryStatus.ACTIVE.value),
                        created_at=m_created_at,
                        embedding=embed
                    )
                )

            ranked = self.ranker.rank(query, mem_models, limit=limit)
            if not ranked:
                return {
                    "content": [{
                        "type": "text",
                        "text": f"No relevant memories found for user '{user_id}' matching '{query}'."
                    }]
                }

            formatted_output = [f"Found {len(ranked)} relevant memories for '{user_id}':"]
            for idx, (mem, score) in enumerate(ranked, 1):
                formatted_output.append(f"{idx}. [{mem.category}] {mem.statement} (relevance: {score:.2f}, ID: {mem.id})")

            return {
                "content": [{
                    "type": "text",
                    "text": "\n".join(formatted_output)
                }]
            }

        elif name == "save_memory":
            user_id = args.get("user_id")
            statement = args.get("statement")
            category = args.get("category", "FACT").upper()

            if not user_id or not statement:
                return {"isError": True, "content": [{"type": "text", "text": "Both 'user_id' and 'statement' are required."}]}

            # Enforce quota before saving
            PlanEnforcer.enforce_memory_quota(db, org_id)

            # Track billable turn
            UsageTracker.record_event(
                db=db,
                org_id=org_id,
                endpoint="/mcp/save_memory",
                event_type=BillableEventType.INGESTION_TURN,
                units_billed=1
            )

            # Generate embedding
            emb = self.embeddings.embed_text(statement)
            emb_json = json.dumps(emb) if emb else None

            # Encrypt statement
            enc_stmt = encrypt_field(statement)

            now = datetime.now(timezone.utc)
            mem_id = f"mem_{uuid.uuid4().hex[:12]}"
            memory = Memory(
                id=mem_id,
                org_id=org_id,
                project_id=project_id,
                user_id=user_id,
                statement=enc_stmt,
                category=category,
                embedding_json=emb_json,
                confidence_score=0.95,
                importance_score=0.85,
                freshness_score=1.00,
                status=MemoryStatus.ACTIVE.value,
                source_type=SourceType.DIRECT_USER.value,
                created_at=now,
                updated_at=now
            )
            db.add(memory)
            db.commit()

            return {
                "content": [{
                    "type": "text",
                    "text": f"Successfully remembered: \"{statement}\" (Category: {category}, ID: {mem_id})"
                }]
            }

        elif name == "get_user_profile":
            user_id = args.get("user_id")
            if not user_id:
                return {"isError": True, "content": [{"type": "text", "text": "'user_id' is required."}]}

            memories = db.query(Memory).filter(
                Memory.org_id == org_id,
                Memory.user_id == user_id,
                Memory.status == MemoryStatus.ACTIVE.value
            ).all()

            if not memories:
                return {
                    "content": [{
                        "type": "text",
                        "text": f"No active profile records stored for user '{user_id}'."
                    }]
                }

            lines = [f"### User Knowledge Profile: {user_id} ({len(memories)} memories)\n"]
            for m in memories:
                try:
                    stmt = decrypt_field(m.statement)
                except Exception:
                    stmt = m.statement
                created_str = m.created_at.strftime("%Y-%m-%d") if m.created_at else "Unknown"
                lines.append(f"- **[{m.category}]** {stmt} *(saved: {created_str})*")

            return {
                "content": [{
                    "type": "text",
                    "text": "\n".join(lines)
                }]
            }

        elif name == "forget_memory":
            user_id = args.get("user_id")
            memory_id = args.get("memory_id")

            if not user_id:
                return {"isError": True, "content": [{"type": "text", "text": "'user_id' is required."}]}

            if memory_id:
                mem = db.query(Memory).filter(
                    Memory.id == memory_id,
                    Memory.org_id == org_id,
                    Memory.user_id == user_id
                ).first()
                if not mem:
                    return {"isError": True, "content": [{"type": "text", "text": f"Memory '{memory_id}' not found."}]}

                mem.status = MemoryStatus.SOFT_DELETED.value
                db.commit()
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Memory '{memory_id}' has been soft-deleted and removed from active context."
                    }]
                }
            else:
                # Wipe all memories for user
                count = db.query(Memory).filter(
                    Memory.org_id == org_id,
                    Memory.user_id == user_id
                ).update({Memory.status: MemoryStatus.SOFT_DELETED.value})
                db.commit()
                return {
                    "content": [{
                        "type": "text",
                        "text": f"GDPR Wipe complete: {count} memories for user '{user_id}' were removed."
                    }]
                }

        elif name == "search_data_assets":
            from ..engine.data_assets import DataAssetEngine
            query = args.get("query")
            if not query:
                return {"isError": True, "content": [{"type": "text", "text": "'query' is required."}]}

            engine = DataAssetEngine(session=db, embedding_service=self.embeddings)
            results = engine.search_assets(
                org_id=org_id,
                query=query,
                platform=args.get("platform"),
                certified_only=bool(args.get("certified_only", False)),
                limit=int(args.get("limit", 5))
            )

            if not results["assets"]:
                return {
                    "content": [{
                        "type": "text",
                        "text": f"No enterprise data assets found matching query: '{query}'."
                    }]
                }

            lines = [f"### Enterprise Data Assets ({results['hits_count']} matches in {results['latency_ms']}ms)\n"]
            for a in results["assets"]:
                cert_badge = "✅ [CERTIFIED]" if a["is_certified"] else "⚪ [UNCERTIFIED]"
                lines.append(f"#### {cert_badge} `{a['fqn']}` ({a['platform'].upper()} {a['asset_type']})")
                if a["warning_banner"]:
                    lines.append(f"> {a['warning_banner']}")
                lines.append(f"- **Description**: {a['description'] or 'No description provided.'}")
                lines.append(f"- **Owner**: {a['owner'] or 'Unassigned'} | **Health**: {a['health_status']} | **Confidence**: {int(a['confidence_score'] * 100)}%")
                if a["columns"]:
                    col_preview = ", ".join([f"`{c.get('name')}` ({c.get('type')})" for c in a["columns"][:6]])
                    lines.append(f"- **Columns**: {col_preview}{'...' if len(a['columns']) > 6 else ''}")
                lines.append("")

            return {"content": [{"type": "text", "text": "\n".join(lines)}]}

        elif name == "get_table_schema":
            from ..engine.data_assets import DataAssetEngine
            fqn = args.get("fqn")
            if not fqn:
                return {"isError": True, "content": [{"type": "text", "text": "'fqn' is required."}]}

            engine = DataAssetEngine(session=db, embedding_service=self.embeddings)
            asset = engine.get_asset(org_id=org_id, fqn=fqn)
            if not asset:
                return {"isError": True, "content": [{"type": "text", "text": f"Data asset with FQN '{fqn}' not found."}]}

            cols = json.loads(asset.columns_json) if asset.columns_json else []
            lines = [
                f"# Table Schema: `{asset.fqn}`",
                f"- **Platform**: {asset.platform.upper()}",
                f"- **Type**: {asset.asset_type}",
                f"- **Certified**: {'Yes (by ' + str(asset.certified_by) + ')' if asset.is_certified else 'No'}",
                f"- **Owner**: {asset.owner or 'Unassigned'}",
                f"- **Health Status**: {asset.health_status}",
                f"- **Description**: {asset.description or 'None'}\n",
                "| Column | Data Type | PK | Nullable | Description |",
                "|---|---|---|---|---|"
            ]
            for c in cols:
                pk_str = "🔑 Yes" if c.get("is_pk") else "No"
                null_str = "Yes" if c.get("is_nullable", True) else "No"
                lines.append(f"| `{c.get('name')}` | `{c.get('type')}` | {pk_str} | {null_str} | {c.get('description') or ''} |")

            return {"content": [{"type": "text", "text": "\n".join(lines)}]}

        elif name == "get_metric_definition":
            from ..engine.data_assets import DataAssetEngine
            metric_name = args.get("metric_name")
            if not metric_name:
                return {"isError": True, "content": [{"type": "text", "text": "'metric_name' is required."}]}

            engine = DataAssetEngine(session=db, embedding_service=self.embeddings)
            metric = engine.get_metric(org_id=org_id, name=metric_name)
            if not metric:
                # Try search fallback
                hits = engine.search_metrics(org_id=org_id, query=metric_name, limit=1)
                if hits:
                    metric = hits[0]
                else:
                    return {"isError": True, "content": [{"type": "text", "text": f"Business metric '{metric_name}' not found."}]}

            lines = [
                f"# Business Metric: {metric['display_name']} (`{metric['name']}`)",
                f"- **Certified**: {'✅ Certified' if metric['is_certified'] else '⚪ Uncertified'}",
                f"- **Steward**: {metric['steward'] or 'Unassigned'}",
                f"- **Definition**: {metric['definition']}",
                f"- **Formula**: `{metric['formula'] or 'N/A'}`",
                f"- **Primary Table**: `{metric['primary_table_fqn'] or 'N/A'}`\n",
                "### Canonical SQL Expression:",
                f"```sql\n{metric['sql_expression'] or '-- No SQL expression defined'}\n```\n",
                "### Recommended JOIN Recipe:",
                f"```sql\n{metric['join_recipe'] or '-- Direct query on primary table'}\n```"
            ]
            return {"content": [{"type": "text", "text": "\n".join(lines)}]}

        elif name == "get_data_lineage":
            from ..engine.data_assets import DataAssetEngine
            fqn = args.get("fqn")
            direction = args.get("direction", "upstream")
            max_depth = int(args.get("max_depth", 5))
            if not fqn:
                return {"isError": True, "content": [{"type": "text", "text": "'fqn' is required."}]}

            engine = DataAssetEngine(session=db, embedding_service=self.embeddings)
            if direction == "upstream":
                res = engine.get_upstream_lineage(org_id=org_id, fqn=fqn, max_depth=max_depth)
                lines = [
                    f"# Upstream Provenance: `{fqn}`",
                    f"- **Root Sources**: {', '.join([f'`{s}`' for s in res['root_sources']]) or 'None (Root Table)'}",
                    f"- **Total Upstream Dependencies**: {len(res['nodes'])}\n",
                    "### Upstream Node Dependency Chain:"
                ]
                for n in res["nodes"]:
                    cert_badge = "✅" if n["is_certified"] else "⚪"
                    lines.append(f"- (Level -{n['depth']}) {cert_badge} `{n['fqn']}` [Health: {n['health_status']}]")
            else:
                res = engine.get_downstream_blast_radius(org_id=org_id, fqn=fqn, max_depth=max_depth)
                lines = [
                    f"# Downstream Blast Radius: `{fqn}`",
                    f"- **Total Impacted Assets**: {res['total_impacted_assets']}\n",
                    "### Impacted Downstream Tables & Dashboards:"
                ]
                for n in res["impacted_nodes"]:
                    lines.append(f"- (Level +{n['depth']}) `{n['fqn']}` ({n['asset_type']}) - Owner: {n['owner']}")

            return {"content": [{"type": "text", "text": "\n".join(lines)}]}

        else:
            return {"isError": True, "content": [{"type": "text", "text": f"Unknown tool: {name}"}]}

    def _jsonrpc_response(self, req_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": result
        }

    def _jsonrpc_error(self, req_id: Any, code: int, message: str) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": code,
                "message": message
            }
        }
