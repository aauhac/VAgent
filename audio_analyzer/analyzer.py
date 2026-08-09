"""Compatibility shim — use audio_analyzer.pipeline.analyze_audio."""

from audio_analyzer.pipeline import analyze_audio, analyze_mp3

__all__ = ["analyze_audio", "analyze_mp3"]
