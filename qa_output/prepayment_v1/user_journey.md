# User Journey (API E2E)

1. Create analysis (WAV) → completed
2. Access: song_detail=false, diagnostic=false
3. GET detailed-report → 402 SONG_DETAIL_LOCKED
4. POST mock-unlock-detail → 200 (idempotent 2nd call)
5. GET detailed-report → 200 song_detail
6. Access: song_detail=true, diagnostic=false (product split OK)
7. PUT vocal-goals/active REGISTER_CONNECTION → ACTIVE
8. Second analysis completed
9. POST progress insight with goal context → 200
10. Create diagnostic session → report 402
11. mock-pay (idempotent) → unlock
12. concerns GENERAL_DISCOVERY → safety → start recordings
13. Upload 1 task → skip remaining → analyze → report 200
14. Rebind services on same runtime_dir (restart sim)
15. Detail entitlement, goal, diagnostic session+report all recover
16. New unpaid analysis still 402

Script: `scripts/e2e_pre_payment_full_product.py`
Artifact: `qa_output/prepayment_v1/e2e_api_journey.json`
