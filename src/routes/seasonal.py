"""Seasonal design workflow endpoints."""
import base64
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db, Season, SeasonProductIdea, SeasonLook, SeasonResearch, SeasonStatus, MoodBoard
from ..cdo.seasonal import SeasonalDesigner
from ..cdo.mood_board import MoodBoardGenerator

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
            "look_count": len(s.looks) if s.looks else 0,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        } for s in seasons],
    }


@router.get("/cdo/seasons/{season_id}", tags=["Seasons"])
async def get_season(season_id: int, db: Session = Depends(get_db)):
    """Get season detail including research, looks, and flat ideas list."""
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    ideas = db.query(SeasonProductIdea).filter(
        SeasonProductIdea.season_id == season_id
    ).order_by(SeasonProductIdea.priority.desc()).all()

    looks = db.query(SeasonLook).filter(
        SeasonLook.season_id == season_id
    ).order_by(SeasonLook.look_number).all()

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
        "looks": [{
            "id": look.id,
            "look_number": look.look_number,
            "name": look.name,
            "theme": look.theme,
            "occasion": look.occasion,
            "styling_notes": look.styling_notes,
            "pieces": [_serialize_idea(i) for i in ideas if i.look_id == look.id],
        } for look in looks],
        "ideas": [_serialize_idea(i) for i in ideas],
    }


@router.post("/cdo/seasons/{season_id}/research", tags=["Seasons"])
async def research_customer(season_id: int, db: Session = Depends(get_db)):
    """Trigger 5-step research: 4 Perplexity trend sections + 1 GPT-4o customer profile.

    Returns structured research sections with citations.
    """
    designer = SeasonalDesigner(db)
    result = designer.research_customer(season_id)
    if not result:
        raise HTTPException(status_code=404, detail="Season not found")
    return result


@router.get("/cdo/seasons/{season_id}/research", tags=["Seasons"])
async def get_research(season_id: int, db: Session = Depends(get_db)):
    """Get structured research sections with citations for a season."""
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    records = db.query(SeasonResearch).filter(
        SeasonResearch.season_id == season_id
    ).order_by(SeasonResearch.id).all()

    return {
        "season_id": season.id,
        "season_name": season.name,
        "total_sections": len(records),
        "total_citations": sum(len(r.citations or []) for r in records),
        "sections": [{
            "id": r.id,
            "research_type": r.research_type,
            "content": r.content,
            "citations": r.citations or [],
            "source": r.source,
            "model_used": r.model_used,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in records],
    }


@router.post("/cdo/seasons/{season_id}/generate-ideas", tags=["Seasons"])
async def generate_ideas(
    season_id: int,
    look_count: int = Query(default=5, alias="look_count"),
    count: int = Query(default=None),
    db: Session = Depends(get_db),
):
    """Generate coordinated looks for the season.

    Each look is a themed outfit with 2-4 pieces.
    look_count = number of looks (default 5), yielding 10-20 total items.
    """
    # Support both 'look_count' and legacy 'count' parameter
    num_looks = count if count is not None else look_count

    designer = SeasonalDesigner(db)
    result = designer.generate_product_ideas(season_id, count=num_looks)
    if not result:
        raise HTTPException(status_code=404, detail="Season not found")
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/cdo/seasons/{season_id}/looks", tags=["Seasons"])
async def get_looks(season_id: int, db: Session = Depends(get_db)):
    """Get coordinated looks with their pieces for a season."""
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    looks = db.query(SeasonLook).filter(
        SeasonLook.season_id == season_id
    ).order_by(SeasonLook.look_number).all()

    ideas = db.query(SeasonProductIdea).filter(
        SeasonProductIdea.season_id == season_id
    ).all()

    return {
        "season_id": season.id,
        "season_name": season.name,
        "total_looks": len(looks),
        "total_pieces": len(ideas),
        "looks": [{
            "id": look.id,
            "look_number": look.look_number,
            "name": look.name,
            "theme": look.theme,
            "occasion": look.occasion,
            "styling_notes": look.styling_notes,
            "pieces": [_serialize_idea(i) for i in ideas if i.look_id == look.id],
        } for look in looks],
    }


@router.get("/cdo/seasons/{season_id}/ideas", tags=["Seasons"])
async def list_ideas(
    season_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List product ideas for a season (flat list)."""
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
        "ideas": [_serialize_idea(i) for i in ideas],
    }


@router.post("/cdo/seasons/{season_id}/ideas/{idea_id}/promote", tags=["Seasons"])
async def promote_idea(
    season_id: int,
    idea_id: int,
    db: Session = Depends(get_db),
):
    """Promote a product idea into the product pipeline."""
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


@router.post("/cdo/seasons/{season_id}/ideas/{idea_id}/generate-image", tags=["Seasons"])
async def generate_idea_image(
    season_id: int,
    idea_id: int,
    db: Session = Depends(get_db),
):
    """Generate a DALL-E product sketch for an idea."""
    idea = db.query(SeasonProductIdea).filter(
        SeasonProductIdea.id == idea_id,
        SeasonProductIdea.season_id == season_id,
    ).first()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found in this season")

    designer = SeasonalDesigner(db)
    result = designer.generate_idea_image(idea_id)
    if not result:
        raise HTTPException(status_code=404, detail="Idea not found")
    return result


@router.post("/cdo/seasons/{season_id}/generate-all-images", tags=["Seasons"])
async def generate_all_idea_images(
    season_id: int,
    db: Session = Depends(get_db),
):
    """Generate DALL-E images for all pending ideas in a season."""
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    ideas = db.query(SeasonProductIdea).filter(
        SeasonProductIdea.season_id == season_id,
        SeasonProductIdea.image_url.is_(None),
    ).all()

    designer = SeasonalDesigner(db)
    results = []
    for idea in ideas:
        result = designer.generate_idea_image(idea.id)
        results.append(result)

    return {
        "season_id": season_id,
        "images_generated": len([r for r in results if r and r.get("image_url")]),
        "total_ideas": len(ideas),
        "results": results,
    }


@router.post("/cdo/seasons/{season_id}/ideas/{idea_id}/reject", tags=["Seasons"])
async def reject_idea(
    season_id: int,
    idea_id: int,
    db: Session = Depends(get_db),
):
    """Reject a product idea."""
    idea = db.query(SeasonProductIdea).filter(
        SeasonProductIdea.id == idea_id,
        SeasonProductIdea.season_id == season_id,
    ).first()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found in this season")

    idea.status = "rejected"
    db.commit()
    return {"success": True, "message": f"Idea '{idea.title}' rejected"}


@router.post("/cdo/seasons/{season_id}/ideas/{idea_id}/mood-board", tags=["Mood Boards"])
async def generate_mood_board(
    season_id: int,
    idea_id: int,
    db: Session = Depends(get_db),
):
    """Generate a mood board for a product idea.

    Creates reference images (via web search), design variation sketches
    (via GPT Image 1.5), and written design specifications (via GPT-4o).
    """
    idea = db.query(SeasonProductIdea).filter(
        SeasonProductIdea.id == idea_id,
        SeasonProductIdea.season_id == season_id,
    ).first()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found in this season")

    generator = MoodBoardGenerator(db)
    result = generator.generate_mood_board(idea_id)
    if not result:
        raise HTTPException(status_code=404, detail="Idea not found")
    if "error" in result and result.get("status") != "complete":
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.get("/cdo/seasons/{season_id}/ideas/{idea_id}/mood-board", tags=["Mood Boards"])
async def get_mood_board(
    season_id: int,
    idea_id: int,
    db: Session = Depends(get_db),
):
    """Get an existing mood board for a product idea."""
    idea = db.query(SeasonProductIdea).filter(
        SeasonProductIdea.id == idea_id,
        SeasonProductIdea.season_id == season_id,
    ).first()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found in this season")

    generator = MoodBoardGenerator(db)
    result = generator.get_mood_board(idea_id)
    if not result:
        raise HTTPException(status_code=404, detail="Idea not found")
    return result


@router.get("/cdo/seasons/{season_id}/ideas/{idea_id}/mood-board/sketch/{variation_name}", tags=["Mood Boards"])
async def get_mood_board_sketch(
    season_id: int,
    idea_id: int,
    variation_name: str,
    db: Session = Depends(get_db),
):
    """Get a specific design sketch image from a mood board.

    Returns the raw PNG image for a specific variation.
    """
    from fastapi.responses import Response

    idea = db.query(SeasonProductIdea).filter(
        SeasonProductIdea.id == idea_id,
        SeasonProductIdea.season_id == season_id,
    ).first()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found in this season")

    mood_board = db.query(MoodBoard).filter(MoodBoard.idea_id == idea_id).first()
    if not mood_board or not mood_board.design_sketches:
        raise HTTPException(status_code=404, detail="Mood board not found")

    for sketch in mood_board.design_sketches:
        if sketch.get("variation_name", "").lower() == variation_name.lower():
            if sketch.get("image_data"):
                image_bytes = base64.b64decode(sketch["image_data"])
                return Response(
                    content=image_bytes,
                    media_type="image/png",
                    headers={"Content-Disposition": f'inline; filename="{variation_name}.png"'},
                )
            raise HTTPException(status_code=404, detail=f"Sketch '{variation_name}' has no image data")

    raise HTTPException(status_code=404, detail=f"Variation '{variation_name}' not found")


def _serialize_idea(i: SeasonProductIdea) -> dict:
    """Serialize a SeasonProductIdea to dict with all new fields."""
    return {
        "id": i.id,
        "look_id": i.look_id,
        "title": i.title,
        "category": i.category,
        "subcategory": i.subcategory,
        "style": i.style,
        "description": i.description,
        "customer_fit": i.customer_fit,
        "fabric_recommendation": i.fabric_recommendation,
        "fabric_weight": i.fabric_weight,
        "fabric_weave": i.fabric_weave,
        "fabric_composition": i.fabric_composition,
        "fabric_type": i.fabric_type,
        "colorway": i.colorway,
        "sourced_externally": i.sourced_externally,
        "trend_citations": i.trend_citations,
        "suggested_vendors": i.suggested_vendors,
        "suggested_retail": i.suggested_retail,
        "estimated_cost": i.estimated_cost,
        "estimated_margin": i.estimated_margin,
        "priority": i.priority,
        "ai_rationale": i.ai_rationale,
        "status": i.status,
        "image_url": i.image_url,
        "labor_cost": i.labor_cost,
        "material_cost": i.material_cost,
        "sewing_time_minutes": i.sewing_time_minutes,
        "promoted_concept_id": i.promoted_concept_id,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    }
