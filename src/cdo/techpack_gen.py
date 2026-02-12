"""
Tech Pack Generator

Generates complete tech packs from product concepts including
measurements, BOM, and construction operations.
"""
import logging
from datetime import datetime
from typing import Optional, Dict

from sqlalchemy.orm import Session
from sqlalchemy import func

from ..db import (
    TechPack, TechPackMeasurement, TechPackMaterial, TechPackConstruction,
    ProductConcept, ProductPipeline, TechPackStatus, PipelinePhase
)
from .competency import get_category_info
from .grading import get_grading_rules, generate_size_spec

logger = logging.getLogger(__name__)

# Standard BOM templates by category
BOM_TEMPLATES = {
    "jeans": [
        {"type": "fabric", "name": "Shell Denim", "placement": "Body", "qty": 1.75, "unit": "yards", "cost": 8.50},
        {"type": "fabric", "name": "Pocket Lining", "placement": "Pockets", "qty": 0.5, "unit": "yards", "cost": 2.00},
        {"type": "trim", "name": "Zipper - YKK Brass", "placement": "Fly", "qty": 1, "unit": "each", "cost": 0.85},
        {"type": "trim", "name": "Button - Metal Shank", "placement": "Waistband", "qty": 1, "unit": "each", "cost": 0.25},
        {"type": "trim", "name": "Rivets - Copper", "placement": "Pocket Corners", "qty": 6, "unit": "each", "cost": 0.10},
        {"type": "trim", "name": "Back Patch - Leather", "placement": "Waistband Back", "qty": 1, "unit": "each", "cost": 0.50},
        {"type": "label", "name": "Main Label - Woven", "placement": "Waistband Interior", "qty": 1, "unit": "each", "cost": 0.15},
        {"type": "label", "name": "Size Label", "placement": "Waistband Interior", "qty": 1, "unit": "each", "cost": 0.08},
        {"type": "label", "name": "Care Label", "placement": "Side Seam", "qty": 1, "unit": "each", "cost": 0.05},
        {"type": "thread", "name": "Top Stitch Thread", "placement": "Exterior", "qty": 150, "unit": "yards", "cost": 0.30},
        {"type": "thread", "name": "Seam Thread", "placement": "Interior", "qty": 200, "unit": "yards", "cost": 0.20},
        {"type": "interlining", "name": "Waistband Interfacing", "placement": "Waistband", "qty": 0.15, "unit": "yards", "cost": 0.40},
    ],
    "shirts": [
        {"type": "fabric", "name": "Shell Fabric", "placement": "Body", "qty": 2.25, "unit": "yards", "cost": 6.00},
        {"type": "trim", "name": "Buttons", "placement": "Front Placket", "qty": 7, "unit": "each", "cost": 0.12},
        {"type": "interlining", "name": "Collar Interfacing", "placement": "Collar", "qty": 0.1, "unit": "yards", "cost": 0.30},
        {"type": "interlining", "name": "Cuff Interfacing", "placement": "Cuffs", "qty": 0.1, "unit": "yards", "cost": 0.30},
        {"type": "label", "name": "Main Label", "placement": "Collar", "qty": 1, "unit": "each", "cost": 0.15},
        {"type": "label", "name": "Size/Care Label", "placement": "Side Seam", "qty": 1, "unit": "each", "cost": 0.08},
        {"type": "thread", "name": "Matching Thread", "placement": "All Seams", "qty": 200, "unit": "yards", "cost": 0.25},
    ],
    "denim_jackets": [
        {"type": "fabric", "name": "Shell Denim", "placement": "Body", "qty": 2.5, "unit": "yards", "cost": 9.00},
        {"type": "fabric", "name": "Lining", "placement": "Body Interior", "qty": 2.0, "unit": "yards", "cost": 3.50},
        {"type": "trim", "name": "Buttons - Metal", "placement": "Front/Cuffs", "qty": 8, "unit": "each", "cost": 0.30},
        {"type": "trim", "name": "Snaps", "placement": "Pocket Flaps", "qty": 4, "unit": "each", "cost": 0.20},
        {"type": "label", "name": "Main Label", "placement": "Collar", "qty": 1, "unit": "each", "cost": 0.15},
        {"type": "label", "name": "Size/Care Label", "placement": "Side Seam", "qty": 1, "unit": "each", "cost": 0.08},
        {"type": "thread", "name": "Top Stitch Thread", "placement": "Exterior", "qty": 200, "unit": "yards", "cost": 0.35},
        {"type": "thread", "name": "Seam Thread", "placement": "Interior", "qty": 250, "unit": "yards", "cost": 0.25},
    ],
}

# Standard construction operations by category
CONSTRUCTION_TEMPLATES = {
    "jeans": [
        (1, "Cut Pieces", "Cut all pattern pieces from shell and lining", "Auto Cutter", None, 3),
        (2, "Fuse Waistband", "Apply interfacing to waistband", "Fusing Press", None, 1),
        (3, "Sew Front Pockets", "Attach pocket bags to front panels", "Single Needle", "301", 4),
        (4, "Sew Coin Pocket", "Attach coin pocket to right front", "Single Needle", "301", 2),
        (5, "Sew Fly", "Construct fly with zipper", "Single Needle", "301", 5),
        (6, "Join Front Rise", "Sew front panels together at fly", "Single Needle", "301", 2),
        (7, "Sew Back Yoke", "Join back yoke to back panels", "Single Needle", "301", 3),
        (8, "Sew Back Pockets", "Topstitch back pockets to panels", "Single Needle", "301", 4),
        (9, "Join Back Rise", "Sew back panels together", "Single Needle", "301", 2),
        (10, "Sew Inseams", "Join front to back at inseams", "Serger", "504", 3),
        (11, "Sew Outseams", "Join front to back at outseams", "Flat Feller", "401", 3),
        (12, "Attach Waistband", "Sew waistband to body", "Single Needle", "301", 3),
        (13, "Buttonhole", "Create waistband buttonhole", "Buttonhole Machine", None, 1),
        (14, "Set Rivets", "Set pocket rivets", "Rivet Machine", None, 2),
        (15, "Hem", "Hem leg openings", "Chain Stitch", "401", 2),
        (16, "Bartack", "Bartack stress points", "Bartack Machine", None, 2),
        (17, "Press", "Final press", "Steam Press", None, 3),
        (18, "QC Inspect", "Quality control inspection", None, None, 3),
        (19, "Label & Tag", "Attach labels and hang tags", None, None, 2),
    ],
    "shirts": [
        (1, "Cut Pieces", "Cut all pattern pieces", "Auto Cutter", None, 3),
        (2, "Fuse Collar/Cuffs", "Apply interfacing", "Fusing Press", None, 2),
        (3, "Sew Collar", "Construct collar assembly", "Single Needle", "301", 4),
        (4, "Sew Yoke", "Attach front/back yoke", "Single Needle", "301", 3),
        (5, "Sew Shoulder Seams", "Join front to back", "Serger", "504", 2),
        (6, "Set Sleeves", "Attach sleeves to body", "Serger", "504", 3),
        (7, "Sew Side Seams", "Close side seams", "Serger", "504", 2),
        (8, "Attach Collar", "Set collar to neckline", "Single Needle", "301", 3),
        (9, "Sew Placket", "Construct front placket", "Single Needle", "301", 4),
        (10, "Buttonholes", "Create buttonholes", "Buttonhole Machine", None, 3),
        (11, "Sew Cuffs", "Construct and attach cuffs", "Single Needle", "301", 4),
        (12, "Hem", "Hem shirt bottom", "Coverstitch", "406", 2),
        (13, "Press", "Final press", "Steam Press", None, 3),
        (14, "QC Inspect", "Quality control", None, None, 2),
    ],
    "denim_jackets": [
        (1, "Cut Pieces", "Cut shell and lining", "Auto Cutter", None, 4),
        (2, "Fuse", "Apply interfacing to collar/facing", "Fusing Press", None, 2),
        (3, "Sew Front Panels", "Construct front panels with pockets", "Single Needle", "301", 5),
        (4, "Sew Back Panel", "Construct back with yoke", "Single Needle", "301", 4),
        (5, "Join Shoulder Seams", "Sew shoulders", "Single Needle", "301", 2),
        (6, "Set Sleeves", "Attach sleeves", "Single Needle", "301", 4),
        (7, "Sew Side Seams", "Close sides", "Flat Feller", "401", 3),
        (8, "Construct Collar", "Build collar assembly", "Single Needle", "301", 4),
        (9, "Attach Collar", "Set collar to neckline", "Single Needle", "301", 3),
        (10, "Sew Facing", "Attach front facing", "Single Needle", "301", 3),
        (11, "Buttonholes", "Create buttonholes", "Buttonhole Machine", None, 2),
        (12, "Cuff Construction", "Build and attach cuffs", "Single Needle", "301", 4),
        (13, "Waistband", "Attach adjustable waistband tabs", "Single Needle", "301", 3),
        (14, "Topstitch", "Final topstitching", "Single Needle", "301", 4),
        (15, "Press", "Final press", "Steam Press", None, 3),
        (16, "QC Inspect", "Quality control", None, None, 3),
    ],
}

# Base measurements for generating size specs
BASE_MEASUREMENTS = {
    "jeans": {
        # Base size 32 measurements (inches)
        "waist": 33.0,
        "front_rise": 10.5,
        "back_rise": 14.5,
        "hip": 40.0,
        "thigh": 23.0,
        "knee": 16.5,
        "leg_opening": 15.0,
        "inseam": 32.0,
        "outseam": 42.5,
    },
}


class TechPackGenerator:
    """Generates complete tech packs from product concepts."""

    def __init__(self, db: Session):
        self.db = db

    def generate_from_concept(self, concept_id: int) -> Optional[Dict]:
        """Generate a full tech pack from a product concept."""
        concept = self.db.query(ProductConcept).filter(
            ProductConcept.id == concept_id
        ).first()
        if not concept:
            return None

        category = (concept.category or "jeans").lower().replace(" ", "_").replace("-", "_")

        # Create tech pack
        count = self.db.query(func.count(TechPack.id)).scalar() or 0
        tech_pack_number = f"TP-{datetime.now().strftime('%Y%m')}-{count + 1:04d}"

        tech_pack = TechPack(
            tech_pack_number=tech_pack_number,
            style_name=concept.title,
            category=category,
            season=f"{'F' if datetime.now().month >= 7 else 'S'}{datetime.now().strftime('%y')}",
            description=concept.brief,
            target_cost=concept.target_cost,
            target_retail=concept.target_retail,
            target_margin=concept.target_margin,
            status=TechPackStatus.DRAFT,
            ai_generated=True,
            ai_model="cdo_techpack_gen",
        )
        self.db.add(tech_pack)
        self.db.flush()

        # Generate measurements
        measurements_count = self._generate_measurements(tech_pack, category)

        # Generate BOM
        materials_count = self._generate_bom(tech_pack, category)

        # Generate construction operations
        construction_count = self._generate_construction(tech_pack, category)

        # Link concept to tech pack
        concept.tech_pack_id = tech_pack.id

        # Update pipeline
        pipeline = self.db.query(ProductPipeline).filter(
            ProductPipeline.concept_id == concept_id
        ).first()
        if pipeline:
            pipeline.tech_pack_id = tech_pack.id
            pipeline.current_phase = PipelinePhase.TECHNICAL_DESIGN
            pipeline.technical_design_started = datetime.utcnow()

        self.db.commit()

        return {
            "tech_pack_id": tech_pack.id,
            "tech_pack_number": tech_pack_number,
            "measurements_generated": measurements_count,
            "materials_generated": materials_count,
            "construction_ops_generated": construction_count,
            "category": category,
        }

    def _generate_measurements(self, tech_pack: TechPack, category: str) -> int:
        """Generate size measurements from grading rules."""
        base_measurements = BASE_MEASUREMENTS.get(category, BASE_MEASUREMENTS.get("jeans", {}))
        grading_rules = get_grading_rules(category)
        size_spec = generate_size_spec(category, base_measurements)

        count = 0
        for size, measurements in size_spec.items():
            measurement = TechPackMeasurement(
                tech_pack_id=tech_pack.id,
                size=size,
                waist=measurements.get("waist"),
                front_rise=measurements.get("front_rise"),
                back_rise=measurements.get("back_rise"),
                hip=measurements.get("hip"),
                thigh=measurements.get("thigh"),
                knee=measurements.get("knee"),
                leg_opening=measurements.get("leg_opening"),
                inseam=measurements.get("inseam"),
                outseam=measurements.get("outseam"),
                additional_measurements={
                    k: v for k, v in measurements.items()
                    if k not in ("waist", "front_rise", "back_rise", "hip",
                                 "thigh", "knee", "leg_opening", "inseam", "outseam")
                },
            )
            self.db.add(measurement)
            count += 1

        return count

    def _generate_bom(self, tech_pack: TechPack, category: str) -> int:
        """Generate bill of materials from template."""
        template = BOM_TEMPLATES.get(category, BOM_TEMPLATES.get("jeans", []))

        count = 0
        for item in template:
            material = TechPackMaterial(
                tech_pack_id=tech_pack.id,
                material_type=item["type"],
                material_name=item["name"],
                placement=item["placement"],
                quantity_per_unit=item["qty"],
                unit_of_measure=item["unit"],
                unit_cost=item["cost"],
            )
            self.db.add(material)
            count += 1

        return count

    def _generate_construction(self, tech_pack: TechPack, category: str) -> int:
        """Generate construction operations from template."""
        template = CONSTRUCTION_TEMPLATES.get(category, CONSTRUCTION_TEMPLATES.get("jeans", []))

        count = 0
        for item in template:
            op_num, op_name, desc, machine, stitch = item[0], item[1], item[2], item[3], item[4]
            estimated_minutes = item[5] if len(item) > 5 else None

            construction = TechPackConstruction(
                tech_pack_id=tech_pack.id,
                operation_number=op_num,
                operation_name=op_name,
                description=desc,
                machine_type=machine,
                stitch_type=stitch,
                estimated_minutes=estimated_minutes,
            )
            self.db.add(construction)
            count += 1

        return count
