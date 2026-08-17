# Secret audit

- `BEGIN PRIVATE KEY` in repo source: none found
- mTLS cert/key paths are env-only (`TOSS_MTLS_CERT_PATH` / `TOSS_MTLS_KEY_PATH`)
- Login response tests assert Toss access/refresh tokens are absent
- Session tokens are HMAC-signed VAgent tokens, not Toss tokens
- gitleaks: not run (not installed)
- `.env` payment/mTLS keys: not set in this workspace (LIVE_IAP_NOT_VERIFIED_CREDENTIALS_MISSING)

Do not log: AccessToken, RefreshToken, mTLS private key, authorizationCode, full session token.
Order IDs may be masked (`abcd…wxyz`) in payment logs.
