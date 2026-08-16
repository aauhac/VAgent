# Representation Strategy Comparison (EXPERIMENTAL)

Production default remains **SINGLE_CENTROID**.
Multi-prototype is **not** auto-promoted.
False-accept evaluation: **INSUFFICIENT_MULTI_SINGER_NEGATIVES**

| Strategy | LOO MATCH | Mean | Min | Hard+ mean | love again |
|---|---:|---:|---:|---:|---:|
| SINGLE_CENTROID | 11/11 | 0.8373 | 0.7646 | 0.7843 | 0.7646 |
| MEDOID | 9/11 | 0.7823 | 0.6874 | 0.7311 | 0.6874 |
| MULTI_PROTOTYPE_K2 | 11/11 | 0.8543 | 0.7992 | 0.8186 | 0.8115 |
| MULTI_PROTOTYPE_K3 | 11/11 | 0.8480 | 0.7987 | 0.8100 | 0.8115 |

Does multi-prototype help hard positives: **YES**
Verdict: **MULTI_PROTOTYPE_PROMISING_BUT_UNVALIDATED**
Can production winner be selected now: **NO**

Unlabeled remaining mean centroid/k2/k3: 0.4100 / 0.4388 / 0.4424
(Not true negatives — do not interpret as false-accept rate.)
