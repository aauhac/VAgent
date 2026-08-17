# Dependency audit

## Python

- pytest: 1274 passed / 1 skipped
- pip-audit: **NOT INSTALLED**
- bandit: **NOT INSTALLED**

## Node (miniapp)

- tsc: PASS
- build:web: PASS
- build:toss: PASS (vocalfb.ait)

npm audit (do **not** `npm audit fix --force`):

- Transitive `@babel/core` advisory via `@apps-in-toss/web-framework` / granite toolchain
- Suggested force-fix would jump web-framework to 3.x (breaking)
- Classification: P2 toolchain, not an app payment bypass

IAP imports tree-shake: build succeeded with dynamic `import('@apps-in-toss/web-framework')`.
