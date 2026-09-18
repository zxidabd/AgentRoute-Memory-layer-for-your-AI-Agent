"""Production v1 Enterprise Data Assets, Business Metrics, and Lineage routes."""

from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status, Body
from sqlalchemy.orm import Session

from ...database import get_db_session
from ..auth import get_current_tenant
from ...engine.data_assets import DataAssetEngine
from ...engine.embeddings import EmbeddingService

router = APIRouter(prefix="/v1", tags=["Data Assets & Context Graph (v1)"])
embeddings = EmbeddingService()


@router.post(
    "/data-assets/sync/dbt",
    status_code=status.HTTP_200_OK,
    summary="1-Click dbt Manifest Ingestion",
    description="Ingests dbt manifest.json to automatically register all models, sources, tests, column descriptions, and lineage edges."
)
def sync_dbt_manifest(
    manifest: Dict[str, Any] = Body(..., description="Complete dbt manifest.json dictionary"),
    platform: str = Query(default="snowflake", description="Target platform (snowflake, bigquery, databricks, postgres)"),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
):
    engine = DataAssetEngine(session=db, embedding_service=embeddings)
    stats = engine.ingest_dbt_manifest(org_id=tenant_id, manifest=manifest, platform=platform)
    return {
        "status": "success",
        "platform": platform,
        "summary": stats
    }


@router.post(
    "/data-assets/register",
    status_code=status.HTTP_201_CREATED,
    summary="Register or Update Data Asset",
    description="Explicitly register or update a warehouse table, view, schema, or pipeline with column descriptions."
)
def register_data_asset(
    payload: Dict[str, Any] = Body(...),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
):
    name = payload.get("name")
    fqn = payload.get("fqn")
    if not name or not fqn:
        raise HTTPException(status_code=400, detail="'name' and 'fqn' are required fields.")

    engine = DataAssetEngine(session=db, embedding_service=embeddings)
    asset = engine.register_asset(
        org_id=tenant_id,
        name=name,
        fqn=fqn,
        asset_type=payload.get("asset_type", "TABLE"),
        platform=payload.get("platform", "snowflake"),
        description=payload.get("description", ""),
        columns=payload.get("columns", []),
        owner=payload.get("owner"),
        is_certified=bool(payload.get("is_certified", False)),
        certified_by=payload.get("certified_by"),
        health_status=payload.get("health_status", "HEALTHY"),
        metadata=payload.get("metadata", {}),
    )
    return {
        "status": "created",
        "id": asset.id,
        "fqn": asset.fqn,
        "is_certified": asset.is_certified,
        "health_status": asset.health_status,
    }


@router.get(
    "/data-assets/recall",
    status_code=status.HTTP_200_OK,
    summary="Sub-25ms Hybrid Search for Data Assets",
    description="Finds relevant tables, views, and pipelines using hybrid vector and lexical BM25 matching."
)
def search_data_assets(
    query: str = Query(..., description="Natural language search phrase (e.g. 'verified churn metrics')"),
    platform: Optional[str] = Query(default=None),
    certified_only: bool = Query(default=False),
    limit: int = Query(default=5, ge=1, le=50),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
):
    engine = DataAssetEngine(session=db, embedding_service=embeddings)
    return engine.search_assets(
        org_id=tenant_id,
        query=query,
        platform=platform,
        certified_only=certified_only,
        limit=limit
    )


@router.get(
    "/data-assets/schema",
    status_code=status.HTTP_200_OK,
    summary="Retrieve Table Schema & Documentation",
    description="Returns detailed column types, primary keys, and descriptions for an asset by FQN."
)
def get_table_schema(
    fqn: str = Query(..., description="Fully Qualified Name of the table"),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
):
    engine = DataAssetEngine(session=db, embedding_service=embeddings)
    asset = engine.get_asset(org_id=tenant_id, fqn=fqn)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset '{fqn}' not found.")

    import json
    cols = json.loads(asset.columns_json) if asset.columns_json else []
    return {
        "fqn": asset.fqn,
        "name": asset.name,
        "platform": asset.platform,
        "asset_type": asset.asset_type,
        "is_certified": asset.is_certified,
        "certified_by": asset.certified_by,
        "health_status": asset.health_status,
        "owner": asset.owner,
        "columns": cols
    }


@router.get(
    "/data-assets/lineage",
    status_code=status.HTTP_200_OK,
    summary="Lineage Provenance & Blast Radius Traversal",
    description="Traces upstream root sources or downstream blast radius of broken tables."
)
def get_data_lineage(
    fqn: str = Query(..., description="Fully Qualified Name of the table"),
    direction: str = Query(default="upstream", pattern="^(upstream|downstream)$"),
    max_depth: int = Query(default=5, ge=1, le=10),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
):
    engine = DataAssetEngine(session=db, embedding_service=embeddings)
    if direction == "upstream":
        return engine.get_upstream_lineage(org_id=tenant_id, fqn=fqn, max_depth=max_depth)
    else:
        return engine.get_downstream_blast_radius(org_id=tenant_id, fqn=fqn, max_depth=max_depth)


@router.post(
    "/metrics/register",
    status_code=status.HTTP_201_CREATED,
    summary="Register or Certify Business Metric",
    description="Registers a KPI definition with canonical SQL formula and join recipe."
)
def register_metric(
    payload: Dict[str, Any] = Body(...),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
):
    name = payload.get("name")
    display_name = payload.get("display_name", name)
    definition = payload.get("definition", "")
    if not name:
        raise HTTPException(status_code=400, detail="'name' is required.")

    engine = DataAssetEngine(session=db, embedding_service=embeddings)
    metric = engine.register_metric(
        org_id=tenant_id,
        name=name,
        display_name=display_name,
        definition=definition,
        formula=payload.get("formula"),
        sql_expression=payload.get("sql_expression"),
        primary_table_fqn=payload.get("primary_table_fqn"),
        join_recipe=payload.get("join_recipe"),
        is_certified=bool(payload.get("is_certified", True)),
        steward=payload.get("steward"),
        tags=payload.get("tags", []),
    )
    return {
        "status": "created",
        "id": metric.id,
        "name": metric.name,
        "is_certified": metric.is_certified
    }


@router.get(
    "/metrics/recall",
    status_code=status.HTTP_200_OK,
    summary="Search Business Metrics & Formulas",
    description="Searches for certified metrics, canonical SQL expressions, and join paths."
)
def recall_metrics(
    query: str = Query(...),
    limit: int = Query(default=5, ge=1, le=20),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
):
    engine = DataAssetEngine(session=db, embedding_service=embeddings)
    return engine.search_metrics(org_id=tenant_id, query=query, limit=limit)
