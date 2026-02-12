"""
Concept Development Module

Generates concept briefs and AI sketches using OpenAI GPT and DALL-E.
Estimates pricing based on competitor data and internal COGS templates.
"""
import logging
from datetime import datetime
from typing import Optional, Dict

from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import (
    ProductOpportunity, ProductConcept, ProductPipeline,
    OpportunityStatus, ConceptStatus, PipelinePhase
)
from .competency import get_category_info, estimate_pricing

logger = logging.getLogger(__name__)
settings = get_settings()


class ConceptDesigner:
    """Generates product concept briefs and AI sketches."""

    def __init__(self, db: Session):
        self.db = db
        self._openai_client = None

    @property
    def openai_client(self):
        if self._openai_client is None and settings.openai_api_key:
            from openai import OpenAI
            self._openai_client = OpenAI(api_key=settings.openai_api_key)
        return self._openai_client

    def promote_opportunity(self, opportunity_id: int) -> Optional[ProductConcept]:
        """Promote an opportunity to a concept."""
        opp = self.db.query(ProductOpportunity).filter(
            ProductOpportunity.id == opportunity_id
        ).first()
        if not opp:
            return None

        # Generate concept number
        from sqlalchemy import func
        count = self.db.query(func.count(ProductConcept.id)).scalar() or 0
        concept_number = f"CONCEPT-{datetime.now().strftime('%Y%m')}-{count + 1:04d}"

        # Get pricing estimate
        pricing = estimate_pricing(opp.category or "jeans")

        concept = ProductConcept(
            opportunity_id=opp.id,
            concept_number=concept_number,
            title=opp.title,
            category=opp.category,
            target_retail=opp.estimated_retail or pricing.get("estimated_retail"),
            target_cost=opp.estimated_cost or pricing.get("estimated_cost"),
            target_margin=opp.estimated_margin or pricing.get("estimated_margin_pct"),
            status=ConceptStatus.BRIEF_COMPLETE,
        )

        opp.status = OpportunityStatus.PROMOTED

        self.db.add(concept)
        self.db.commit()
        self.db.refresh(concept)

        # Create pipeline entry
        pipe_count = self.db.query(func.count(ProductPipeline.id)).scalar() or 0
        pipeline = ProductPipeline(
            pipeline_number=f"PIPE-{datetime.now().strftime('%Y%m')}-{pipe_count + 1:04d}",
            opportunity_id=opp.id,
            concept_id=concept.id,
            title=opp.title,
            category=opp.category,
            current_phase=PipelinePhase.CONCEPT,
            discovery_started=opp.created_at,
            concept_started=datetime.utcnow(),
        )
        self.db.add(pipeline)
        self.db.commit()

        return concept

    def generate_brief(self, concept_id: int) -> Optional[Dict]:
        """Generate an AI concept brief using GPT."""
        concept = self.db.query(ProductConcept).filter(
            ProductConcept.id == concept_id
        ).first()
        if not concept:
            return None

        if not self.openai_client:
            logger.warning("OpenAI not configured - generating placeholder brief")
            return self._placeholder_brief(concept)

        category_info = get_category_info(concept.category or "jeans")

        prompt = f"""You are a product designer for Dearborn Denim, a premium American-made
denim and workwear brand based in Chicago. Generate a product concept brief.

Product: {concept.title}
Category: {concept.category}
Target Retail: ${concept.target_retail or 'TBD'}
Target Customer: Working professionals who value quality, durability, and American manufacturing

Include:
1. Product description (2-3 sentences)
2. Target customer profile
3. Key features (5-7 bullet points)
4. What differentiates this from competitors
5. Suggested materials and construction details
6. Inspiration references (styles, eras, cultural references)

Keep the tone practical and focused on American craftsmanship.
Subcategories available: {category_info.get('subcategories', [])}
"""

        try:
            response = self.openai_client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1500,
            )
            brief_text = response.choices[0].message.content

            concept.brief = brief_text
            concept.key_features = self._extract_features(brief_text)
            concept.status = ConceptStatus.BRIEF_COMPLETE
            self.db.commit()

            return {
                "concept_id": concept.id,
                "brief": brief_text,
                "status": concept.status.value,
            }

        except Exception as e:
            logger.error(f"Brief generation failed: {e}")
            return {"error": str(e)}

    def generate_sketch(self, concept_id: int) -> Optional[Dict]:
        """Generate an AI product sketch using DALL-E."""
        concept = self.db.query(ProductConcept).filter(
            ProductConcept.id == concept_id
        ).first()
        if not concept:
            return None

        if not self.openai_client:
            logger.warning("OpenAI not configured - sketch generation skipped")
            return {"error": "OpenAI not configured", "concept_id": concept.id}

        prompt = (
            f"Product design sketch of {concept.title}, "
            f"category: {concept.category}, "
            f"American workwear style, premium denim brand, "
            f"clean technical flat sketch on white background, "
            f"front and back view, fashion design illustration style"
        )

        try:
            response = self.openai_client.images.generate(
                model=settings.dall_e_model,
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            )

            image_url = response.data[0].url
            concept.sketch_url = image_url
            concept.sketch_prompt = prompt

            if concept.status == ConceptStatus.DRAFT:
                concept.status = ConceptStatus.SKETCH_GENERATED

            self.db.commit()

            return {
                "concept_id": concept.id,
                "sketch_url": image_url,
                "prompt": prompt,
                "status": concept.status.value,
            }

        except Exception as e:
            logger.error(f"Sketch generation failed: {e}")
            return {"error": str(e), "concept_id": concept.id}

    def _placeholder_brief(self, concept: ProductConcept) -> Dict:
        """Generate a placeholder brief when OpenAI is not available."""
        category_info = get_category_info(concept.category or "jeans")
        pricing = estimate_pricing(concept.category or "jeans")

        brief = f"""# Product Concept Brief: {concept.title}

## Description
A new {concept.category or 'denim'} product for Dearborn Denim's lineup,
designed for the modern working professional who values quality American-made apparel.

## Target Customer
Working professionals aged 25-55 who appreciate durability, comfort, and
American craftsmanship. They're willing to pay a premium for made-in-USA quality.

## Key Features
- Premium American-made construction
- Durable materials built to last
- Comfortable fit for all-day wear
- Classic styling with modern details
- Reinforced stress points

## Differentiators
- Made in Chicago, supporting American manufacturing
- Direct-to-consumer pricing
- Quality that outlasts fast fashion alternatives

## Estimated Pricing
- Cost: ${pricing.get('estimated_cost', 'TBD')}
- Retail: ${pricing.get('estimated_retail', 'TBD')}
- Margin: {pricing.get('estimated_margin_pct', 'TBD')}%
"""
        concept.brief = brief
        concept.key_features = [
            "Premium American-made construction",
            "Durable materials",
            "Comfortable fit",
            "Classic styling",
            "Reinforced stress points",
        ]
        concept.status = ConceptStatus.BRIEF_COMPLETE
        self.db.commit()

        return {
            "concept_id": concept.id,
            "brief": brief,
            "status": concept.status.value,
            "note": "placeholder_brief_openai_not_configured",
        }

    def _extract_features(self, brief_text: str) -> list:
        """Extract key features from brief text."""
        features = []
        in_features = False
        for line in brief_text.split("\n"):
            line = line.strip()
            if "key features" in line.lower() or "features" in line.lower():
                in_features = True
                continue
            if in_features:
                if line.startswith(("-", "*", "•")):
                    features.append(line.lstrip("-*• ").strip())
                elif line and not line.startswith("#"):
                    continue
                elif line.startswith("#"):
                    break
            if len(features) >= 7:
                break
        return features
