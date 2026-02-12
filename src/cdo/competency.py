"""
Core Competency Filter

Defines what Dearborn Denim can and cannot manufacture,
product categories, and competitor tracking list.
"""

# What Dearborn can make (core competencies)
CAN_MAKE = [
    "jeans",
    "denim_pants",
    "chinos",
    "work_pants",
    "shorts",
    "denim_jackets",
    "chore_coats",
    "work_shirts",
    "button_down_shirts",
    "western_shirts",
    "t_shirts",
    "henleys",
    "flannels",
    "overalls",
    "coveralls",
]

# What Dearborn cannot make (outside core competency)
CANNOT_MAKE = [
    "footwear",
    "accessories",
    "underwear",
    "socks",
    "hats",
    "suits",
    "formal_wear",
    "athletic_wear",
    "swimwear",
    "knitwear",
    "leather_goods",
]

# Product categories with their attributes
PRODUCT_CATEGORIES = {
    "jeans": {
        "subcategories": ["5-pocket", "slim", "straight", "relaxed", "bootcut", "skinny"],
        "base_pattern": "jean_5pocket",
        "size_range": {"waist": list(range(28, 44, 2)), "inseam": [30, 32, 34]},
        "typical_cost_range": (18, 35),
        "typical_retail_range": (68, 128),
        "typical_margin": 0.55,
        "construction_ops": 45,
    },
    "denim_pants": {
        "subcategories": ["carpenter", "painter", "utility"],
        "base_pattern": "jean_5pocket",
        "size_range": {"waist": list(range(28, 44, 2)), "inseam": [30, 32, 34]},
        "typical_cost_range": (20, 38),
        "typical_retail_range": (78, 138),
        "typical_margin": 0.52,
        "construction_ops": 50,
    },
    "chinos": {
        "subcategories": ["slim", "straight", "relaxed"],
        "base_pattern": "jean_5pocket",
        "size_range": {"waist": list(range(28, 42, 2)), "inseam": [30, 32, 34]},
        "typical_cost_range": (15, 28),
        "typical_retail_range": (58, 98),
        "typical_margin": 0.58,
        "construction_ops": 35,
    },
    "shorts": {
        "subcategories": ["chino", "denim", "utility"],
        "base_pattern": "jean_5pocket",
        "size_range": {"waist": list(range(28, 42, 2))},
        "typical_cost_range": (12, 22),
        "typical_retail_range": (48, 78),
        "typical_margin": 0.58,
        "construction_ops": 30,
    },
    "denim_jackets": {
        "subcategories": ["trucker", "chore", "sherpa-lined"],
        "base_pattern": "jacket_chore",
        "size_range": {"alpha": ["S", "M", "L", "XL", "XXL"]},
        "typical_cost_range": (28, 55),
        "typical_retail_range": (98, 178),
        "typical_margin": 0.50,
        "construction_ops": 55,
    },
    "shirts": {
        "subcategories": ["western", "button_down", "flannel", "work_shirt"],
        "base_pattern": "shirt_western",
        "size_range": {"alpha": ["S", "M", "L", "XL", "XXL"]},
        "typical_cost_range": (14, 28),
        "typical_retail_range": (58, 98),
        "typical_margin": 0.55,
        "construction_ops": 40,
    },
    "t_shirts": {
        "subcategories": ["crew", "henley", "pocket_tee"],
        "base_pattern": "shirt_western",
        "size_range": {"alpha": ["S", "M", "L", "XL", "XXL"]},
        "typical_cost_range": (8, 16),
        "typical_retail_range": (28, 48),
        "typical_margin": 0.60,
        "construction_ops": 20,
    },
    "overalls": {
        "subcategories": ["bib", "coverall"],
        "base_pattern": "jean_5pocket",
        "size_range": {"alpha": ["S", "M", "L", "XL", "XXL"]},
        "typical_cost_range": (30, 55),
        "typical_retail_range": (108, 168),
        "typical_margin": 0.50,
        "construction_ops": 60,
    },
}

# Competitors to track
COMPETITORS = {
    "levis": {
        "name": "Levi's",
        "url": "https://www.levi.com",
        "categories": ["jeans", "denim_jackets", "shorts", "shirts"],
        "price_tier": "mid",
    },
    "wrangler": {
        "name": "Wrangler",
        "url": "https://www.wrangler.com",
        "categories": ["jeans", "shirts", "shorts"],
        "price_tier": "value",
    },
    "carhartt": {
        "name": "Carhartt",
        "url": "https://www.carhartt.com",
        "categories": ["jeans", "denim_pants", "denim_jackets", "overalls", "shirts"],
        "price_tier": "mid",
    },
    "ralph_lauren": {
        "name": "Ralph Lauren",
        "url": "https://www.ralphlauren.com",
        "categories": ["jeans", "chinos", "shirts"],
        "price_tier": "premium",
    },
    "faherty": {
        "name": "Faherty",
        "url": "https://fahertybrand.com",
        "categories": ["jeans", "chinos", "shorts", "shirts"],
        "price_tier": "premium",
    },
    "origin": {
        "name": "Origin Maine",
        "url": "https://originmaine.com",
        "categories": ["jeans", "denim_jackets", "shirts"],
        "price_tier": "premium",
    },
    "uniqlo": {
        "name": "Uniqlo",
        "url": "https://www.uniqlo.com",
        "categories": ["jeans", "chinos", "shirts", "t_shirts"],
        "price_tier": "value",
    },
}


def is_feasible(category: str) -> bool:
    """Check if a product category is within Dearborn's core competency."""
    normalized = category.lower().replace(" ", "_").replace("-", "_")
    return normalized in CAN_MAKE or normalized in PRODUCT_CATEGORIES


def get_category_info(category: str) -> dict:
    """Get production info for a category."""
    normalized = category.lower().replace(" ", "_").replace("-", "_")
    return PRODUCT_CATEGORIES.get(normalized, {})


def estimate_pricing(category: str, quality_tier: str = "mid") -> dict:
    """Estimate pricing for a product category."""
    info = get_category_info(category)
    if not info:
        return {}

    cost_low, cost_high = info["typical_cost_range"]
    retail_low, retail_high = info["typical_retail_range"]

    if quality_tier == "value":
        cost = cost_low
        retail = retail_low
    elif quality_tier == "premium":
        cost = cost_high
        retail = retail_high
    else:
        cost = (cost_low + cost_high) / 2
        retail = (retail_low + retail_high) / 2

    margin = (retail - cost) / retail * 100 if retail > 0 else 0

    return {
        "estimated_cost": round(cost, 2),
        "estimated_retail": round(retail, 2),
        "estimated_margin_pct": round(margin, 1),
        "typical_margin": info["typical_margin"],
    }


# Chicago manufacturing labor rates
LABOR_RATE_PER_HOUR = 26.00  # $17/hr base × 1.5 = $26/hr fully loaded (taxes, unemployment, benefits, PTO)

# Estimated sewing time per category (minutes)
SEWING_TIME_MINUTES = {
    "jeans": 45,
    "denim_pants": 50,
    "chinos": 35,
    "work_pants": 40,
    "shorts": 25,
    "denim_jackets": 55,
    "chore_coats": 50,
    "work_shirts": 40,
    "button_down_shirts": 38,
    "western_shirts": 42,
    "shirts": 40,
    "t_shirts": 15,
    "henleys": 18,
    "flannels": 40,
    "overalls": 65,
    "coveralls": 70,
}


def estimate_manufacturing_cost(category: str) -> dict:
    """Estimate manufacturing cost based on Chicago labor rates + material BOM.

    Uses $26/hr fully-loaded labor rate (1.5× of $17/hr base) which includes:
    - Base wage: $17/hr
    - Employer payroll taxes (FICA, FUTA, SUTA): ~$2.30/hr
    - Workers comp insurance: ~$1.00/hr
    - Health insurance contribution: ~$2.50/hr
    - PTO/holidays/sick time: ~$1.70/hr
    - Unemployment insurance: ~$0.50/hr
    - Misc overhead (training, breaks): ~$1.00/hr
    """
    normalized = category.lower().replace(" ", "_").replace("-", "_")
    sewing_minutes = SEWING_TIME_MINUTES.get(normalized, 40)  # default 40 min
    labor_cost = (sewing_minutes / 60) * LABOR_RATE_PER_HOUR

    # Get material cost from BOM templates
    material_cost = _estimate_material_cost(normalized)

    total_cost = labor_cost + material_cost

    return {
        "labor_cost": round(labor_cost, 2),
        "material_cost": round(material_cost, 2),
        "total_manufacturing_cost": round(total_cost, 2),
        "sewing_time_minutes": sewing_minutes,
        "labor_rate_per_hour": LABOR_RATE_PER_HOUR,
    }


def _estimate_material_cost(category: str) -> float:
    """Estimate material cost from BOM templates in techpack_gen."""
    try:
        from .techpack_gen import BOM_TEMPLATES
        bom = BOM_TEMPLATES.get(category, BOM_TEMPLATES.get("jeans", []))
        total = 0.0
        for item in bom:
            qty = item.get("qty", item.get("quantity_per_unit", 0))
            cost = item.get("cost", item.get("unit_cost", 0))
            total += qty * cost
        return total
    except (ImportError, Exception):
        # Fallback estimates if BOM_TEMPLATES not accessible
        FALLBACK_MATERIAL_COSTS = {
            "jeans": 18.50,
            "denim_pants": 20.00,
            "chinos": 14.00,
            "shorts": 10.00,
            "denim_jackets": 28.00,
            "shirts": 14.00,
            "t_shirts": 6.00,
            "overalls": 30.00,
        }
        return FALLBACK_MATERIAL_COSTS.get(category, 15.00)
