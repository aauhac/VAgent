# Architecture (VAgent v2)

## Pipeline

```mermaid
flowchart TD
  A[Original Audio] --> B[Optional Demucs separate=false default]
  B --> C[Analysis Signal<br/>mono / SR / DC only]
  B --> D[Preview Signal<br/>listening EQ/comp only]
  C --> E[Feature Extraction<br/>waveform / spectral / pitch / phonation]
  E --> F[Quality Gate]
  F -->|fail| G[score.available = false<br/>정확한 분석이 어려운 녹음]
  F -->|pass/warn| H[Scoring v2<br/>stability / projection / resonance / dynamic_control]
  H --> I[Issues + Timeline<br/>phonation_instability only]
  I --> J[Optional LLM Narration]
  J --> K[FastAPI public_result]
  K --> L[Toss Mini App vocalfb]
  D --> L
```

## Principles

- Deterministic score first; LLM never computes scores.
- Melody F0 movement ≠ phonation instability.
- UNKNOWN confidence never becomes strength.
- Quality FAIL ≠ skill score 0.
- Analysis path must not use preview EQ.
