"""Analytics endpoints."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db, SalesSnapshot, ProductPerformance

router = APIRouter()


@router.get("/cdo/analytics/sales", tags=["Analytics"])
async def get_sales_analytics(
    days: int = 30,
    db: Session = Depends(get_db)
):
    """Get sales analytics for specified period."""
    start_date = datetime.utcnow() - timedelta(days=days)

    snapshots = db.query(SalesSnapshot).filter(
        SalesSnapshot.snapshot_date >= start_date
    ).order_by(SalesSnapshot.snapshot_date).all()

    return {
        "period_days": days,
        "daily_data": [{
            "date": s.snapshot_date.isoformat(),
            "revenue": s.total_revenue,
            "orders": s.total_orders,
            "units": s.total_units,
            "aov": s.average_order_value
        } for s in snapshots],
        "totals": {
            "revenue": sum(s.total_revenue or 0 for s in snapshots),
            "orders": sum(s.total_orders or 0 for s in snapshots),
            "units": sum(s.total_units or 0 for s in snapshots)
        }
    }


@router.get("/cdo/analytics/products", tags=["Analytics"])
async def get_product_analytics(
    sort_by: str = "revenue_30d",
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """Get product performance analytics."""
    sort_column = getattr(ProductPerformance, sort_by, ProductPerformance.revenue_30d)

    products = db.query(ProductPerformance).order_by(
        sort_column.desc()
    ).limit(limit).all()

    return {
        "products": [{
            "sku": p.sku,
            "name": p.product_name,
            "units_sold_30d": p.units_sold_30d,
            "revenue_30d": p.revenue_30d,
            "return_rate": p.return_rate_30d,
            "days_of_stock": p.days_of_stock,
            "performance_score": p.performance_score,
            "trend": p.trend_direction
        } for p in products]
    }
