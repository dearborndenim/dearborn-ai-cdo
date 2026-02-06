"""Alert endpoints."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..db import get_db, CDOAlert, AlertSeverity

router = APIRouter()


class AlertCreate(BaseModel):
    severity: AlertSeverity = AlertSeverity.INFO
    category: str
    title: str
    message: Optional[str] = None


class AlertResolve(BaseModel):
    resolved_by: str = "system"


@router.get("/cdo/alerts", tags=["Alerts"])
async def list_alerts(
    resolved: Optional[bool] = None,
    category: Optional[str] = None,
    severity: Optional[AlertSeverity] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List CDO alerts."""
    query = db.query(CDOAlert)

    if resolved is not None:
        query = query.filter(CDOAlert.is_resolved == resolved)
    if category:
        query = query.filter(CDOAlert.category == category)
    if severity:
        query = query.filter(CDOAlert.severity == severity)

    total = query.count()
    alerts = query.order_by(CDOAlert.created_at.desc()).limit(limit).all()

    return {
        "total": total,
        "alerts": [{
            "id": a.id,
            "severity": a.severity.value if a.severity else "info",
            "category": a.category,
            "title": a.title,
            "message": a.message,
            "is_resolved": a.is_resolved,
            "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
            "resolved_by": a.resolved_by,
            "created_at": a.created_at.isoformat() if a.created_at else None
        } for a in alerts]
    }


@router.post("/cdo/alerts", tags=["Alerts"])
async def create_alert(
    data: AlertCreate,
    db: Session = Depends(get_db)
):
    """Create a new CDO alert."""
    alert = CDOAlert(
        severity=data.severity,
        category=data.category,
        title=data.title,
        message=data.message,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    return {
        "success": True,
        "alert_id": alert.id,
        "severity": alert.severity.value if alert.severity else "info",
        "title": alert.title,
    }


@router.get("/cdo/alerts/{alert_id}", tags=["Alerts"])
async def get_alert(
    alert_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific alert by ID."""
    alert = db.query(CDOAlert).filter(CDOAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {
        "id": alert.id,
        "severity": alert.severity.value if alert.severity else "info",
        "category": alert.category,
        "title": alert.title,
        "message": alert.message,
        "is_resolved": alert.is_resolved,
        "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
        "resolved_by": alert.resolved_by,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
    }


@router.post("/cdo/alerts/{alert_id}/resolve", tags=["Alerts"])
async def resolve_alert(
    alert_id: int,
    data: AlertResolve = None,
    db: Session = Depends(get_db)
):
    """Resolve an alert."""
    alert = db.query(CDOAlert).filter(CDOAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if alert.is_resolved:
        raise HTTPException(status_code=400, detail="Alert already resolved")

    alert.is_resolved = True
    alert.resolved_at = datetime.utcnow()
    alert.resolved_by = data.resolved_by if data else "system"
    db.commit()

    return {
        "success": True,
        "alert_id": alert.id,
        "resolved_at": alert.resolved_at.isoformat(),
    }


@router.delete("/cdo/alerts/{alert_id}", tags=["Alerts"])
async def delete_alert(
    alert_id: int,
    db: Session = Depends(get_db)
):
    """Delete an alert."""
    alert = db.query(CDOAlert).filter(CDOAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    db.delete(alert)
    db.commit()

    return {"success": True, "deleted_id": alert_id}
