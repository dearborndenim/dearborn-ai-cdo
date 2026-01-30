"""Health check and status endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel

from ..config import get_settings
from ..db import get_db, ShopifyAuth
from ..event_bus import event_bus

settings = get_settings()
router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    module: str
    database: str
    event_bus: str
    shopify: str


@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    event_bus_status = "connected" if event_bus.is_connected() else "disconnected"

    shopify_auth = db.query(ShopifyAuth).first()
    shopify_status = "connected" if shopify_auth else "not_configured"

    return HealthResponse(
        status="healthy",
        module="CDO",
        database=db_status,
        event_bus=event_bus_status,
        shopify=shopify_status
    )


@router.get("/cdo/events/status", tags=["Events"])
async def event_bus_status_check():
    """Check event bus connection status."""
    return {
        "connected": event_bus.is_connected(),
        "redis_url": settings.redis_url[:30] + "..." if settings.redis_url else None
    }


@router.get("/")
async def root():
    """Root endpoint."""
    return {
        "module": "CDO",
        "name": "Dearborn AI CDO",
        "version": "1.0.0",
        "status": "operational",
        "docs": "/docs"
    }
