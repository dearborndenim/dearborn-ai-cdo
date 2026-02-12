"""
Trend Researcher Module

Uses Perplexity Sonar (web-grounded AI) for real-time trend research,
with GPT-4o fallback and placeholder text as last resort.

Research areas:
1. Fashion/denim trends (silhouettes, fits, colors, cultural influences)
2. Fabric trends (weights, weaves, blends, sustainability, mills)
3. Silhouette/style recommendations per category
4. Competitor analysis (new releases, prices, market gaps)
"""
import json
import logging
from typing import Dict, List, Optional

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class TrendResearcher:
    """Web-grounded trend research using Perplexity Sonar with GPT-4o fallback."""

    def __init__(self):
        self._perplexity_client = None
        self._openai_client = None

    @property
    def perplexity_client(self):
        if self._perplexity_client is None and settings.perplexity_api_key:
            from openai import OpenAI
            self._perplexity_client = OpenAI(
                api_key=settings.perplexity_api_key,
                base_url="https://api.perplexity.ai",
            )
        return self._perplexity_client

    @property
    def openai_client(self):
        if self._openai_client is None and settings.openai_api_key:
            from openai import OpenAI
            self._openai_client = OpenAI(api_key=settings.openai_api_key)
        return self._openai_client

    def research_fashion_trends(self, season_name: str, target_demo: Dict) -> Dict:
        """Research fashion/denim trends for the season."""
        gender = target_demo.get("gender", "All")
        age = target_demo.get("age_range", "25-55")

        prompt = f"""Research current and emerging fashion and denim trends for {season_name}.
Focus on the American premium denim and workwear market targeting {gender}, ages {age}.

Cover:
1. **Silhouettes & Fits** — Which jean fits are gaining/losing popularity (wide leg, straight, slim, relaxed taper)? What about non-denim bottoms?
2. **Colors & Washes** — Trending denim washes (raw, stonewash, vintage, black), and non-denim color palettes for the season
3. **Cultural Influences** — What cultural movements, media, or lifestyle trends are driving fashion choices (workwear revival, quiet luxury, Americana, etc.)
4. **Key Design Details** — Hardware, stitching, pocket styles, selvedge details, hem treatments that are trending
5. **Overall Direction** — Where is the premium casual/denim market heading for {season_name}?

Be specific with examples from recent collections and runway shows. Include brand names and specific products where relevant."""

        return self._execute_research(
            prompt=prompt,
            research_type="fashion_trends",
            season_name=season_name,
        )

    def research_fabric_trends(self, season_name: str) -> Dict:
        """Research trending fabrics, denim weights, weaves, and mills."""
        prompt = f"""Research current fabric trends in the premium denim and workwear industry for {season_name}.

Cover:
1. **Denim Weights** — What weights are trending? Is the market moving toward lighter or heavier denim? What's the sweet spot for premium casual?
2. **Weaves & Textures** — Trending weaves (twill, dobby, herringbone, slub, selvedge). What textures are consumers seeking?
3. **Fabric Blends** — Popular compositions (100% cotton, cotton-elastane, cotton-hemp, cotton-Tencel). What stretch percentages are preferred?
4. **Sustainability** — Organic cotton trends, recycled fibers, waterless dyeing, BCI cotton adoption in premium segment
5. **Key Mills & Suppliers** — Which denim and fabric mills are producing the most sought-after materials? (Cone Denim, Kaihara, Kurabo, Candiani, Vidalia Mills, etc.)
6. **Non-Denim Fabrics** — What fabrics are trending for shirts, chinos, and outerwear? (brushed twills, japanese chambrays, french terry, etc.)
7. **Knit Fabrics** — What knit constructions and yarns are trending for sweaters and knitwear in the workwear-adjacent market?

Be specific with weights (oz/yd or gsm), compositions, and supplier names where possible."""

        return self._execute_research(
            prompt=prompt,
            research_type="fabric_trends",
            season_name=season_name,
        )

    def research_silhouettes(self, season_name: str, categories: List[str]) -> Dict:
        """Research per-category style and silhouette recommendations."""
        cat_list = ", ".join(categories)

        prompt = f"""Research specific style and silhouette trends for the following product categories in the premium American workwear/denim market for {season_name}: {cat_list}

For each category, provide:

**Jeans/Denim Pants**: Which fits are growing vs declining? (relaxed straight, slim taper, wide leg, athletic, etc.) What rise heights? What leg openings?
**Shirts**: Which collar styles, button configurations, and fits are trending? (camp collar, band collar, western snap, oversized, etc.)
**Outerwear/Jackets**: Which jacket styles are gaining momentum? (trucker, chore coat, shirt jacket/shacket, bomber, field jacket)
**T-shirts/Henleys**: What fits and weights? (boxy, relaxed, slim, heavyweight vs midweight)
**Shorts**: What lengths and styles? (7", 9", walk short, camp short)
**Knitwear**: What styles pair well with workwear? (fisherman sweater, half-zip, cotton cardigan, waffle knit)
**Chinos**: What fits and construction details? (pleated vs flat front, cuffed vs uncuffed)

Include specific measurements where relevant (leg opening width, inseam lengths, etc.)."""

        return self._execute_research(
            prompt=prompt,
            research_type="silhouette_trends",
            season_name=season_name,
        )

    def research_competitors(self, season_name: str) -> Dict:
        """Research competitor new releases and market positioning."""
        prompt = f"""Research recent and upcoming product releases from these premium American denim/workwear brands for {season_name}:

- Levi's (Made & Crafted and mainline)
- Faherty
- Carhartt (WIP and mainline)
- Origin Maine
- Taylor Stitch
- Buck Mason
- Todd Snyder
- Flint and Tinder / Huckberry brands

For each brand, cover:
1. **New Products** — Key new releases for the season (specific product names, styles)
2. **Pricing** — Price points for comparable products (jeans, jackets, shirts)
3. **Fabric Choices** — What fabrics/weights are they using?
4. **Marketing Angle** — How are they positioning their seasonal collections?
5. **Market Gaps** — Where are they NOT competing? What niches are underserved?

Also identify opportunities where a premium American-made brand (manufacturing in Chicago, $68-$178 price range) could differentiate. What are customers asking for that nobody is providing?"""

        return self._execute_research(
            prompt=prompt,
            research_type="competitor_analysis",
            season_name=season_name,
        )

    def _execute_research(self, prompt: str, research_type: str, season_name: str) -> Dict:
        """Execute research with Perplexity → GPT-4o → placeholder fallback chain."""
        # Try Perplexity first
        if self.perplexity_client:
            try:
                response = self.perplexity_client.chat.completions.create(
                    model="sonar",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2000,
                )
                content = response.choices[0].message.content

                # Extract citations if available
                citations = []
                if hasattr(response, 'citations') and response.citations:
                    citations = [{"url": c, "title": c} for c in response.citations]

                return {
                    "research_type": research_type,
                    "content": content,
                    "citations": citations,
                    "source": "perplexity",
                    "model_used": "sonar",
                }
            except Exception as e:
                logger.warning(f"Perplexity research failed for {research_type}: {e}")

        # Fallback to GPT-4o
        if self.openai_client:
            try:
                response = self.openai_client.chat.completions.create(
                    model=settings.openai_model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2000,
                )
                content = response.choices[0].message.content
                return {
                    "research_type": research_type,
                    "content": content,
                    "citations": [],
                    "source": "gpt4o",
                    "model_used": settings.openai_model,
                }
            except Exception as e:
                logger.warning(f"GPT-4o research failed for {research_type}: {e}")

        # Final fallback: placeholder text
        logger.warning(f"All AI providers unavailable — using placeholder for {research_type}")
        return {
            "research_type": research_type,
            "content": self._placeholder_content(research_type, season_name),
            "citations": [],
            "source": "placeholder",
            "model_used": None,
        }

    def _placeholder_content(self, research_type: str, season_name: str) -> str:
        """Generate placeholder research content when no AI is available."""
        placeholders = {
            "fashion_trends": f"""# Fashion Trends — {season_name}

## Silhouettes & Fits
- Relaxed straight and wide-leg jeans continue to gain market share over slim fits
- High-rise and mid-rise dominate; low-rise showing early signs of return in younger demos
- Looser, more relaxed fits across all categories reflect post-pandemic comfort preferences

## Colors & Washes
- Raw and dark indigo remain premium staples
- Vintage-inspired medium washes growing in popularity
- Earth tones (olive, rust, tan) trending for non-denim pieces
- Black denim seeing renewed interest

## Cultural Influences
- Workwear revival continues (heritage Americana, blue collar aesthetic)
- "Quiet luxury" — understated quality over logos
- Sustainability as a core value, not just marketing

## Design Details
- Selvedge and visible construction details as status markers
- Contrast stitching making a comeback
- Utility details (extra pockets, D-rings, tool loops) crossing into casual wear

*Note: Enable Perplexity API for web-grounded research with citations.*""",

            "fabric_trends": f"""# Fabric Trends — {season_name}

## Denim Weights
- 12-14oz remains the sweet spot for premium denim
- Lighter 9-10oz gaining traction for year-round comfort
- Heavyweight 16oz+ niche but loyal following

## Weaves & Textures
- Selvedge continues as premium marker
- Slubby, irregular textures for vintage character
- Broken twill gaining interest for softer hand feel

## Blends
- 98/2 cotton-elastane most popular for stretch denim
- 100% cotton rigid denim for purists
- Cotton-hemp blends emerging for sustainability

## Sustainability
- Organic cotton adoption growing in premium segment
- Recycled cotton still quality concerns at scale
- Waterless dyeing technologies gaining traction

## Key Mills
- Cone Denim (USA), Kaihara (Japan), Candiani (Italy)
- Vidalia Mills (USA), Kurabo (Japan)

*Note: Enable Perplexity API for web-grounded research with citations.*""",

            "silhouette_trends": f"""# Silhouette Trends by Category — {season_name}

## Jeans
- Relaxed straight (32-34" leg opening): fastest growing fit
- Slim taper: still strong but plateauing
- Wide leg: growing from niche to mainstream

## Shirts
- Camp collar and band collar trending for casual
- Western snap buttons maintaining workwear appeal
- Slightly oversized/relaxed fit preferred

## Outerwear
- Chore coat: dominant workwear jacket silhouette
- Trucker jacket: classic, always relevant
- Shirt jacket (shacket): still strong transitional piece

## Knitwear
- Fisherman sweaters pair well with workwear
- Half-zip pullovers for layering
- Cotton/wool blend cardigans trending

*Note: Enable Perplexity API for web-grounded research with citations.*""",

            "competitor_analysis": f"""# Competitor Analysis — {season_name}

## Levi's
- Premium Made & Crafted line: $128-$248 jeans
- Pushing vintage-inspired fits and washes
- Strong sustainability messaging

## Faherty
- Premium casual with $128-$168 denim range
- Focus on comfort and stretch fabrics
- Strong in shirts and knits

## Carhartt
- WIP line competing in premium workwear
- Mainline still value-oriented
- Strong brand loyalty in trades

## Market Gaps
- Few brands offer premium American-made at $68-$128
- Opportunity in knit/denim crossover pieces
- Technical workwear details in casual silhouettes underserved

*Note: Enable Perplexity API for web-grounded research with citations.*""",

            "customer_profile": f"""# Customer Profile — {season_name}

This segment values quality, authenticity, and American manufacturing.
They shop deliberately, research before buying, and maintain brand loyalty
when quality expectations are met. Price sensitivity is moderate — they
expect premium pricing for premium products but compare value carefully.

*Note: Enable OpenAI API for AI-generated customer profiles.*""",
        }

        return placeholders.get(research_type, f"# {research_type}\n\nPlaceholder content for {season_name}. Enable AI APIs for real research.")
