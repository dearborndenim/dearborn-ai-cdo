"""
Size Grading Rules

Defines grading increments by garment type for generating
size-graded pattern sets from base patterns.
"""

# Jeans/pants grading: waist sizes 28-42, 2" increments
JEANS_GRADING = {
    "base_size": "32",
    "size_range": ["28", "30", "32", "34", "36", "38", "40", "42"],
    "inseam_options": [30, 32, 34],
    "grade_rules": {
        # Measurement: increment per size (inches)
        "waist": 1.0,
        "hip": 1.0,
        "thigh": 0.5,
        "knee": 0.375,
        "leg_opening": 0.25,
        "front_rise": 0.25,
        "back_rise": 0.25,
        "outseam": 0.0,  # stays constant per inseam
    },
    "ease": {
        "waist": 1.0,  # ease added to body measurement
        "hip": 2.0,
        "thigh": 2.5,
    },
}

# Shirts grading: S-XXL alpha sizes
SHIRT_GRADING = {
    "base_size": "M",
    "size_range": ["S", "M", "L", "XL", "XXL"],
    "grade_rules": {
        "chest": 2.0,
        "waist": 2.0,
        "hip": 2.0,
        "neck": 0.5,
        "sleeve_length": 0.5,
        "shoulder": 0.5,
        "body_length": 0.75,
        "across_back": 0.75,
    },
    "ease": {
        "chest": 4.0,
        "waist": 4.0,
        "hip": 4.0,
    },
}

# Jacket grading
JACKET_GRADING = {
    "base_size": "M",
    "size_range": ["S", "M", "L", "XL", "XXL"],
    "grade_rules": {
        "chest": 2.0,
        "waist": 2.0,
        "hip": 2.0,
        "shoulder": 0.625,
        "sleeve_length": 0.5,
        "body_length": 0.75,
        "across_back": 0.75,
        "bicep": 0.5,
        "wrist": 0.25,
    },
    "ease": {
        "chest": 6.0,
        "waist": 6.0,
        "hip": 4.0,
    },
}

# T-shirt grading
TSHIRT_GRADING = {
    "base_size": "M",
    "size_range": ["S", "M", "L", "XL", "XXL"],
    "grade_rules": {
        "chest": 2.0,
        "waist": 2.0,
        "hip": 2.0,
        "shoulder": 0.5,
        "sleeve_length": 0.375,
        "body_length": 0.75,
    },
    "ease": {
        "chest": 4.0,
        "waist": 4.0,
    },
}

# Map category to grading rules
GRADING_BY_CATEGORY = {
    "jeans": JEANS_GRADING,
    "denim_pants": JEANS_GRADING,
    "chinos": JEANS_GRADING,
    "shorts": JEANS_GRADING,
    "shirts": SHIRT_GRADING,
    "denim_jackets": JACKET_GRADING,
    "t_shirts": TSHIRT_GRADING,
    "overalls": JEANS_GRADING,
}


def get_grading_rules(category: str) -> dict:
    """Get grading rules for a garment category."""
    normalized = category.lower().replace(" ", "_").replace("-", "_")
    return GRADING_BY_CATEGORY.get(normalized, JEANS_GRADING)


def grade_measurement(base_value: float, base_size: str, target_size: str, measurement: str, category: str) -> float:
    """Calculate graded measurement for a specific size.

    Args:
        base_value: The measurement at base size
        base_size: The base/sample size
        target_size: The size to grade to
        measurement: The measurement name (waist, hip, etc.)
        category: The garment category

    Returns:
        Graded measurement value
    """
    rules = get_grading_rules(category)
    increment = rules["grade_rules"].get(measurement, 0)
    sizes = rules["size_range"]

    if base_size not in sizes or target_size not in sizes:
        return base_value

    base_idx = sizes.index(base_size)
    target_idx = sizes.index(target_size)
    size_diff = target_idx - base_idx

    return round(base_value + (increment * size_diff), 3)


def generate_size_spec(category: str, base_measurements: dict) -> dict:
    """Generate full size spec from base size measurements.

    Args:
        category: Garment category
        base_measurements: Dict of measurement name to value at base size

    Returns:
        Dict of size -> measurements
    """
    rules = get_grading_rules(category)
    base_size = rules["base_size"]
    sizes = rules["size_range"]

    spec = {}
    for size in sizes:
        spec[size] = {}
        for measurement, value in base_measurements.items():
            spec[size][measurement] = grade_measurement(
                value, base_size, size, measurement, category
            )

    return spec
