"""Tech Pack CRUD endpoints."""
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from ..db import (
    get_db, TechPack, TechPackMeasurement, TechPackMaterial,
    TechPackConstruction, TechPackStatus
)
from ..event_bus import publish_tech_pack_ready

router = APIRouter()


# Pydantic Models

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


# Endpoints

@router.get("/cdo/tech-packs", tags=["Tech Packs"])
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


@router.post("/cdo/tech-packs", tags=["Tech Packs"])
async def create_tech_pack(
    data: TechPackCreate,
    db: Session = Depends(get_db)
):
    """Create a new tech pack."""
    count = db.query(func.count(TechPack.id)).scalar() or 0
    tech_pack_number = f"TP-{datetime.now().strftime('%Y%m')}-{count + 1:04d}"

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


@router.get("/cdo/tech-packs/{tech_pack_id}", tags=["Tech Packs"])
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


@router.post("/cdo/tech-packs/{tech_pack_id}/measurements", tags=["Tech Packs"])
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


@router.post("/cdo/tech-packs/{tech_pack_id}/materials", tags=["Tech Packs"])
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


@router.post("/cdo/tech-packs/{tech_pack_id}/construction", tags=["Tech Packs"])
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


@router.patch("/cdo/tech-packs/{tech_pack_id}/status", tags=["Tech Packs"])
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

    if status == TechPackStatus.APPROVED and old_status != TechPackStatus.APPROVED:
        background_tasks.add_task(
            publish_tech_pack_ready,
            tech_pack.id,
            tech_pack.tech_pack_number,
            tech_pack.style_name,
            status.value
        )

    return {"success": True, "status": status.value}


@router.get("/cdo/tech-packs/{tech_pack_id}/pdf", tags=["Tech Packs"])
async def get_tech_pack_pdf(tech_pack_id: int, db: Session = Depends(get_db)):
    """Generate and download a tech pack as PDF."""
    from ..cdo.pdf_gen import generate_tech_pack_pdf

    tech_pack = db.query(TechPack).filter(TechPack.id == tech_pack_id).first()
    if not tech_pack:
        raise HTTPException(status_code=404, detail="Tech pack not found")

    pdf_bytes = generate_tech_pack_pdf(db, tech_pack_id)
    if not pdf_bytes:
        raise HTTPException(status_code=500, detail="Failed to generate PDF")

    filename = f"{tech_pack.tech_pack_number}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
