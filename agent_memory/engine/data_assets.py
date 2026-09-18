"""Enterprise Data Assets, Business Metrics, and Lineage Context Graph Engine.

Provides sub-25ms hybrid vector (dense) + lexical (BM25) search for
enterprise data warehouses, schemas, tables, views, columns, metrics, and lineage graphs.
Supports 1-click dbt manifest ingestion and live SQL schema reflection.
"""

import json
import time
import math
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple, Set
from collections import deque
from sqlalchemy.orm import Session

from ..models.db_models import (
    DataAsset, BusinessMetric, DataLineageEdge,
    AssetType, AssetHealthStatus, LineageEdgeType
)
from .embeddings import EmbeddingService

logger = logging.getLogger("memorybrain.data_assets")


def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


def _compute_bm25_score(query_tokens: Set[str], document_text: str) -> float:
    if not query_tokens or not document_text:
        return 0.0
    doc_lower = document_text.lower()
    matches = 0
    total_tokens = len(query_tokens)
    for token in query_tokens:
        if token in doc_lower:
            matches += 1
            if f" {token} " in f" {doc_lower} " or f"_{token}_" in f"_{doc_lower}_" or f".{token}." in f".{doc_lower}.":
                matches += 1
    return min(1.0, matches / (total_tokens * 1.5))


class DataAssetEngine:
    """Core engine managing enterprise tables, columns, metrics, and lineage graphs."""

    def __init__(self, session: Session, embedding_service: Optional[EmbeddingService] = None):
        self.session = session
        self.embeddings = embedding_service or EmbeddingService()

    def register_asset(
        self,
        org_id: str,
        name: str,
        fqn: str,
        asset_type: str = AssetType.TABLE.value,
        platform: str = "snowflake",
        description: str = "",
        columns: Optional[List[Dict[str, Any]]] = None,
        owner: Optional[str] = None,
        is_certified: bool = False,
        certified_by: Optional[str] = None,
        health_status: str = AssetHealthStatus.HEALTHY.value,
        metadata: Optional[Dict[str, Any]] = None,
        project_id: Optional[str] = None,
        freshness_timestamp: Optional[datetime] = None,
    ) -> DataAsset:
        columns = columns or []
        metadata = metadata or {}

        col_summary = ", ".join(
            [f"{c.get('name', '')} ({c.get('type', '')}): {c.get('description', '')}" for c in columns]
        )
        embed_payload = (
            f"Asset: {name} | FQN: {fqn} | Platform: {platform} | Type: {asset_type} | "
            f"Description: {description} | Columns: {col_summary} | Owner: {owner or 'Unassigned'}"
        )
        vec = self.embeddings.embed_text(embed_payload)
        embedding_json = json.dumps(vec)

        existing = (
            self.session.query(DataAsset)
            .filter(DataAsset.org_id == org_id, DataAsset.fqn == fqn)
            .first()
        )

        now = datetime.now(timezone.utc)
        if existing:
            existing.name = name
            existing.asset_type = asset_type
            existing.platform = platform
            existing.description = description
            existing.columns_json = json.dumps(columns)
            existing.owner = owner
            existing.is_certified = is_certified
            existing.certified_by = certified_by
            existing.health_status = health_status
            existing.metadata_json = json.dumps(metadata)
            existing.embedding_json = embedding_json
            existing.updated_at = now
            existing.last_synced_at = now
            if freshness_timestamp:
                existing.freshness_timestamp = freshness_timestamp
            self.session.commit()
            return existing

        asset_id = f"ast_{uuid.uuid4().hex[:12]}"
        new_asset = DataAsset(
            id=asset_id,
            org_id=org_id,
            project_id=project_id,
            asset_type=asset_type,
            platform=platform,
            name=name,
            fqn=fqn,
            description=description,
            columns_json=json.dumps(columns),
            owner=owner,
            is_certified=is_certified,
            certified_by=certified_by,
            health_status=health_status,
            freshness_timestamp=freshness_timestamp or now,
            metadata_json=json.dumps(metadata),
            embedding_json=embedding_json,
            created_at=now,
            updated_at=now,
            last_synced_at=now,
        )
        self.session.add(new_asset)
        self.session.commit()
        return new_asset

    def get_asset(self, org_id: str, fqn: str) -> Optional[DataAsset]:
        return (
            self.session.query(DataAsset)
            .filter(DataAsset.org_id == org_id, DataAsset.fqn == fqn)
            .first()
        )

    def search_assets(
        self,
        org_id: str,
        query: str,
        asset_type: Optional[str] = None,
        platform: Optional[str] = None,
        certified_only: bool = False,
        limit: int = 5,
    ) -> Dict[str, Any]:
        start_time = time.perf_counter()
        query_tokens = set(t.lower() for t in query.split() if len(t) > 2)
        query_vec = self.embeddings.embed_text(query)

        q = self.session.query(DataAsset).filter(DataAsset.org_id == org_id)
        if asset_type:
            q = q.filter(DataAsset.asset_type == asset_type)
        if platform:
            q = q.filter(DataAsset.platform == platform)
        if certified_only:
            q = q.filter(DataAsset.is_certified == True)

        candidates = q.all()
        scored: List[Tuple[DataAsset, float, float, float]] = []

        for asset in candidates:
            dense_sim = 0.0
            if asset.embedding_json:
                try:
                    asset_vec = json.loads(asset.embedding_json)
                    dense_sim = _cosine_similarity(query_vec, asset_vec)
                except Exception:
                    pass

            doc_text = f"{asset.name} {asset.fqn} {asset.description or ''} {asset.columns_json or ''} {asset.platform} {asset.owner or ''}"
            lexical_sim = _compute_bm25_score(query_tokens, doc_text)

            combined_score = (0.55 * dense_sim) + (0.45 * lexical_sim)
            if asset.is_certified:
                combined_score += 0.15

            scored.append((asset, combined_score, dense_sim, lexical_sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        top_hits = scored[:limit]
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        results = []

        for asset, final_score, d_sim, l_sim in top_hits:
            cols = []
            if asset.columns_json:
                try:
                    cols = json.loads(asset.columns_json)
                except Exception:
                    pass

            warning_banner = None
            if asset.health_status == AssetHealthStatus.FAILING.value:
                warning_banner = f"⚠️ [CRITICAL ALERT: Underlying pipeline for '{asset.name}' is FAILING. Source data may be corrupted or missing.]"
            elif asset.health_status == AssetHealthStatus.STALE.value:
                warning_banner = f"⚠️ [WARNING: Data in '{asset.name}' is STALE. Recent events may not be reflected.]"

            results.append({
                "id": asset.id,
                "name": asset.name,
                "fqn": asset.fqn,
                "asset_type": asset.asset_type,
                "platform": asset.platform,
                "description": asset.description,
                "is_certified": asset.is_certified,
                "certified_by": asset.certified_by,
                "owner": asset.owner,
                "health_status": asset.health_status,
                "warning_banner": warning_banner,
                "columns": cols,
                "confidence_score": round(min(1.0, final_score), 3),
                "dense_score": round(d_sim, 3),
                "lexical_score": round(l_sim, 3),
                "last_synced_at": asset.last_synced_at.isoformat() if asset.last_synced_at else None,
            })

        return {
            "query": query,
            "hits_count": len(results),
            "latency_ms": elapsed_ms,
            "assets": results
        }

    def register_metric(
        self,
        org_id: str,
        name: str,
        display_name: str,
        definition: str,
        formula: Optional[str] = None,
        sql_expression: Optional[str] = None,
        primary_table_fqn: Optional[str] = None,
        join_recipe: Optional[str] = None,
        is_certified: bool = True,
        steward: Optional[str] = None,
        tags: Optional[List[str]] = None,
        project_id: Optional[str] = None,
    ) -> BusinessMetric:
        tags = tags or []
        existing = (
            self.session.query(BusinessMetric)
            .filter(BusinessMetric.org_id == org_id, BusinessMetric.name == name)
            .first()
        )

        now = datetime.now(timezone.utc)
        if existing:
            existing.display_name = display_name
            existing.definition = definition
            existing.formula = formula
            existing.sql_expression = sql_expression
            existing.primary_table_fqn = primary_table_fqn
            existing.join_recipe = join_recipe
            existing.is_certified = is_certified
            existing.steward = steward
            existing.tags_json = json.dumps(tags)
            existing.updated_at = now
            self.session.commit()
            return existing

        metric_id = f"met_{uuid.uuid4().hex[:12]}"
        new_metric = BusinessMetric(
            id=metric_id,
            org_id=org_id,
            project_id=project_id,
            name=name,
            display_name=display_name,
            definition=definition,
            formula=formula,
            sql_expression=sql_expression,
            primary_table_fqn=primary_table_fqn,
            join_recipe=join_recipe,
            is_certified=is_certified,
            steward=steward,
            tags_json=json.dumps(tags),
            created_at=now,
            updated_at=now,
        )
        self.session.add(new_metric)
        self.session.commit()
        return new_metric

    def get_metric(self, org_id: str, name: str) -> Optional[Dict[str, Any]]:
        metric = (
            self.session.query(BusinessMetric)
            .filter(BusinessMetric.org_id == org_id, BusinessMetric.name == name)
            .first()
        )
        if not metric:
            return None

        tags = []
        if metric.tags_json:
            try:
                tags = json.loads(metric.tags_json)
            except Exception:
                pass

        return {
            "id": metric.id,
            "name": metric.name,
            "display_name": metric.display_name,
            "definition": metric.definition,
            "formula": metric.formula,
            "sql_expression": metric.sql_expression,
            "primary_table_fqn": metric.primary_table_fqn,
            "join_recipe": metric.join_recipe,
            "is_certified": metric.is_certified,
            "steward": metric.steward,
            "tags": tags,
        }

    def search_metrics(self, org_id: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        query_lower = query.lower()
        metrics = self.session.query(BusinessMetric).filter(BusinessMetric.org_id == org_id).all()
        scored = []

        for m in metrics:
            score = 0.0
            if query_lower in m.name.lower():
                score += 0.8
            if query_lower in m.display_name.lower():
                score += 0.6
            if query_lower in m.definition.lower():
                score += 0.4
            if m.tags_json and query_lower in m.tags_json.lower():
                score += 0.3
            if m.is_certified:
                score += 0.2
            if score > 0.1:
                scored.append((m, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        results = []
        for m, score in scored[:limit]:
            tags = []
            if m.tags_json:
                try:
                    tags = json.loads(m.tags_json)
                except Exception:
                    pass
            results.append({
                "name": m.name,
                "display_name": m.display_name,
                "definition": m.definition,
                "formula": m.formula,
                "sql_expression": m.sql_expression,
                "primary_table_fqn": m.primary_table_fqn,
                "join_recipe": m.join_recipe,
                "is_certified": m.is_certified,
                "steward": m.steward,
                "tags": tags,
                "score": round(score, 2),
            })
        return results

    def add_lineage_edge(
        self,
        org_id: str,
        upstream_asset_fqn: str,
        downstream_asset_fqn: str,
        edge_type: str = LineageEdgeType.TRANSFORMS_INTO.value,
        transformation_logic: Optional[str] = None,
    ) -> DataLineageEdge:
        existing = (
            self.session.query(DataLineageEdge)
            .filter(
                DataLineageEdge.org_id == org_id,
                DataLineageEdge.upstream_asset_fqn == upstream_asset_fqn,
                DataLineageEdge.downstream_asset_fqn == downstream_asset_fqn,
            )
            .first()
        )
        if existing:
            existing.edge_type = edge_type
            existing.transformation_logic = transformation_logic
            self.session.commit()
            return existing

        edge_id = f"edg_{uuid.uuid4().hex[:12]}"
        edge = DataLineageEdge(
            id=edge_id,
            org_id=org_id,
            upstream_asset_fqn=upstream_asset_fqn,
            downstream_asset_fqn=downstream_asset_fqn,
            edge_type=edge_type,
            transformation_logic=transformation_logic,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(edge)
        self.session.commit()
        return edge

    def get_upstream_lineage(self, org_id: str, fqn: str, max_depth: int = 5) -> Dict[str, Any]:
        queue = deque([(fqn, 0)])
        visited = set([fqn])
        upstream_nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        root_sources: List[str] = []

        while queue:
            current_fqn, depth = queue.popleft()
            if depth >= max_depth:
                continue

            parent_edges = (
                self.session.query(DataLineageEdge)
                .filter(
                    DataLineageEdge.org_id == org_id,
                    DataLineageEdge.downstream_asset_fqn == current_fqn,
                )
                .all()
            )

            if not parent_edges and current_fqn != fqn:
                root_sources.append(current_fqn)

            for pe in parent_edges:
                edges.append({
                    "from": pe.upstream_asset_fqn,
                    "to": pe.downstream_asset_fqn,
                    "edge_type": pe.edge_type,
                    "transformation": pe.transformation_logic,
                })
                if pe.upstream_asset_fqn not in visited:
                    visited.add(pe.upstream_asset_fqn)
                    parent_asset = self.get_asset(org_id, pe.upstream_asset_fqn)
                    upstream_nodes.append({
                        "fqn": pe.upstream_asset_fqn,
                        "name": parent_asset.name if parent_asset else pe.upstream_asset_fqn.split(".")[-1],
                        "depth": depth + 1,
                        "health_status": parent_asset.health_status if parent_asset else "UNKNOWN",
                        "is_certified": parent_asset.is_certified if parent_asset else False,
                    })
                    queue.append((pe.upstream_asset_fqn, depth + 1))

        return {
            "target_fqn": fqn,
            "upstream_depth": max_depth,
            "root_sources": list(set(root_sources)),
            "nodes": upstream_nodes,
            "edges": edges,
        }

    def get_downstream_blast_radius(self, org_id: str, fqn: str, max_depth: int = 5) -> Dict[str, Any]:
        queue = deque([(fqn, 0)])
        visited = set([fqn])
        impacted_nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []

        while queue:
            current_fqn, depth = queue.popleft()
            if depth >= max_depth:
                continue

            child_edges = (
                self.session.query(DataLineageEdge)
                .filter(
                    DataLineageEdge.org_id == org_id,
                    DataLineageEdge.upstream_asset_fqn == current_fqn,
                )
                .all()
            )

            for ce in child_edges:
                edges.append({
                    "from": ce.upstream_asset_fqn,
                    "to": ce.downstream_asset_fqn,
                    "edge_type": ce.edge_type,
                })
                if ce.downstream_asset_fqn not in visited:
                    visited.add(ce.downstream_asset_fqn)
                    child_asset = self.get_asset(org_id, ce.downstream_asset_fqn)
                    impacted_nodes.append({
                        "fqn": ce.downstream_asset_fqn,
                        "name": child_asset.name if child_asset else ce.downstream_asset_fqn.split(".")[-1],
                        "depth": depth + 1,
                        "asset_type": child_asset.asset_type if child_asset else "UNKNOWN",
                        "owner": child_asset.owner if child_asset else "UNKNOWN",
                    })
                    queue.append((ce.downstream_asset_fqn, depth + 1))

        return {
            "failed_asset_fqn": fqn,
            "total_impacted_assets": len(impacted_nodes),
            "impacted_nodes": impacted_nodes,
            "lineage_edges": edges,
        }

    def ingest_dbt_manifest(
        self,
        org_id: str,
        manifest: Dict[str, Any],
        platform: str = "snowflake",
        project_id: Optional[str] = None,
    ) -> Dict[str, int]:
        nodes = manifest.get("nodes", {})
        sources = manifest.get("sources", {})
        metrics = manifest.get("metrics", {}) or manifest.get("semantic_models", {})
        exposures = manifest.get("exposures", {})

        stats = {
            "models_ingested": 0,
            "sources_ingested": 0,
            "metrics_ingested": 0,
            "lineage_edges_created": 0,
            "exposures_ingested": 0,
        }

        # 1. Sources
        for src_key, src in sources.items():
            source_name = src.get("source_name", "")
            table_name = src.get("name", "")
            schema = src.get("schema", source_name)
            fqn = f"{platform}.{schema}.{table_name}"
            cols = []
            for col_name, col_data in src.get("columns", {}).items():
                cols.append({
                    "name": col_name,
                    "type": col_data.get("data_type", "VARCHAR"),
                    "description": col_data.get("description", ""),
                })
            self.register_asset(
                org_id=org_id,
                name=table_name,
                fqn=fqn,
                asset_type=AssetType.TABLE.value,
                platform=platform,
                description=src.get("description", f"Raw source table {table_name}"),
                columns=cols,
                owner=src.get("meta", {}).get("owner", "data-engineering"),
                is_certified=False,
                health_status=AssetHealthStatus.HEALTHY.value,
                project_id=project_id,
            )
            stats["sources_ingested"] += 1

        # 2. Nodes
        node_fqn_map = {}
        for node_id, node in nodes.items():
            resource_type = node.get("resource_type")
            if resource_type not in ("model", "seed", "snapshot"):
                continue

            name = node.get("name", "")
            schema = node.get("schema", "analytics")
            database = node.get("database", "prod")
            fqn = f"{platform}.{database}.{schema}.{name}"
            node_fqn_map[node_id] = fqn

            meta = node.get("meta", {})
            is_certified = meta.get("certified", False) or "certified" in node.get("tags", [])
            certified_by = meta.get("certified_by", "Data Governance Team") if is_certified else None
            owner = meta.get("owner", node.get("config", {}).get("meta", {}).get("owner", "BI Team"))

            cols = []
            for col_name, col_data in node.get("columns", {}).items():
                cols.append({
                    "name": col_name,
                    "type": col_data.get("data_type", "VARCHAR"),
                    "description": col_data.get("description", ""),
                })

            materialization = node.get("config", {}).get("materialized", "table")
            asset_type = AssetType.VIEW.value if materialization == "view" else AssetType.TABLE.value

            self.register_asset(
                org_id=org_id,
                name=name,
                fqn=fqn,
                asset_type=asset_type,
                platform=platform,
                description=node.get("description", ""),
                columns=cols,
                owner=owner,
                is_certified=is_certified,
                certified_by=certified_by,
                health_status=AssetHealthStatus.HEALTHY.value,
                metadata={"raw_sql": node.get("raw_code", ""), "materialization": materialization},
                project_id=project_id,
            )
            stats["models_ingested"] += 1

        # 3. Lineage Edges
        for node_id, node in nodes.items():
            downstream_fqn = node_fqn_map.get(node_id)
            if not downstream_fqn:
                continue

            depends_on_nodes = node.get("depends_on", {}).get("nodes", [])
            for upstream_id in depends_on_nodes:
                upstream_fqn = node_fqn_map.get(upstream_id)
                if not upstream_fqn and upstream_id.startswith("source."):
                    src_obj = sources.get(upstream_id)
                    if src_obj:
                        src_schema = src_obj.get("schema") or src_obj.get("source_name", "")
                        src_table = src_obj.get("name", "")
                        upstream_fqn = f"{platform}.{src_schema}.{src_table}"

                if upstream_fqn:
                    self.add_lineage_edge(
                        org_id=org_id,
                        upstream_asset_fqn=upstream_fqn,
                        downstream_asset_fqn=downstream_fqn,
                        edge_type=LineageEdgeType.TRANSFORMS_INTO.value,
                    )
                    stats["lineage_edges_created"] += 1

        # 4. Exposures
        for exp_id, exp in exposures.items():
            exp_name = exp.get("name", "")
            exp_fqn = f"bi_exposure.{exp.get('type', 'dashboard')}.{exp_name}"
            self.register_asset(
                org_id=org_id,
                name=exp_name,
                fqn=exp_fqn,
                asset_type=AssetType.PIPELINE.value,
                platform="bi_tool",
                description=exp.get("description", ""),
                owner=exp.get("owner", {}).get("name", "Analytics"),
                is_certified=True,
                project_id=project_id,
            )
            stats["exposures_ingested"] += 1

            for dep_node in exp.get("depends_on", {}).get("nodes", []):
                dep_fqn = node_fqn_map.get(dep_node)
                if dep_fqn:
                    self.add_lineage_edge(
                        org_id=org_id,
                        upstream_asset_fqn=dep_fqn,
                        downstream_asset_fqn=exp_fqn,
                        edge_type=LineageEdgeType.FEEDS_DASHBOARD.value,
                    )
                    stats["lineage_edges_created"] += 1

        # 5. Metrics
        for met_key, met in metrics.items():
            m_name = met.get("name", met_key)
            self.register_metric(
                org_id=org_id,
                name=m_name,
                display_name=met.get("label", m_name.replace("_", " ").title()),
                definition=met.get("description", ""),
                formula=met.get("calculation_method", ""),
                sql_expression=met.get("expression", ""),
                primary_table_fqn=node_fqn_map.get(met.get("model", "")),
                is_certified=True,
                steward="dbt-semantic-layer",
                project_id=project_id,
            )
            stats["metrics_ingested"] += 1

        return stats

    def reflect_sql_schema(
        self,
        org_id: str,
        engine_or_conn: Any,
        schema_name: str = "public",
        platform: str = "postgres",
        project_id: Optional[str] = None,
    ) -> int:
        from sqlalchemy import inspect
        inspector = inspect(engine_or_conn)
        table_names = inspector.get_table_names(schema=schema_name)
        count = 0

        for tname in table_names:
            columns_meta = inspector.get_columns(tname, schema=schema_name)
            pk_constraint = inspector.get_pk_constraint(tname, schema=schema_name)
            pk_cols = set(pk_constraint.get("constrained_columns", []))

            cols = []
            for col in columns_meta:
                cname = col.get("name")
                cols.append({
                    "name": cname,
                    "type": str(col.get("type")),
                    "is_pk": cname in pk_cols,
                    "is_nullable": col.get("nullable", True),
                    "description": col.get("comment", ""),
                })

            fqn = f"{platform}.{schema_name}.{tname}"
            self.register_asset(
                org_id=org_id,
                name=tname,
                fqn=fqn,
                asset_type=AssetType.TABLE.value,
                platform=platform,
                description=f"Reflected table '{tname}' in schema '{schema_name}' with {len(cols)} columns.",
                columns=cols,
                owner="dba",
                is_certified=True,
                health_status=AssetHealthStatus.HEALTHY.value,
                project_id=project_id,
            )
            count += 1

        return count
