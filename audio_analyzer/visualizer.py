"""
visualizer.py
-------------
분석 결과를 PNG 이미지로 저장하거나 대화형 창으로 표시한다.

생성 파일
    - waveform.png   : 시간-진폭 파형
    - spectrogram.png: mel 스펙트로그램 (로그 스케일)
    - pitch_curve.png: 프레임별 F0 곡선 (유성음 구간만 표시)
"""

from pathlib import Path
import numpy as np
import librosa
import librosa.display
import matplotlib


# ---------------------------------------------------------------------------
# 공개 함수
# ---------------------------------------------------------------------------

def generate_visualizations(
    y: np.ndarray,
    sr: int,
    pitch_features: dict,
    output_dir: Path,
) -> None:
    """세 가지 시각화 이미지를 output_dir 에 저장한다."""
    matplotlib.use("Agg")
    import matplotlib.pyplot as _plt

    _save_waveform(y, sr, output_dir / "waveform.png", _plt)
    _save_spectrogram(y, sr, output_dir / "spectrogram.png", _plt)
    _save_pitch_curve(pitch_features, output_dir / "pitch_curve.png", _plt)


def show_visualizations(
    y: np.ndarray,
    sr: int,
    pitch_features: dict,
) -> None:
    """
    파형 / 스펙트로그램 / Pitch 곡선을 하나의 창에 대화형으로 표시한다.
    GUI 백엔드를 자동 선택한다 (TkAgg → Qt5Agg → WXAgg 순).
    """
    _switch_to_gui_backend()
    import matplotlib.pyplot as _plt

    hop_length = 512
    n_fft = 2048

    fig, axes = _plt.subplots(3, 1, figsize=(14, 10))
    fig.suptitle("Vocal Analysis", fontsize=14, fontweight="bold")

    # ── 1. Waveform (최대 44100 포인트로 다운샘플) ─────────────────────────────
    ax0 = axes[0]
    MAX_POINTS = 44100
    if len(y) > MAX_POINTS:
        idx = np.linspace(0, len(y) - 1, MAX_POINTS, dtype=int)
        y_plot = y[idx]
        times = np.linspace(0, len(y) / sr, MAX_POINTS)
    else:
        y_plot = y
        times = np.linspace(0, len(y) / sr, len(y))
    ax0.plot(times, y_plot, color="#4C9BE8", linewidth=0.4, alpha=0.85)
    ax0.set_ylabel("Amplitude")
    ax0.set_title("Waveform")
    ax0.set_xlim(0, times[-1])
    ax0.set_ylim(-1.05, 1.05)
    ax0.axhline(0, color="gray", linewidth=0.5, linestyle="--")
    ax0.set_xlabel("")

    # ── 2. Mel Spectrogram ────────────────────────────────────────────────────
    ax1 = axes[1]
    S = librosa.feature.melspectrogram(
        y=y, sr=sr, n_fft=n_fft, hop_length=hop_length, n_mels=128
    )
    S_db = librosa.power_to_db(S, ref=np.max)
    img = librosa.display.specshow(
        S_db, sr=sr, hop_length=hop_length,
        x_axis="time", y_axis="mel", ax=ax1, cmap="magma",
    )
    fig.colorbar(img, ax=ax1, format="%+2.0f dB")
    ax1.set_title("Mel Spectrogram")
    ax1.set_xlabel("")

    # ── 3. Pitch Curve ────────────────────────────────────────────────────────
    ax2 = axes[2]
    frame_f0 = pitch_features.get("frame_f0", [])
    if frame_f0:
        t_arr = np.array([f["time_sec"] for f in frame_f0])
        f0_arr = np.array(
            [f["f0_hz"] if f["f0_hz"] is not None else np.nan for f in frame_f0]
        )
        ax2.plot(t_arr, f0_arr, color="#E87A4C", linewidth=1.0, label="F0 (Hz)")
        ax2.set_xlim(t_arr[0], t_arr[-1])
        ax2.legend(loc="upper right")
        ax2.grid(axis="y", linewidth=0.4, alpha=0.5)
    else:
        ax2.text(0.5, 0.5, "No voiced frames detected",
                 ha="center", va="center", transform=ax2.transAxes)
    ax2.set_xlabel("Time (s)")
    ax2.set_ylabel("Frequency (Hz)")
    ax2.set_title("Pitch Curve (F0)")

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    _plt.show()


# ---------------------------------------------------------------------------
# 내부 함수
# ---------------------------------------------------------------------------

def _switch_to_gui_backend() -> None:
    """사용 가능한 GUI 백엔드를 순서대로 시도한다."""
    for backend in ("TkAgg", "Qt5Agg", "WXAgg"):
        try:
            matplotlib.use(backend)
            return
        except Exception:
            continue


def _save_waveform(y: np.ndarray, sr: int, path: Path, _plt) -> None:
    """시간-진폭 파형을 PNG로 저장한다. 긴 음원은 최대 44100 포인트로 다운샘플."""
    MAX_POINTS = 44100
    if len(y) > MAX_POINTS:
        idx = np.linspace(0, len(y) - 1, MAX_POINTS, dtype=int)
        y_plot = y[idx]
        times = np.linspace(0, len(y) / sr, MAX_POINTS)
    else:
        y_plot = y
        times = np.linspace(0, len(y) / sr, len(y))

    fig, ax = _plt.subplots(figsize=(12, 3))
    ax.plot(times, y_plot, color="#4C9BE8", linewidth=0.4, alpha=0.85)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Amplitude")
    ax.set_title("Waveform")
    ax.set_xlim(0, times[-1])
    ax.set_ylim(-1, 1)
    ax.axhline(0, color="gray", linewidth=0.5, linestyle="--")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    _plt.close(fig)


def _save_spectrogram(y: np.ndarray, sr: int, path: Path, _plt) -> None:
    """Mel 스펙트로그램(dB 스케일)을 PNG로 저장한다."""
    hop_length = 512
    n_fft = 2048

    S = librosa.feature.melspectrogram(
        y=y, sr=sr, n_fft=n_fft, hop_length=hop_length, n_mels=128
    )
    S_db = librosa.power_to_db(S, ref=np.max)

    fig, ax = _plt.subplots(figsize=(12, 4))
    img = librosa.display.specshow(
        S_db, sr=sr, hop_length=hop_length,
        x_axis="time", y_axis="mel", ax=ax, cmap="magma",
    )
    fig.colorbar(img, ax=ax, format="%+2.0f dB")
    ax.set_title("Mel Spectrogram")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    _plt.close(fig)


def _save_pitch_curve(pitch_features: dict, path: Path, _plt) -> None:
    """프레임별 F0 곡선을 PNG로 저장한다. Unvoiced 구간은 빈칸으로 표시한다."""
    frame_f0 = pitch_features.get("frame_f0", [])

    fig, ax = _plt.subplots(figsize=(12, 3))

    if not frame_f0:
        ax.set_title("Pitch Curve (no voiced frames detected)")
    else:
        times = np.array([f["time_sec"] for f in frame_f0])
        f0_values = np.array(
            [f["f0_hz"] if f["f0_hz"] is not None else np.nan for f in frame_f0]
        )
        ax.plot(times, f0_values, color="#E87A4C", linewidth=1.0, label="F0 (Hz)")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Frequency (Hz)")
        ax.set_title("Pitch Curve (F0)")
        ax.set_xlim(times[0], times[-1])
        ax.legend(loc="upper right")
        ax.grid(axis="y", linewidth=0.4, alpha=0.5)

    fig.tight_layout()
    fig.savefig(path, dpi=150)
    _plt.close(fig)
