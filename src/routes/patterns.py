"""Pattern file endpoints."""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..db import get_db, PatternFile, PatternPiece, TechPack, PatternStatus

router = APIRouter()


# Pydantic Models

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


# Endpoints

@router.get("/cdo/patterns", tags=["Patterns"])
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


@router.post("/cdo/patterns", tags=["Patterns"])
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


@router.post("/cdo/patterns/{pattern_id}/pieces", tags=["Patterns"])
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
    pattern.total_pieces = (pattern.total_pieces or 0) + 1
    db.commit()

    return {"success": True, "piece_id": piece.id}


@router.post("/cdo/patterns/{pattern_id}/generate-dxf", tags=["Patterns"])
async def generate_dxf_template(
    pattern_id: int,
    db: Session = Depends(get_db)
):
    """Generate a DXF template file for pattern pieces.

    Creates a basic DXF structure that can be edited by pattern makers.
    """
    pattern = db.query(PatternFile).filter(PatternFile.id == pattern_id).first()
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern file not found")

    tech_pack = pattern.tech_pack
    if not tech_pack:
        raise HTTPException(status_code=400, detail="Pattern has no associated tech pack")

    dxf_content = _generate_basic_dxf_template(pattern, tech_pack)

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


def _generate_basic_dxf_template(pattern: PatternFile, tech_pack: TechPack) -> str:
    """Generate a basic DXF template structure."""
    dxf_lines = [
        "0", "SECTION",
        "2", "HEADER",
        "9", "$ACADVER",
        "1", "AC1015",
        "9", "$INSUNITS",
        "70", "1",
        "0", "ENDSEC",
        "0", "SECTION",
        "2", "ENTITIES",
    ]

    y_offset = 0
    for piece in pattern.pieces:
        dxf_lines.extend([
            "0", "TEXT",
            "8", "LABELS",
            "10", "0",
            "20", str(y_offset),
            "30", "0",
            "40", "0.5",
            "1", f"{piece.piece_name} ({piece.piece_code or 'N/A'})",
        ])

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
