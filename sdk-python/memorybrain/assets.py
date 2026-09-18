"""Enterprise Data Assets & Metrics Resource for Python SDK."""

from typing import Optional, Dict, Any, List
from ._http import HTTPClient


class DataAssetResource:
    """Manages enterprise tables, views, pipelines, and schema discovery."""

    def __init__(self, http: HTTPClient):
        self._http = http

    def recall(
        self,
        query: str,
        platform: Optional[str] = None,
        certified_only: bool = False,
        limit: int = 5
    ) -> Dict[str, Any]:
        """Hybrid search across enterprise tables, views, and pipelines (<25ms)."""
        params: Dict[str, Any] = {"query": query, "limit": limit}
        if platform:
            params["platform"] = platform
        if certified_only:
            params["certified_only"] = "true"
        return self._http.get("/v1/data-assets/recall", params=params)

    def get_schema(self, fqn: str) -> Dict[str, Any]:
        """Retrieves table columns, primary keys, and documentation by FQN."""
        return self._http.get("/v1/data-assets/schema", params={"fqn": fqn})

    def get_lineage(self, fqn: str, direction: str = "upstream", max_depth: int = 5) -> Dict[str, Any]:
        """Traces upstream provenance or downstream blast radius."""
        return self._http.get("/v1/data-assets/lineage", params={
            "fqn": fqn,
            "direction": direction,
            "max_depth": max_depth
        })

    def sync_dbt(self, manifest: Dict[str, Any], platform: str = "snowflake") -> Dict[str, Any]:
        """1-Click ingestion of dbt manifest.json."""
        return self._http.post("/v1/data-assets/sync/dbt", json=manifest, params={"platform": platform})

    def register(
        self,
        name: str,
        fqn: str,
        asset_type: str = "TABLE",
        platform: str = "snowflake",
        description: str = "",
        columns: Optional[List[Dict[str, Any]]] = None,
        owner: Optional[str] = None,
        is_certified: bool = False,
        certified_by: Optional[str] = None,
        health_status: str = "HEALTHY",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Registers or updates a warehouse data asset."""
        payload = {
            "name": name,
            "fqn": fqn,
            "asset_type": asset_type,
            "platform": platform,
            "description": description,
            "columns": columns or [],
            "owner": owner,
            "is_certified": is_certified,
            "certified_by": certified_by,
            "health_status": health_status,
            "metadata": metadata or {}
        }
        return self._http.post("/v1/data-assets/register", json=payload)


class MetricResource:
    """Manages certified business KPIs, formulas, and canonical SQL join paths."""

    def __init__(self, http: HTTPClient):
        self._http = http

    def recall(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Searches certified business metrics and SQL expressions."""
        return self._http.get("/v1/metrics/recall", params={"query": query, "limit": limit})

    def register(
        self,
        name: str,
        display_name: str,
        definition: str,
        formula: Optional[str] = None,
        sql_expression: Optional[str] = None,
        primary_table_fqn: Optional[str] = None,
        join_recipe: Optional[str] = None,
        is_certified: bool = True,
        steward: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Registers or updates a certified business metric."""
        payload = {
            "name": name,
            "display_name": display_name,
            "definition": definition,
            "formula": formula,
            "sql_expression": sql_expression,
            "primary_table_fqn": primary_table_fqn,
            "join_recipe": join_recipe,
            "is_certified": is_certified,
            "steward": steward,
            "tags": tags or []
        }
        return self._http.post("/v1/metrics/register", json=payload)
