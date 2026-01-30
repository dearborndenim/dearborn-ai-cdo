"""Event bus webhook and test endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..event_bus import event_bus, publish_demand_forecast

router = APIRouter()


@router.post("/cdo/events/webhook", tags=["Events"])
async def receive_event(event: dict, db: Session = Depends(get_db)):
    """Receive events from other modules."""
    event_bus.handle_incoming_event(event)
    return {"success": True, "event_id": event.get("event_id")}


@router.post("/cdo/events/test-demand-forecast", tags=["Events"])
async def test_demand_forecast():
    """Test demand forecast event to COO."""
    event_id = publish_demand_forecast(
        sku="TEST-SKU-001",
        product_name="Test Product",
        forecast_period_days=30,
        forecasted_units=500,
        confidence=0.85
    )
    return {"success": True, "event_id": event_id}
