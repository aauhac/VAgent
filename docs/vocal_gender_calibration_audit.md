# 여성/남성 음원 calibration audit (후속)

이번 작업에서는 성별에 따른 분석 파라미터를 변경하지 않는다.
성별 추정 기능도 추가하지 않는다.

여성 샘플이 준비되면 `scripts/audit_public_analysis.py` 로 남성 샘플과 **같은 조건**에서 비교한 뒤에만 threshold calibration을 검토한다.

## 비교할 항목

- F0 distribution
- voiced_ratio
- n usable segments
- evidence mass
- source family count
- family agreement
- UNRESOLVED 비율 (`vocal_type_teaser.resolution_state`)
- main finding FOUND / NONE / UNRESOLVED 비율

## 하지 말 것

- 보류 결과를 흉성/두성/믹스로 강제 변환
- 여성 음원이 잘 나오게 하려고 FMIN/FMAX, F0, NAQ, H1H2, evidence mass, family agreement threshold 완화
