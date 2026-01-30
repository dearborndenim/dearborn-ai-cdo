"""
Pattern Block Library

Hardcoded base geometries for common garment types.
These are the foundation patterns that AI modifies for new styles.
All coordinates in inches, base sizes as specified.
"""

# Jean 5-Pocket base pattern (size 32 waist, 32 inseam)
JEAN_5POCKET = {
    "name": "jean_5pocket",
    "base_size": "32",
    "pieces": {
        "front_panel": {
            "code": "FP",
            "cut_qty": 2,
            "mirror": True,
            "grain": "straight",
            "fabric": "shell",
            "points": [
                (0, 0), (0, 10.5),  # center front, rise
                (1.5, 12.5),  # waistband curve
                (8.25, 12.0),  # side waist
                (11.5, 10.0),  # side hip
                (11.5, 0),  # side hem at knee height
                (12.0, -22.0),  # side at hem
                (7.5, -22.0),  # center at hem
            ],
            "notches": [(0, 5.25), (11.5, 5.25)],  # knee notch
            "grain_line": [(5, -5), (5, 8)],
        },
        "back_panel": {
            "code": "BP",
            "cut_qty": 2,
            "mirror": True,
            "grain": "straight",
            "fabric": "shell",
            "points": [
                (0, 0), (0, 14.5),  # center back, rise
                (2.0, 16.0),  # waistband curve
                (8.5, 15.5),  # side waist
                (12.5, 12.0),  # side hip
                (12.5, 0),  # side at knee
                (13.0, -22.0),  # side at hem
                (7.5, -22.0),  # center at hem
            ],
            "notches": [(0, 7.25), (12.5, 7.25)],
            "grain_line": [(6, -5), (6, 10)],
        },
        "waistband": {
            "code": "WB",
            "cut_qty": 1,
            "mirror": False,
            "grain": "straight",
            "fabric": "shell",
            "points": [
                (0, 0), (0, 1.75),
                (33.0, 1.75), (33.0, 0),
            ],
            "notches": [(16.5, 0)],  # center back notch
            "grain_line": [(5, 0.875), (28, 0.875)],
        },
        "front_pocket_bag": {
            "code": "FPB",
            "cut_qty": 2,
            "mirror": True,
            "grain": "any",
            "fabric": "lining",
            "points": [
                (0, 0), (0, 6.0),
                (5.5, 8.0), (7.0, 6.0),
                (7.0, 0),
            ],
            "notches": [],
            "grain_line": [(2, 1), (2, 5)],
        },
        "back_pocket": {
            "code": "BKP",
            "cut_qty": 2,
            "mirror": True,
            "grain": "straight",
            "fabric": "shell",
            "points": [
                (0, 0), (0, 6.5),
                (5.5, 6.5), (5.5, 0),
            ],
            "notches": [(2.75, 6.5)],  # center top
            "grain_line": [(2.75, 1), (2.75, 5)],
        },
        "coin_pocket": {
            "code": "CP",
            "cut_qty": 1,
            "mirror": False,
            "grain": "straight",
            "fabric": "shell",
            "points": [
                (0, 0), (0, 3.5),
                (3.0, 3.5), (3.0, 0),
            ],
            "notches": [],
            "grain_line": [(1.5, 0.5), (1.5, 3)],
        },
        "fly_shield": {
            "code": "FS",
            "cut_qty": 1,
            "mirror": False,
            "grain": "straight",
            "fabric": "shell",
            "points": [
                (0, 0), (0, 8.0),
                (2.5, 8.0), (2.5, 0),
            ],
            "notches": [],
            "grain_line": [(1.25, 1), (1.25, 6)],
        },
    },
}

# Slim jean variant (narrower thigh, knee, and leg opening)
JEAN_SLIM = {
    "name": "jean_slim",
    "base_size": "32",
    "derives_from": "jean_5pocket",
    "modifications": {
        "front_panel": {"thigh_adjust": -0.5, "knee_adjust": -0.75, "hem_adjust": -1.0},
        "back_panel": {"thigh_adjust": -0.5, "knee_adjust": -0.75, "hem_adjust": -1.0},
    },
}

# Western shirt base pattern (size M)
SHIRT_WESTERN = {
    "name": "shirt_western",
    "base_size": "M",
    "pieces": {
        "front_body": {
            "code": "FB",
            "cut_qty": 2,
            "mirror": True,
            "grain": "straight",
            "fabric": "shell",
            "points": [
                (0, 0), (0, 30.0),  # center front, full length
                (8.0, 30.5),  # shoulder
                (10.0, 28.0),  # armhole top
                (11.0, 24.0),  # armhole curve
                (11.0, 0),  # side hem
            ],
            "notches": [(0, 15.0)],  # waist notch
            "grain_line": [(5, 5), (5, 25)],
        },
        "back_body": {
            "code": "BB",
            "cut_qty": 1,
            "mirror": False,
            "grain": "straight",
            "fabric": "shell",
            "points": [
                (0, 0), (0, 30.5),  # center back
                (8.5, 31.0),  # shoulder
                (10.5, 28.0),  # armhole
                (11.5, 24.0),
                (11.5, 0),
            ],
            "notches": [(0, 15.0)],
            "grain_line": [(5, 5), (5, 25)],
        },
        "sleeve": {
            "code": "SL",
            "cut_qty": 2,
            "mirror": True,
            "grain": "straight",
            "fabric": "shell",
            "points": [
                (0, 0), (0, 25.0),  # underarm to cap
                (4.0, 27.0),  # cap peak
                (8.0, 25.0),
                (8.0, 0),
            ],
            "notches": [(4.0, 27.0)],  # cap point
            "grain_line": [(4, 2), (4, 22)],
        },
        "collar": {
            "code": "CL",
            "cut_qty": 2,
            "mirror": False,
            "grain": "straight",
            "fabric": "shell",
            "points": [
                (0, 0), (0, 3.0),
                (8.0, 3.25), (8.0, 0),
            ],
            "notches": [(4.0, 0)],  # center
            "grain_line": [(2, 1.5), (6, 1.5)],
        },
        "collar_stand": {
            "code": "CS",
            "cut_qty": 2,
            "mirror": False,
            "grain": "straight",
            "fabric": "shell",
            "points": [
                (0, 0), (0, 1.5),
                (8.0, 1.5), (8.0, 0),
            ],
            "notches": [(4.0, 0)],
            "grain_line": [(2, 0.75), (6, 0.75)],
        },
        "cuff": {
            "code": "CF",
            "cut_qty": 4,
            "mirror": False,
            "grain": "straight",
            "fabric": "shell",
            "points": [
                (0, 0), (0, 2.5),
                (9.0, 2.5), (9.0, 0),
            ],
            "notches": [],
            "grain_line": [(2, 1.25), (7, 1.25)],
        },
        "yoke": {
            "code": "YK",
            "cut_qty": 2,
            "mirror": False,
            "grain": "straight",
            "fabric": "shell",
            "points": [
                (0, 0), (0, 5.0),
                (8.5, 5.0), (10.0, 3.5),
                (10.0, 0),
            ],
            "notches": [],
            "grain_line": [(4, 1), (4, 4)],
        },
    },
}

# Chore jacket base pattern (size M)
JACKET_CHORE = {
    "name": "jacket_chore",
    "base_size": "M",
    "pieces": {
        "front_body": {
            "code": "JFB",
            "cut_qty": 2,
            "mirror": True,
            "grain": "straight",
            "fabric": "shell",
            "points": [
                (0, 0), (0, 28.0),
                (9.0, 28.5),
                (11.0, 26.0),
                (12.5, 22.0),
                (12.5, 0),
            ],
            "notches": [(0, 14.0)],
            "grain_line": [(5, 5), (5, 23)],
        },
        "back_body": {
            "code": "JBB",
            "cut_qty": 1,
            "mirror": False,
            "grain": "straight",
            "fabric": "shell",
            "points": [
                (0, 0), (0, 28.5),
                (9.5, 29.0),
                (11.5, 26.0),
                (13.0, 22.0),
                (13.0, 0),
            ],
            "notches": [(0, 14.0)],
            "grain_line": [(5, 5), (5, 23)],
        },
        "sleeve": {
            "code": "JSL",
            "cut_qty": 2,
            "mirror": True,
            "grain": "straight",
            "fabric": "shell",
            "points": [
                (0, 0), (0, 25.0),
                (5.0, 27.5),
                (10.0, 25.0),
                (10.0, 0),
            ],
            "notches": [(5.0, 27.5)],
            "grain_line": [(5, 3), (5, 22)],
        },
        "collar": {
            "code": "JCL",
            "cut_qty": 2,
            "mirror": False,
            "grain": "straight",
            "fabric": "shell",
            "points": [
                (0, 0), (0, 3.5),
                (9.0, 3.75), (9.0, 0),
            ],
            "notches": [(4.5, 0)],
            "grain_line": [(2, 1.75), (7, 1.75)],
        },
        "chest_pocket": {
            "code": "JCP",
            "cut_qty": 2,
            "mirror": True,
            "grain": "straight",
            "fabric": "shell",
            "points": [
                (0, 0), (0, 7.0),
                (6.0, 7.0), (6.0, 0),
            ],
            "notches": [(3.0, 7.0)],
            "grain_line": [(3, 1), (3, 6)],
        },
        "lower_pocket": {
            "code": "JLP",
            "cut_qty": 2,
            "mirror": True,
            "grain": "straight",
            "fabric": "shell",
            "points": [
                (0, 0), (0, 8.0),
                (7.0, 8.0), (7.0, 0),
            ],
            "notches": [(3.5, 8.0)],
            "grain_line": [(3.5, 1), (3.5, 7)],
        },
    },
}

# Library lookup
PATTERN_BLOCKS = {
    "jean_5pocket": JEAN_5POCKET,
    "jean_slim": JEAN_SLIM,
    "shirt_western": SHIRT_WESTERN,
    "jacket_chore": JACKET_CHORE,
}


def get_block(name: str) -> dict:
    """Get a pattern block by name."""
    return PATTERN_BLOCKS.get(name, {})


def list_blocks() -> list:
    """List available pattern blocks."""
    return [
        {"name": name, "base_size": block.get("base_size", ""), "pieces": len(block.get("pieces", {}))}
        for name, block in PATTERN_BLOCKS.items()
        if "pieces" in block
    ]
