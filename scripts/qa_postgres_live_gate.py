"""Run disposable QA Postgres live gate. Prints no secrets."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.qa-postgres.yml"
OUT = ROOT / "qa_output" / "production_release_v1" / "postgres_live"
URL = "postgresql+psycopg://vagent_qa:vagent_qa@127.0.0.1:55432/vagent_qa"
PY = ROOT / ".venv" / "Scripts" / "python.exe"
if not PY.exists():
    PY = Path(sys.executable)


def _run(cmd: list[str], *, env: dict | None = None, timeout: int = 180) -> subprocess.CompletedProcess:
    merged = os.environ.copy()
    merged["PYTHONUTF8"] = "1"
    merged["PYTHONIOENCODING"] = "utf-8"
    if env:
        merged.update(env)
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=merged,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _out(proc: subprocess.CompletedProcess) -> str:
    return (proc.stdout or "") + (proc.stderr or "")


def _write(name: str, text: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cleaned = text.replace("vagent_qa:vagent_qa", "vagent_qa:***")
    (OUT / name).write_text(cleaned, encoding="utf-8")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    docker = _run(["docker", "version"])
    info = _run(["docker", "info"])
    compose = _run(["docker", "compose", "version"])
    _write("docker_version.txt", _out(docker))
    _write("docker_info.txt", _out(info)[-4000:])
    _write("docker_compose_version.txt", _out(compose))
    if docker.returncode != 0 or info.returncode != 0:
        _write(
            "RESULT.txt",
            "BLOCKED_POSTGRES_NOT_VERIFIED\nDocker daemon unavailable.\n",
        )
        print("BLOCKED_POSTGRES_NOT_VERIFIED")
        return 2

    up = _run(["docker", "compose", "-f", str(COMPOSE), "up", "-d"], timeout=120)
    _write("compose_up.txt", _out(up))
    if up.returncode != 0:
        _write("RESULT.txt", "BLOCKED_POSTGRES_NOT_VERIFIED\ncompose up failed\n")
        return 2

    for _ in range(40):
        ready = _run(
            ["docker", "exec", "vagent-postgres-qa-gate", "pg_isready", "-U", "vagent_qa", "-d", "vagent_qa"]
        )
        if ready.returncode == 0:
            break
        time.sleep(1)
    else:
        _write("RESULT.txt", "BLOCKED_POSTGRES_NOT_VERIFIED\nPostgres not ready\n")
        return 2

    env = {"DATABASE_URL": URL, "POSTGRES_QA_URL": URL}
    reset_public = _run(
        [
            "docker",
            "exec",
            "vagent-postgres-qa-gate",
            "psql",
            "-U",
            "vagent_qa",
            "-d",
            "vagent_qa",
            "-c",
            "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO vagent_qa;",
        ]
    )
    _write("fresh_reset.log", _out(reset_public))
    fresh = _run([str(PY), "-m", "alembic", "upgrade", "head"], env=env, timeout=120)
    _write("fresh_upgrade.log", _out(fresh))
    if fresh.returncode != 0:
        _write("RESULT.txt", "FAIL\nfresh alembic upgrade head failed\n")
        return 1

    schema = _run(
        [
            "docker",
            "exec",
            "vagent-postgres-qa-gate",
            "psql",
            "-U",
            "vagent_qa",
            "-d",
            "vagent_qa",
            "-c",
            "\\dt",
            "-c",
            "SELECT indexname FROM pg_indexes WHERE tablename IN ('purchase_orders','payment_intents','entitlements','diagnostic_sessions') ORDER BY 1;",
        ]
    )
    _write("schema_verification.txt", _out(schema))

    tests = _run(
        [str(PY), "-m", "pytest", "tests/payments/test_postgres_live_gate.py", "-q", "--tb=short"],
        env=env,
        timeout=180,
    )
    _write("payment_persistence.log", _out(tests))
    if tests.returncode != 0:
        _write("RESULT.txt", "FAIL\nlive postgres payment tests failed\n")
        return 1

    # Existing upgrade: recreate schema at previous revision in a second database.
    recreate_upgrade = _run(
        [
            "docker",
            "exec",
            "vagent-postgres-qa-gate",
            "psql",
            "-U",
            "vagent_qa",
            "-d",
            "postgres",
            "-c",
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='vagent_qa_upgrade'; "
            "DROP DATABASE IF EXISTS vagent_qa_upgrade; CREATE DATABASE vagent_qa_upgrade;",
        ]
    )
    _write("existing_recreate_db.log", _out(recreate_upgrade))
    upgrade_url = URL.rsplit("/", 1)[0] + "/vagent_qa_upgrade"
    prev = _run(
        [str(PY), "-m", "alembic", "upgrade", "20260816_0004"],
        env={"DATABASE_URL": upgrade_url},
        timeout=120,
    )
    _write("existing_pre_0005.log", _out(prev))
    seed = _run(
        [str(PY), str(ROOT / "scripts" / "_seed_qa_upgrade.py")],
        env={"DATABASE_URL": upgrade_url},
        timeout=60,
    )
    _write("existing_seed.log", _out(seed))
    head = _run(
        [str(PY), "-m", "alembic", "upgrade", "head"],
        env={"DATABASE_URL": upgrade_url},
        timeout=120,
    )
    _write("existing_upgrade_0005.log", _out(head))
    check = _run(
        [
            "docker",
            "exec",
            "vagent-postgres-qa-gate",
            "psql",
            "-U",
            "vagent_qa",
            "-d",
            "vagent_qa_upgrade",
            "-c",
            "SELECT id, original_filename FROM analyses;",
            "-c",
            "SELECT tablename FROM pg_tables WHERE tablename IN ('payment_intents','auth_sessions');",
        ]
    )
    _write("existing_upgrade_result.txt", _out(check))
    if prev.returncode != 0 or head.returncode != 0 or "keep.wav" not in (check.stdout or ""):
        _write("RESULT.txt", "FAIL\nexisting upgrade path failed\n")
        return 1

    # DB outage: pause container and probe /ready via sqlalchemy reachable helper
    _run(["docker", "pause", "vagent-postgres-qa-gate"])
    time.sleep(1)
    outage = _run(
        [
            str(PY),
            "-c",
            (
                "import os; os.environ['DATABASE_URL']=%r; os.environ['VAGENT_ENV']='production';"
                "from backend.app.db.session import reset_engine, database_reachable;"
                "reset_engine();"
                "print('reachable', database_reachable())"
            )
            % URL,
        ],
        timeout=30,
    )
    _write("db_outage.txt", _out(outage))
    _run(["docker", "unpause", "vagent-postgres-qa-gate"])
    recovered = _run(
        [
            str(PY),
            "-c",
            (
                "import os; os.environ['DATABASE_URL']=%r;"
                "from backend.app.db.session import reset_engine, database_reachable;"
                "reset_engine();"
                "print('reachable', database_reachable())"
            )
            % URL,
        ],
        timeout=30,
    )
    _write("db_outage_recovered.txt", _out(recovered))
    if "reachable False" not in (outage.stdout or "") or "reachable True" not in (recovered.stdout or ""):
        _write("RESULT.txt", "FAIL\nDB outage fail-closed check failed\n")
        return 1

    _write(
        "RESULT.txt",
        "PASS\nfresh migration PASS\nexisting upgrade PASS\npayment persistence PASS\n"
        "restart PASS\nrefund PASS\nreplay PASS\nDB outage fail-closed PASS\n",
    )
    print("POSTGRES_LIVE_GATE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
