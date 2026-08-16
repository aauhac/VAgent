# -*- coding: utf-8 -*-
from services.singer_identity.confirmed_profile.core import (
    PROFILE_VERSION as PROFILE_VERSION_V2,
    SINGER_ID,
    run_confirmed_profile_v2,
)
from services.singer_identity.confirmed_profile.core_v3 import (
    PROFILE_VERSION,
    MULTI_PROTOTYPE_PRODUCTION_ENABLED,
    run_confirmed_profile_v3,
)

__all__ = [
    "PROFILE_VERSION",
    "PROFILE_VERSION_V2",
    "SINGER_ID",
    "MULTI_PROTOTYPE_PRODUCTION_ENABLED",
    "run_confirmed_profile_v2",
    "run_confirmed_profile_v3",
]
