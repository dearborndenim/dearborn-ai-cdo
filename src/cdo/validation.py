"""
Validation Orchestrator

Sends margin_check_request to CFO and capacity_check_request to COO.
Tracks responses via ValidationRequest table with 48hr timeout.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict

from sqlalchemy.orm import Session

from ..db import (
    ProductConcept, ValidationRequest, ProductPipeline,
    ConceptStatus, ValidationStatus, PipelinePhase
)
from ..event_bus import event_bus, CDOOutboundEvent

logger = logging.getLogger(__name__)

VALIDATION_TIMEOUT_HOURS = 48


class ValidationOrchestrator:
    """Manages cross-module validation for product concepts."""

    def __init__(self, db: Session):
        self.db = db

    def request_validation(self, concept_id: int) -> Dict:
        """Send margin check to CFO and capacity check to COO."""
        concept = self.db.query(ProductConcept).filter(
            ProductConcept.id == concept_id
        ).first()
        if not concept:
            return {"error": "Concept not found"}

        results = {}

        # Send margin check to CFO
        margin_req = self._send_margin_check(concept)
        results["margin_check"] = margin_req

        # Send capacity check to COO
        capacity_req = self._send_capacity_check(concept)
        results["capacity_check"] = capacity_req

        # Update concept status
        concept.status = ConceptStatus.VALIDATING
        concept.cfo_validation = ValidationStatus.SENT
        concept.coo_validation = ValidationStatus.SENT

        # Update pipeline
        pipeline = self.db.query(ProductPipeline).filter(
            ProductPipeline.concept_id == concept_id
        ).first()
        if pipeline:
            pipeline.current_phase = PipelinePhase.VALIDATION
            pipeline.validation_started = datetime.utcnow()

        self.db.commit()

        return results

    def _send_margin_check(self, concept: ProductConcept) -> Dict:
        """Send margin check request to CFO."""
        payload = {
            "concept_id": concept.id,
            "concept_number": concept.concept_number,
            "title": concept.title,
            "category": concept.category,
            "target_retail": concept.target_retail,
            "target_cost": concept.target_cost,
            "target_margin": concept.target_margin,
            "request_type": "margin_check",
        }

        timeout_at = datetime.utcnow() + timedelta(hours=VALIDATION_TIMEOUT_HOURS)

        # Create validation request record
        val_req = ValidationRequest(
            concept_id=concept.id,
            validation_type="margin_check",
            target_module="cfo",
            request_payload=payload,
            sent_at=datetime.utcnow(),
            status=ValidationStatus.SENT,
            timeout_at=timeout_at,
        )
        self.db.add(val_req)
        self.db.flush()

        # Publish event
        event_id = event_bus.publish(
            CDOOutboundEvent.DEMAND_FORECAST,  # reuse for now
            {
                **payload,
                "title": f"Margin Check: {concept.title}",
                "message": f"Please validate margins for {concept.title} "
                          f"(retail: ${concept.target_retail}, cost: ${concept.target_cost})",
                "validation_request_id": val_req.id,
            },
            target_module="cfo"
        )
        val_req.event_id = event_id

        return {
            "validation_request_id": val_req.id,
            "type": "margin_check",
            "target": "cfo",
            "event_id": event_id,
            "timeout_at": timeout_at.isoformat(),
        }

    def _send_capacity_check(self, concept: ProductConcept) -> Dict:
        """Send capacity check request to COO."""
        payload = {
            "concept_id": concept.id,
            "concept_number": concept.concept_number,
            "title": concept.title,
            "category": concept.category,
            "estimated_units": 500,  # default batch estimate
            "request_type": "capacity_check",
        }

        timeout_at = datetime.utcnow() + timedelta(hours=VALIDATION_TIMEOUT_HOURS)

        val_req = ValidationRequest(
            concept_id=concept.id,
            validation_type="capacity_check",
            target_module="coo",
            request_payload=payload,
            sent_at=datetime.utcnow(),
            status=ValidationStatus.SENT,
            timeout_at=timeout_at,
        )
        self.db.add(val_req)
        self.db.flush()

        event_id = event_bus.publish(
            CDOOutboundEvent.DEMAND_FORECAST,
            {
                **payload,
                "title": f"Capacity Check: {concept.title}",
                "message": f"Please check production capacity for {concept.title} "
                          f"(estimated 500 units)",
                "validation_request_id": val_req.id,
            },
            target_module="coo"
        )
        val_req.event_id = event_id

        return {
            "validation_request_id": val_req.id,
            "type": "capacity_check",
            "target": "coo",
            "event_id": event_id,
            "timeout_at": timeout_at.isoformat(),
        }

    def handle_validation_response(
        self,
        validation_request_id: int,
        approved: bool,
        response_data: Dict = None,
        summary: str = None,
    ) -> Dict:
        """Process a validation response from CFO or COO."""
        val_req = self.db.query(ValidationRequest).filter(
            ValidationRequest.id == validation_request_id
        ).first()
        if not val_req:
            return {"error": "Validation request not found"}

        val_req.status = ValidationStatus.APPROVED if approved else ValidationStatus.REJECTED
        val_req.response_payload = response_data or {}
        val_req.responded_at = datetime.utcnow()
        val_req.result_summary = summary

        # Update concept validation status
        concept = self.db.query(ProductConcept).filter(
            ProductConcept.id == val_req.concept_id
        ).first()
        if concept:
            status = ValidationStatus.APPROVED if approved else ValidationStatus.REJECTED
            if val_req.validation_type == "margin_check":
                concept.cfo_validation = status
            elif val_req.validation_type == "capacity_check":
                concept.coo_validation = status

            # Check if both validations are complete
            self._check_validation_complete(concept)

        self.db.commit()

        return {
            "validation_request_id": val_req.id,
            "status": val_req.status.value,
            "concept_id": val_req.concept_id,
        }

    def _check_validation_complete(self, concept: ProductConcept):
        """Check if both CFO and COO validations are complete."""
        if (concept.cfo_validation in (ValidationStatus.APPROVED, ValidationStatus.REJECTED) and
            concept.coo_validation in (ValidationStatus.APPROVED, ValidationStatus.REJECTED)):

            if (concept.cfo_validation == ValidationStatus.APPROVED and
                concept.coo_validation == ValidationStatus.APPROVED):
                concept.status = ConceptStatus.VALIDATED
            else:
                concept.status = ConceptStatus.VALIDATION_FAILED

    def check_timeouts(self) -> int:
        """Check for timed-out validation requests. Returns count of timed out."""
        timed_out = self.db.query(ValidationRequest).filter(
            ValidationRequest.status == ValidationStatus.SENT,
            ValidationRequest.timeout_at <= datetime.utcnow()
        ).all()

        count = 0
        for req in timed_out:
            req.status = ValidationStatus.TIMED_OUT
            req.result_summary = f"Timed out after {VALIDATION_TIMEOUT_HOURS} hours"

            # Update concept
            concept = self.db.query(ProductConcept).filter(
                ProductConcept.id == req.concept_id
            ).first()
            if concept:
                if req.validation_type == "margin_check":
                    concept.cfo_validation = ValidationStatus.TIMED_OUT
                elif req.validation_type == "capacity_check":
                    concept.coo_validation = ValidationStatus.TIMED_OUT
                self._check_validation_complete(concept)

            count += 1

        if count > 0:
            self.db.commit()
            logger.warning(f"{count} validation requests timed out")

        return count
