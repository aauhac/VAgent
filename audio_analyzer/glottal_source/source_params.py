"""
Estimated glottal source parameters from inverse-filtered flow.

Field names use estimated_ / proxy_ — never claim EGG CQ identity.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from .gci import estimate_gci


def _cycle_params(
    flow: np.ndarray,
    dflow: np.ndarray,
    gci: np.ndarray,
    sr: int,
) -> list[dict[str, float]]:
    out = []
    for i in range(len(gci) - 1):
        a, b = int(gci[i]), int(gci[i + 1])
        if b - a < 4:
            continue
        seg = flow[a:b]
        dseg = dflow[a:b]
        t0 = (b - a) / float(sr)
        if t0 <= 0:
            continue
        ac = float(np.max(seg) - np.min(seg)) + 1e-12
        d_peak = float(np.max(np.abs(dseg))) + 1e-12
        aq = ac / d_peak
        estimated_naq = aq / t0
        # QOQ proxy: fraction of cycle where flow > 50% of peak-to-peak
        thr = np.min(seg) + 0.5 * ac
        open_frac = float(np.mean(seg > thr))
        estimated_qoq = open_frac
        # MFDR proxy: max flow declination rate (negative derivative magnitude)
        estimated_mfdr = d_peak
        # Normalized MFDR: amplitude-relative (usable as directional proxy)
        estimated_mfdr_norm = float(d_peak / ac)
        # ClQ proxy (NOT EGG CQ): 1 - open_frac
        estimated_clq_proxy = float(np.clip(1.0 - open_frac, 0.0, 1.0))
        out.append(
            {
                "estimated_naq": estimated_naq,
                "estimated_qoq": estimated_qoq,
                "estimated_oq_proxy": estimated_qoq,
                "estimated_clq_proxy": estimated_clq_proxy,
                "estimated_mfdr_proxy": estimated_mfdr,
                "estimated_mfdr_norm_proxy": estimated_mfdr_norm,
                "glottal_pulse_amplitude_proxy": ac,
                "t0_sec": t0,
            }
        )
    return out


def compute_source_params(
    glottal_flow: np.ndarray,
    sr: int,
    f0_hz: Optional[float] = None,
) -> dict[str, Any]:
    g = np.asarray(glottal_flow, dtype=float)
    gci_info = estimate_gci(g, sr, f0_hz=f0_hz)
    if not gci_info.get("valid"):
        return {
            "valid": False,
            "reason": "insufficient_gci",
            "estimated_naq": None,
            "estimated_qoq": None,
            "estimated_oq_proxy": None,
            "estimated_clq_proxy": None,
            "estimated_mfdr_proxy": None,
            "estimated_hrf_proxy": None,
            "gci": gci_info,
        }

    dflow = np.diff(g, prepend=g[0])
    gci = np.asarray(gci_info["gci_samples"], dtype=int)
    cycles = _cycle_params(g, dflow, gci, sr)
    if len(cycles) < 2:
        return {
            "valid": False,
            "reason": "too_few_cycles",
            "estimated_naq": None,
            "gci": gci_info,
        }

    def med(key: str) -> float:
        return float(np.median([c[key] for c in cycles]))

    # HRF proxy from spectrum of differentiated glottal estimate
    spec = np.abs(np.fft.rfft(dflow * np.hanning(len(dflow))))
    freqs = np.fft.rfftfreq(len(dflow), 1.0 / sr)
    f0 = f0_hz or gci_info.get("f0_implied_hz") or 150.0
    h_amps = []
    for k in range(1, 6):
        target = k * f0
        if target >= freqs[-1]:
            break
        idx = int(np.argmin(np.abs(freqs - target)))
        h_amps.append(float(spec[idx]) + 1e-12)
    if len(h_amps) >= 2:
        hrf = float(np.sum(h_amps[1:]) / h_amps[0])
        h1_h2_db = float(20 * np.log10(h_amps[0] / h_amps[1]))
    else:
        hrf = None
        h1_h2_db = None

    return {
        "valid": True,
        "reason": None,
        "estimated_naq": med("estimated_naq"),
        "estimated_qoq": med("estimated_qoq"),
        "estimated_oq_proxy": med("estimated_oq_proxy"),
        "estimated_clq_proxy": med("estimated_clq_proxy"),
        "estimated_mfdr_proxy": med("estimated_mfdr_proxy"),
        "estimated_mfdr_norm_proxy": med("estimated_mfdr_norm_proxy"),
        "estimated_hrf_proxy": hrf,
        "estimated_source_h1_h2_db": h1_h2_db,
        "glottal_pulse_amplitude_proxy": med("glottal_pulse_amplitude_proxy"),
        "n_cycles": len(cycles),
        "cycle_dispersion_naq": float(np.std([c["estimated_naq"] for c in cycles])),
        "gci": gci_info,
        "grade": "B",  # well-supported audio proxy when validity passes
        "caveat": (
            "Audio-derived OQ/ClQ proxies are NOT identical to EGG CQ "
            "or imaging-based closed quotient."
        ),
    }
