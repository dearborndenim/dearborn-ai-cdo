"""Report endpoints."""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from ..db import (
    get_db, Report, SalesSnapshot, ProductPerformance, ReportType
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

    else:
        title = f"{data.report_type.value.title()} Report"
        report_data = {"note": "Report type implementation pending"}

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
