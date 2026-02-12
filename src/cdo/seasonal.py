"""
Seasonal Design Module

Manages season-based product development workflow:
1. CEO assigns a season with target customer demographics
2. AI researches the customer segment
3. AI generates product ideas tailored to that customer and season
4. Best ideas get promoted into the existing product pipeline
"""
import json
import logging
from datetime import datetime
from typing import Optional, Dict, List

from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import (
    Season, SeasonProductIdea, SeasonStatus,
    ProductOpportunity, OpportunityStatus,
)
from .competency import CAN_MAKE, PRODUCT_CATEGORIES, estimate_pricing, is_feasible, estimate_manufacturing_cost

logger = logging.getLogger(__name__)
settings = get_settings()


class SeasonalDesigner:
    """Manages seasonal design workflow: customer research → product ideation."""

    def __init__(self, db: Session):
        self.db = db
        self._openai_client = None

    @property
    def openai_client(self):
        if self._openai_client is None and settings.openai_api_key:
            from openai import OpenAI
            self._openai_client = OpenAI(api_key=settings.openai_api_key)
        return self._openai_client

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

    def research_customer(self, season_id: int) -> Optional[Dict]:
        """Research the target customer segment using AI."""
        season = self.db.query(Season).filter(Season.id == season_id).first()
        if not season:
            return None

        season.status = SeasonStatus.RESEARCHING
        self.db.commit()

        demo = season.target_demo or {}

        if not self.openai_client:
            logger.warning("OpenAI not configured — generating placeholder research")
            research = self._placeholder_research(season, demo)
        else:
            research = self._ai_research(season, demo)

        season.customer_research = research
        season.status = SeasonStatus.RESEARCH_COMPLETE
        self.db.commit()

        return {
            "season_id": season.id,
            "season_name": season.name,
            "status": season.status.value,
            "customer_research": research,
        }

    def generate_product_ideas(self, season_id: int, count: int = 8) -> Optional[Dict]:
        """Generate product ideas for the season based on customer research."""
        season = self.db.query(Season).filter(Season.id == season_id).first()
        if not season:
            return None

        if not season.customer_research:
            return {"error": "Customer research not yet completed. Call /research first."}

        if not self.openai_client:
            logger.warning("OpenAI not configured — generating placeholder ideas")
            ideas = self._placeholder_ideas(season)
        else:
            ideas = self._ai_generate_ideas(season, count)

        # Override AI cost estimates with real manufacturing calculations
        for idea_data in ideas:
            category = idea_data.get("category", "jeans")
            mfg_cost = estimate_manufacturing_cost(category)
            idea_data["estimated_cost"] = mfg_cost["total_manufacturing_cost"]
            idea_data["labor_cost"] = mfg_cost["labor_cost"]
            idea_data["material_cost"] = mfg_cost["material_cost"]
            idea_data["sewing_time_minutes"] = mfg_cost["sewing_time_minutes"]

        # Save ideas to DB
        saved_ideas = []
        for idea_data in ideas:
            # Validate pricing against competency module
            category = idea_data.get("category", "jeans")
            comp_pricing = estimate_pricing(category)

            idea = SeasonProductIdea(
                season_id=season.id,
                title=idea_data.get("title", "Untitled"),
                category=category,
                subcategory=idea_data.get("subcategory"),
                description=idea_data.get("description", ""),
                customer_fit=idea_data.get("customer_fit", ""),
                suggested_retail=idea_data.get("suggested_retail") or comp_pricing.get("estimated_retail"),
                estimated_cost=idea_data.get("estimated_cost") or comp_pricing.get("estimated_cost"),
                estimated_margin=comp_pricing.get("estimated_margin_pct"),
                priority=idea_data.get("priority", "medium"),
                ai_rationale=idea_data.get("ai_rationale", ""),
                status="pending",
                labor_cost=idea_data.get("labor_cost"),
                material_cost=idea_data.get("material_cost"),
                sewing_time_minutes=idea_data.get("sewing_time_minutes"),
            )
            self.db.add(idea)
            saved_ideas.append(idea)

        season.status = SeasonStatus.IDEATION
        self.db.commit()

        for idea in saved_ideas:
            self.db.refresh(idea)

        return {
            "season_id": season.id,
            "season_name": season.name,
            "status": season.status.value,
            "ideas_generated": len(saved_ideas),
            "ideas": [{
                "id": i.id,
                "title": i.title,
                "category": i.category,
                "subcategory": i.subcategory,
                "description": i.description,
                "customer_fit": i.customer_fit,
                "suggested_retail": i.suggested_retail,
                "estimated_cost": i.estimated_cost,
                "estimated_margin": i.estimated_margin,
                "priority": i.priority,
            } for i in saved_ideas],
        }

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

            # Notify CEO for approval tracking
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

            # Notify CMO for marketing awareness
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

    def _get_existing_products(self) -> List[Dict]:
        """Get existing product catalog for context in brainstorming."""
        from ..db import ProductPerformance
        try:
            products = self.db.query(ProductPerformance).order_by(
                ProductPerformance.revenue_30d.desc().nullslast()
            ).limit(50).all()
            return [{
                "name": p.product_name,
                "sku": p.sku,
                "revenue_30d": float(p.revenue_30d) if p.revenue_30d else 0,
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

    def generate_idea_image(self, idea_id: int) -> Optional[Dict]:
        """Generate a DALL-E product sketch for a seasonal idea."""
        idea = self.db.query(SeasonProductIdea).filter(
            SeasonProductIdea.id == idea_id
        ).first()
        if not idea:
            return None

        if not self.openai_client:
            logger.warning("OpenAI not configured — cannot generate image")
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

    # ==================== AI Methods ====================

    def _ai_research(self, season: Season, demo: Dict) -> str:
        """Generate customer research using OpenAI."""
        prompt = f"""You are a consumer researcher for Dearborn Denim & Apparel, a premium
American-made denim and workwear brand based in Chicago, Illinois. They manufacture
all products in their own factory. Price range is $48-$178 depending on the garment.

Research the following customer segment for our {season.name} line:

- Gender: {demo.get('gender', 'All')}
- Age Range: {demo.get('age_range', '25-55')}
- Income: {demo.get('income', '$75,000+')}
- Location: {demo.get('location', 'USA')}
- Description: {demo.get('description', 'Quality-conscious consumers')}

Provide a comprehensive customer profile covering:

1. **Lifestyle Summary** — How they spend their time, work/life balance, hobbies
2. **Shopping Habits** — Where they shop, online vs in-store, purchase frequency, brand loyalty
3. **Style Preferences** — Casual vs dressed up, fit preferences, color preferences for this season
4. **Price Sensitivity** — What they're willing to pay for quality denim/workwear, value perception
5. **Brand Affinities** — Other brands they likely wear, what draws them to premium American-made
6. **What They Want from Denim/Workwear** — Durability, comfort, versatility, sustainability
7. **{season.name}-Specific Needs** — What this season means for their wardrobe, key occasions, weather considerations

Write in a practical, business-oriented tone. Be specific with actionable insights."""

        try:
            response = self.openai_client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"AI customer research failed: {e}")
            return self._placeholder_research(season, demo)

    def _ai_generate_ideas(self, season: Season, count: int) -> List[Dict]:
        """Generate product ideas using OpenAI."""
        # Gather context: existing products and trends
        existing_products = self._get_existing_products()
        recent_trends = self._get_recent_trends()

        products_context = ""
        if existing_products:
            product_lines = [f"  - {p['name']} (SKU: {p['sku']}, 30-day revenue: ${p['revenue_30d']:,.0f})" for p in existing_products[:20]]
            products_context = f"""
Our current product catalog (top sellers):
{chr(10).join(product_lines)}
"""

        trends_context = ""
        if recent_trends:
            trend_lines = [f"  - {t['name']} (score: {t['score']:.0f}, category: {t['category']})" for t in recent_trends[:10]]
            trends_context = f"""
Current market trends we're tracking:
{chr(10).join(trend_lines)}
"""

        # Build category summary for the prompt
        cat_summary = []
        for cat_name, cat_info in PRODUCT_CATEGORIES.items():
            cost_low, cost_high = cat_info["typical_cost_range"]
            retail_low, retail_high = cat_info["typical_retail_range"]
            subs = ", ".join(cat_info.get("subcategories", []))
            cat_summary.append(
                f"- {cat_name}: subcategories [{subs}], "
                f"retail ${retail_low}-${retail_high}, cost ${cost_low}-${cost_high}"
            )

        demo = season.target_demo or {}

        prompt = f"""You are the Chief Design Officer for Dearborn Denim & Apparel, a premium
American-made denim and workwear brand based in Chicago.

Based on this customer research:
{season.customer_research}

Target customer: {demo.get('gender', 'All')}, age {demo.get('age_range', '25-55')}, income {demo.get('income', '$75,000+')}, {demo.get('location', 'USA')}
Season: {season.name}
{products_context}
{trends_context}
Dearborn can manufacture these product types: {', '.join(CAN_MAKE)}

Product categories with pricing:
{chr(10).join(cat_summary)}

Based on our current product lineup and market trends, suggest a mix of:
- Variations/updates to our existing top sellers (e.g., new fabric, new fit, seasonal version)
- New products similar to what we already make that fill gaps in our lineup

For each suggestion, indicate whether it's a "variation" of an existing product or a "new" product.

Suggest exactly {count} specific products for this season. For each product, provide:
- title: A specific product name (e.g. "Summer Stretch Slim Jean" not just "Jeans")
- category: Must be one of: {', '.join(PRODUCT_CATEGORIES.keys())}
- subcategory: From the subcategories listed above
- description: 2-3 sentences about the product
- customer_fit: Why this product is perfect for the target customer
- suggested_retail: Retail price (must be within the category's range)
- estimated_cost: Production cost estimate
- priority: "high", "medium", or "low"
- ai_rationale: Brief reasoning for including this in the seasonal lineup

Return ONLY a valid JSON array with no additional text. Example format:
[{{"title": "...", "category": "...", "subcategory": "...", "description": "...", "customer_fit": "...", "suggested_retail": 98, "estimated_cost": 26, "priority": "high", "ai_rationale": "..."}}]"""

        try:
            response = self.openai_client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=3000,
            )
            content = response.choices[0].message.content

            # Parse JSON from response (handle markdown code blocks)
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            ideas = json.loads(content.strip())
            if not isinstance(ideas, list):
                ideas = [ideas]

            return ideas

        except Exception as e:
            logger.error(f"AI product idea generation failed: {e}")
            return self._placeholder_ideas(season)

    # ==================== Fallback Methods ====================

    def _placeholder_research(self, season: Season, demo: Dict) -> str:
        """Generate placeholder research when OpenAI is not available."""
        gender = demo.get("gender", "Adults")
        age = demo.get("age_range", "25-55")
        income = demo.get("income", "$75,000+")
        location = demo.get("location", "USA")

        return f"""# Customer Research: {season.name}

## Target Segment
{gender}, aged {age}, household income {income}, based in {location}.

## Lifestyle Summary
This customer segment consists of established professionals who value quality over quantity.
They have disposable income for premium purchases and prefer brands with authentic stories.
They spend weekends outdoors, at social gatherings, or working on projects around the home.

## Shopping Habits
- Primarily shops online but appreciates in-store experiences
- Researches products before purchasing; reads reviews
- Buys fewer, higher-quality items; "buy it for life" mentality
- Loyal to brands that deliver consistent quality

## Style Preferences
- Clean, classic American style — not trendy but not dated
- Prefers versatile pieces that work for multiple occasions
- Gravitates toward earth tones, indigo, and neutral colors
- Values good fit; willing to try different cuts

## Price Sensitivity
- Willing to pay $80-$150 for quality denim
- Perceives American-made as worth a premium
- Compares value based on durability, not just upfront cost

## Brand Affinities
- Respects brands like Carhartt, Faherty, and Filson
- Values transparency in manufacturing
- Drawn to "Made in USA" and Chicago craftsmanship story

## What They Want from Denim/Workwear
- Durability that holds up to active lifestyles
- Comfort for all-day wear
- Versatility — office to weekend without changing
- Sustainable and ethical manufacturing

## {season.name}-Specific Needs
- Lighter weight fabrics for warm weather
- Breathable materials
- Casual styling for outdoor activities
- Versatile pieces for travel and vacations

*Note: This is a template profile. Enable OpenAI for AI-generated research.*"""

    def _placeholder_ideas(self, season: Season) -> List[Dict]:
        """Generate placeholder product ideas when OpenAI is not available."""
        demo = season.target_demo or {}
        gender = demo.get("gender", "Unisex")

        return [
            {
                "title": f"{season.name} Lightweight Stretch Jean",
                "category": "jeans",
                "subcategory": "straight",
                "description": f"A lightweight stretch denim jean built for {season.name.lower()} comfort. "
                               "Features breathable fabric with just enough stretch for all-day wear.",
                "customer_fit": f"Perfect for {gender.lower()} who want premium denim that doesn't overheat in warm weather.",
                "suggested_retail": 98,
                "estimated_cost": 26,
                "priority": "high",
                "ai_rationale": "Core product updated for seasonal needs.",
            },
            {
                "title": f"{season.name} Chino Short",
                "category": "shorts",
                "subcategory": "chino",
                "description": "A tailored chino short in lightweight twill. Clean enough for a patio dinner, "
                               "tough enough for yard work.",
                "customer_fit": "Versatile warm-weather essential for the quality-conscious customer.",
                "suggested_retail": 68,
                "estimated_cost": 16,
                "priority": "high",
                "ai_rationale": "Shorts are essential for summer and high-margin.",
            },
            {
                "title": f"{season.name} Camp Collar Shirt",
                "category": "shirts",
                "subcategory": "button_down",
                "description": "A relaxed camp collar shirt in a breezy cotton-linen blend. "
                               "Classic Americana meets warm-weather ease.",
                "customer_fit": "Bridges the gap between casual and polished for weekend outings.",
                "suggested_retail": 78,
                "estimated_cost": 20,
                "priority": "medium",
                "ai_rationale": "Camp collar trending for summer casual wear.",
            },
            {
                "title": f"Dearborn Pocket Tee",
                "category": "t_shirts",
                "subcategory": "pocket_tee",
                "description": "A heavyweight pocket tee in premium American cotton. "
                               "The kind of t-shirt that gets better with every wash.",
                "customer_fit": "Foundational layering piece that signals quality without trying too hard.",
                "suggested_retail": 38,
                "estimated_cost": 10,
                "priority": "medium",
                "ai_rationale": "Low cost, high margin, repeat purchase potential.",
            },
        ]
