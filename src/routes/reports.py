"""Report endpoints."""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from ..db import (
    get_db, Report, SalesSnapshot, ProductPerformance, ReportType,
    CustomerSegment, CustomerAnalytics, TechPack, ProductIdea,
    ProductPipeline
)

router = APIRouter()


class ReportRequest(BaseModel):
    report_type: ReportType
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None


@router.get("/cdo/reports", tags=["Reports"])
async def list_reports(
    report_type: Optional[ReportType] = None,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """List generated reports."""
    query = db.query(Report)

    if report_type:
        query = query.filter(Report.report_type == report_type)

    total = query.count()
    reports = query.order_by(Report.created_at.desc()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "reports": [{
            "id": r.id,
            "report_number": r.report_number,
            "title": r.title,
            "type": r.report_type.value if r.report_type else None,
            "period_start": r.period_start.isoformat() if r.period_start else None,
            "period_end": r.period_end.isoformat() if r.period_end else None,
            "created_at": r.created_at.isoformat() if r.created_at else None
        } for r in reports]
    }


@router.post("/cdo/reports/generate", tags=["Reports"])
async def generate_report(
    data: ReportRequest,
    db: Session = Depends(get_db)
):
    """Generate a new report."""
    count = db.query(func.count(Report.id)).scalar() or 0
    report_number = f"RPT-{datetime.now().strftime('%Y%m%d')}-{count + 1:04d}"

    period_end = data.period_end or datetime.utcnow()
    period_start = data.period_start or (period_end - timedelta(days=30))

    report_data = {}
    insights = []
    recommendations = []

    if data.report_type == ReportType.SALES:
        snapshots = db.query(SalesSnapshot).filter(
            SalesSnapshot.snapshot_date >= period_start,
            SalesSnapshot.snapshot_date <= period_end
        ).all()

        report_data = {
            "total_revenue": sum(s.total_revenue or 0 for s in snapshots),
            "total_orders": sum(s.total_orders or 0 for s in snapshots),
            "total_units": sum(s.total_units or 0 for s in snapshots),
            "daily_breakdown": [{
                "date": s.snapshot_date.isoformat(),
                "revenue": s.total_revenue,
                "orders": s.total_orders
            } for s in snapshots]
        }
        title = "Sales Report"

    elif data.report_type == ReportType.PRODUCT:
        products = db.query(ProductPerformance).order_by(
            ProductPerformance.revenue_30d.desc()
        ).limit(50).all()

        report_data = {
            "top_products": [{
                "sku": p.sku,
                "name": p.product_name,
                "revenue": p.revenue_30d,
                "units": p.units_sold_30d
            } for p in products]
        }
        title = "Product Performance Report"

    elif data.report_type == ReportType.INVENTORY:
        # Aggregate product performance as inventory proxy (CDO tracks sell-through)
        products = db.query(ProductPerformance).all()
        low_stock = [p for p in products if p.days_of_stock is not None and p.days_of_stock < 14]
        report_data = {
            "total_skus_tracked": len(products),
            "low_stock_skus": [{
                "sku": p.sku,
                "name": p.product_name,
                "days_of_stock": p.days_of_stock,
                "sell_through_rate": p.sell_through_rate,
            } for p in low_stock],
            "top_velocity": [{
                "sku": p.sku,
                "name": p.product_name,
                "units_sold_30d": p.units_sold_30d,
                "days_of_stock": p.days_of_stock,
            } for p in sorted(products, key=lambda x: x.units_sold_30d or 0, reverse=True)[:20]],
        }
        title = "Inventory Velocity Report"
        insights.append("Low stock items need reorder attention from COO")

    elif data.report_type == ReportType.CUSTOMER:
        segments = db.query(CustomerSegment).all()
        customers = db.query(CustomerAnalytics).order_by(
            CustomerAnalytics.total_spent.desc()
        ).limit(100).all()
        total_customers = db.query(func.count(CustomerAnalytics.id)).scalar() or 0

        report_data = {
            "total_customers": total_customers,
            "segments": [{
                "name": s.segment_name,
                "count": s.customer_count,
                "total_ltv": s.total_ltv,
                "avg_order_frequency": s.average_order_frequency,
            } for s in segments],
            "top_customers": [{
                "email": c.email,
                "total_orders": c.total_orders,
                "total_spent": c.total_spent,
                "lifetime_value": c.lifetime_value,
                "churn_risk": c.churn_risk_score,
                "preferred_categories": c.preferred_categories,
            } for c in customers[:20]],
            "churn_risk_high": len([c for c in customers if (c.churn_risk_score or 0) > 0.7]),
        }
        title = "Customer Analytics Report"

    elif data.report_type == ReportType.FINANCIAL:
        snapshots = db.query(SalesSnapshot).filter(
            SalesSnapshot.snapshot_date >= period_start,
            SalesSnapshot.snapshot_date <= period_end
        ).order_by(SalesSnapshot.snapshot_date).all()

        total_rev = sum(s.total_revenue or 0 for s in snapshots)
        total_orders = sum(s.total_orders or 0 for s in snapshots)
        online = sum(s.online_revenue or 0 for s in snapshots)
        wholesale = sum(s.wholesale_revenue or 0 for s in snapshots)
        retail = sum(s.retail_revenue or 0 for s in snapshots)

        report_data = {
            "total_revenue": total_rev,
            "total_orders": total_orders,
            "average_order_value": total_rev / total_orders if total_orders else 0,
            "channel_breakdown": {
                "online": online,
                "wholesale": wholesale,
                "retail": retail,
            },
            "daily_revenue": [{
                "date": s.snapshot_date.isoformat(),
                "revenue": s.total_revenue,
                "orders": s.total_orders,
            } for s in snapshots],
        }
        title = "Financial Summary Report"
        recommendations.append("Cross-reference with CFO module for margin analysis")

    elif data.report_type == ReportType.CROSS_MODULE:
        # Aggregate data across CDO domain for cross-module handoff
        pipeline_items = db.query(ProductPipeline).all()
        ideas = db.query(ProductIdea).all()
        tech_packs = db.query(TechPack).all()
        snapshots = db.query(SalesSnapshot).filter(
            SalesSnapshot.snapshot_date >= period_start,
            SalesSnapshot.snapshot_date <= period_end
        ).all()

        report_data = {
            "pipeline_summary": {
                "total": len(pipeline_items),
                "by_phase": {},
            },
            "product_ideas": {
                "total": len(ideas),
                "by_status": {},
            },
            "tech_packs": {
                "total": len(tech_packs),
                "by_status": {},
            },
            "revenue_period": sum(s.total_revenue or 0 for s in snapshots),
            "handoff_status": {
                "to_coo": len([p for p in pipeline_items if p.handoff_to_coo]),
                "to_cmo": len([p for p in pipeline_items if p.handoff_to_cmo]),
                "to_cfo": len([p for p in pipeline_items if p.handoff_to_cfo]),
            },
        }

        for p in pipeline_items:
            phase = p.current_phase.value if p.current_phase else "unknown"
            report_data["pipeline_summary"]["by_phase"][phase] = \
                report_data["pipeline_summary"]["by_phase"].get(phase, 0) + 1

        for idea in ideas:
            status = idea.status.value if idea.status else "unknown"
            report_data["product_ideas"]["by_status"][status] = \
                report_data["product_ideas"]["by_status"].get(status, 0) + 1

        for tp in tech_packs:
            status = tp.status.value if tp.status else "unknown"
            report_data["tech_packs"]["by_status"][status] = \
                report_data["tech_packs"]["by_status"].get(status, 0) + 1

        title = "Cross-Module Status Report"
        insights.append("Pipeline handoff data ready for COO/CMO/CFO consumption")

    else:
        title = f"{data.report_type.value.title()} Report"
        report_data = {}

    report = Report(
        report_number=report_number,
        title=title,
        report_type=data.report_type,
        period_start=period_start,
        period_end=period_end,
        data=report_data,
        insights=insights,
        recommendations=recommendations,
        generated_by="system"
    )

    db.add(report)
    db.commit()
    db.refresh(report)

    return {
        "success": True,
        "report_id": report.id,
        "report_number": report_number
    }
