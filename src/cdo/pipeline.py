"""
Pipeline Engine

State machine managing the 6-phase product lifecycle:
DISCOVERY -> CONCEPT -> VALIDATION -> APPROVAL -> TECHNICAL_DESIGN -> HANDOFF -> COMPLETE
"""
import logging
from datetime import datetime
from typing import Optional, Dict

from sqlalchemy.orm import Session

from ..db import (
    ProductPipeline, ProductConcept, ProductOpportunity, TechPack,
    PipelinePhase, ConceptStatus, ValidationStatus
)
from ..event_bus import event_bus, CDOOutboundEvent

logger = logging.getLogger(__name__)

# Valid phase transitions
TRANSITIONS = {
    PipelinePhase.DISCOVERY: [PipelinePhase.CONCEPT, PipelinePhase.CANCELLED],
    PipelinePhase.CONCEPT: [PipelinePhase.VALIDATION, PipelinePhase.CANCELLED],
    PipelinePhase.VALIDATION: [PipelinePhase.APPROVAL, PipelinePhase.CONCEPT, PipelinePhase.CANCELLED],
    PipelinePhase.APPROVAL: [PipelinePhase.TECHNICAL_DESIGN, PipelinePhase.CONCEPT, PipelinePhase.CANCELLED],
    PipelinePhase.TECHNICAL_DESIGN: [PipelinePhase.HANDOFF, PipelinePhase.CANCELLED],
    PipelinePhase.HANDOFF: [PipelinePhase.COMPLETE],
    PipelinePhase.COMPLETE: [],
    PipelinePhase.CANCELLED: [],
}


class PipelineEngine:
    """Manages product lifecycle through the 6-phase pipeline."""

    def __init__(self, db: Session):
        self.db = db

    def get_pipeline(self, pipeline_id: int) -> Optional[Dict]:
        """Get pipeline status and details."""
        pipeline = self.db.query(ProductPipeline).filter(
            ProductPipeline.id == pipeline_id
        ).first()
        if not pipeline:
            return None

        return self._serialize_pipeline(pipeline)

    def list_pipeline(self, phase: PipelinePhase = None) -> list:
        """List all pipeline items, optionally filtered by phase."""
        query = self.db.query(ProductPipeline)
        if phase:
            query = query.filter(ProductPipeline.current_phase == phase)

        pipelines = query.order_by(ProductPipeline.updated_at.desc()).all()
        return [self._serialize_pipeline(p) for p in pipelines]

    def advance_phase(self, pipeline_id: int, notes: str = None) -> Dict:
        """Advance pipeline to the next phase."""
        pipeline = self.db.query(ProductPipeline).filter(
            ProductPipeline.id == pipeline_id
        ).first()
        if not pipeline:
            return {"error": "Pipeline not found"}

        current = pipeline.current_phase
        allowed = TRANSITIONS.get(current, [])

        if not allowed:
            return {"error": f"Pipeline in {current.value} phase cannot advance"}

        # Determine next phase based on current state
        next_phase = self._determine_next_phase(pipeline, current, allowed)
        if not next_phase:
            return {"error": "Cannot determine next phase - prerequisites not met"}

        return self._transition(pipeline, next_phase, notes)

    def set_phase(self, pipeline_id: int, target_phase: PipelinePhase, notes: str = None) -> Dict:
        """Manually set pipeline to a specific phase (must be valid transition)."""
        pipeline = self.db.query(ProductPipeline).filter(
            ProductPipeline.id == pipeline_id
        ).first()
        if not pipeline:
            return {"error": "Pipeline not found"}

        allowed = TRANSITIONS.get(pipeline.current_phase, [])
        if target_phase not in allowed:
            return {
                "error": f"Cannot transition from {pipeline.current_phase.value} to {target_phase.value}",
                "allowed": [p.value for p in allowed],
            }

        return self._transition(pipeline, target_phase, notes)

    def _determine_next_phase(
        self,
        pipeline: ProductPipeline,
        current: PipelinePhase,
        allowed: list,
    ) -> Optional[PipelinePhase]:
        """Determine the next phase based on prerequisites."""

        if current == PipelinePhase.DISCOVERY:
            return PipelinePhase.CONCEPT

        elif current == PipelinePhase.CONCEPT:
            # Need concept linked (promoted ideas from seasons are ready to advance)
            if pipeline.concept_id:
                concept = self.db.query(ProductConcept).filter(
                    ProductConcept.id == pipeline.concept_id
                ).first()
                if concept and concept.status in (
                    ConceptStatus.DRAFT,
                    ConceptStatus.BRIEF_COMPLETE,
                    ConceptStatus.SKETCH_GENERATED,
                ):
                    return PipelinePhase.VALIDATION
            return None

        elif current == PipelinePhase.VALIDATION:
            # Auto-validate if not yet validated
            if pipeline.concept_id:
                concept = self.db.query(ProductConcept).filter(
                    ProductConcept.id == pipeline.concept_id
                ).first()
                if concept:
                    if concept.status != ConceptStatus.VALIDATED:
                        from .validation import ValidationOrchestrator
                        orchestrator = ValidationOrchestrator(self.db)
                        orchestrator.request_validation(pipeline.concept_id)
                        logger.info(f"Auto-validated concept {concept.concept_number} on advance")
                    return PipelinePhase.APPROVAL
            return None

        elif current == PipelinePhase.APPROVAL:
            # Auto-approve CEO (Rob is the CEO using this UI)
            if pipeline.concept_id:
                concept = self.db.query(ProductConcept).filter(
                    ProductConcept.id == pipeline.concept_id
                ).first()
                if concept:
                    if concept.ceo_approval != ValidationStatus.APPROVED:
                        concept.ceo_approval = ValidationStatus.APPROVED
                        logger.info(f"Auto-approved CEO for concept {concept.concept_number}")
                    return PipelinePhase.TECHNICAL_DESIGN
            return None

        elif current == PipelinePhase.TECHNICAL_DESIGN:
            # Need tech pack complete
            if pipeline.tech_pack_id:
                return PipelinePhase.HANDOFF
            return None

        elif current == PipelinePhase.HANDOFF:
            # Need all handoffs complete
            if pipeline.handoff_to_coo:
                return PipelinePhase.COMPLETE
            return None

        return None

    def _transition(self, pipeline: ProductPipeline, target: PipelinePhase, notes: str = None) -> Dict:
        """Execute a phase transition."""
        old_phase = pipeline.current_phase
        pipeline.current_phase = target

        # Set phase timestamp
        now = datetime.utcnow()
        timestamp_map = {
            PipelinePhase.DISCOVERY: "discovery_started",
            PipelinePhase.CONCEPT: "concept_started",
            PipelinePhase.VALIDATION: "validation_started",
            PipelinePhase.APPROVAL: "approval_started",
            PipelinePhase.TECHNICAL_DESIGN: "technical_design_started",
            PipelinePhase.HANDOFF: "handoff_started",
            PipelinePhase.COMPLETE: "completed_at",
        }
        if target in timestamp_map:
            setattr(pipeline, timestamp_map[target], now)

        # Store notes
        if notes:
            phase_notes = pipeline.phase_notes or {}
            phase_notes[target.value] = notes
            pipeline.phase_notes = phase_notes

        # Trigger phase-specific actions
        self._on_phase_enter(pipeline, target)

        self.db.commit()

        logger.info(
            f"Pipeline {pipeline.pipeline_number}: "
            f"{old_phase.value} -> {target.value}"
        )

        return {
            "pipeline_id": pipeline.id,
            "pipeline_number": pipeline.pipeline_number,
            "old_phase": old_phase.value,
            "new_phase": target.value,
            "transitioned_at": now.isoformat(),
        }

    def _on_phase_enter(self, pipeline: ProductPipeline, phase: PipelinePhase):
        """Execute actions when entering a new phase."""

        if phase == PipelinePhase.VALIDATION:
            # Trigger validation (auto-approves CFO + COO for now)
            if pipeline.concept_id:
                try:
                    from .validation import ValidationOrchestrator
                    orchestrator = ValidationOrchestrator(self.db)
                    orchestrator.request_validation(pipeline.concept_id)
                    logger.info(f"Validation triggered for pipeline {pipeline.pipeline_number}")
                except Exception as e:
                    logger.error(f"Failed to trigger validation: {e}")

        elif phase == PipelinePhase.TECHNICAL_DESIGN:
            # Auto-generate tech pack if concept exists but tech pack doesn't
            if pipeline.concept_id and not pipeline.tech_pack_id:
                try:
                    from .techpack_gen import TechPackGenerator
                    generator = TechPackGenerator(self.db)
                    result = generator.generate_from_concept(pipeline.concept_id)
                    if result and result.get("tech_pack_id"):
                        pipeline.tech_pack_id = result["tech_pack_id"]
                        logger.info(f"Auto-generated tech pack for pipeline {pipeline.pipeline_number}")
                except Exception as e:
                    logger.error(f"Failed to auto-generate tech pack: {e}")

        elif phase == PipelinePhase.HANDOFF:
            self._execute_handoff(pipeline)

        elif phase == PipelinePhase.COMPLETE:
            logger.info(f"Pipeline {pipeline.pipeline_number} completed")
            self._on_complete(pipeline)

        # Notify CEO dashboard
        event_bus.publish(
            CDOOutboundEvent.PERFORMANCE_REPORT,
            {
                "title": f"Pipeline Update: {pipeline.title}",
                "message": f"Product '{pipeline.title}' moved to {phase.value} phase",
                "pipeline_number": pipeline.pipeline_number,
                "phase": phase.value,
            },
            target_module="ceo"
        )

    def _execute_handoff(self, pipeline: ProductPipeline):
        """Execute handoff to COO, CMO, and CFO."""

        # Handoff to COO (production)
        if pipeline.tech_pack_id:
            tech_pack = self.db.query(TechPack).filter(
                TechPack.id == pipeline.tech_pack_id
            ).first()
            if tech_pack:
                event_bus.publish(
                    CDOOutboundEvent.TECH_PACK_READY,
                    {
                        "title": f"New Product for Production: {pipeline.title}",
                        "message": f"Tech pack {tech_pack.tech_pack_number} ready for production",
                        "tech_pack_id": tech_pack.id,
                        "tech_pack_number": tech_pack.tech_pack_number,
                        "pattern_share_link": pipeline.pattern_share_link,
                        "techpack_share_link": pipeline.techpack_share_link,
                    },
                    target_module="coo"
                )
                pipeline.handoff_to_coo = True

        # Handoff to CMO (marketing brief)
        concept = None
        if pipeline.concept_id:
            concept = self.db.query(ProductConcept).filter(
                ProductConcept.id == pipeline.concept_id
            ).first()

        event_bus.publish(
            CDOOutboundEvent.PRODUCT_RECOMMENDATION,
            {
                "title": f"New Product Launch: {pipeline.title}",
                "message": f"Prepare marketing for {pipeline.title}",
                "category": pipeline.category,
                "target_retail": concept.target_retail if concept else None,
                "sketch_url": concept.sketch_url if concept else None,
                "brief": concept.brief if concept else None,
            },
            target_module="cmo"
        )
        pipeline.handoff_to_cmo = True

        # Handoff to CFO (budget allocation)
        event_bus.publish(
            CDOOutboundEvent.DEMAND_FORECAST,
            {
                "title": f"Budget Request: {pipeline.title}",
                "message": f"Allocate production budget for {pipeline.title}",
                "estimated_cost": concept.target_cost if concept else None,
                "estimated_retail": concept.target_retail if concept else None,
                "estimated_units": 500,
            },
            target_module="cfo"
        )
        pipeline.handoff_to_cfo = True

    def _on_complete(self, pipeline: ProductPipeline):
        """Execute actions when pipeline reaches COMPLETE phase."""
        concept = None
        if pipeline.concept_id:
            concept = self.db.query(ProductConcept).filter(
                ProductConcept.id == pipeline.concept_id
            ).first()

        # Notify COO: product approved for production, submit POs
        event_bus.publish(
            CDOOutboundEvent.PRODUCT_APPROVED_FOR_PRODUCTION,
            {
                "title": f"Production Approved: {pipeline.title}",
                "message": f"Product '{pipeline.title}' approved for production. Submit purchase orders.",
                "pipeline_id": pipeline.id,
                "pipeline_number": pipeline.pipeline_number,
                "category": pipeline.category,
                "tech_pack_id": pipeline.tech_pack_id,
            },
            target_module="coo"
        )

        # Notify CFO: allocate production budget, update cashflow
        event_bus.publish(
            CDOOutboundEvent.PRODUCT_BUDGET_ALLOCATED,
            {
                "title": f"Budget Allocation: {pipeline.title}",
                "message": f"Allocate production budget for {pipeline.title}",
                "pipeline_id": pipeline.id,
                "pipeline_number": pipeline.pipeline_number,
                "estimated_cost": concept.target_cost if concept else None,
                "estimated_retail": concept.target_retail if concept else None,
                "estimated_units": 500,
            },
            target_module="cfo"
        )

        # Notify CMO: schedule marketing campaigns
        event_bus.publish(
            CDOOutboundEvent.PRODUCT_LAUNCH_SCHEDULED,
            {
                "title": f"Product Launch: {pipeline.title}",
                "message": f"Schedule marketing campaigns for {pipeline.title}",
                "pipeline_id": pipeline.id,
                "pipeline_number": pipeline.pipeline_number,
                "category": pipeline.category,
                "target_retail": concept.target_retail if concept else None,
                "sketch_url": concept.sketch_url if concept else None,
            },
            target_module="cmo"
        )

    def _serialize_pipeline(self, p: ProductPipeline) -> Dict:
        """Serialize pipeline to dict."""
        # Look up concept data if concept_id is present
        concept_data = None
        if p.concept_id:
            concept = self.db.query(ProductConcept).filter(ProductConcept.id == p.concept_id).first()
            if concept:
                concept_data = {
                    "id": concept.id,
                    "concept_number": concept.concept_number,
                    "title": concept.title,
                    "category": concept.category,
                    "brief": concept.brief,
                    "target_customer": concept.target_customer,
                    "key_features": concept.key_features,
                    "differentiators": concept.differentiators,
                    "sketch_url": concept.sketch_url,
                    "sketch_share_link": concept.sketch_share_link,
                    "target_retail": concept.target_retail,
                    "target_cost": concept.target_cost,
                    "target_margin": concept.target_margin,
                    "pricing_rationale": concept.pricing_rationale,
                    "status": concept.status.value if concept.status else None,
                    "cfo_validation": concept.cfo_validation.value if concept.cfo_validation else None,
                    "coo_validation": concept.coo_validation.value if concept.coo_validation else None,
                    "ceo_approval": concept.ceo_approval.value if concept.ceo_approval else None,
                }

        # Look up tech pack data if tech_pack_id is present
        tech_pack_data = None
        if p.tech_pack_id:
            tech_pack = self.db.query(TechPack).filter(TechPack.id == p.tech_pack_id).first()
            if tech_pack:
                tech_pack_data = {
                    "id": tech_pack.id,
                    "tech_pack_number": tech_pack.tech_pack_number,
                    "title": tech_pack.style_name,
                    "category": tech_pack.category,
                    "status": tech_pack.status,
                }

        return {
            "id": p.id,
            "pipeline_number": p.pipeline_number,
            "title": p.title,
            "category": p.category,
            "current_phase": p.current_phase.value if p.current_phase else None,
            "opportunity_id": p.opportunity_id,
            "concept_id": p.concept_id,
            "tech_pack_id": p.tech_pack_id,
            "handoff_to_coo": p.handoff_to_coo,
            "handoff_to_cmo": p.handoff_to_cmo,
            "handoff_to_cfo": p.handoff_to_cfo,
            "pattern_share_link": p.pattern_share_link,
            "techpack_share_link": p.techpack_share_link,
            "phase_timestamps": {
                "discovery": p.discovery_started.isoformat() if p.discovery_started else None,
                "concept": p.concept_started.isoformat() if p.concept_started else None,
                "validation": p.validation_started.isoformat() if p.validation_started else None,
                "approval": p.approval_started.isoformat() if p.approval_started else None,
                "technical_design": p.technical_design_started.isoformat() if p.technical_design_started else None,
                "handoff": p.handoff_started.isoformat() if p.handoff_started else None,
                "completed": p.completed_at.isoformat() if p.completed_at else None,
            },
            "phase_notes": p.phase_notes,
            "concept": concept_data,
            "tech_pack": tech_pack_data,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }
