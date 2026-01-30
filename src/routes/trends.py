"""Trend analysis endpoints."""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db, TrendAnalysis

router = APIRouter()


@router.get("/cdo/trends", tags=["Trends"])
async def list_trends(
    min_score: float = 0,
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List tracked trends."""
    query = db.query(TrendAnalysis).filter(TrendAnalysis.trend_score >= min_score)

    if category:
        query = query.filter(TrendAnalysis.category == category)

    trends = query.order_by(TrendAnalysis.trend_score.desc()).all()

    return {
        "trends": [{
            "id": t.id,
            "name": t.trend_name,
            "category": t.category,
            "score": t.trend_score,
            "growth_rate": t.growth_rate,
            "relevance_score": t.relevance_score,
            "keywords": t.keywords,
            "recommended_actions": t.recommended_actions
        } for t in trends]
    }
