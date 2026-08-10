# Vocal Function Literature Hostile Audit (v2)

Verdict key: SUPPORTED | CONDITIONAL | WEAK | UNSUPPORTED

| Parameter | Audio-only meaning | Verdict | Product use |
|-----------|-------------------|---------|-------------|
| F0 / voicing | Direct acoustic | SUPPORTED | Level 1 |
| CPP / CPPS proxy | Periodicity ↔ perceived breathiness (speech-heavy lit.) | CONDITIONAL | Leakage family; confound by F0/SPL |
| HNR | Periodicity / noise | CONDITIONAL | Same periodicity family as CPP |
| H1−H2 / H1*−H2* | Source spectral balance correlate | CONDITIONAL | Contact/leakage direction; vowel confounds |
| NAQ (GIF) | Glottal pulse shape proxy (Alku et al.) | CONDITIONAL | Contact continuum; validity-gated |
| QOQ / OQ proxy | Open-phase fraction proxy | CONDITIONAL / WEAK in singing | estimated_ only; ≠ EGG CQ |
| ClQ proxy | 1−OQ style | WEAK vs EGG CQ | Never label as CQ |
| MFDR | Flow declination rate proxy | CONDITIONAL | Effort/contact secondary |
| Rd / LF params | Model fit | WEAK in song mix | Research / debug |
| Formants LPC | Tract resonances | CONDITIONAL | High F0 poorly resolved |
| Formant tuning | H–F proximity | CONDITIONAL | Style-aware descriptive |
| Strain from single metric | — | UNSUPPORTED | Multi-family + persistence required |
| Anatomy (nodules, TA/LCA) | — | UNSUPPORTED | Banned |
| Subglottal pressure / diaphragm | — | UNSUPPORTED | Proxy wording only |

GIF method in product: `iaif_proxy_v1` (Alku-inspired).  
Not claimed identical to COVAREP/DisVoice clinical pipelines.  
No paper mean used as clinical bad/good threshold (directional + personal baseline only).

Primary refs (direction/validity, not cutoffs): Alku IAIF/NAQ literature; Hillenbrand CPP; Boersma HNR; Saldías CPPS singing confounds; Gobl/Ni Chasaide voice quality; Sundberg singer’s formant (descriptive).
