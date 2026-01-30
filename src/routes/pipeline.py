"""Pipeline, concept, and validation endpoints."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db import (
    get_db, ProductConcept, ValidationRequest,
    ConceptStatus, ValidationStatus, PipelinePhase
)
from ..cdo.concept import ConceptDesigner
from ..cdo.validation import ValidationOrchestrator
from ..cdo.techpack_gen import TechPackGenerator
from ..cdo.pattern_gen import DraftPatternGenerator
from ..cdo.pipeline import PipelineEngine
from ..cdo.onedrive import onedrive

router = APIRouter()


# ==================== Concepts ====================

@router.get("/cdo/concepts", tags=["Concepts"])
async def list_concepts(
    status: Optional[ConceptStatus] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List product concepts."""
    query = db.query(ProductConcept)
    if status:
        query = query.filter(ProductConcept.status == status)

    concepts = query.order_by(ProductConcept.updated_at.desc()).limit(limit).all()

    return {
        "total": len(concepts),
        "concepts": [{
            "id": c.id,
            "concept_number": c.concept_number,
            "title": c.title,
            "category": c.category,
            "status": c.status.value if c.status else None,
            "target_retail": c.target_retail,
            "target_cost": c.target_cost,
            "target_margin": c.target_margin,
            "cfo_validation": c.cfo_validation.value if c.cfo_validation else None,
            "coo_validation": c.coo_validation.value if c.coo_validation else None,
            "ceo_approval": c.ceo_approval.value if c.ceo_approval else None,
            "sketch_url": c.sketch_url,
            "sketch_share_link": c.sketch_share_link,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        } for c in concepts]
    }


@router.get("/cdo/concepts/{concept_id}", tags=["Concepts"])
async def get_concept(concept_id: int, db: Session = Depends(get_db)):
    """Get concept details."""
    concept = db.query(ProductConcept).filter(
        ProductConcept.id == concept_id
    ).first()
    if not concept:
        raise HTTPException(status_code=404, detail="Concept not found")

    return {
        "id": concept.id,
        "concept_number": concept.concept_number,
        "title": concept.title,
        "category": concept.category,
        "brief": concept.brief,
        "target_customer": concept.target_customer,
        "key_features": concept.key_features,
        "differentiators": concept.differentiators,
        "inspiration_references": concept.inspiration_references,
        "sketch_url": concept.sketch_url,
        "sketch_share_link": concept.sketch_share_link,
        "target_retail": concept.target_retail,
        "target_cost": concept.target_cost,
        "target_margin": concept.target_margin,
        "pricing_rationale": concept.pricing_rationale,
        "cfo_validation": concept.cfo_validation.value if concept.cfo_validation else None,
        "coo_validation": concept.coo_validation.value if concept.coo_validation else None,
        "ceo_approval": concept.ceo_approval.value if concept.ceo_approval else None,
        "ceo_decision_notes": concept.ceo_decision_notes,
        "status": concept.status.value if concept.status else None,
        "tech_pack_id": concept.tech_pack_id,
        "created_at": concept.created_at.isoformat() if concept.created_at else None,
        "updated_at": concept.updated_at.isoformat() if concept.updated_at else None,
    }


@router.post("/cdo/concepts/{concept_id}/generate-brief", tags=["Concepts"])
async def generate_concept_brief(concept_id: int, db: Session = Depends(get_db)):
    """Generate AI concept brief using GPT."""
    designer = ConceptDesigner(db)
    result = designer.generate_brief(concept_id)
    if not result:
        raise HTTPException(status_code=404, detail="Concept not found")
    return result


@router.post("/cdo/concepts/{concept_id}/generate-sketch", tags=["Concepts"])
async def generate_concept_sketch(concept_id: int, db: Session = Depends(get_db)):
    """Generate AI product sketch using DALL-E."""
    designer = ConceptDesigner(db)
    result = designer.generate_sketch(concept_id)
    if not result:
        raise HTTPException(status_code=404, detail="Concept not found")

    # Upload sketch to OneDrive if URL was generated
    if result.get("sketch_url") and onedrive.is_configured:
        try:
            import httpx
            # Download the DALL-E image
            async with httpx.AsyncClient() as client:
                img_response = await client.get(result["sketch_url"], timeout=30.0)
                if img_response.status_code == 200:
                    concept = db.query(ProductConcept).filter(
                        ProductConcept.id == concept_id
                    ).first()
                    filename = f"{concept.concept_number}_sketch.png"
                    upload = onedrive.upload_file("sketches", filename, img_response.content)
                    if upload:
                        concept.sketch_onedrive_id = upload["file_id"]
                        concept.sketch_share_link = upload.get("share_link")
                        db.commit()
                        result["onedrive"] = upload
        except Exception as e:
            result["onedrive_error"] = str(e)

    return result


@router.post("/cdo/concepts/{concept_id}/validate", tags=["Concepts"])
async def validate_concept(concept_id: int, db: Session = Depends(get_db)):
    """Send concept to CFO (margin check) and COO (capacity check)."""
    orchestrator = ValidationOrchestrator(db)
    result = orchestrator.request_validation(concept_id)
    return result


@router.post("/cdo/concepts/{concept_id}/submit-for-approval", tags=["Concepts"])
async def submit_for_ceo_approval(concept_id: int, db: Session = Depends(get_db)):
    """Submit validated concept to CEO for approval."""
    concept = db.query(ProductConcept).filter(
        ProductConcept.id == concept_id
    ).first()
    if not concept:
        raise HTTPException(status_code=404, detail="Concept not found")

    if concept.status != ConceptStatus.VALIDATED:
        raise HTTPException(
            status_code=400,
            detail=f"Concept must be validated before CEO approval (current: {concept.status.value})"
        )

    concept.status = ConceptStatus.SUBMITTED_FOR_APPROVAL
    concept.ceo_approval = ValidationStatus.SENT

    # Send to CEO via event bus
    from ..event_bus import event_bus, CDOOutboundEvent
    event_bus.publish(
        CDOOutboundEvent.PRODUCT_RECOMMENDATION,
        {
            "concept_id": concept.id,
            "concept_number": concept.concept_number,
            "title": concept.title,
            "category": concept.category,
            "brief": concept.brief,
            "target_retail": concept.target_retail,
            "target_cost": concept.target_cost,
            "target_margin": concept.target_margin,
            "sketch_url": concept.sketch_url,
            "sketch_share_link": concept.sketch_share_link,
            "risk_level": "medium",
            "title": f"Product Approval: {concept.title}",
            "message": f"Concept {concept.concept_number} is ready for CEO approval",
        },
        target_module="ceo"
    )

    db.commit()

    return {"success": True, "message": "Submitted for CEO approval"}


# ==================== Validations ====================

@router.get("/cdo/validations", tags=["Validations"])
async def list_validations(
    status: Optional[ValidationStatus] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List validation request status."""
    query = db.query(ValidationRequest)
    if status:
        query = query.filter(ValidationRequest.status == status)

    validations = query.order_by(ValidationRequest.created_at.desc()).limit(limit).all()

    return {
        "validations": [{
            "id": v.id,
            "concept_id": v.concept_id,
            "validation_type": v.validation_type,
            "target_module": v.target_module,
            "status": v.status.value if v.status else None,
            "sent_at": v.sent_at.isoformat() if v.sent_at else None,
            "responded_at": v.responded_at.isoformat() if v.responded_at else None,
            "timeout_at": v.timeout_at.isoformat() if v.timeout_at else None,
            "result_summary": v.result_summary,
        } for v in validations]
    }


# ==================== Tech Pack Generation ====================

@router.post("/cdo/tech-packs/{concept_id}/generate-full", tags=["Tech Packs"])
async def generate_full_tech_pack(concept_id: int, db: Session = Depends(get_db)):
    """Generate a complete tech pack from a concept (measurements, BOM, construction)."""
    generator = TechPackGenerator(db)
    result = generator.generate_from_concept(concept_id)
    if not result:
        raise HTTPException(status_code=404, detail="Concept not found")
    return result


# ==================== Pattern Generation ====================

@router.post("/cdo/patterns/{tech_pack_id}/generate-full", tags=["Patterns"])
async def generate_full_pattern(
    tech_pack_id: int,
    block_name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Generate DXF pattern from tech pack using pattern blocks."""
    generator = DraftPatternGenerator(db)
    result = generator.generate_pattern(tech_pack_id, block_name=block_name)
    if not result:
        raise HTTPException(status_code=404, detail="Tech pack not found")

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    # Upload DXF to OneDrive
    dxf_bytes = result.pop("dxf_bytes", None)
    if dxf_bytes and onedrive.is_configured:
        try:
            upload = onedrive.upload_file("patterns", result["file_name"], dxf_bytes)
            if upload:
                result["onedrive"] = upload
                # Update pipeline with share link
                from ..db import ProductPipeline
                pipeline = db.query(ProductPipeline).filter(
                    ProductPipeline.tech_pack_id == tech_pack_id
                ).first()
                if pipeline:
                    pipeline.pattern_onedrive_id = upload["file_id"]
                    pipeline.pattern_share_link = upload.get("share_link")
                    db.commit()
        except Exception as e:
            result["onedrive_error"] = str(e)

    return result


@router.get("/cdo/patterns/{pattern_id}/download-dxf", tags=["Patterns"])
async def download_pattern_dxf(pattern_id: int, db: Session = Depends(get_db)):
    """Download the DXF file for a pattern.

    Regenerates the DXF from block data. For production use,
    retrieve from OneDrive instead.
    """
    from ..db import PatternFile
    pattern = db.query(PatternFile).filter(PatternFile.id == pattern_id).first()
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")

    # Regenerate DXF
    generator = DraftPatternGenerator(db)
    result = generator.generate_pattern(pattern.tech_pack_id)
    if not result or "error" in result:
        raise HTTPException(status_code=500, detail="Failed to generate DXF")

    dxf_bytes = result.get("dxf_bytes", b"")
    return Response(
        content=dxf_bytes,
        media_type="application/dxf",
        headers={"Content-Disposition": f'attachment; filename="{pattern.file_name}"'},
    )


# ==================== Pipeline ====================

@router.get("/cdo/pipeline", tags=["Pipeline"])
async def list_pipeline(
    phase: Optional[PipelinePhase] = None,
    db: Session = Depends(get_db)
):
    """Get full pipeline view."""
    engine = PipelineEngine(db)
    pipelines = engine.list_pipeline(phase)
    return {"total": len(pipelines), "pipeline": pipelines}


@router.get("/cdo/pipeline/{pipeline_id}", tags=["Pipeline"])
async def get_pipeline(pipeline_id: int, db: Session = Depends(get_db)):
    """Get product lifecycle details."""
    engine = PipelineEngine(db)
    result = engine.get_pipeline(pipeline_id)
    if not result:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return result


@router.post("/cdo/pipeline/{pipeline_id}/advance", tags=["Pipeline"])
async def advance_pipeline(
    pipeline_id: int,
    notes: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Advance pipeline to the next phase."""
    engine = PipelineEngine(db)
    result = engine.advance_phase(pipeline_id, notes)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
