"""
Draft Pattern Generator

Generates DXF pattern files using the ezdxf library.
Uses base blocks from blocks.py, applies grading, and exports
AccuMark-compatible DXF files (R2010 format).
"""
import io
import logging
from datetime import datetime
from typing import Optional, Dict, List

from sqlalchemy.orm import Session
from sqlalchemy import func

from ..db import (
    PatternFile, PatternPiece, TechPack, ProductPipeline,
    PatternStatus, PipelinePhase
)
from .blocks import get_block, PATTERN_BLOCKS
from .grading import get_grading_rules, grade_measurement

logger = logging.getLogger(__name__)


class DraftPatternGenerator:
    """Generates DXF pattern files from block library."""

    def __init__(self, db: Session):
        self.db = db

    def generate_pattern(
        self,
        tech_pack_id: int,
        block_name: str = None,
        sizes: List[str] = None,
    ) -> Optional[Dict]:
        """Generate a DXF pattern file from a tech pack and block.

        Args:
            tech_pack_id: Tech pack to generate pattern for
            block_name: Pattern block to use (auto-detected from category if None)
            sizes: List of sizes to include (uses all if None)

        Returns:
            Dict with pattern info including DXF bytes
        """
        tech_pack = self.db.query(TechPack).filter(TechPack.id == tech_pack_id).first()
        if not tech_pack:
            return None

        # Auto-detect block from category
        if not block_name:
            category = (tech_pack.category or "jeans").lower().replace(" ", "_").replace("-", "_")
            from .competency import PRODUCT_CATEGORIES
            cat_info = PRODUCT_CATEGORIES.get(category, {})
            block_name = cat_info.get("base_pattern", "jean_5pocket")

        block = get_block(block_name)
        if not block or "pieces" not in block:
            return {"error": f"Block '{block_name}' not found or has no pieces"}

        # Get grading rules
        category = (tech_pack.category or "jeans").lower().replace(" ", "_").replace("-", "_")
        grading = get_grading_rules(category)

        if sizes is None:
            sizes = grading["size_range"]

        # Generate DXF
        try:
            dxf_bytes = self._create_dxf(block, grading, sizes, tech_pack)
        except Exception as e:
            logger.error(f"DXF generation failed: {e}")
            return {"error": f"DXF generation failed: {str(e)}"}

        # Create pattern file record
        file_name = f"{tech_pack.style_name.replace(' ', '_')}_{block_name}_{datetime.now().strftime('%Y%m%d')}.dxf"

        pattern = PatternFile(
            tech_pack_id=tech_pack_id,
            file_name=file_name,
            file_type="dxf",
            base_size=block.get("base_size", "32"),
            sizes_included=sizes,
            total_pieces=len(block["pieces"]),
            status=PatternStatus.DRAFT,
            ai_generated=True,
            requires_human_review=True,
            review_notes="AI-generated draft pattern - requires human review in AccuMark before production use",
        )
        self.db.add(pattern)
        self.db.flush()

        # Add piece records
        for piece_name, piece_data in block["pieces"].items():
            piece = PatternPiece(
                pattern_file_id=pattern.id,
                piece_name=piece_name,
                piece_code=piece_data.get("code"),
                fabric_type=piece_data.get("fabric", "shell"),
                cut_quantity=piece_data.get("cut_qty", 1),
                grain_line=piece_data.get("grain", "straight"),
                mirror=piece_data.get("mirror", False),
            )
            self.db.add(piece)

        self.db.commit()

        return {
            "pattern_id": pattern.id,
            "file_name": file_name,
            "block_used": block_name,
            "base_size": block.get("base_size"),
            "sizes": sizes,
            "pieces": len(block["pieces"]),
            "dxf_bytes": dxf_bytes,
            "dxf_size_bytes": len(dxf_bytes),
            "requires_review": True,
        }

    def _create_dxf(self, block: dict, grading: dict, sizes: list, tech_pack: TechPack) -> bytes:
        """Create a DXF file using ezdxf library."""
        import ezdxf

        doc = ezdxf.new("R2010")
        msp = doc.modelspace()

        # Create layers
        doc.layers.add("PATTERN", color=7)  # white
        doc.layers.add("GRAIN_LINE", color=3)  # green
        doc.layers.add("NOTCHES", color=1)  # red
        doc.layers.add("SEAM_ALLOWANCE", color=5)  # blue
        doc.layers.add("LABELS", color=2)  # yellow
        doc.layers.add("INTERNAL", color=4)  # cyan

        # Layout pieces with spacing
        x_offset = 0
        base_size = block.get("base_size", grading.get("base_size", "32"))

        for piece_name, piece_data in block["pieces"].items():
            points = piece_data.get("points", [])
            if not points:
                continue

            # Draw base size pattern piece
            shifted_points = [(p[0] + x_offset, p[1]) for p in points]

            # Draw outline as LWPOLYLINE (closed)
            if len(shifted_points) >= 3:
                msp.add_lwpolyline(
                    shifted_points,
                    close=True,
                    dxfattribs={"layer": "PATTERN"}
                )

            # Draw grain line
            grain = piece_data.get("grain_line", [])
            if len(grain) >= 2:
                msp.add_line(
                    (grain[0][0] + x_offset, grain[0][1]),
                    (grain[1][0] + x_offset, grain[1][1]),
                    dxfattribs={"layer": "GRAIN_LINE"}
                )
                # Arrow at top of grain line
                arrow_x = grain[1][0] + x_offset
                arrow_y = grain[1][1]
                msp.add_line(
                    (arrow_x, arrow_y),
                    (arrow_x - 0.25, arrow_y - 0.5),
                    dxfattribs={"layer": "GRAIN_LINE"}
                )
                msp.add_line(
                    (arrow_x, arrow_y),
                    (arrow_x + 0.25, arrow_y - 0.5),
                    dxfattribs={"layer": "GRAIN_LINE"}
                )

            # Draw notches
            for notch in piece_data.get("notches", []):
                nx, ny = notch[0] + x_offset, notch[1]
                msp.add_line(
                    (nx - 0.125, ny - 0.25),
                    (nx + 0.125, ny + 0.25),
                    dxfattribs={"layer": "NOTCHES"}
                )

            # Add piece label
            label_x = x_offset + 2
            label_y = min(p[1] for p in points) - 1.5
            code = piece_data.get("code", "")
            cut_qty = piece_data.get("cut_qty", 1)
            mirror = "MIRROR" if piece_data.get("mirror") else ""

            msp.add_text(
                f"{piece_name.upper()} ({code})",
                height=0.4,
                dxfattribs={"layer": "LABELS"}
            ).set_placement((label_x, label_y))

            msp.add_text(
                f"Cut {cut_qty} {mirror}".strip(),
                height=0.3,
                dxfattribs={"layer": "LABELS"}
            ).set_placement((label_x, label_y - 0.6))

            msp.add_text(
                f"Size: {base_size}",
                height=0.3,
                dxfattribs={"layer": "LABELS"}
            ).set_placement((label_x, label_y - 1.2))

            # Move x_offset for next piece
            max_x = max(p[0] for p in points) if points else 15
            x_offset += max_x + 5

        # Add title block
        msp.add_text(
            f"DEARBORN DENIM - {tech_pack.style_name}",
            height=0.6,
            dxfattribs={"layer": "LABELS"}
        ).set_placement((0, min(p[1] for piece in block["pieces"].values() for p in piece.get("points", [(0, 0)])) - 5))

        msp.add_text(
            f"TP: {tech_pack.tech_pack_number} | Base: {base_size} | AI DRAFT - REVIEW REQUIRED",
            height=0.35,
            dxfattribs={"layer": "LABELS"}
        ).set_placement((0, min(p[1] for piece in block["pieces"].values() for p in piece.get("points", [(0, 0)])) - 6))

        # Write to bytes
        stream = io.BytesIO()
        doc.write(stream)
        return stream.getvalue()
