# Enrollment Size Robustness Curve

| Size | N evals | Mean held-out sim | Min | Top1 global rate | MATCH rate | UNCERTAIN rate |
|---:|---:|---:|---:|---:|---:|---:|
| 2 | 168 | 0.7997 | 0.6728 | 0.1369 | 0.9286 | 0.0714 |
| 3 | 280 | 0.8198 | 0.6965 | 0.1750 | 0.9857 | 0.0143 |
| 4 | 280 | 0.8304 | 0.7162 | 0.2214 | 0.9964 | 0.0036 |
| 5 | 168 | 0.8369 | 0.7354 | 0.2560 | 1.0000 | 0.0000 |
| 6 | 56 | 0.8413 | 0.7558 | 0.3393 | 1.0000 | 0.0000 |
| 7 | 8 | 0.8446 | 0.7785 | 0.5000 | 1.0000 | 0.0000 |

Does more enrollment improve robustness: **YES**
Evidence: mean sim 0.7997 (size=2) → 0.8446 (size=7); top1 0.1369 → 0.5000
