"""
Dearborn AI CDO Module - FastAPI Server

Chief Data Officer: Analytics, Tech Packs, Pattern Files, Product Development
"""
import logging
import secrets
import httpx
from datetime import datetime, timedelta
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from pydantic import BaseModel, Field

from .config import get_settings
from .db import (
    init_db, get_db, SessionLocal,
    SalesSnapshot, ProductPerformance, CustomerSegment, CustomerAnalytics,
    TechPack, TechPackMeasurement, TechPackMaterial, TechPackConstruction,
    PatternFile, PatternPiece,
    ProductIdea, TrendAnalysis,
    Report, ReportSchedule,
    CDOAlert, CDOEvent, ShopifyAuth,
    TechPackStatus, PatternStatus, ProductIdeaStatus, ReportType, ReportFrequency, AlertSeverity
)
from .event_bus import event_bus, publish_tech_pack_ready, publish_product_recommendation, publish_demand_forecast

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.log_level))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    logger.info("Starting Dearborn AI CDO Module...")

    try:
        init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

    logger.info("CDO Module startup complete")
    yield

    logger.info("Shutting down CDO Module...")
    event_bus.disconnect()


app = FastAPI(
    title="Dearborn AI CDO",
    description="""
    Chief Data Officer Module for Dearborn Denim AI

    ## Features
    - **Analytics**: Sales, customer, and product performance analytics
    - **Tech Packs**: Technical package creation and management
    - **Pattern Files**: DXF/AAMA pattern file generation
    - **Product Development**: AI-powered product recommendations
    - **Reports**: Automated reporting and insights
    - **Trend Analysis**: Market and fashion trend tracking
    """,
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== Pydantic Models ====================

class HealthResponse(BaseModel):
    status: str
    module: str
    database: str
    event_bus: str
    shopify: str


class DashboardResponse(BaseModel):
    sales_summary: dict
    top_products: list
    customer_metrics: dict
    recent_tech_packs: list
    pending_ideas: int
    active_trends: int


# Tech Pack Models
class TechPackCreate(BaseModel):
    style_name: str
    style_number: Optional[str] = None
    category: str
    season: Optional[str] = None
    description: Optional[str] = None
    fit_type: Optional[str] = None
    rise: Optional[str] = None
    leg_opening: Optional[str] = None
    primary_fabric: Optional[str] = None
    fabric_weight: Optional[str] = None
    fabric_content: Optional[str] = None
    target_cost: Optional[float] = None
    target_retail: Optional[float] = None


class TechPackMeasurementCreate(BaseModel):
    size: str
    waist: Optional[float] = None
    front_rise: Optional[float] = None
    back_rise: Optional[float] = None
    hip: Optional[float] = None
    thigh: Optional[float] = None
    knee: Optional[float] = None
    leg_opening: Optional[float] = None
    inseam: Optional[float] = None
    outseam: Optional[float] = None
    additional_measurements: Optional[dict] = None


class TechPackMaterialCreate(BaseModel):
    material_type: str
    material_name: str
    supplier: Optional[str] = None
    supplier_code: Optional[str] = None
    color: Optional[str] = None
    color_code: Optional[str] = None
    placement: Optional[str] = None
    quantity_per_unit: Optional[float] = None
    unit_of_measure: Optional[str] = None
    unit_cost: Optional[float] = None


class TechPackConstructionCreate(BaseModel):
    operation_number: int
    operation_name: str
    description: Optional[str] = None
    machine_type: Optional[str] = None
    stitch_type: Optional[str] = None
    stitches_per_inch: Optional[float] = None
    thread_type: Optional[str] = None
    thread_color: Optional[str] = None
    seam_allowance: Optional[float] = None


# Pattern File Models
class PatternFileCreate(BaseModel):
    tech_pack_id: int
    file_name: str
    file_type: str = "dxf"
    base_size: str
    sizes_included: List[str]


class PatternPieceCreate(BaseModel):
    piece_name: str
    piece_code: Optional[str] = None
    fabric_type: str = "shell"
    cut_quantity: int = 1
    grain_line: str = "straight"
    mirror: bool = False


# Product Idea Models
class ProductIdeaCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: str
    source: str = "internal"
    target_market: Optional[str] = None
    estimated_cost: Optional[float] = None
    estimated_retail: Optional[float] = None
    estimated_annual_units: Optional[int] = None


# Report Models
class ReportRequest(BaseModel):
    report_type: ReportType
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None


# ==================== Health & Status ====================

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    # Check database
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    # Check event bus
    event_bus_status = "connected" if event_bus.is_connected() else "disconnected"

    # Check Shopify
    shopify_auth = db.query(ShopifyAuth).first()
    shopify_status = "connected" if shopify_auth else "not_configured"

    return HealthResponse(
        status="healthy",
        module="CDO",
        database=db_status,
        event_bus=event_bus_status,
        shopify=shopify_status
    )


@app.get("/cdo/events/status", tags=["Events"])
async def event_bus_status():
    """Check event bus connection status."""
    return {
        "connected": event_bus.is_connected(),
        "redis_url": settings.redis_url[:30] + "..." if settings.redis_url else None
    }


# ==================== Dashboard ====================

@app.get("/cdo/dashboard", response_model=DashboardResponse, tags=["Dashboard"])
async def get_dashboard(db: Session = Depends(get_db)):
    """Get CDO dashboard overview."""

    # Sales summary (last 30 days)
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

    # Top products
    top_products = db.query(ProductPerformance).order_by(
        ProductPerformance.revenue_30d.desc()
    ).limit(10).all()

    # Customer metrics
    customer_count = db.query(func.count(CustomerAnalytics.id)).scalar() or 0
    avg_ltv = db.query(func.avg(CustomerAnalytics.lifetime_value)).scalar() or 0

    customer_metrics = {
        "total_customers": customer_count,
        "average_ltv": float(avg_ltv),
        "segments": db.query(func.count(CustomerSegment.id)).scalar() or 0
    }

    # Recent tech packs
    recent_tech_packs = db.query(TechPack).order_by(
        TechPack.updated_at.desc()
    ).limit(5).all()

    # Pending product ideas
    pending_ideas = db.query(func.count(ProductIdea.id)).filter(
        ProductIdea.status == ProductIdeaStatus.CONCEPT
    ).scalar() or 0

    # Active trends
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


# ==================== Tech Packs ====================

@app.get("/cdo/tech-packs", tags=["Tech Packs"])
async def list_tech_packs(
    status: Optional[TechPackStatus] = None,
    category: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List all tech packs with optional filtering."""
    query = db.query(TechPack)

    if status:
        query = query.filter(TechPack.status == status)
    if category:
        query = query.filter(TechPack.category == category)

    total = query.count()
    tech_packs = query.order_by(TechPack.updated_at.desc()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "tech_packs": [{
            "id": tp.id,
            "tech_pack_number": tp.tech_pack_number,
            "style_name": tp.style_name,
            "style_number": tp.style_number,
            "category": tp.category,
            "season": tp.season,
            "status": tp.status.value if tp.status else "draft",
            "created_at": tp.created_at.isoformat() if tp.created_at else None,
            "updated_at": tp.updated_at.isoformat() if tp.updated_at else None
        } for tp in tech_packs]
    }


@app.post("/cdo/tech-packs", tags=["Tech Packs"])
async def create_tech_pack(
    data: TechPackCreate,
    db: Session = Depends(get_db)
):
    """Create a new tech pack."""
    # Generate tech pack number
    count = db.query(func.count(TechPack.id)).scalar() or 0
    tech_pack_number = f"TP-{datetime.now().strftime('%Y%m')}-{count + 1:04d}"

    # Calculate target margin if prices provided
    target_margin = None
    if data.target_cost and data.target_retail and data.target_retail > 0:
        target_margin = ((data.target_retail - data.target_cost) / data.target_retail) * 100

    tech_pack = TechPack(
        tech_pack_number=tech_pack_number,
        style_name=data.style_name,
        style_number=data.style_number,
        category=data.category,
        season=data.season,
        description=data.description,
        fit_type=data.fit_type,
        rise=data.rise,
        leg_opening=data.leg_opening,
        primary_fabric=data.primary_fabric,
        fabric_weight=data.fabric_weight,
        fabric_content=data.fabric_content,
        target_cost=data.target_cost,
        target_retail=data.target_retail,
        target_margin=target_margin,
        status=TechPackStatus.DRAFT
    )

    db.add(tech_pack)
    db.commit()
    db.refresh(tech_pack)

    return {
        "success": True,
        "tech_pack_id": tech_pack.id,
        "tech_pack_number": tech_pack_number
    }


@app.get("/cdo/tech-packs/{tech_pack_id}", tags=["Tech Packs"])
async def get_tech_pack(tech_pack_id: int, db: Session = Depends(get_db)):
    """Get full tech pack details including measurements, materials, and construction."""
    tech_pack = db.query(TechPack).filter(TechPack.id == tech_pack_id).first()
    if not tech_pack:
        raise HTTPException(status_code=404, detail="Tech pack not found")

    return {
        "tech_pack": {
            "id": tech_pack.id,
            "tech_pack_number": tech_pack.tech_pack_number,
            "style_name": tech_pack.style_name,
            "style_number": tech_pack.style_number,
            "category": tech_pack.category,
            "season": tech_pack.season,
            "description": tech_pack.description,
            "design_notes": tech_pack.design_notes,
            "fit_type": tech_pack.fit_type,
            "rise": tech_pack.rise,
            "leg_opening": tech_pack.leg_opening,
            "primary_fabric": tech_pack.primary_fabric,
            "fabric_weight": tech_pack.fabric_weight,
            "fabric_content": tech_pack.fabric_content,
            "fabric_supplier": tech_pack.fabric_supplier,
            "target_cost": tech_pack.target_cost,
            "target_retail": tech_pack.target_retail,
            "target_margin": tech_pack.target_margin,
            "status": tech_pack.status.value if tech_pack.status else "draft",
            "ai_generated": tech_pack.ai_generated,
            "created_at": tech_pack.created_at.isoformat() if tech_pack.created_at else None,
            "updated_at": tech_pack.updated_at.isoformat() if tech_pack.updated_at else None
        },
        "measurements": [{
            "id": m.id,
            "size": m.size,
            "waist": m.waist,
            "front_rise": m.front_rise,
            "back_rise": m.back_rise,
            "hip": m.hip,
            "thigh": m.thigh,
            "knee": m.knee,
            "leg_opening": m.leg_opening,
            "inseam": m.inseam,
            "outseam": m.outseam,
            "additional": m.additional_measurements
        } for m in tech_pack.measurements],
        "materials": [{
            "id": m.id,
            "type": m.material_type,
            "name": m.material_name,
            "supplier": m.supplier,
            "color": m.color,
            "placement": m.placement,
            "quantity": m.quantity_per_unit,
            "unit": m.unit_of_measure,
            "cost": m.unit_cost
        } for m in tech_pack.materials],
        "construction": [{
            "id": c.id,
            "operation_number": c.operation_number,
            "operation_name": c.operation_name,
            "description": c.description,
            "machine_type": c.machine_type,
            "stitch_type": c.stitch_type,
            "spi": c.stitches_per_inch
        } for c in sorted(tech_pack.construction, key=lambda x: x.operation_number)],
        "patterns": [{
            "id": p.id,
            "file_name": p.file_name,
            "file_type": p.file_type,
            "status": p.status.value if p.status else "draft",
            "sizes": p.sizes_included
        } for p in tech_pack.patterns]
    }


@app.post("/cdo/tech-packs/{tech_pack_id}/measurements", tags=["Tech Packs"])
async def add_measurement(
    tech_pack_id: int,
    data: TechPackMeasurementCreate,
    db: Session = Depends(get_db)
):
    """Add measurement spec to tech pack."""
    tech_pack = db.query(TechPack).filter(TechPack.id == tech_pack_id).first()
    if not tech_pack:
        raise HTTPException(status_code=404, detail="Tech pack not found")

    measurement = TechPackMeasurement(
        tech_pack_id=tech_pack_id,
        size=data.size,
        waist=data.waist,
        front_rise=data.front_rise,
        back_rise=data.back_rise,
        hip=data.hip,
        thigh=data.thigh,
        knee=data.knee,
        leg_opening=data.leg_opening,
        inseam=data.inseam,
        outseam=data.outseam,
        additional_measurements=data.additional_measurements
    )

    db.add(measurement)
    db.commit()

    return {"success": True, "measurement_id": measurement.id}


@app.post("/cdo/tech-packs/{tech_pack_id}/materials", tags=["Tech Packs"])
async def add_material(
    tech_pack_id: int,
    data: TechPackMaterialCreate,
    db: Session = Depends(get_db)
):
    """Add material to tech pack bill of materials."""
    tech_pack = db.query(TechPack).filter(TechPack.id == tech_pack_id).first()
    if not tech_pack:
        raise HTTPException(status_code=404, detail="Tech pack not found")

    material = TechPackMaterial(
        tech_pack_id=tech_pack_id,
        material_type=data.material_type,
        material_name=data.material_name,
        supplier=data.supplier,
        supplier_code=data.supplier_code,
        color=data.color,
        color_code=data.color_code,
        placement=data.placement,
        quantity_per_unit=data.quantity_per_unit,
        unit_of_measure=data.unit_of_measure,
        unit_cost=data.unit_cost
    )

    db.add(material)
    db.commit()

    return {"success": True, "material_id": material.id}


@app.post("/cdo/tech-packs/{tech_pack_id}/construction", tags=["Tech Packs"])
async def add_construction_step(
    tech_pack_id: int,
    data: TechPackConstructionCreate,
    db: Session = Depends(get_db)
):
    """Add construction operation to tech pack."""
    tech_pack = db.query(TechPack).filter(TechPack.id == tech_pack_id).first()
    if not tech_pack:
        raise HTTPException(status_code=404, detail="Tech pack not found")

    construction = TechPackConstruction(
        tech_pack_id=tech_pack_id,
        operation_number=data.operation_number,
        operation_name=data.operation_name,
        description=data.description,
        machine_type=data.machine_type,
        stitch_type=data.stitch_type,
        stitches_per_inch=data.stitches_per_inch,
        thread_type=data.thread_type,
        thread_color=data.thread_color,
        seam_allowance=data.seam_allowance
    )

    db.add(construction)
    db.commit()

    return {"success": True, "construction_id": construction.id}


@app.patch("/cdo/tech-packs/{tech_pack_id}/status", tags=["Tech Packs"])
async def update_tech_pack_status(
    tech_pack_id: int,
    status: TechPackStatus,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Update tech pack status."""
    tech_pack = db.query(TechPack).filter(TechPack.id == tech_pack_id).first()
    if not tech_pack:
        raise HTTPException(status_code=404, detail="Tech pack not found")

    old_status = tech_pack.status
    tech_pack.status = status

    if status == TechPackStatus.APPROVED:
        tech_pack.approved_date = datetime.utcnow()

    db.commit()

    # Notify COO if approved for production
    if status == TechPackStatus.APPROVED and old_status != TechPackStatus.APPROVED:
        background_tasks.add_task(
            publish_tech_pack_ready,
            tech_pack.id,
            tech_pack.tech_pack_number,
            tech_pack.style_name,
            status.value
        )

    return {"success": True, "status": status.value}


# ==================== Pattern Files ====================

@app.get("/cdo/patterns", tags=["Patterns"])
async def list_patterns(
    status: Optional[PatternStatus] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List all pattern files."""
    query = db.query(PatternFile)

    if status:
        query = query.filter(PatternFile.status == status)

    total = query.count()
    patterns = query.order_by(PatternFile.updated_at.desc()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "patterns": [{
            "id": p.id,
            "file_name": p.file_name,
            "file_type": p.file_type,
            "tech_pack_id": p.tech_pack_id,
            "base_size": p.base_size,
            "sizes_included": p.sizes_included,
            "total_pieces": p.total_pieces,
            "status": p.status.value if p.status else "draft",
            "ai_generated": p.ai_generated,
            "requires_human_review": p.requires_human_review
        } for p in patterns]
    }


@app.post("/cdo/patterns", tags=["Patterns"])
async def create_pattern_file(
    data: PatternFileCreate,
    db: Session = Depends(get_db)
):
    """Create a new pattern file record."""
    tech_pack = db.query(TechPack).filter(TechPack.id == data.tech_pack_id).first()
    if not tech_pack:
        raise HTTPException(status_code=404, detail="Tech pack not found")

    pattern = PatternFile(
        tech_pack_id=data.tech_pack_id,
        file_name=data.file_name,
        file_type=data.file_type,
        base_size=data.base_size,
        sizes_included=data.sizes_included,
        status=PatternStatus.DRAFT,
        ai_generated=False,
        requires_human_review=True
    )

    db.add(pattern)
    db.commit()
    db.refresh(pattern)

    return {"success": True, "pattern_id": pattern.id}


@app.post("/cdo/patterns/{pattern_id}/pieces", tags=["Patterns"])
async def add_pattern_piece(
    pattern_id: int,
    data: PatternPieceCreate,
    db: Session = Depends(get_db)
):
    """Add a pattern piece to a pattern file."""
    pattern = db.query(PatternFile).filter(PatternFile.id == pattern_id).first()
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern file not found")

    piece = PatternPiece(
        pattern_file_id=pattern_id,
        piece_name=data.piece_name,
        piece_code=data.piece_code,
        fabric_type=data.fabric_type,
        cut_quantity=data.cut_quantity,
        grain_line=data.grain_line,
        mirror=data.mirror
    )

    db.add(piece)

    # Update piece count
    pattern.total_pieces = (pattern.total_pieces or 0) + 1

    db.commit()

    return {"success": True, "piece_id": piece.id}


@app.post("/cdo/patterns/{pattern_id}/generate-dxf", tags=["Patterns"])
async def generate_dxf_template(
    pattern_id: int,
    db: Session = Depends(get_db)
):
    """
    Generate a DXF template file for pattern pieces.

    This creates a basic DXF structure that can be edited by pattern makers.
    The actual pattern geometry would be added by humans.
    """
    pattern = db.query(PatternFile).filter(PatternFile.id == pattern_id).first()
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern file not found")

    # Get associated tech pack measurements
    tech_pack = pattern.tech_pack
    if not tech_pack:
        raise HTTPException(status_code=400, detail="Pattern has no associated tech pack")

    # Generate basic DXF structure (placeholder - would be more complex in production)
    dxf_content = generate_basic_dxf_template(pattern, tech_pack)

    # In production, this would save to S3 or similar
    # For now, return the template
    pattern.ai_generated = True
    pattern.requires_human_review = True
    pattern.review_notes = "AI-generated template - requires human pattern maker review and completion"
    db.commit()

    return {
        "success": True,
        "message": "DXF template generated - requires human review",
        "pattern_id": pattern.id,
        "dxf_preview": dxf_content[:500] + "..." if len(dxf_content) > 500 else dxf_content
    }


def generate_basic_dxf_template(pattern: PatternFile, tech_pack: TechPack) -> str:
    """Generate a basic DXF template structure."""
    # This is a simplified DXF template
    # Real implementation would use ezdxf or similar library
    dxf_lines = [
        "0", "SECTION",
        "2", "HEADER",
        "9", "$ACADVER",
        "1", "AC1015",  # AutoCAD 2000 format
        "9", "$INSUNITS",
        "70", "1",  # Inches
        "0", "ENDSEC",
        "0", "SECTION",
        "2", "ENTITIES",
    ]

    # Add placeholder for each pattern piece
    y_offset = 0
    for piece in pattern.pieces:
        # Add text label for piece
        dxf_lines.extend([
            "0", "TEXT",
            "8", "LABELS",  # Layer
            "10", "0",  # X
            "20", str(y_offset),  # Y
            "30", "0",  # Z
            "40", "0.5",  # Text height
            "1", f"{piece.piece_name} ({piece.piece_code or 'N/A'})",
        ])

        # Add placeholder rectangle (to be replaced with actual pattern)
        dxf_lines.extend([
            "0", "LINE",
            "8", "PATTERN",
            "10", "0", "20", str(y_offset + 1), "30", "0",
            "11", "20", "21", str(y_offset + 1), "31", "0",
            "0", "LINE",
            "8", "PATTERN",
            "10", "20", "20", str(y_offset + 1), "30", "0",
            "11", "20", "21", str(y_offset + 15), "31", "0",
            "0", "LINE",
            "8", "PATTERN",
            "10", "20", "20", str(y_offset + 15), "30", "0",
            "11", "0", "21", str(y_offset + 15), "31", "0",
            "0", "LINE",
            "8", "PATTERN",
            "10", "0", "20", str(y_offset + 15), "30", "0",
            "11", "0", "21", str(y_offset + 1), "31", "0",
        ])

        y_offset += 20

    dxf_lines.extend([
        "0", "ENDSEC",
        "0", "EOF"
    ])

    return "\n".join(dxf_lines)


# ==================== Product Development ====================

@app.get("/cdo/product-ideas", tags=["Product Development"])
async def list_product_ideas(
    status: Optional[ProductIdeaStatus] = None,
    category: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List product ideas."""
    query = db.query(ProductIdea)

    if status:
        query = query.filter(ProductIdea.status == status)
    if category:
        query = query.filter(ProductIdea.category == category)

    total = query.count()
    ideas = query.order_by(ProductIdea.priority_score.desc().nullslast()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "ideas": [{
            "id": i.id,
            "idea_number": i.idea_number,
            "title": i.title,
            "category": i.category,
            "source": i.source,
            "priority_score": i.priority_score,
            "estimated_revenue": i.estimated_annual_revenue,
            "status": i.status.value if i.status else "concept"
        } for i in ideas]
    }


@app.post("/cdo/product-ideas", tags=["Product Development"])
async def create_product_idea(
    data: ProductIdeaCreate,
    db: Session = Depends(get_db)
):
    """Create a new product idea."""
    count = db.query(func.count(ProductIdea.id)).scalar() or 0
    idea_number = f"IDEA-{datetime.now().strftime('%Y%m')}-{count + 1:04d}"

    # Calculate estimated revenue
    estimated_revenue = None
    if data.estimated_retail and data.estimated_annual_units:
        estimated_revenue = data.estimated_retail * data.estimated_annual_units

    # Calculate margin
    estimated_margin = None
    if data.estimated_cost and data.estimated_retail and data.estimated_retail > 0:
        estimated_margin = ((data.estimated_retail - data.estimated_cost) / data.estimated_retail) * 100

    idea = ProductIdea(
        idea_number=idea_number,
        title=data.title,
        description=data.description,
        category=data.category,
        source=data.source,
        target_market=data.target_market,
        estimated_cost=data.estimated_cost,
        estimated_retail=data.estimated_retail,
        estimated_margin=estimated_margin,
        estimated_annual_units=data.estimated_annual_units,
        estimated_annual_revenue=estimated_revenue,
        status=ProductIdeaStatus.CONCEPT
    )

    db.add(idea)
    db.commit()
    db.refresh(idea)

    return {"success": True, "idea_id": idea.id, "idea_number": idea_number}


@app.post("/cdo/product-ideas/{idea_id}/submit-for-approval", tags=["Product Development"])
async def submit_idea_for_approval(
    idea_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Submit product idea to CEO for approval."""
    idea = db.query(ProductIdea).filter(ProductIdea.id == idea_id).first()
    if not idea:
        raise HTTPException(status_code=404, detail="Product idea not found")

    idea.status = ProductIdeaStatus.RESEARCH
    db.commit()

    # Send to CEO
    background_tasks.add_task(
        publish_product_recommendation,
        idea.id,
        idea.title,
        idea.category,
        idea.estimated_annual_revenue or 0,
        idea.priority_score or 50,
        idea.description or "New product development opportunity"
    )

    return {"success": True, "message": "Submitted for CEO approval"}


# ==================== Trends & Analytics ====================

@app.get("/cdo/trends", tags=["Trends"])
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


@app.get("/cdo/analytics/sales", tags=["Analytics"])
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


@app.get("/cdo/analytics/products", tags=["Analytics"])
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


# ==================== Reports ====================

@app.get("/cdo/reports", tags=["Reports"])
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


@app.post("/cdo/reports/generate", tags=["Reports"])
async def generate_report(
    data: ReportRequest,
    db: Session = Depends(get_db)
):
    """Generate a new report."""
    count = db.query(func.count(Report.id)).scalar() or 0
    report_number = f"RPT-{datetime.now().strftime('%Y%m%d')}-{count + 1:04d}"

    # Default date range
    period_end = data.period_end or datetime.utcnow()
    period_start = data.period_start or (period_end - timedelta(days=30))

    # Generate report data based on type
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


# ==================== Shopify OAuth ====================

@app.get("/cdo/auth/shopify", tags=["Auth"])
async def shopify_auth_redirect():
    """Initiate Shopify OAuth flow."""
    if not settings.shopify_client_id:
        raise HTTPException(status_code=400, detail="Shopify credentials not configured")

    state = secrets.token_urlsafe(32)
    scopes = "read_products,read_orders,read_customers,read_inventory"

    auth_url = (
        f"https://{settings.shopify_store}/admin/oauth/authorize"
        f"?client_id={settings.shopify_client_id}"
        f"&scope={scopes}"
        f"&redirect_uri={settings.cdo_api_url or 'http://localhost:8000'}/cdo/auth/shopify/callback"
        f"&state={state}"
    )

    return {"auth_url": auth_url, "state": state}


@app.get("/cdo/auth/shopify/callback", tags=["Auth"])
async def shopify_callback(
    code: str,
    state: str,
    shop: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Handle Shopify OAuth callback."""
    if not settings.shopify_client_id or not settings.shopify_client_secret:
        raise HTTPException(status_code=400, detail="Shopify credentials not configured")

    # Exchange code for token
    token_url = f"https://{settings.shopify_store}/admin/oauth/access_token"

    async with httpx.AsyncClient() as client:
        response = await client.post(token_url, json={
            "client_id": settings.shopify_client_id,
            "client_secret": settings.shopify_client_secret,
            "code": code
        })

        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to exchange code for token")

        data = response.json()
        access_token = data.get("access_token")
        scope = data.get("scope")

    # Store token
    auth = db.query(ShopifyAuth).filter(ShopifyAuth.store == settings.shopify_store).first()
    if auth:
        auth.access_token = access_token
        auth.scope = scope
        auth.updated_at = datetime.utcnow()
    else:
        auth = ShopifyAuth(
            store=settings.shopify_store,
            access_token=access_token,
            scope=scope
        )
        db.add(auth)

    db.commit()

    return {"success": True, "message": "Shopify connected successfully", "scope": scope}


# ==================== Data Sync ====================

@app.post("/cdo/sync/orders", tags=["Sync"])
async def sync_shopify_orders(
    days: int = 30,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """Sync orders from Shopify for analytics."""
    auth = db.query(ShopifyAuth).filter(ShopifyAuth.store == settings.shopify_store).first()
    if not auth:
        raise HTTPException(status_code=400, detail="Shopify not connected")

    # Would sync orders and update SalesSnapshot, ProductPerformance, CustomerAnalytics
    # This is a placeholder for the actual implementation
    return {
        "success": True,
        "message": f"Order sync initiated for last {days} days",
        "note": "Full implementation would sync from Shopify GraphQL API"
    }


# ==================== Events ====================

@app.post("/cdo/events/webhook", tags=["Events"])
async def receive_event(event: dict, db: Session = Depends(get_db)):
    """Receive events from other modules."""
    event_bus.handle_incoming_event(event)
    return {"success": True, "event_id": event.get("event_id")}


@app.post("/cdo/events/test-demand-forecast", tags=["Events"])
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


# ==================== Alerts ====================

@app.get("/cdo/alerts", tags=["Alerts"])
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


# ==================== Root ====================

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "module": "CDO",
        "name": "Dearborn AI CDO",
        "version": "1.0.0",
        "status": "operational",
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
