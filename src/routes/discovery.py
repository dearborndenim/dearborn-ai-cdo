"""Discovery and opportunity endpoints."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import (
    get_db, DiscoveryScan, ProductOpportunity,
    OpportunityStatus
)
from ..cdo.discovery import run_weekly_discovery_scan
from ..cdo.concept import ConceptDesigner

router = APIRouter()


@router.post("/cdo/discovery/scan", tags=["Discovery"])
async def trigger_discovery_scan(db: Session = Depends(get_db)):
    """Manually trigger a discovery scan."""
    result = run_weekly_discovery_scan(db)
    return result


@router.get("/cdo/discovery/scans", tags=["Discovery"])
async def list_scans(
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """List past discovery scans."""
    scans = db.query(DiscoveryScan).order_by(
        DiscoveryScan.started_at.desc()
    ).limit(limit).all()

    return {
        "scans": [{
            "id": s.id,
            "scan_type": s.scan_type,
            "status": s.status,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            "trends_found": s.trends_found,
            "competitors_scanned": s.competitors_scanned,
            "opportunities_generated": s.opportunities_generated,
        } for s in scans]
    }


@router.get("/cdo/opportunities", tags=["Discovery"])
async def list_opportunities(
    status: Optional[OpportunityStatus] = None,
    min_score: float = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List scored product opportunities."""
    query = db.query(ProductOpportunity).filter(
        ProductOpportunity.composite_score >= min_score
    )

    if status:
        query = query.filter(ProductOpportunity.status == status)

    opportunities = query.order_by(
        ProductOpportunity.composite_score.desc()
    ).limit(limit).all()

    return {
        "total": len(opportunities),
        "opportunities": [{
            "id": o.id,
            "title": o.title,
            "category": o.category,
            "composite_score": o.composite_score,
            "trend_score": o.trend_score,
            "market_score": o.market_score,
            "feasibility_score": o.feasibility_score,
            "estimated_retail": o.estimated_retail,
            "estimated_cost": o.estimated_cost,
            "estimated_margin": o.estimated_margin,
            "status": o.status.value if o.status else None,
            "trend_keywords": o.trend_keywords,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        } for o in opportunities]
    }


@router.post("/cdo/opportunities/{opportunity_id}/promote", tags=["Discovery"])
async def promote_opportunity(
    opportunity_id: int,
    db: Session = Depends(get_db)
):
    """Promote an opportunity to a product concept."""
    designer = ConceptDesigner(db)
    concept = designer.promote_opportunity(opportunity_id)

    if not concept:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    return {
        "success": True,
        "concept_id": concept.id,
        "concept_number": concept.concept_number,
        "message": "Opportunity promoted to concept",
    }


@router.post("/cdo/opportunities/{opportunity_id}/reject", tags=["Discovery"])
async def reject_opportunity(
    opportunity_id: int,
    reason: str = "Not aligned with current strategy",
    db: Session = Depends(get_db)
):
    """Reject an opportunity."""
    opp = db.query(ProductOpportunity).filter(
        ProductOpportunity.id == opportunity_id
    ).first()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    opp.status = OpportunityStatus.REJECTED
    opp.rejected_reason = reason
    db.commit()

    return {"success": True, "message": "Opportunity rejected"}
