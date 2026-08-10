# Vocal Quality Boundary

VAgent Vocal Quality / Phonation State Engine observes **audio-only** tendencies.
It is **not** a medical or laryngeal diagnosis system.

## Audio-only systems CAN observe

- Acoustic periodicity (cepstral / HNR *proxies*)
- Spectral balance / tilt / centroid
- Harmonic structure proxies (e.g. raw H1−H2)
- Voice onset energy / periodicity establishment patterns
- Time-local irregularity / intermittency
- Register-transition acoustic disruption patterns
- Quality *tendencies* consistent with breathy / pressed / rough *perception*

## Audio-only systems CANNOT observe

- Actual laryngeal muscle tension
- Anatomical glottal closure pattern
- Lesions (nodules, polyps, etc.)
- Subglottal pressure
- Diaphragm / respiratory muscle activation
- Exact vocal fold contact
- “TA/CT imbalance” as a physiological fact
- Clinical diagnoses

## Allowed user language (examples)

- “숨이 섞이는 음질과 일치할 수 있는 경향이 반복해서 나타났어요.”
- “압착된 음질과 일치할 수 있는 음향 패턴이 관찰됐어요.”
- “중역 존재감이 낮고 어두운 음색 경향이 관찰됐어요.”
- “음역 전환 구간에서 주기성·스펙트럼 변화가 크게 나타났어요.”

## Forbidden user language (examples)

- “목이 조이고 있다”
- “성대 접촉이 부족하다”
- “후두가 긴장했다”
- “TA/CT 전환이 문제다”
- “성문이 벌어졌다”
- “결절이 있다”

When evidence is weak, conflicting, or contaminated (e.g. separation artifacts),
the engine must return **UNKNOWN / AMBIGUOUS** rather than force a conclusion.
