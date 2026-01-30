"""
Discovery Module - Trend Scanning and Opportunity Scoring

Scans Google Trends and competitor sites for product opportunities.
Scores and ranks opportunities for the product pipeline.
"""
import logging
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy.orm import Session

from ..db import (
    DiscoveryScan, ProductOpportunity, CompetitorProduct,
    TrendAnalysis, OpportunityStatus
)
from .competency import COMPETITORS, PRODUCT_CATEGORIES, is_feasible, estimate_pricing

logger = logging.getLogger(__name__)

# Scoring weights
TREND_WEIGHT = 0.30
MARKET_WEIGHT = 0.30
FEASIBILITY_WEIGHT = 0.25
MARGIN_WEIGHT = 0.15


class TrendScanner:
    """Scans Google Trends and competitor data for product opportunities."""

    def __init__(self, db: Session):
        self.db = db

    def scan_google_trends(self, keywords: List[str] = None) -> List[Dict]:
        """Scan Google Trends for denim/apparel trends.

        Uses pytrends library when available, falls back to placeholder data.
        """
        if keywords is None:
            keywords = [
                "raw denim", "selvedge jeans", "sustainable denim",
                "wide leg jeans", "relaxed fit jeans", "workwear",
                "chore coat", "denim jacket", "made in USA clothing",
                "carpenter pants", "utility wear"
            ]

        trends = []
        try:
            from pytrends.request import TrendReq
            pytrends = TrendReq(hl='en-US', tz=300)

            # Process in batches of 5 (pytrends limit)
            for i in range(0, len(keywords), 5):
                batch = keywords[i:i+5]
                try:
                    pytrends.build_payload(batch, timeframe='today 3-m', geo='US')
                    interest = pytrends.interest_over_time()

                    if not interest.empty:
                        for kw in batch:
                            if kw in interest.columns:
                                values = interest[kw].values
                                avg_interest = float(values.mean())
                                recent = float(values[-7:].mean()) if len(values) >= 7 else avg_interest
                                older = float(values[:7].mean()) if len(values) >= 7 else avg_interest
                                growth = ((recent - older) / max(older, 1)) * 100

                                trends.append({
                                    "keyword": kw,
                                    "avg_interest": avg_interest,
                                    "recent_interest": recent,
                                    "growth_rate": round(growth, 1),
                                    "data_points": len(values),
                                })
                except Exception as e:
                    logger.warning(f"Trends batch failed for {batch}: {e}")

        except ImportError:
            logger.info("pytrends not installed, using keyword analysis only")
            for kw in keywords:
                trends.append({
                    "keyword": kw,
                    "avg_interest": 50,
                    "recent_interest": 50,
                    "growth_rate": 0,
                    "data_points": 0,
                    "note": "pytrends_unavailable"
                })

        return trends

    def scan_competitors(self) -> List[Dict]:
        """Scan competitor product pages for new items and pricing.

        Uses BeautifulSoup when available for basic page parsing.
        """
        results = []

        for key, competitor in COMPETITORS.items():
            try:
                import httpx
                from bs4 import BeautifulSoup

                # Only scan if we haven't scanned recently
                last_product = self.db.query(CompetitorProduct).filter(
                    CompetitorProduct.competitor == competitor["name"]
                ).order_by(CompetitorProduct.last_seen.desc()).first()

                if last_product and (datetime.utcnow() - last_product.last_seen).days < 1:
                    logger.info(f"Skipping {competitor['name']} - scanned recently")
                    continue

                # Note: Real scraping would need proper selectors per site
                # This is a framework that logs what it would do
                logger.info(f"Would scan {competitor['name']} at {competitor['url']}")
                results.append({
                    "competitor": competitor["name"],
                    "status": "framework_ready",
                    "categories": competitor["categories"],
                })

            except ImportError:
                logger.info(f"httpx/bs4 not available for competitor scan")
                results.append({
                    "competitor": competitor["name"],
                    "status": "dependencies_missing",
                })
            except Exception as e:
                logger.warning(f"Error scanning {competitor['name']}: {e}")
                results.append({
                    "competitor": competitor["name"],
                    "status": f"error: {str(e)}",
                })

        return results


class OpportunityScorer:
    """Scores and ranks product opportunities."""

    def __init__(self, db: Session):
        self.db = db

    def score_opportunity(
        self,
        title: str,
        category: str,
        trend_data: Dict = None,
        competitor_data: Dict = None,
        market_data: Dict = None,
    ) -> Dict:
        """Calculate composite score for a product opportunity."""

        # Trend score (0-100)
        trend_score = 50  # default
        if trend_data:
            interest = trend_data.get("avg_interest", 50)
            growth = trend_data.get("growth_rate", 0)
            trend_score = min(100, (interest * 0.6) + (max(0, growth) * 0.4))

        # Market score (0-100) - based on competitor activity and gap analysis
        market_score = 50
        if competitor_data:
            num_competitors = len(competitor_data.get("competitor_refs", []))
            avg_price = competitor_data.get("avg_price", 0)
            if num_competitors > 0:
                market_score = min(100, 40 + (num_competitors * 10))

        # Feasibility score (0-100) - based on core competency fit
        feasibility_score = 0
        if is_feasible(category):
            cat_info = PRODUCT_CATEGORIES.get(
                category.lower().replace(" ", "_").replace("-", "_"), {}
            )
            if cat_info:
                feasibility_score = 85
                if cat_info.get("construction_ops", 0) <= 40:
                    feasibility_score = 95  # simpler = higher feasibility
            else:
                feasibility_score = 60  # can make but not core category

        # Margin score (0-100)
        pricing = estimate_pricing(category)
        margin_score = 50
        if pricing:
            margin_pct = pricing.get("estimated_margin_pct", 0)
            margin_score = min(100, margin_pct * 1.5)

        # Composite
        composite = (
            trend_score * TREND_WEIGHT +
            market_score * MARKET_WEIGHT +
            feasibility_score * FEASIBILITY_WEIGHT +
            margin_score * MARGIN_WEIGHT
        )

        return {
            "trend_score": round(trend_score, 1),
            "market_score": round(market_score, 1),
            "feasibility_score": round(feasibility_score, 1),
            "margin_score": round(margin_score, 1),
            "composite_score": round(composite, 1),
            "pricing": pricing,
        }


def run_weekly_discovery_scan(db: Session) -> Dict:
    """Orchestrator for weekly discovery scan.

    1. Scan Google Trends for denim/apparel keywords
    2. Scan competitor sites for new products
    3. Generate and score opportunities
    4. Save to database
    """
    logger.info("Starting weekly discovery scan...")

    # Create scan record
    scan = DiscoveryScan(
        scan_type="weekly_auto",
        started_at=datetime.utcnow(),
        scan_config={"keywords": "default", "competitors": list(COMPETITORS.keys())},
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)

    scanner = TrendScanner(db)
    scorer = OpportunityScorer(db)
    opportunities_created = 0
    errors = []

    try:
        # 1. Scan trends
        trends = scanner.scan_google_trends()
        scan.trends_found = len(trends)

        # Save trends to DB
        for trend in trends:
            if trend.get("avg_interest", 0) >= 30:
                trend_record = TrendAnalysis(
                    trend_name=trend["keyword"],
                    category="denim",
                    trend_score=trend["avg_interest"],
                    growth_rate=trend["growth_rate"],
                    keywords=[trend["keyword"]],
                    relevance_score=min(100, trend["avg_interest"] * 1.2),
                )
                db.add(trend_record)

        # 2. Scan competitors
        comp_results = scanner.scan_competitors()
        scan.competitors_scanned = len(comp_results)

        # 3. Generate opportunities from high-scoring trends
        for trend in sorted(trends, key=lambda t: t.get("avg_interest", 0), reverse=True)[:10]:
            # Map trend keyword to category
            category = _keyword_to_category(trend["keyword"])
            if not category or not is_feasible(category):
                continue

            scores = scorer.score_opportunity(
                title=f"Opportunity: {trend['keyword'].title()}",
                category=category,
                trend_data=trend,
            )

            if scores["composite_score"] >= 40:
                opp = ProductOpportunity(
                    discovery_scan_id=scan.id,
                    title=f"{trend['keyword'].title()} - New Style Opportunity",
                    description=f"Trend-driven opportunity based on '{trend['keyword']}' "
                                f"with {trend['avg_interest']}% interest and "
                                f"{trend['growth_rate']}% growth.",
                    category=category,
                    trend_score=scores["trend_score"],
                    market_score=scores["market_score"],
                    feasibility_score=scores["feasibility_score"],
                    composite_score=scores["composite_score"],
                    trend_keywords=[trend["keyword"]],
                    market_data=trend,
                    estimated_retail=scores["pricing"].get("estimated_retail"),
                    estimated_cost=scores["pricing"].get("estimated_cost"),
                    estimated_margin=scores["pricing"].get("estimated_margin_pct"),
                    status=OpportunityStatus.SCORED,
                )
                db.add(opp)
                opportunities_created += 1

        scan.opportunities_generated = opportunities_created
        scan.status = "completed"
        scan.completed_at = datetime.utcnow()

    except Exception as e:
        logger.error(f"Discovery scan error: {e}")
        errors.append(str(e))
        scan.status = "failed"
        scan.error_log = errors

    db.commit()

    result = {
        "scan_id": scan.id,
        "status": scan.status,
        "trends_found": scan.trends_found,
        "competitors_scanned": scan.competitors_scanned,
        "opportunities_generated": opportunities_created,
        "errors": errors,
    }
    logger.info(f"Discovery scan complete: {result}")
    return result


def _keyword_to_category(keyword: str) -> Optional[str]:
    """Map a trend keyword to a product category."""
    keyword_lower = keyword.lower()

    mappings = {
        "jeans": "jeans",
        "denim": "jeans",
        "selvedge": "jeans",
        "raw denim": "jeans",
        "wide leg": "jeans",
        "relaxed fit": "jeans",
        "slim fit": "jeans",
        "bootcut": "jeans",
        "skinny": "jeans",
        "carpenter": "denim_pants",
        "utility": "denim_pants",
        "work pants": "denim_pants",
        "chore coat": "denim_jackets",
        "denim jacket": "denim_jackets",
        "trucker jacket": "denim_jackets",
        "workwear": "denim_pants",
        "flannel": "shirts",
        "western shirt": "shirts",
        "work shirt": "shirts",
        "overalls": "overalls",
        "coverall": "overalls",
        "chino": "chinos",
        "shorts": "shorts",
    }

    for key, category in mappings.items():
        if key in keyword_lower:
            return category

    return None
