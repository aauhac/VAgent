# Production region checklist

Provider packaging path: **AWS Lightsail** (`deploy/lightsail/`).  
Do not mark 「국외 이전 없음」 until the live instance region and data stores are reviewed.

| Asset | Question | Status |
| --- | --- | --- |
| Compute | Lightsail instance country/region | **OPERATOR_INPUT_REQUIRED** (not in repo) |
| PostgreSQL | Primary region | **OPERATOR_INPUT_REQUIRED** |
| PostgreSQL replicas / PITR | Replica and backup region | **OPERATOR_INPUT_REQUIRED** |
| Audio / runtime artifacts | Region of the persistent volume (and future object storage) | **OPERATOR_INPUT_REQUIRED** |
| Backup | Snapshot / backup region and retention location | **OPERATOR_INPUT_REQUIRED** |
| Logs | Log sink region | **OPERATOR_INPUT_REQUIRED** |
| Monitoring | Metrics / traces region | **OPERATOR_INPUT_REQUIRED** / unused if unset |
| External processor | Apps in Toss / Toss servers (login, IAP, callbacks) | Toss infrastructure — separate processor |
| LLM / OpenAI-compatible | Only if `OPENAI_API_KEY` / `BASE_URL` is enabled | unused on live HTTP analysis path |
| CDN / miniapp static | Toss-hosted `*.apps.tossmini.com` | Toss-hosted; not our origin |

Rules:

- Prefer a Korea region for compute, PostgreSQL, audio volume, backups, logs, and monitoring.
- A cloud-provided HTTPS hostname does not imply the data stays in Korea.
- Do not invent `ap-northeast-2` (or any region) in legal docs without console evidence.
- Fill this table from the live AWS account, then align privacy policy §6.
