# Production region checklist

Do not mark 국외 이전 없음 until a real vendor contract and service geography are reviewed.

Provider is **not chosen**. For each row, fill country/region from the actual
product docs / DPA **after** an account exists.

| Asset | Question | Status |
| --- | --- | --- |
| Compute | Country/region of the backend VM or platform | UNCONFIRMED |
| PostgreSQL | Primary region | UNCONFIRMED |
| PostgreSQL replicas / PITR | Replica and backup region | UNCONFIRMED |
| Audio / runtime artifacts | Region of the persistent volume (and future object storage) | UNCONFIRMED |
| Backup | Snapshot / backup region and retention location | UNCONFIRMED |
| Logs | Log sink region | UNCONFIRMED |
| Monitoring | Metrics / traces region | UNCONFIRMED |
| External processor | Apps in Toss / Toss servers (login, IAP, callbacks) | Toss infrastructure — treat as a separate processor; do not assume domestic without their DPA |
| LLM / OpenAI-compatible | Only if `OPENAI_API_KEY` / `BASE_URL` is enabled | UNCONFIRMED / unused if unset |
| CDN / miniapp static | Toss-hosted `*.apps.tossmini.com` | Toss-hosted; not our origin |

Rules:

- Prefer a Korea region for compute, PostgreSQL, audio volume, backups, logs, and monitoring once a vendor is chosen.
- A cloud-provided HTTPS hostname does not imply the data stays in Korea.
- Do not copy a “no international transfer” sentence into the privacy policy until this table is filled from real contracts.
