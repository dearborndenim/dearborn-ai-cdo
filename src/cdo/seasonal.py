"""
Seasonal Design Module

Manages season-based product development workflow:
1. CEO assigns a season with target customer demographics
2. AI researches the customer segment (Perplexity for trends, GPT-4o for profile)
3. AI generates coordinated LOOKS (outfits of 2-4 pieces) with fabric specifics
4. Best ideas get promoted into the existing product pipeline

Research uses Perplexity Sonar for web-grounded trend data, with GPT-4o fallback.
Ideation uses GPT-4o for structured product generation grounded in research.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List

import httpx
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import (
    Season, SeasonProductIdea, SeasonLook, SeasonResearch, SeasonStatus,
    ProductOpportunity, OpportunityStatus, ProductPerformance,
)
from .competency import CAN_MAKE, PRODUCT_CATEGORIES, estimate_pricing, is_feasible, estimate_manufacturing_cost
from .trend_researcher import TrendResearcher

logger = logging.getLogger(__name__)
settings = get_settings()


class SeasonalDesigner:
    """Manages seasonal design workflow: trend research -> customer research -> coordinated look generation."""

    def __init__(self, db: Session):
        self.db = db
        self._openai_client = None
        self._researcher = None

    @property
    def openai_client(self):
        if self._openai_client is None and settings.openai_api_key:
            from openai import OpenAI
            self._openai_client = OpenAI(api_key=settings.openai_api_key)
        return self._openai_client

    @property
    def researcher(self):
        if self._researcher is None:
            self._researcher = TrendResearcher()
        return self._researcher

    def create_season(
        self,
        name: str,
        season_code: str,
        target_demo: Dict,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Season:
        """Create a new season design assignment."""
        season = Season(
            name=name,
            season_code=season_code,
            target_demo=target_demo,
            start_date=start_date,
            end_date=end_date,
            status=SeasonStatus.PLANNING,
        )
        self.db.add(season)
        self.db.commit()
        self.db.refresh(season)
        return season

    # ==================== Research Phase ====================

    def research_customer(self, season_id: int) -> Optional[Dict]:
        """Run 5-step research: 4 Perplexity trend sections + 1 GPT-4o customer profile.

        Saves each as a SeasonResearch record. Stores concatenated summary on
        Season.customer_research for backward compatibility.
        """
        season = self.db.query(Season).filter(Season.id == season_id).first()
        if not season:
            return None

        season.status = SeasonStatus.RESEARCHING
        self.db.commit()

        demo = season.target_demo or {}
        categories = list(PRODUCT_CATEGORIES.keys())

        # Run 4 Perplexity trend research sections
        research_sections = []

        fashion = self.researcher.research_fashion_trends(season.name, demo)
        research_sections.append(fashion)

        fabric = self.researcher.research_fabric_trends(season.name)
        research_sections.append(fabric)

        silhouettes = self.researcher.research_silhouettes(season.name, categories)
        research_sections.append(silhouettes)

        competitors = self.researcher.research_competitors(season.name)
        research_sections.append(competitors)

        # GPT-4o customer profile (existing approach)
        customer = self._research_customer_profile(season, demo)
        research_sections.append(customer)

        # Delete any prior research for this season
        self.db.query(SeasonResearch).filter(
            SeasonResearch.season_id == season.id
        ).delete()

        # Save each section as a SeasonResearch record
        for section in research_sections:
            record = SeasonResearch(
                season_id=season.id,
                research_type=section["research_type"],
                content=section["content"],
                citations=section.get("citations", []),
                source=section["source"],
                model_used=section.get("model_used"),
            )
            self.db.add(record)

        # Backward compat: concatenate into Season.customer_research
        summary_parts = []
        for section in research_sections:
            summary_parts.append(f"=== {section['research_type'].upper()} ===\n{section['content']}")
        season.customer_research = "\n\n".join(summary_parts)

        season.status = SeasonStatus.RESEARCH_COMPLETE
        self.db.commit()

        return {
            "season_id": season.id,
            "season_name": season.name,
            "status": season.status.value,
            "research_sections": [{
                "research_type": s["research_type"],
                "source": s["source"],
                "model_used": s.get("model_used"),
                "citation_count": len(s.get("citations", [])),
                "content_preview": s["content"][:300] + "..." if len(s["content"]) > 300 else s["content"],
            } for s in research_sections],
            "total_citations": sum(len(s.get("citations", [])) for s in research_sections),
        }

    def _research_customer_profile(self, season: Season, demo: Dict) -> Dict:
        """Generate customer profile using GPT-4o (or placeholder)."""
        if not self.openai_client:
            return {
                "research_type": "customer_profile",
                "content": self._placeholder_customer_profile(season, demo),
                "citations": [],
                "source": "placeholder",
                "model_used": None,
            }

        prompt = f"""You are a consumer researcher for Dearborn Denim & Apparel, a premium
American-made denim and workwear brand based in Chicago, Illinois. They manufacture
all products in their own factory (with knitwear sourced from partners). Price range is $48-$178.

Research the following customer segment for our {season.name} line:

- Gender: {demo.get('gender', 'All')}
- Age Range: {demo.get('age_range', '25-55')}
- Income: {demo.get('income', '$75,000+')}
- Location: {demo.get('location', 'USA')}
- Description: {demo.get('description', 'Quality-conscious consumers')}

Provide a comprehensive customer profile covering:

1. **Lifestyle Summary** - How they spend their time, work/life balance, hobbies
2. **Shopping Habits** - Where they shop, online vs in-store, purchase frequency, brand loyalty
3. **Style Preferences** - Casual vs dressed up, fit preferences, color preferences for this season
4. **Price Sensitivity** - What they're willing to pay for quality denim/workwear, value perception
5. **Brand Affinities** - Other brands they likely wear, what draws them to premium American-made
6. **What They Want from Denim/Workwear** - Durability, comfort, versatility, sustainability
7. **{season.name}-Specific Needs** - What this season means for their wardrobe, key occasions, weather considerations
8. **Knitwear Preferences** - What knit pieces they'd want to pair with workwear/denim

Write in a practical, business-oriented tone. Be specific with actionable insights."""

        try:
            response = self.openai_client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
            )
            return {
                "research_type": "customer_profile",
                "content": response.choices[0].message.content,
                "citations": [],
                "source": "gpt4o",
                "model_used": settings.openai_model,
            }
        except Exception as e:
            logger.error(f"GPT-4o customer profile failed: {e}")
            return {
                "research_type": "customer_profile",
                "content": self._placeholder_customer_profile(season, demo),
                "citations": [],
                "source": "placeholder",
                "model_used": None,
            }

    # ==================== Context Gathering ====================

    def _get_existing_products(self) -> List[Dict]:
        """Get existing product catalog for context in brainstorming."""
        try:
            products = self.db.query(ProductPerformance).order_by(
                ProductPerformance.revenue_30d.desc().nullslast()
            ).limit(50).all()
            return [{
                "name": p.product_name,
                "sku": p.sku,
                "revenue_30d": float(p.revenue_30d) if p.revenue_30d else 0,
                "revenue_lifetime": float(p.revenue_lifetime) if p.revenue_lifetime else 0,
                "performance_score": float(p.performance_score) if p.performance_score else 0,
                "trend_direction": p.trend_direction or "stable",
            } for p in products]
        except Exception as e:
            logger.warning(f"Could not fetch existing products: {e}")
            return []

    def _get_recent_trends(self) -> List[Dict]:
        """Get recent trend data for context in brainstorming."""
        from ..db import TrendAnalysis
        try:
            trends = self.db.query(TrendAnalysis).order_by(
                TrendAnalysis.trend_score.desc().nullslast()
            ).limit(20).all()
            return [{
                "name": t.trend_name,
                "score": float(t.trend_score) if t.trend_score else 0,
                "category": t.category,
            } for t in trends]
        except Exception as e:
            logger.warning(f"Could not fetch trends: {e}")
            return []

    def _get_coo_inventory(self) -> List[Dict]:
        """Fetch COO fabric inventory as context (not a constraint).

        Returns available fabrics from COO module. Graceful failure returns empty list.
        """
        if not settings.coo_api_url:
            logger.info("COO_API_URL not configured - skipping inventory context")
            return []

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    f"{settings.coo_api_url}/coo/materials",
                    params={"material_type": "fabric", "limit": 100},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    materials = data.get("materials", data.get("items", []))
                    return [{
                        "name": m.get("name", m.get("material_name", "")),
                        "type": m.get("material_type", "fabric"),
                        "quantity": m.get("quantity", m.get("quantity_on_hand", 0)),
                        "unit": m.get("unit", "yards"),
                    } for m in materials]
                else:
                    logger.warning(f"COO inventory request returned {resp.status_code}")
                    return []
        except Exception as e:
            logger.warning(f"Could not fetch COO inventory: {e}")
            return []

    def _ensure_shopify_data(self) -> bool:
        """Check if ProductPerformance data is recent (<7 days old)."""
        try:
            latest = self.db.query(ProductPerformance).order_by(
                ProductPerformance.last_updated.desc().nullslast()
            ).first()
            if not latest or not latest.last_updated:
                logger.warning("No Shopify product performance data available")
                return False
            age = datetime.utcnow() - latest.last_updated
            if age > timedelta(days=7):
                logger.warning(f"Shopify data is {age.days} days old (stale)")
                return False
            return True
        except Exception as e:
            logger.warning(f"Could not check Shopify data freshness: {e}")
            return False

    def _get_season_research(self, season_id: int) -> Dict[str, str]:
        """Load all SeasonResearch records into a dict keyed by research_type."""
        records = self.db.query(SeasonResearch).filter(
            SeasonResearch.season_id == season_id
        ).all()
        return {r.research_type: r.content for r in records}

    # ==================== Idea Generation (Coordinated Looks) ====================

    def generate_product_ideas(self, season_id: int, count: int = 5) -> Optional[Dict]:
        """Generate coordinated looks for the season.

        Each look is a themed outfit of 2-4 pieces. count = number of looks (default 5),
        yielding 10-20 total product ideas.
        """
        season = self.db.query(Season).filter(Season.id == season_id).first()
        if not season:
            return None

        if not season.customer_research:
            return {"error": "Customer research not yet completed. Call /research first."}

        # Gather all context
        research_sections = self._get_season_research(season_id)
        existing_products = self._get_existing_products()
        recent_trends = self._get_recent_trends()
        coo_inventory = self._get_coo_inventory()
        shopify_fresh = self._ensure_shopify_data()

        if not self.openai_client:
            logger.warning("OpenAI not configured - generating placeholder looks")
            looks_data = self._placeholder_looks(season, count)
        else:
            looks_data = self._ai_generate_looks(
                season, count, research_sections,
                existing_products, recent_trends, coo_inventory,
            )

        # Delete existing looks+ideas for this season (regeneration)
        self.db.query(SeasonProductIdea).filter(
            SeasonProductIdea.season_id == season.id
        ).delete()
        self.db.query(SeasonLook).filter(
            SeasonLook.season_id == season.id
        ).delete()
        self.db.flush()

        # Save looks and ideas
        saved_looks = []
        all_ideas = []

        for look_data in looks_data:
            look = SeasonLook(
                season_id=season.id,
                look_number=look_data.get("look_number", len(saved_looks) + 1),
                name=look_data.get("name", f"Look {len(saved_looks) + 1}"),
                theme=look_data.get("theme", ""),
                occasion=look_data.get("occasion", ""),
                styling_notes=look_data.get("styling_notes", ""),
            )
            self.db.add(look)
            self.db.flush()

            for piece_data in look_data.get("pieces", []):
                category = piece_data.get("category", "jeans")
                sourced_ext = piece_data.get("sourced_externally", False)

                # Override AI cost estimates with manufacturing calculations
                mfg_cost = estimate_manufacturing_cost(category)
                piece_data["estimated_cost"] = mfg_cost["total_manufacturing_cost"]
                piece_data["labor_cost"] = mfg_cost["labor_cost"]
                piece_data["material_cost"] = mfg_cost["material_cost"]
                piece_data["sewing_time_minutes"] = mfg_cost["sewing_time_minutes"]

                # Validate pricing against competency module
                comp_pricing = estimate_pricing(category)

                idea = SeasonProductIdea(
                    season_id=season.id,
                    look_id=look.id,
                    title=piece_data.get("title", "Untitled"),
                    category=category,
                    subcategory=piece_data.get("subcategory"),
                    style=piece_data.get("style"),
                    description=piece_data.get("description", ""),
                    customer_fit=piece_data.get("customer_fit", ""),
                    fabric_recommendation=piece_data.get("fabric_recommendation"),
                    fabric_weight=piece_data.get("fabric_weight"),
                    fabric_weave=piece_data.get("fabric_weave"),
                    fabric_composition=piece_data.get("fabric_composition"),
                    fabric_type=piece_data.get("fabric_type"),
                    colorway=piece_data.get("colorway"),
                    sourced_externally=sourced_ext or PRODUCT_CATEGORIES.get(category, {}).get("sourced_externally", False),
                    trend_citations=piece_data.get("trend_citations"),
                    suggested_vendors=piece_data.get("suggested_vendors"),
                    suggested_retail=piece_data.get("suggested_retail") or comp_pricing.get("estimated_retail"),
                    estimated_cost=piece_data.get("estimated_cost") or comp_pricing.get("estimated_cost"),
                    estimated_margin=comp_pricing.get("estimated_margin_pct"),
                    priority=piece_data.get("priority", "medium"),
                    ai_rationale=piece_data.get("ai_rationale", ""),
                    status="pending",
                    labor_cost=piece_data.get("labor_cost"),
                    material_cost=piece_data.get("material_cost"),
                    sewing_time_minutes=piece_data.get("sewing_time_minutes"),
                )
                self.db.add(idea)
                all_ideas.append(idea)

            saved_looks.append(look)

        season.status = SeasonStatus.IDEATION
        self.db.commit()

        for look in saved_looks:
            self.db.refresh(look)
        for idea in all_ideas:
            self.db.refresh(idea)

        # Post-generation validation: check category coverage
        warnings = self._validate_category_coverage(all_ideas)

        return {
            "season_id": season.id,
            "season_name": season.name,
            "status": season.status.value,
            "shopify_data_available": shopify_fresh,
            "looks_generated": len(saved_looks),
            "ideas_generated": len(all_ideas),
            "warnings": warnings,
            "looks": [{
                "id": look.id,
                "look_number": look.look_number,
                "name": look.name,
                "theme": look.theme,
                "occasion": look.occasion,
                "styling_notes": look.styling_notes,
                "pieces": [{
                    "id": idea.id,
                    "title": idea.title,
                    "category": idea.category,
                    "subcategory": idea.subcategory,
                    "style": idea.style,
                    "fabric_recommendation": idea.fabric_recommendation,
                    "fabric_weight": idea.fabric_weight,
                    "fabric_composition": idea.fabric_composition,
                    "colorway": idea.colorway,
                    "sourced_externally": idea.sourced_externally,
                    "suggested_retail": idea.suggested_retail,
                    "estimated_cost": idea.estimated_cost,
                    "priority": idea.priority,
                } for idea in all_ideas if idea.look_id == look.id],
            } for look in saved_looks],
        }

    def _ai_generate_looks(
        self, season: Season, count: int,
        research_sections: Dict[str, str],
        existing_products: List[Dict],
        recent_trends: List[Dict],
        coo_inventory: List[Dict],
    ) -> List[Dict]:
        """Generate coordinated looks using GPT-4o grounded in research data."""

        # Build context strings
        research_context = ""
        for rtype, content in research_sections.items():
            research_context += f"\n### {rtype.replace('_', ' ').title()}\n{content}\n"

        products_context = ""
        if existing_products:
            product_lines = [
                f"  - {p['name']} (${p['revenue_30d']:,.0f}/30d, score: {p['performance_score']:.0f}, trend: {p['trend_direction']})"
                for p in existing_products[:20]
            ]
            products_context = f"\nCurrent top-selling products:\n{chr(10).join(product_lines)}\n"

        trends_context = ""
        if recent_trends:
            trend_lines = [f"  - {t['name']} (score: {t['score']:.0f}, {t['category']})" for t in recent_trends[:10]]
            trends_context = f"\nDiscovered market trends:\n{chr(10).join(trend_lines)}\n"

        inventory_context = ""
        if coo_inventory:
            inv_lines = [f"  - {m['name']}: {m['quantity']} {m['unit']}" for m in coo_inventory[:20]]
            inventory_context = f"\nCOO Fabric Inventory (available, context only - not a constraint):\n{chr(10).join(inv_lines)}\n"

        # Category summary
        cat_summary = []
        for cat_name, cat_info in PRODUCT_CATEGORIES.items():
            cost_low, cost_high = cat_info["typical_cost_range"]
            retail_low, retail_high = cat_info["typical_retail_range"]
            subs = ", ".join(cat_info.get("subcategories", []))
            ext = " [SOURCED EXTERNALLY from partners]" if cat_info.get("sourced_externally") else ""
            cat_summary.append(
                f"- {cat_name}: subcategories [{subs}], "
                f"retail ${retail_low}-${retail_high}, cost ${cost_low}-${cost_high}{ext}"
            )

        demo = season.target_demo or {}

        prompt = f"""You are the Chief Design Officer for Dearborn Denim & Apparel, a premium American-made denim and workwear brand based in Chicago. You design coordinated seasonal collections as LOOKS (outfits), not individual items.

## Research Data
{research_context}

## Target Customer
- Gender: {demo.get('gender', 'All')}
- Age: {demo.get('age_range', '25-55')}
- Income: {demo.get('income', '$75,000+')}
- Location: {demo.get('location', 'USA')}
{products_context}
{trends_context}
{inventory_context}
## Product Categories & Pricing
{chr(10).join(cat_summary)}

## Important Notes
- Dearborn manufactures in-house in Chicago: {', '.join(CAN_MAKE)}
- **Knitwear** (sweaters, cardigans, knit polos, pullovers) is sourced from external partners but included in the seasonal lineup
- Suggest ideal fabrics with specific weights and compositions — you are NOT constrained by current inventory
- Each look should be a coordinated outfit that a customer would wear together

## Your Task
Design exactly {count} coordinated LOOKS for {season.name}. Each look is a themed outfit with 2-4 pieces.

**Category coverage requirements across ALL looks combined:**
- Bottoms (jeans, denim_pants, chinos, shorts): at least 3 pieces total
- Tops (shirts, t_shirts): at least 2 pieces total
- Outerwear (denim_jackets): at least 1 piece total
- Knitwear: at least 1 piece total (sourced_externally: true)

For each LOOK provide:
- `look_number`: sequential integer starting at 1
- `name`: creative look name (e.g. "Heritage Workwear", "Weekend Rebel")
- `theme`: 1-2 sentence description of the look's vibe
- `occasion`: when/where this outfit would be worn (e.g. "weekend casual", "date night", "job site to bar")
- `styling_notes`: how to wear it, layering tips, accessories suggestions

For each PIECE within a look:
- `title`: specific product name (e.g. "Relaxed Straight Raw Selvedge Jean", not just "Jeans")
- `category`: one of: {', '.join(PRODUCT_CATEGORIES.keys())}
- `subcategory`: from the category's subcategories
- `style`: specific fit/style (e.g. "relaxed straight", "slim tapered", "trucker", "camp collar")
- `description`: 2-3 sentences about the product
- `fabric_recommendation`: specific fabric (e.g. "14oz Japanese selvedge denim", "6oz chambray")
- `fabric_weight`: weight (e.g. "14oz", "6oz", "280gsm")
- `fabric_weave`: weave type (e.g. "twill", "plain", "dobby", "knit", "selvedge twill")
- `fabric_composition`: exact blend (e.g. "98% cotton, 2% elastane", "100% organic cotton")
- `fabric_type`: "woven" or "knit"
- `colorway`: array of 2-3 color options (e.g. ["raw indigo", "rinsed black", "vintage wash"])
- `sourced_externally`: true only for knitwear
- `suggested_retail`: price within category range
- `estimated_cost`: production cost estimate
- `priority`: "high", "medium", or "low"
- `ai_rationale`: why this piece is in the collection, grounded in the research data
- `suggested_vendors`: array of suggested fabric mills/suppliers (e.g. ["Cone Denim", "Kaihara"])
- `customer_fit`: why this product fits the target customer

Return ONLY valid JSON — no markdown, no code fences. Use this exact structure:
[
  {{
    "look_number": 1,
    "name": "...",
    "theme": "...",
    "occasion": "...",
    "styling_notes": "...",
    "pieces": [
      {{
        "title": "...",
        "category": "...",
        "subcategory": "...",
        "style": "...",
        "description": "...",
        "fabric_recommendation": "...",
        "fabric_weight": "...",
        "fabric_weave": "...",
        "fabric_composition": "...",
        "fabric_type": "...",
        "colorway": ["...", "..."],
        "sourced_externally": false,
        "suggested_retail": 98,
        "estimated_cost": 26,
        "priority": "high",
        "ai_rationale": "...",
        "suggested_vendors": ["..."],
        "customer_fit": "..."
      }}
    ]
  }}
]"""

        try:
            response = self.openai_client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=5000,
            )
            content = response.choices[0].message.content

            # Parse JSON (handle markdown code blocks)
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            looks = json.loads(content.strip())
            if not isinstance(looks, list):
                looks = [looks]

            return looks

        except Exception as e:
            logger.error(f"AI look generation failed: {e}")
            return self._placeholder_looks(season, count)

    def _validate_category_coverage(self, ideas: List[SeasonProductIdea]) -> List[str]:
        """Check that generated looks cover required categories."""
        warnings = []
        categories = [i.category for i in ideas if i.category]

        bottoms = [c for c in categories if c in ("jeans", "denim_pants", "chinos", "shorts")]
        tops = [c for c in categories if c in ("shirts", "t_shirts")]
        outerwear = [c for c in categories if c in ("denim_jackets",)]
        knits = [c for c in categories if c in ("knitwear",)]

        if len(bottoms) < 3:
            warnings.append(f"Only {len(bottoms)} bottoms generated (recommended: 3+)")
        if len(tops) < 2:
            warnings.append(f"Only {len(tops)} tops generated (recommended: 2+)")
        if len(outerwear) < 1:
            warnings.append("No outerwear generated (recommended: 1+)")
        if len(knits) < 1:
            warnings.append("No knitwear generated (recommended: 1+)")

        return warnings

    # ==================== Promote & Image Generation ====================

    def promote_idea(self, idea_id: int) -> Optional[Dict]:
        """Promote a season idea into the product pipeline."""
        idea = self.db.query(SeasonProductIdea).filter(
            SeasonProductIdea.id == idea_id
        ).first()
        if not idea:
            return None

        if idea.status == "promoted":
            return {"error": "Idea already promoted", "concept_id": idea.promoted_concept_id}

        # Create a ProductOpportunity
        opp = ProductOpportunity(
            title=idea.title,
            description=idea.description,
            category=idea.category,
            trend_score=50,
            market_score=60,
            feasibility_score=85 if is_feasible(idea.category or "jeans") else 40,
            composite_score=65,
            ai_analysis=idea.customer_fit,
            estimated_retail=idea.suggested_retail,
            estimated_cost=idea.estimated_cost,
            estimated_margin=idea.estimated_margin,
            status=OpportunityStatus.SCORED,
        )
        self.db.add(opp)
        self.db.commit()
        self.db.refresh(opp)

        idea.promoted_opportunity_id = opp.id

        # Promote opportunity to concept using existing ConceptDesigner
        from .concept import ConceptDesigner
        designer = ConceptDesigner(self.db)
        concept = designer.promote_opportunity(opp.id)

        if concept:
            idea.promoted_concept_id = concept.id
            idea.status = "promoted"
            self.db.commit()

            # Publish events for cross-module awareness
            from ..event_bus import event_bus, CDOOutboundEvent

            event_bus.publish(
                CDOOutboundEvent.PRODUCT_RECOMMENDATION,
                {
                    "title": f"New Product: {idea.title}",
                    "message": f"Seasonal idea promoted to concept {concept.concept_number}",
                    "concept_id": concept.id,
                    "concept_number": concept.concept_number,
                    "category": idea.category,
                    "estimated_retail": idea.suggested_retail,
                    "estimated_cost": idea.estimated_cost,
                    "risk_level": "medium",
                },
                target_module="ceo"
            )

            event_bus.publish(
                CDOOutboundEvent.PRODUCT_PIPELINE_UPDATED,
                {
                    "title": f"New Product Entering Pipeline: {idea.title}",
                    "message": f"Product idea '{idea.title}' has been promoted to the development pipeline",
                    "concept_id": concept.id,
                    "concept_number": concept.concept_number,
                    "category": idea.category,
                    "estimated_retail": idea.suggested_retail,
                    "season_id": idea.season_id,
                },
                target_module="cmo"
            )

            return {
                "success": True,
                "idea_id": idea.id,
                "opportunity_id": opp.id,
                "concept_id": concept.id,
                "concept_number": concept.concept_number,
                "message": f"Idea '{idea.title}' promoted to concept {concept.concept_number}",
            }

        idea.status = "promoted"
        self.db.commit()

        return {
            "success": True,
            "idea_id": idea.id,
            "opportunity_id": opp.id,
            "concept_id": None,
            "message": f"Idea '{idea.title}' promoted to opportunity (concept creation pending)",
        }

    def generate_idea_image(self, idea_id: int) -> Optional[Dict]:
        """Generate a DALL-E product sketch for a seasonal idea."""
        idea = self.db.query(SeasonProductIdea).filter(
            SeasonProductIdea.id == idea_id
        ).first()
        if not idea:
            return None

        if not self.openai_client:
            logger.warning("OpenAI not configured - cannot generate image")
            return {"idea_id": idea_id, "image_url": None, "error": "OpenAI not configured"}

        prompt = (
            f"Technical fashion flat sketch of {idea.title}. "
            f"Category: {idea.category or 'clothing'}. "
            f"Clean technical flat drawing on white background, "
            f"front and back view side by side, "
            f"American workwear style, premium denim brand, "
            f"fashion design illustration, no models, no mannequins, "
            f"detailed construction lines showing stitching and hardware"
        )

        try:
            response = self.openai_client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            )
            image_url = response.data[0].url
            idea.image_url = image_url
            idea.image_prompt = prompt
            self.db.commit()
            return {"idea_id": idea.id, "image_url": image_url}
        except Exception as e:
            logger.error(f"DALL-E image generation failed for idea {idea_id}: {e}")
            return {"idea_id": idea_id, "image_url": None, "error": str(e)}

    # ==================== Placeholder/Fallback Methods ====================

    def _placeholder_customer_profile(self, season: Season, demo: Dict) -> str:
        """Generate placeholder customer profile when AI is not available."""
        gender = demo.get("gender", "Adults")
        age = demo.get("age_range", "25-55")
        income = demo.get("income", "$75,000+")
        location = demo.get("location", "USA")

        return f"""# Customer Profile: {season.name}

## Target Segment
{gender}, aged {age}, household income {income}, based in {location}.

## Lifestyle Summary
Established professionals who value quality over quantity. Disposable income
for premium purchases; prefer brands with authentic stories. Weekends spent
outdoors, at social gatherings, or on home projects.

## Shopping Habits
- Primarily online, appreciates in-store experiences
- Researches products before purchasing; reads reviews
- "Buy it for life" mentality; fewer, higher-quality items
- Loyal to brands that deliver consistent quality

## Style Preferences
- Clean, classic American style
- Versatile pieces for multiple occasions
- Earth tones, indigo, and neutrals
- Values good fit; open to different cuts

## Price Sensitivity
- Willing to pay $80-$150 for quality denim
- Perceives American-made as worth a premium
- Compares value based on durability

## Brand Affinities
- Carhartt, Faherty, Filson, Taylor Stitch
- Values manufacturing transparency
- Drawn to "Made in USA" and Chicago story

## Knitwear Preferences
- Classic fisherman sweaters, cotton cardigans
- Prefers natural fibers (cotton, wool, cashmere blends)
- Wants knits that pair with jeans and workwear

*Note: Enable OpenAI for AI-generated customer profiles.*"""

    def _placeholder_looks(self, season: Season, count: int) -> List[Dict]:
        """Generate placeholder coordinated looks when AI is not available."""
        all_looks = [
            {
                "look_number": 1,
                "name": "Heritage Workwear",
                "theme": "Classic American workwear updated with premium fabrics and modern fit",
                "occasion": "weekend casual, errands, coffee shop",
                "styling_notes": "Roll cuffs on the jeans to show selvedge ID. Layer the chore coat open over the henley.",
                "pieces": [
                    {
                        "title": f"{season.name} Relaxed Straight Selvedge Jean",
                        "category": "jeans", "subcategory": "straight", "style": "relaxed straight",
                        "description": "A relaxed straight jean in heavyweight selvedge denim. Roomy through the thigh with a straight leg.",
                        "fabric_recommendation": "14oz Japanese selvedge denim", "fabric_weight": "14oz",
                        "fabric_weave": "selvedge twill", "fabric_composition": "100% cotton",
                        "fabric_type": "woven", "colorway": ["raw indigo", "one-wash"],
                        "sourced_externally": False, "suggested_retail": 128, "estimated_cost": 32,
                        "priority": "high", "ai_rationale": "Core product in the relaxed fit trend.",
                        "suggested_vendors": ["Kaihara", "Cone Denim"],
                        "customer_fit": "Premium quality in a comfortable, modern fit.",
                    },
                    {
                        "title": "Heavyweight Pocket Henley",
                        "category": "t_shirts", "subcategory": "henley", "style": "henley",
                        "description": "A heavyweight henley in slubby cotton jersey. Three-button placket, reinforced seams.",
                        "fabric_recommendation": "8oz slub cotton jersey", "fabric_weight": "8oz",
                        "fabric_weave": "knit", "fabric_composition": "100% cotton",
                        "fabric_type": "knit", "colorway": ["natural", "navy", "olive"],
                        "sourced_externally": False, "suggested_retail": 48, "estimated_cost": 12,
                        "priority": "high", "ai_rationale": "Essential layering piece; high margin.",
                        "suggested_vendors": ["US Blanks"],
                        "customer_fit": "Foundational piece that gets better with every wash.",
                    },
                    {
                        "title": "Waxed Canvas Chore Coat",
                        "category": "denim_jackets", "subcategory": "chore", "style": "chore coat",
                        "description": "A classic chore coat in waxed canvas with corduroy collar. Four patch pockets, brass hardware.",
                        "fabric_recommendation": "10oz waxed cotton canvas", "fabric_weight": "10oz",
                        "fabric_weave": "plain", "fabric_composition": "100% cotton (waxed)",
                        "fabric_type": "woven", "colorway": ["field tan", "olive", "navy"],
                        "sourced_externally": False, "suggested_retail": 168, "estimated_cost": 45,
                        "priority": "high", "ai_rationale": "Chore coats dominate workwear outerwear.",
                        "suggested_vendors": ["Halley Stevensons"],
                        "customer_fit": "Versatile jacket from job site to dinner.",
                    },
                ],
            },
            {
                "look_number": 2,
                "name": "Smart Weekend",
                "theme": "Elevated casual for brunch, date night, or a weekend in the city",
                "occasion": "date night, brunch, city weekend",
                "styling_notes": "Tuck the shirt into the chinos. Add the sweater over shoulders if warm.",
                "pieces": [
                    {
                        "title": f"{season.name} Slim Taper Stretch Chino",
                        "category": "chinos", "subcategory": "slim", "style": "slim taper",
                        "description": "A tailored chino in stretch twill. Slim through thigh, tapered to a clean ankle.",
                        "fabric_recommendation": "8oz stretch cavalry twill", "fabric_weight": "8oz",
                        "fabric_weave": "twill", "fabric_composition": "98% cotton, 2% elastane",
                        "fabric_type": "woven", "colorway": ["khaki", "olive", "navy"],
                        "sourced_externally": False, "suggested_retail": 88, "estimated_cost": 20,
                        "priority": "high", "ai_rationale": "Every lineup needs a clean chino option.",
                        "suggested_vendors": ["Mount Vernon Mills"],
                        "customer_fit": "Step-up from jeans for the dressier occasion.",
                    },
                    {
                        "title": "Camp Collar Chambray Shirt",
                        "category": "shirts", "subcategory": "button_down", "style": "camp collar",
                        "description": "A relaxed camp collar shirt in lightweight chambray. Breezy and polished.",
                        "fabric_recommendation": "4oz cotton chambray", "fabric_weight": "4oz",
                        "fabric_weave": "plain", "fabric_composition": "100% cotton",
                        "fabric_type": "woven", "colorway": ["light indigo", "white"],
                        "sourced_externally": False, "suggested_retail": 78, "estimated_cost": 20,
                        "priority": "medium", "ai_rationale": "Camp collar trending for warm weather.",
                        "suggested_vendors": ["Albini"],
                        "customer_fit": "Effortlessly polished.",
                    },
                    {
                        "title": "Cotton Crew Sweater",
                        "category": "knitwear", "subcategory": "sweater", "style": "crew neck",
                        "description": "A midweight cotton crew sweater for layering. Clean lines, ribbed cuffs and hem.",
                        "fabric_recommendation": "12gg combed cotton knit", "fabric_weight": "280gsm",
                        "fabric_weave": "knit", "fabric_composition": "100% combed cotton",
                        "fabric_type": "knit", "colorway": ["oatmeal", "navy", "charcoal"],
                        "sourced_externally": True, "suggested_retail": 88, "estimated_cost": 28,
                        "priority": "medium", "ai_rationale": "Knitwear rounds out the offering.",
                        "suggested_vendors": ["Partner TBD"],
                        "customer_fit": "Easy layering piece that pairs with everything.",
                    },
                ],
            },
            {
                "look_number": 3,
                "name": "Trail Ready",
                "theme": "Rugged outdoor style for the customer who works hard and plays harder",
                "occasion": "hiking, camping, outdoor weekend",
                "styling_notes": "Wear the flannel open over the tee with sleeves rolled. Pair with boots.",
                "pieces": [
                    {
                        "title": "Utility Work Pant",
                        "category": "denim_pants", "subcategory": "utility", "style": "straight utility",
                        "description": "A straight-leg utility pant in duck canvas. Double-knee reinforcement, tool loop.",
                        "fabric_recommendation": "12oz duck canvas", "fabric_weight": "12oz",
                        "fabric_weave": "plain", "fabric_composition": "100% cotton",
                        "fabric_type": "woven", "colorway": ["brown duck", "stone", "black"],
                        "sourced_externally": False, "suggested_retail": 108, "estimated_cost": 28,
                        "priority": "medium", "ai_rationale": "Utility pants trending in workwear-to-casual.",
                        "suggested_vendors": ["Cone Denim"],
                        "customer_fit": "Built for real durability.",
                    },
                    {
                        "title": f"{season.name} Midweight Flannel",
                        "category": "shirts", "subcategory": "flannel", "style": "flannel",
                        "description": "A midweight brushed flannel in seasonal plaid. Button-down collar, chest pockets.",
                        "fabric_recommendation": "5oz brushed cotton flannel", "fabric_weight": "5oz",
                        "fabric_weave": "twill", "fabric_composition": "100% cotton",
                        "fabric_type": "woven", "colorway": ["red/black plaid", "green/navy plaid"],
                        "sourced_externally": False, "suggested_retail": 88, "estimated_cost": 22,
                        "priority": "medium", "ai_rationale": "Flannel is evergreen in the workwear market.",
                        "suggested_vendors": ["Portuguese Flannel"],
                        "customer_fit": "Layering essential for outdoor-minded customers.",
                    },
                ],
            },
        ]
        return all_looks[:count]
