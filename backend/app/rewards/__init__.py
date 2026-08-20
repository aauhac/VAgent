"""Rewarded-ad unlocks (SONG_DETAIL only)."""

from .rewarded_detail import (
    DAILY_LIMIT,
    REWARD_TYPE_SONG_DETAIL,
    RewardedAdError,
    claim_rewarded_song_detail,
    create_rewarded_session,
    rewarded_ad_status,
)

__all__ = [
    "DAILY_LIMIT",
    "REWARD_TYPE_SONG_DETAIL",
    "RewardedAdError",
    "claim_rewarded_song_detail",
    "create_rewarded_session",
    "rewarded_ad_status",
]
