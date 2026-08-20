# -*- coding: utf-8 -*-
"""Lightsail package + Home product copy contracts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MINI = ROOT / "miniapp" / "src"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_home_product_tier_section_removed():
    home = (MINI / "pages" / "Home.tsx").read_text(encoding="utf-8")
    assert "분석 단계" not in home
    assert "확인 항목 측정" not in home
    assert "home-product-compare" not in home
    assert "보컬 리포트" not in home
    assert "고음과 음색이 어떻게 달라지는지" not in home
    assert "개인화 발성 피드백" not in home
    assert "맞춤 연습" not in home
    assert "단계별 훈련" not in home
    assert "₩990" not in home
    assert "₩1,980" not in home
    assert "displayAmount" not in home
    assert "녹음 시작" in home
    assert "이용약관" in home
    assert "무료 리포트" in home
    assert "상세 리포트" in home
    assert "보컬 진단" in home
    assert "15~60초 한 구절이면 충분해요." in home


def test_precision_home_promise_matches_report_feedback_not_training():
    prem = (MINI / "pages" / "PremiumReport.tsx").read_text(encoding="utf-8")
    assert "당신이 궁금했던 것" in prem
    assert 'data-testid="qa-section"' in prem
    # Training remains debug-only
    assert "showDebug" in prem
    home = (MINI / "pages" / "Home.tsx").read_text(encoding="utf-8")
    assert "연습법" not in home
    assert "훈련 프로그램" not in home


def test_lightsail_deploy_files_exist():
    assert (ROOT / "scripts" / "package_lightsail_release.ps1").is_file()
    assert (ROOT / "deploy" / "lightsail" / "docker-compose.production.yml").is_file()
    assert (ROOT / "deploy" / "lightsail" / "deploy.sh").is_file()
    assert (ROOT / "deploy" / "lightsail" / "Dockerfile.backend").is_file()
    assert (ROOT / "deploy" / "lightsail" / "nginx-vocalfb.conf.template").is_file()
    assert (ROOT / "deploy" / "lightsail" / "check_capacity.sh").is_file()


def test_compose_ports_are_loopback_and_postgres_closed():
    compose = _read("deploy/lightsail/docker-compose.production.yml")
    assert "127.0.0.1:8000:8000" in compose
    assert "0.0.0.0:8000" not in compose
    assert "5432:5432" not in compose
    assert "/var/lib/vocalfb/runtime:/var/lib/vocalfb/runtime" in compose
    assert "/var/lib/vocalfb/postgres:/var/lib/postgresql/data" in compose
    assert "/etc/vocalfb/secrets:/etc/vocalfb/secrets:ro" in compose
    assert "replicas:" not in compose
    assert "scale:" not in compose


def test_compose_queue_worker_model_cache_and_aws_env_files():
    compose = _read("deploy/lightsail/docker-compose.production.yml")
    services: dict[str, str] = {}
    current = None
    chunks: list[str] = []
    for line in compose.splitlines(keepends=True):
        if line.startswith("  ") and not line.startswith("    ") and line.strip().endswith(":"):
            name = line.strip().rstrip(":")
            if current is not None:
                services[current] = "".join(chunks)
            current = name
            chunks = [line]
        elif current is not None:
            chunks.append(line)
    if current is not None:
        services[current] = "".join(chunks)

    postgres = services["postgres"]
    backend = services["backend"]
    worker = services["worker"]

    assert "profiles:" in worker
    assert "queue-worker" in worker
    assert "TORCH_HOME: /model-cache" in worker
    assert "/var/lib/vocalfb/model-cache:/model-cache" in worker
    assert "/var/lib/vocalfb/runtime:/var/lib/vocalfb/runtime" in worker
    assert "/var/lib/vocalfb/worker:/var/lib/vocalfb/worker" in worker
    assert "/etc/vocalfb/secrets:/etc/vocalfb/secrets:ro" in worker
    assert worker.count("replicas:") == 0
    assert "scale:" not in worker

    aws_env = "/etc/vocalfb/secrets/aws-queue-staging.env"
    vocalfb_env = "/etc/vocalfb/vocalfb.env"
    assert vocalfb_env in backend
    assert aws_env in backend
    assert vocalfb_env in worker
    assert aws_env in worker
    assert vocalfb_env in postgres
    assert aws_env not in postgres
    assert "TORCH_HOME" not in backend
    assert "model-cache" not in backend
    assert "Dockerfile.worker" in worker
    backend_df = _read("deploy/lightsail/Dockerfile.backend")
    assert "ARG INSTALL_SEPARATION=0" in backend_df
    assert "CMD [\"uvicorn\"" in backend_df


def test_backend_dockerfile_single_worker_no_reload():
    df = _read("deploy/lightsail/Dockerfile.backend")
    assert "uvicorn" in df
    assert "backend.app.main:app" in df
    assert "--workers\", \"1\"" in df or "--workers 1" in df
    assert "--reload" not in df
    assert "python:3.12-slim" in df
    assert "ffmpeg" in df
    assert "libsndfile1" in df
    assert "USER vocalfb" in df


def test_deploy_sh_migration_before_backend_and_no_downgrade():
    sh = _read("deploy/lightsail/deploy.sh")
    assert "set -Eeuo pipefail" in sh
    assert "alembic" in sh
    assert "upgrade head" in sh
    assert "alembic downgrade" not in sh
    assert "downgrade head" not in sh
    assert "/health" in sh
    assert "/ready" in sh
    idx_mig = sh.find("upgrade head")
    idx_up = sh.find("up -d backend")
    assert 0 <= idx_mig < idx_up


def test_nginx_template_http_placeholder_only():
    ngx = _read("deploy/lightsail/nginx-vocalfb.conf.template")
    assert "__BACKEND_HOSTNAME__" in ngx
    assert "proxy_pass http://127.0.0.1:8000;" in ngx
    assert "ssl_certificate" not in ngx
    assert "listen 443" not in ngx


def test_env_production_example_uses_repo_names():
    env = _read(".env.production.example")
    assert "VAGENT_ENV=production" in env
    assert "APP_ENV=" not in env
    for name in (
        "DATABASE_URL",
        "PUBLIC_BACKEND_BASE_URL",
        "PAYMENTS_ENABLED",
        "TOSS_LOGIN_ENABLED",
        "TOSS_API_BASE_URL",
        "TOSS_MTLS_CERT_PATH",
        "TOSS_MTLS_KEY_PATH",
        "IAP_SONG_DETAIL_SKU",
        "IAP_DIAGNOSTIC_FULL_SKU",
        "IAP_DIAGNOSTIC_UPGRADE_SKU",
        "VAGENT_SESSION_SECRET",
        "CORS_ORIGINS",
        "TOSS_DISCONNECT_BASIC_USER",
        "TOSS_DISCONNECT_BASIC_PASSWORD",
        "RUNTIME_DIR",
    ):
        assert name in env, name
