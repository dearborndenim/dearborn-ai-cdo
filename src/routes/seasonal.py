"""Seasonal design workflow endpoints."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db, Season, SeasonProductIdea, SeasonStatus
from ..cdo.seasonal import SeasonalDesigner

router = APIRouter()


class SeasonCreate(BaseModel):
    name: str
    season_code: str
    target_demo: dict
    start_date: Optional[str] = None
    end_date: Optional[str] = None


@router.post("/cdo/seasons", tags=["Seasons"])
async def create_season(body: SeasonCreate, db: Session = Depends(get_db)):
    """Create a new seasonal design assignment."""
    # Check for duplicate season code
    existing = db.query(Season).filter(Season.season_code == body.season_code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Season code '{body.season_code}' already exists")

    start = datetime.fromisoformat(body.start_date) if body.start_date else None
    end = datetime.fromisoformat(body.end_date) if body.end_date else None

    designer = SeasonalDesigner(db)
    season = designer.create_season(
        name=body.name,
        season_code=body.season_code,
        target_demo=body.target_demo,
        start_date=start,
        end_date=end,
    )

    return {
        "id": season.id,
        "name": season.name,
        "season_code": season.season_code,
        "status": season.status.value,
        "target_demo": season.target_demo,
        "created_at": season.created_at.isoformat() if season.created_at else None,
    }


@router.get("/cdo/seasons", tags=["Seasons"])
async def list_seasons(
    status: Optional[SeasonStatus] = None,
    db: Session = Depends(get_db),
):
    """List all seasons."""
    query = db.query(Season)
    if status:
        query = query.filter(Season.status == status)

    seasons = query.order_by(Season.created_at.desc()).all()

    return {
        "total": len(seasons),
        "seasons": [{
            "id": s.id,
            "name": s.name,
            "season_code": s.season_code,
            "status": s.status.value if s.status else None,
            "target_demo": s.target_demo,
            "start_date": s.start_date.isoformat() if s.start_date else None,
            "end_date": s.end_date.isoformat() if s.end_date else None,
            "idea_count": len(s.ideas) if s.ideas else 0,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        } for s in seasons],
    }


@router.get("/cdo/seasons/{season_id}", tags=["Seasons"])
async def get_season(season_id: int, db: Session = Depends(get_db)):
    """Get season detail including customer research and idea summary."""
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    ideas = db.query(SeasonProductIdea).filter(
        SeasonProductIdea.season_id == season_id
    ).order_by(SeasonProductIdea.priority.desc()).all()

    return {
        "id": season.id,
        "name": season.name,
        "season_code": season.season_code,
        "status": season.status.value if season.status else None,
        "target_demo": season.target_demo,
        "customer_research": season.customer_research,
        "start_date": season.start_date.isoformat() if season.start_date else None,
        "end_date": season.end_date.isoformat() if season.end_date else None,
        "created_at": season.created_at.isoformat() if season.created_at else None,
        "updated_at": season.updated_at.isoformat() if season.updated_at else None,
        "ideas": [{
            "id": i.id,
            "title": i.title,
            "category": i.category,
            "subcategory": i.subcategory,
            "priority": i.priority,
            "suggested_retail": i.suggested_retail,
            "estimated_cost": i.estimated_cost,
            "estimated_margin": i.estimated_margin,
            "status": i.status,
        } for i in ideas],
    }


@router.post("/cdo/seasons/{season_id}/research", tags=["Seasons"])
async def research_customer(season_id: int, db: Session = Depends(get_db)):
    """Trigger AI customer research for the season's target demographic."""
    designer = SeasonalDesigner(db)
    result = designer.research_customer(season_id)
    if not result:
        raise HTTPException(status_code=404, detail="Season not found")
    return result


@router.post("/cdo/seasons/{season_id}/generate-ideas", tags=["Seasons"])
async def generate_ideas(
    season_id: int,
    count: int = 8,
    db: Session = Depends(get_db),
):
    """Generate AI product ideas for the season."""
    designer = SeasonalDesigner(db)
    result = designer.generate_product_ideas(season_id, count=count)
    if not result:
        raise HTTPException(status_code=404, detail="Season not found")
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/cdo/seasons/{season_id}/ideas", tags=["Seasons"])
async def list_ideas(
    season_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List product ideas for a season."""
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    query = db.query(SeasonProductIdea).filter(
        SeasonProductIdea.season_id == season_id
    )
    if status:
        query = query.filter(SeasonProductIdea.status == status)

    ideas = query.order_by(SeasonProductIdea.id).all()

    return {
        "season_id": season.id,
        "season_name": season.name,
        "total": len(ideas),
        "ideas": [{
            "id": i.id,
            "title": i.title,
            "category": i.category,
            "subcategory": i.subcategory,
            "description": i.description,
            "customer_fit": i.customer_fit,
            "suggested_retail": i.suggested_retail,
            "estimated_cost": i.estimated_cost,
            "estimated_margin": i.estimated_margin,
            "priority": i.priority,
            "ai_rationale": i.ai_rationale,
            "status": i.status,
            "promoted_concept_id": i.promoted_concept_id,
            "created_at": i.created_at.isoformat() if i.created_at else None,
        } for i in ideas],
    }


@router.post("/cdo/seasons/{season_id}/ideas/{idea_id}/promote", tags=["Seasons"])
async def promote_idea(
    season_id: int,
    idea_id: int,
    db: Session = Depends(get_db),
):
    """Promote a product idea into the product pipeline."""
    # Verify idea belongs to the season
    idea = db.query(SeasonProductIdea).filter(
        SeasonProductIdea.id == idea_id,
        SeasonProductIdea.season_id == season_id,
    ).first()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found in this season")

    designer = SeasonalDesigner(db)
    result = designer.promote_idea(idea_id)
    if not result:
        raise HTTPException(status_code=404, detail="Idea not found")
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
