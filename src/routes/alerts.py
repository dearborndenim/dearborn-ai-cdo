"""Alert endpoints."""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db, CDOAlert

router = APIRouter()


@router.get("/cdo/alerts", tags=["Alerts"])
async def list_alerts(
    resolved: Optional[bool] = None,
    category: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List CDO alerts."""
    query = db.query(CDOAlert)

    if resolved is not None:
        query = query.filter(CDOAlert.is_resolved == resolved)
    if category:
        query = query.filter(CDOAlert.category == category)

    alerts = query.order_by(CDOAlert.created_at.desc()).limit(limit).all()

    return {
        "alerts": [{
            "id": a.id,
            "severity": a.severity.value if a.severity else "info",
            "category": a.category,
            "title": a.title,
            "message": a.message,
            "is_resolved": a.is_resolved,
            "created_at": a.created_at.isoformat() if a.created_at else None
        } for a in alerts]
    }
