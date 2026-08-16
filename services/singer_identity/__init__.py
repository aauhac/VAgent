# -*- coding: utf-8 -*-
"""Singer Identity Engine — WHO is singing (not HOW).

Completely independent from VAgent vocal diagnosis / coaching.
"""

__version__ = "1.0.0"
ENGINE_NAME = "singer_identity"
FORBIDDEN_DIAGNOSTIC_AXES = frozenset(
    {
        "effort",
        "contact",
        "breathiness",
        "register_connection",
        "source_balance",
        "brightness",
        "presence",
        "stability",
        "texture",
        "high_note",
    }
)
