"""Dashboard endpoint."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from ..db import (
    get_db, SalesSnapshot, ProductPerformance, CustomerSegment,
    CustomerAnalytics, TechPack, ProductIdea, TrendAnalysis,
    ProductIdeaStatus
)

router = APIRouter()


class DashboardResponse(BaseModel):
    sales_summary: dict
    top_products: list
    customer_metrics: dict
    recent_tech_packs: list
    pending_ideas: int
    active_trends: int


@router.get("/cdo/dashboard", response_model=DashboardResponse, tags=["Dashboard"])
async def get_dashboard(db: Session = Depends(get_db)):
    """Get CDO dashboard overview."""

    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    sales_data = db.query(
        func.sum(SalesSnapshot.total_revenue).label("revenue"),
        func.sum(SalesSnapshot.total_orders).label("orders"),
        func.sum(SalesSnapshot.total_units).label("units")
    ).filter(SalesSnapshot.snapshot_date >= thirty_days_ago).first()

    sales_summary = {
        "period": "last_30_days",
        "total_revenue": float(sales_data.revenue or 0),
        "total_orders": int(sales_data.orders or 0),
        "total_units": int(sales_data.units or 0),
        "average_order_value": float(sales_data.revenue or 0) / max(1, int(sales_data.orders or 1))
    }

    top_products = db.query(ProductPerformance).order_by(
        ProductPerformance.revenue_30d.desc()
    ).limit(10).all()

    customer_count = db.query(func.count(CustomerAnalytics.id)).scalar() or 0
    avg_ltv = db.query(func.avg(CustomerAnalytics.lifetime_value)).scalar() or 0

    customer_metrics = {
        "total_customers": customer_count,
        "average_ltv": float(avg_ltv),
        "segments": db.query(func.count(CustomerSegment.id)).scalar() or 0
    }

    recent_tech_packs = db.query(TechPack).order_by(
        TechPack.updated_at.desc()
    ).limit(5).all()

    pending_ideas = db.query(func.count(ProductIdea.id)).filter(
        ProductIdea.status == ProductIdeaStatus.CONCEPT
    ).scalar() or 0

    active_trends = db.query(func.count(TrendAnalysis.id)).filter(
        TrendAnalysis.trend_score >= 50
    ).scalar() or 0

    return DashboardResponse(
        sales_summary=sales_summary,
        top_products=[{
            "sku": p.sku,
            "name": p.product_name,
            "revenue_30d": p.revenue_30d,
            "units_30d": p.units_sold_30d,
            "performance_score": p.performance_score
        } for p in top_products],
        customer_metrics=customer_metrics,
        recent_tech_packs=[{
            "id": tp.id,
            "number": tp.tech_pack_number,
            "style_name": tp.style_name,
            "status": tp.status.value if tp.status else "draft",
            "updated_at": tp.updated_at.isoformat() if tp.updated_at else None
        } for tp in recent_tech_packs],
        pending_ideas=pending_ideas,
        active_trends=active_trends
    )
