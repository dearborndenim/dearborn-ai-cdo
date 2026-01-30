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
