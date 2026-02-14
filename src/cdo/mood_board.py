"""
Mood Board Generator

Generates product mood boards using:
- OpenAI Responses API with web_search for reference images
- GPT Image 1.5 for design variation sketches
- GPT-4o for written design specifications

Each mood board contains:
1. Reference images: real product photos, fabric swatches, hardware details
2. Design sketches: AI-generated variations (different pockets, trims, fits)
3. Design specs: written construction decisions, fabric rationale, hardware choices
"""
import base64
import json
import logging
from datetime import datetime
from typing import Optional, Dict, List

from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SeasonProductIdea, MoodBoard

logger = logging.getLogger(__name__)
settings = get_settings()

# Design variation templates per product category
VARIATION_TEMPLATES = {
    "jeans": {
        "variations": [
            {
                "name": "Heritage",
                "focus": "classic American workwear details",
                "details": "western scoop front pockets, decorative arc-stitched back pockets, exposed copper rivets at all stress points, button fly with branded tack buttons, gold contrast topstitching throughout, leather back patch on waistband, chain-stitch hem",
            },
            {
                "name": "Minimal",
                "focus": "clean modern Japanese-inspired details",
                "details": "clean welt front pockets with no topstitching, plain back pockets with single bar-tack only, matte black hardware, hidden button fly, tonal thread throughout, raw unhemmed edge, no branding visible",
            },
            {
                "name": "Utility",
                "focus": "functional workwear details",
                "details": "reinforced double-knee panels, cargo pocket on right thigh, hammer loop on left leg, tool pocket inside waistband, heavy-duty brass zipper fly, triple-stitched seams, reflective safety stitching option",
            },
        ],
        "search_queries": [
            "{title} premium selvedge jean product photo",
            "selvedge denim fabric swatch texture closeup",
            "copper rivets jeans hardware detail",
            "chain stitch hem selvedge denim detail",
            "arc stitch back pocket jeans design",
        ],
    },
    "denim_pants": {
        "variations": [
            {
                "name": "Classic Carpenter",
                "focus": "traditional carpenter pant details",
                "details": "hammer loop, rule pocket on right leg, double tool pockets, reinforced knees, brass hardware",
            },
            {
                "name": "Modern Utility",
                "focus": "updated utility pant details",
                "details": "articulated knees, gusseted crotch, zippered cargo pockets, reflective pulls, DWR-coated fabric",
            },
            {
                "name": "Slim Work",
                "focus": "tailored workwear silhouette",
                "details": "tapered leg, hidden phone pocket, stretch panel at waistband, magnetic closures, clean front",
            },
        ],
        "search_queries": [
            "{title} carpenter pant product photo",
            "duck canvas fabric swatch texture",
            "utility pant hardware detail brass",
            "double knee work pant construction",
        ],
    },
    "chinos": {
        "variations": [
            {
                "name": "Classic",
                "focus": "timeless chino details",
                "details": "slant front pockets, single welt back pockets with button, hook-and-bar closure, split waistband, pick stitching on seams",
            },
            {
                "name": "Casual",
                "focus": "relaxed weekend chino",
                "details": "on-seam side pockets, patch back pockets, drawstring waist option, rolled cuff hem, garment-dyed finish",
            },
            {
                "name": "Tailored",
                "focus": "dress chino details",
                "details": "french bearer with extended tab, double welt back pockets, curtain waistband, blind hem, side adjusters instead of belt loops",
            },
        ],
        "search_queries": [
            "{title} premium chino product photo",
            "cavalry twill fabric swatch texture",
            "chino pocket detail construction",
        ],
    },
    "shirts": {
        "variations": [
            {
                "name": "Heritage Workwear",
                "focus": "classic work shirt details",
                "details": "button-down collar, two chest pockets with flap and button, pen slot in left pocket, gusseted side seams, back yoke with box pleat, cat-eye buttons",
            },
            {
                "name": "Camp Collar",
                "focus": "relaxed resort-inspired details",
                "details": "open camp collar, single chest pocket, straight hem (no tails), coconut buttons, side vents, relaxed boxy fit",
            },
            {
                "name": "Western",
                "focus": "classic western shirt details",
                "details": "pointed yoke front and back, snap closures throughout, smile pockets with scallop flaps, pearl snaps, slim fit through body",
            },
        ],
        "search_queries": [
            "{title} premium shirt product photo",
            "chambray fabric swatch texture closeup",
            "work shirt pocket detail construction",
            "pearl snap western shirt hardware",
        ],
    },
    "denim_jackets": {
        "variations": [
            {
                "name": "Classic Trucker",
                "focus": "Type III trucker jacket details",
                "details": "pointed chest pockets with button flap, waist tabs with button adjustment, single-point back yoke, button cuffs, brass shank buttons, pleated back",
            },
            {
                "name": "Chore Coat",
                "focus": "French workwear chore coat details",
                "details": "four large patch pockets, standing collar, three-button front, adjustable button cuff tabs, blanket lining, side entry pockets hidden behind patch pockets",
            },
            {
                "name": "Sherpa-Lined",
                "focus": "insulated trucker details",
                "details": "sherpa pile lining in body and collar, corduroy-lined collar, hand-warmer pockets at waist, inside security pocket, insulated sleeves, brass zipper option",
            },
        ],
        "search_queries": [
            "{title} premium denim jacket product photo",
            "selvedge denim jacket fabric detail",
            "brass shank buttons jacket hardware",
            "sherpa lining denim jacket interior",
        ],
    },
    "t_shirts": {
        "variations": [
            {
                "name": "Classic Crew",
                "focus": "premium basics details",
                "details": "tubular knit construction (no side seams), ribbed crew neck, double-needle hem at sleeves and bottom, taped shoulder seams, heavyweight 6oz+ cotton",
            },
            {
                "name": "Henley",
                "focus": "layering henley details",
                "details": "three-button placket with reinforced bartack, rib-knit collar, raglan sleeve option, extended length for tucking, slub texture",
            },
            {
                "name": "Pocket Tee",
                "focus": "elevated pocket tee details",
                "details": "chest pocket with bartack corners, drop-tail hem, reinforced shoulder seams, contrast stitching option, garment-dyed finish",
            },
        ],
        "search_queries": [
            "{title} premium heavyweight t-shirt product photo",
            "slub cotton jersey fabric texture closeup",
            "henley placket button detail",
        ],
    },
    "knitwear": {
        "variations": [
            {
                "name": "Fisherman",
                "focus": "traditional cable knit details",
                "details": "cable knit panels on chest, ribbed cuffs and hem, saddle shoulder construction, crew neck with rib trim, heavyweight wool blend",
            },
            {
                "name": "Cotton Crew",
                "focus": "clean everyday knit",
                "details": "fine gauge cotton knit, clean seaming, ribbed cuffs and hem, relaxed fit, garment-washed for softness",
            },
            {
                "name": "Cardigan",
                "focus": "layering cardigan details",
                "details": "shawl collar, five-button front, patch pockets at waist, elbow patches option, ribbed cuffs, mid-weight for layering",
            },
        ],
        "search_queries": [
            "{title} premium knitwear product photo",
            "cable knit sweater texture detail",
            "cotton cardigan button detail",
        ],
    },
}

# Default for categories not explicitly listed
DEFAULT_VARIATIONS = {
    "variations": [
        {"name": "Classic", "focus": "traditional design", "details": "clean construction, quality hardware, classic silhouette"},
        {"name": "Modern", "focus": "updated contemporary", "details": "streamlined details, minimal branding, current fit"},
        {"name": "Utility", "focus": "functional design", "details": "extra pockets, reinforced areas, durable hardware"},
    ],
    "search_queries": [
        "{title} premium product photo",
        "{category} construction detail",
    ],
}


class MoodBoardGenerator:
    """Generates mood boards using Perplexity (search) + OpenAI (images/specs)."""

    def __init__(self, db: Session):
        self.db = db
        self._openai_client = None
        self._perplexity_client = None

    @property
    def openai_client(self):
        if self._openai_client is None and settings.openai_api_key:
            from openai import OpenAI
            self._openai_client = OpenAI(api_key=settings.openai_api_key)
        return self._openai_client

    @property
    def perplexity_client(self):
        if self._perplexity_client is None and settings.perplexity_api_key:
            from openai import OpenAI
            self._perplexity_client = OpenAI(
                api_key=settings.perplexity_api_key,
                base_url="https://api.perplexity.ai",
            )
        return self._perplexity_client

    def generate_mood_board(self, idea_id: int) -> Optional[Dict]:
        """Generate a full mood board for a product idea."""
        idea = self.db.query(SeasonProductIdea).filter(
            SeasonProductIdea.id == idea_id
        ).first()
        if not idea:
            return None

        if not self.openai_client:
            return {"idea_id": idea_id, "error": "OpenAI not configured"}

        # Get or create mood board record
        mood_board = self.db.query(MoodBoard).filter(
            MoodBoard.idea_id == idea_id
        ).first()

        if not mood_board:
            mood_board = MoodBoard(idea_id=idea_id, status="generating")
            self.db.add(mood_board)
            self.db.commit()
            self.db.refresh(mood_board)
        else:
            mood_board.status = "generating"
            mood_board.error = None
            self.db.commit()

        try:
            # Step 1: Find reference images via web search
            reference_images = self._search_reference_images(idea)

            # Step 2: Generate design variation sketches
            design_sketches = self._generate_design_sketches(idea)

            # Step 3: Generate written design specs
            design_specs = self._generate_design_specs(idea)

            # Save to DB
            mood_board.reference_images = reference_images
            mood_board.design_sketches = design_sketches
            mood_board.design_specs = design_specs
            mood_board.status = "complete"
            mood_board.updated_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(mood_board)

            return self._serialize_mood_board(mood_board, idea)

        except Exception as e:
            logger.error(f"Mood board generation failed for idea {idea_id}: {e}")
            mood_board.status = "failed"
            mood_board.error = str(e)
            self.db.commit()
            return {"idea_id": idea_id, "error": str(e)}

    def _search_reference_images(self, idea: SeasonProductIdea) -> List[Dict]:
        """Find reference product images using Perplexity Sonar (web-grounded search).

        Falls back to OpenAI Responses API web_search if Perplexity is not configured.
        """
        category = idea.category or "clothing"

        prompt = f"""Find specific product pages and detail photos for a product mood board.

Product: {idea.title}
Category: {category}
Style: {idea.style or 'classic'}
Fabric: {idea.fabric_recommendation or 'premium fabric'}
Description: {idea.description or ''}

Find real product pages from premium brands that serve as design references. I need:

1. **2-3 similar products** from brands like Taylor Stitch, 3sixteen, Rogue Territory, Iron Heart, Faherty, Filson, Carhartt WIP, Buck Mason — products with similar fit, fabric, or construction
2. **1-2 fabric references** — product pages or supplier pages showing the specific fabric type ({idea.fabric_recommendation or category + ' fabric'}) up close
3. **1-2 hardware/construction details** — pages showing relevant hardware (rivets, buttons, zippers) or construction techniques (stitching, pocket styles, seam types)

For each reference, provide:
- The exact product page URL
- Product/page title
- What it shows: product_reference, fabric_swatch, hardware_detail, or construction_detail
- Why it's relevant to this design (one sentence)

Return as a JSON array:
[
  {{"url": "https://...", "title": "...", "category": "product_reference", "caption": "..."}}
]

Return ONLY the JSON array, no other text."""

        # Try Perplexity first (best for web-grounded search with citations)
        if self.perplexity_client:
            result = self._search_with_perplexity(prompt)
            if result:
                return result

        # Fall back to OpenAI web_search
        if self.openai_client:
            result = self._search_with_openai(prompt)
            if result:
                return result

        logger.warning("No search provider available for reference images")
        return []

    def _search_with_perplexity(self, prompt: str) -> Optional[List[Dict]]:
        """Search using Perplexity Sonar — returns citations with URLs."""
        try:
            response = self.perplexity_client.chat.completions.create(
                model="sonar",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
            )
            content = response.choices[0].message.content

            # Extract citations from Perplexity response
            citations = []
            if hasattr(response, 'citations') and response.citations:
                citations = [{"url": c, "title": c} for c in response.citations]

            # Parse the JSON response
            images = self._parse_reference_json(content)

            if images:
                # Merge in Perplexity citations that aren't already listed
                existing_urls = {img.get("url", "") for img in images}
                for citation in citations:
                    if citation["url"] not in existing_urls:
                        images.append({
                            "url": citation["url"],
                            "title": citation["title"],
                            "category": "product_reference",
                            "caption": f"Reference: {citation['title']}",
                            "source": "perplexity_citation",
                        })
                return images[:12]

            # If JSON parsing failed, return just citations
            if citations:
                return [{
                    "url": c["url"],
                    "title": c["title"],
                    "category": "product_reference",
                    "caption": f"Reference: {c['title']}",
                    "source": "perplexity_citation",
                } for c in citations[:8]]

            return None

        except Exception as e:
            logger.warning(f"Perplexity search failed: {e}")
            return None

    def _search_with_openai(self, prompt: str) -> Optional[List[Dict]]:
        """Search using OpenAI Responses API with web_search tool."""
        try:
            response = self.openai_client.responses.create(
                model="gpt-4o",
                tools=[{"type": "web_search"}],
                input=prompt,
            )

            # Extract text content from response
            result_text = ""
            citations = []
            for item in response.output:
                if hasattr(item, 'content'):
                    for content_block in item.content:
                        if hasattr(content_block, 'text'):
                            result_text = content_block.text
                        if hasattr(content_block, 'annotations'):
                            for ann in content_block.annotations:
                                if hasattr(ann, 'url'):
                                    citations.append({
                                        "url": ann.url,
                                        "title": getattr(ann, 'title', ''),
                                    })

            images = self._parse_reference_json(result_text)

            if images:
                existing_urls = {img.get("url", "") for img in images}
                for citation in citations:
                    if citation["url"] not in existing_urls:
                        images.append({
                            "url": citation["url"],
                            "title": citation["title"],
                            "category": "product_reference",
                            "caption": f"Reference: {citation['title']}",
                            "source": "openai_citation",
                        })
                return images[:12]

            if citations:
                return [{
                    "url": c["url"],
                    "title": c["title"],
                    "category": "product_reference",
                    "caption": f"Reference: {c['title']}",
                    "source": "openai_citation",
                } for c in citations[:8]]

            return None

        except Exception as e:
            logger.warning(f"OpenAI web search failed: {e}")
            return None

    def _parse_reference_json(self, text: str) -> Optional[List[Dict]]:
        """Parse JSON array of reference images from AI response text."""
        try:
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            result = json.loads(text.strip())
            if isinstance(result, list):
                return result
        except (json.JSONDecodeError, IndexError):
            pass
        return None

    def _generate_design_sketches(self, idea: SeasonProductIdea) -> List[Dict]:
        """Generate design variation sketches using GPT Image 1.5."""
        category = idea.category or "clothing"
        templates = VARIATION_TEMPLATES.get(category, DEFAULT_VARIATIONS)
        variations = templates["variations"]

        sketches = []
        for variation in variations:
            prompt = (
                f"Technical fashion flat sketch on pure white background. "
                f"Product: {idea.title}. "
                f"Variation: {variation['name']} - {variation['focus']}. "
                f"Specific details: {variation['details']}. "
                f"Fabric: {idea.fabric_recommendation or 'premium fabric'}. "
                f"Show front view only, clean precise line drawing, "
                f"thin black lines on white background, "
                f"fashion technical flat illustration style, "
                f"no shading, no color fill, no models, no mannequins. "
                f"Do NOT include any text, labels, or words in the image."
            )

            try:
                response = self.openai_client.images.generate(
                    model="gpt-image-1",
                    prompt=prompt,
                    size="1024x1024",
                    quality="medium",
                )

                # GPT Image returns base64
                image_b64 = response.data[0].b64_json
                sketches.append({
                    "image_data": image_b64,
                    "prompt": prompt,
                    "variation_name": variation["name"],
                    "description": f"{variation['name']}: {variation['focus']}",
                    "details": variation["details"],
                })
                logger.info(f"Generated {variation['name']} sketch for {idea.title}")

            except Exception as e:
                logger.error(f"Sketch generation failed for {variation['name']}: {e}")
                sketches.append({
                    "image_data": None,
                    "prompt": prompt,
                    "variation_name": variation["name"],
                    "description": f"{variation['name']}: {variation['focus']}",
                    "details": variation["details"],
                    "error": str(e),
                })

        return sketches

    def _generate_design_specs(self, idea: SeasonProductIdea) -> Dict:
        """Generate written design specifications using GPT-4o."""
        category = idea.category or "clothing"
        templates = VARIATION_TEMPLATES.get(category, DEFAULT_VARIATIONS)
        variation_names = [v["name"] for v in templates["variations"]]

        prompt = f"""You are the Chief Design Officer for Dearborn Denim & Apparel, a premium American-made denim and workwear brand. Write detailed design specifications for this product.

Product: {idea.title}
Category: {category}
Style: {idea.style or 'classic'}
Fabric: {idea.fabric_recommendation or 'premium fabric'}
Fabric Weight: {idea.fabric_weight or 'standard'}
Fabric Composition: {idea.fabric_composition or 'cotton blend'}
Description: {idea.description or ''}

Write specifications covering these sections. Be specific to THIS product - reference actual construction methods, stitch types, hardware part numbers where possible.

1. **Construction Decisions**: How this garment should be assembled. Seam types (flat-felled, lap, welt), stitch types (301 lockstitch, 401 chain, 504 overlock), thread specifications (Tex 70 poly-core for topstitch, Tex 40 for seaming). Order of operations for the sewing floor.

2. **Fabric Rationale**: Why this specific fabric was chosen. Weight, hand feel, expected shrinkage and how to account for it, any special finishing (sanforized, garment wash, enzyme wash). Grainline considerations for cutting.

3. **Hardware & Trim Specifications**: Exact hardware choices. Rivet type and plating (brass, copper, matte black), button style and size, zipper brand and type (YKK #5 brass), label placement, care labels, hang tags.

4. **Fit & Sizing Notes**: How this garment should fit on body. Key measurement points, ease allowances, where the garment should hit (rise height, inseam break, jacket length). Grading rules between sizes.

5. **Design Variation Notes**: Compare the {', '.join(variation_names)} variations. For each variation, explain what makes it distinct and which customer segment it targets. Recommend which variation should be the lead style.

Return as JSON:
{{
  "construction_decisions": "...",
  "fabric_rationale": "...",
  "hardware_specs": "...",
  "fit_notes": "...",
  "design_variations": "...",
  "recommended_lead_style": "..."
}}

Return ONLY the JSON object."""

        try:
            response = self.openai_client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=3000,
            )
            content = response.choices[0].message.content

            # Parse JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            specs = json.loads(content.strip())
            return specs

        except Exception as e:
            logger.error(f"Design specs generation failed: {e}")
            return {
                "construction_decisions": f"Error generating specs: {e}",
                "fabric_rationale": "",
                "hardware_specs": "",
                "fit_notes": "",
                "design_variations": "",
                "recommended_lead_style": "",
            }

    def get_mood_board(self, idea_id: int) -> Optional[Dict]:
        """Retrieve an existing mood board."""
        idea = self.db.query(SeasonProductIdea).filter(
            SeasonProductIdea.id == idea_id
        ).first()
        if not idea:
            return None

        mood_board = self.db.query(MoodBoard).filter(
            MoodBoard.idea_id == idea_id
        ).first()

        if not mood_board:
            return {"idea_id": idea_id, "status": "not_generated"}

        return self._serialize_mood_board(mood_board, idea)

    def _serialize_mood_board(self, mb: MoodBoard, idea: SeasonProductIdea) -> Dict:
        """Serialize mood board for API response."""
        # For design sketches, convert base64 to data URLs for easy frontend use
        sketches = []
        for sketch in (mb.design_sketches or []):
            s = {
                "variation_name": sketch.get("variation_name", ""),
                "description": sketch.get("description", ""),
                "details": sketch.get("details", ""),
                "prompt": sketch.get("prompt", ""),
            }
            if sketch.get("image_data"):
                s["image_url"] = f"data:image/png;base64,{sketch['image_data']}"
            elif sketch.get("error"):
                s["error"] = sketch["error"]
            sketches.append(s)

        return {
            "id": mb.id,
            "idea_id": idea.id,
            "idea_title": idea.title,
            "idea_category": idea.category,
            "status": mb.status,
            "reference_images": mb.reference_images or [],
            "design_sketches": sketches,
            "design_specs": mb.design_specs or {},
            "error": mb.error,
            "created_at": mb.created_at.isoformat() if mb.created_at else None,
            "updated_at": mb.updated_at.isoformat() if mb.updated_at else None,
        }
