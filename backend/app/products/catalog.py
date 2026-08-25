"""
Product catalog — display amounts for mock/dev; production uses IAP displayAmount.
Frontend must NOT hardcode prices; consume GET /v1/products.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from ..payments.settings import payments_enabled


PRODUCT_SONG_DETAIL = "song_detail"
PRODUCT_DIAGNOSTIC_FULL = "diagnostic_full"
PRODUCT_DIAGNOSTIC_UPGRADE = "diagnostic_upgrade"


def _sku(env_key: str, default: str) -> str:
    return (os.environ.get(env_key) or default).strip()


def product_catalog(*, song_detail_owned: bool = False) -> dict[str, Any]:
    """
    Return catalog for clients.

    In production, amounts should be replaced by Toss IAP product list displayAmount.
    Mock placeholders are only for development.
    """
    env = (os.environ.get("VAGENT_ENV") or "development").lower()
    is_prod = env == "production"

    products = {
        PRODUCT_SONG_DETAIL: {
            "product_id": PRODUCT_SONG_DETAIL,
            "entitlement_type": "SONG_DETAIL",
            "display_name": "상세 리포트",
            "description": "고음·음색 심층 분석 · 주요 구간 듣기",
            "sku": _sku("IAP_SONG_DETAIL_SKU", "vagent.song_detail"),
            "includes_song_detail": True,
            "requires_diagnostic_tasks": False,
            "mock_display_amount": "₩990",
            "mock_amount_krw": 990,
        },
        PRODUCT_DIAGNOSTIC_FULL: {
            "product_id": PRODUCT_DIAGNOSTIC_FULL,
            "entitlement_type": "DIAGNOSTIC",
            "display_name": "정밀 발성 진단",
            "description": "추가 녹음 · 발성 특성 정밀 확인",
            "sku": _sku("IAP_DIAGNOSTIC_FULL_SKU", "vagent.diagnostic_full"),
            "includes_song_detail": True,
            "requires_diagnostic_tasks": True,
            "mock_display_amount": "₩1,980",
            "mock_amount_krw": 1980,
        },
        PRODUCT_DIAGNOSTIC_UPGRADE: {
            "product_id": PRODUCT_DIAGNOSTIC_UPGRADE,
            "entitlement_type": "DIAGNOSTIC",
            "display_name": "정밀 발성 진단",
            "description": "추가 녹음 · 발성 특성 정밀 확인",
            "sku": _sku("IAP_DIAGNOSTIC_UPGRADE_SKU", "vagent.diagnostic_upgrade"),
            "includes_song_detail": True,
            "requires_diagnostic_tasks": True,
            "mock_display_amount": "₩990",
            "mock_amount_krw": 990,
        },
    }

    # Public display_amount: mock in dev, null in prod until IAP wired
    for p in products.values():
        if is_prod:
            p["display_amount"] = None
            p["amount_source"] = "toss_iap"
        else:
            p["display_amount"] = p["mock_display_amount"]
            p["amount_source"] = "mock"

    diagnostic_product_id = (
        PRODUCT_DIAGNOSTIC_UPGRADE if song_detail_owned else PRODUCT_DIAGNOSTIC_FULL
    )
    return {
        "environment": env,
        "payments_enabled": payments_enabled(),
        "products": products,
        "offers": {
            "song_detail": PRODUCT_SONG_DETAIL if not song_detail_owned else None,
            "diagnostic": diagnostic_product_id,
        },
        "note": (
            "Production amounts come from Apps in Toss IAP displayAmount. "
            "Do not hardcode prices in the miniapp."
        ),
    }


def resolve_diagnostic_product(song_detail_owned: bool) -> str:
    return PRODUCT_DIAGNOSTIC_UPGRADE if song_detail_owned else PRODUCT_DIAGNOSTIC_FULL


def get_product(product_id: str) -> Optional[dict[str, Any]]:
    cat = product_catalog()
    return (cat.get("products") or {}).get(product_id)
