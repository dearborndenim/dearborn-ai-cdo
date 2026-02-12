"""Product development idea endpoints."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from ..db import get_db, ProductIdea, ProductIdeaStatus
from ..event_bus import publish_product_recommendation

router = APIRouter()


class ProductIdeaCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: str
    source: str = "internal"
    target_market: Optional[str] = None
    estimated_cost: Optional[float] = None
    estimated_retail: Optional[float] = None
    estimated_annual_units: Optional[int] = None


@router.get("/cdo/product-ideas", tags=["Product Development"])
async def list_product_ideas(
    status: Optional[ProductIdeaStatus] = None,
    category: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List product ideas."""
    query = db.query(ProductIdea)

    if status:
        query = query.filter(ProductIdea.status == status)
    if category:
        query = query.filter(ProductIdea.category == category)

    total = query.count()
    ideas = query.order_by(ProductIdea.priority_score.desc().nullslast()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "ideas": [{
            "id": i.id,
            "idea_number": i.idea_number,
            "title": i.title,
            "category": i.category,
            "source": i.source,
            "priority_score": i.priority_score,
            "estimated_revenue": i.estimated_annual_revenue,
            "status": i.status.value if i.status else "concept"
        } for i in ideas]
    }


@router.post("/cdo/product-ideas", tags=["Product Development"])
async def create_product_idea(
    data: ProductIdeaCreate,
    db: Session = Depends(get_db)
):
    """Create a new product idea."""
    count = db.query(func.count(ProductIdea.id)).scalar() or 0
    idea_number = f"IDEA-{datetime.now().strftime('%Y%m')}-{count + 1:04d}"

    estimated_revenue = None
    if data.estimated_retail and data.estimated_annual_units:
        estimated_revenue = data.estimated_retail * data.estimated_annual_units

    estimated_margin = None
    if data.estimated_cost and data.estimated_retail and data.estimated_retail > 0:
        estimated_margin = ((data.estimated_retail - data.estimated_cost) / data.estimated_retail) * 100

    idea = ProductIdea(
        idea_number=idea_number,
        title=data.title,
        description=data.description,
        category=data.category,
        source=data.source,
        target_market=data.target_market,
        estimated_cost=data.estimated_cost,
        estimated_retail=data.estimated_retail,
        estimated_margin=estimated_margin,
        estimated_annual_units=data.estimated_annual_units,
        estimated_annual_revenue=estimated_revenue,
        status=ProductIdeaStatus.CONCEPT
    )

    db.add(idea)
    db.commit()
    db.refresh(idea)

    return {"success": True, "idea_id": idea.id, "idea_number": idea_number}


@router.post("/cdo/product-ideas/{idea_id}/submit-for-approval", tags=["Product Development"])
async def submit_idea_for_approval(
    idea_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Submit product idea to CEO for approval."""
    idea = db.query(ProductIdea).filter(ProductIdea.id == idea_id).first()
    if not idea:
        raise HTTPException(status_code=404, detail="Product idea not found")

    idea.status = ProductIdeaStatus.RESEARCH
    db.commit()

    background_tasks.add_task(
        publish_product_recommendation,
        idea.id,
        idea.title,
        idea.category,
        idea.estimated_annual_revenue or 0,
        idea.priority_score or 50,
        idea.description or "New product development opportunity"
    )

    return {"success": True, "message": "Submitted for CEO approval"}


@router.get("/cdo/all-ideas", tags=["Product Development"])
async def list_all_ideas(
    status: Optional[str] = None,
    category: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List all product ideas from both ProductIdea and SeasonProductIdea tables."""
    from ..db import SeasonProductIdea, Season

    results = []

    # Query ProductIdea table
    pi_query = db.query(ProductIdea)
    if status:
        pi_query = pi_query.filter(ProductIdea.status == status)
    if category:
        pi_query = pi_query.filter(ProductIdea.category == category)
    for i in pi_query.order_by(ProductIdea.priority_score.desc().nullslast()).all():
        results.append({
            "id": i.id,
            "source_table": "product_idea",
            "title": i.title,
            "description": i.description,
            "category": i.category,
            "status": i.status.value if i.status else "concept",
            "priority_score": i.priority_score,
            "estimated_cost": i.estimated_cost,
            "estimated_retail": i.estimated_retail,
            "estimated_margin": i.estimated_margin,
            "image_url": None,
            "labor_cost": None,
            "material_cost": None,
            "sewing_time_minutes": None,
            "season_name": None,
            "season_id": None,
            "created_at": i.created_at.isoformat() if i.created_at else None,
        })

    # Query SeasonProductIdea table
    spi_query = db.query(SeasonProductIdea).join(Season, SeasonProductIdea.season_id == Season.id)
    if status:
        spi_query = spi_query.filter(SeasonProductIdea.status == status)
    if category:
        spi_query = spi_query.filter(SeasonProductIdea.category == category)
    for i in spi_query.order_by(SeasonProductIdea.id.desc()).all():
        season = db.query(Season).filter(Season.id == i.season_id).first()
        results.append({
            "id": i.id,
            "source_table": "season_idea",
            "title": i.title,
            "description": i.description,
            "category": i.category,
            "status": i.status or "pending",
            "priority_score": None,
            "estimated_cost": i.estimated_cost,
            "estimated_retail": i.suggested_retail,
            "estimated_margin": i.estimated_margin,
            "image_url": getattr(i, 'image_url', None),
            "labor_cost": getattr(i, 'labor_cost', None),
            "material_cost": getattr(i, 'material_cost', None),
            "sewing_time_minutes": getattr(i, 'sewing_time_minutes', None),
            "season_name": season.name if season else None,
            "season_id": i.season_id,
            "created_at": i.created_at.isoformat() if i.created_at else None,
        })

    # Sort by created_at desc
    results.sort(key=lambda x: x.get("created_at") or "", reverse=True)

    total = len(results)
    results = results[skip:skip + limit]

    return {
        "total": total,
        "ideas": results,
    }
