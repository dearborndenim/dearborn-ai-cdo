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
    """Generates mood boards using OpenAI APIs."""

    def __init__(self, db: Session):
        self.db = db
        self._openai_client = None

    @property
    def openai_client(self):
        if self._openai_client is None and settings.openai_api_key:
            from openai import OpenAI
            self._openai_client = OpenAI(api_key=settings.openai_api_key)
        return self._openai_client

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
        """Use OpenAI Responses API with web_search to find reference product images."""
        category = idea.category or "clothing"
        templates = VARIATION_TEMPLATES.get(category, DEFAULT_VARIATIONS)
        search_queries = templates["search_queries"]

        # Format queries with idea details
        formatted_queries = []
        for q in search_queries:
            formatted = q.format(
                title=idea.title or "",
                category=category,
            )
            formatted_queries.append(formatted)

        # Use Responses API with web_search tool to find reference images
        prompt = f"""You are researching reference images for a product mood board.

Product: {idea.title}
Category: {category}
Style: {idea.style or 'classic'}
Fabric: {idea.fabric_recommendation or 'premium fabric'}
Description: {idea.description or ''}

Search the web for real product images that would serve as reference/inspiration for this product design. Find:

1. **Similar products** from premium brands (Taylor Stitch, Faherty, Filson, Iron Heart, 3sixteen, Rogue Territory)
2. **Fabric closeups** showing the specific fabric type and texture
3. **Hardware details** (rivets, buttons, zippers, snaps) relevant to this product
4. **Construction details** (stitching, pocket styles, seam types) that are relevant

For each image you find, provide:
- The page URL where you found it
- A descriptive title
- What design element it represents (product_reference, fabric_swatch, hardware_detail, construction_detail)
- A brief caption explaining why it's relevant

Return your findings as a JSON array:
[
  {{"url": "page_url", "title": "...", "category": "product_reference|fabric_swatch|hardware_detail|construction_detail", "caption": "..."}}
]

Find at least 5-8 reference images. Return ONLY the JSON array."""

        try:
            response = self.openai_client.responses.create(
                model="gpt-4o",
                tools=[{"type": "web_search"}],
                input=prompt,
            )

            # Extract the text content from the response
            result_text = ""
            for item in response.output:
                if hasattr(item, 'content'):
                    for content_block in item.content:
                        if hasattr(content_block, 'text'):
                            result_text = content_block.text
                            break

            # Also collect URL citations from annotations
            citations = []
            for item in response.output:
                if hasattr(item, 'content'):
                    for content_block in item.content:
                        if hasattr(content_block, 'annotations'):
                            for ann in content_block.annotations:
                                if hasattr(ann, 'url'):
                                    citations.append({
                                        "url": ann.url,
                                        "title": getattr(ann, 'title', ''),
                                    })

            # Parse the JSON response
            try:
                if "```json" in result_text:
                    result_text = result_text.split("```json")[1].split("```")[0]
                elif "```" in result_text:
                    result_text = result_text.split("```")[1].split("```")[0]

                images = json.loads(result_text.strip())
                if isinstance(images, list):
                    # Add citation URLs that aren't already in the list
                    existing_urls = {img.get("url", "") for img in images}
                    for citation in citations:
                        if citation["url"] not in existing_urls:
                            images.append({
                                "url": citation["url"],
                                "title": citation["title"],
                                "category": "product_reference",
                                "caption": f"Reference: {citation['title']}",
                            })
                    return images[:12]  # Cap at 12 references
            except json.JSONDecodeError:
                pass

            # Fallback: return just the citations if JSON parsing failed
            return [{
                "url": c["url"],
                "title": c["title"],
                "category": "product_reference",
                "caption": f"Reference: {c['title']}",
            } for c in citations[:8]]

        except Exception as e:
            logger.error(f"Web search for references failed: {e}")
            # Return empty list - mood board still works without references
            return []

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
                f"Include small callout labels pointing to key construction details."
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
