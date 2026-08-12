import httpx
import os
import subprocess
import sys

from sqlalchemy import create_engine, text

BASE = "http://127.0.0.1:8766"
AID = "e6ed8e510c514ba389e38425d271dbc7"
H = {"X-User-Id": "e2e-user-001", "X-VAgent-User-Key": "e2e-user-001"}
HB = {"X-User-Id": "e2e-user-B"}
DB = "postgresql+psycopg://vagent:vagent@127.0.0.1:5433/vagent"

eng = create_engine(DB)
with eng.connect() as c:
    row = c.execute(
        text("select status, completed_at is not null as has_completed from analyses where id=:i"),
        {"i": AID},
    ).mappings().first()
    print("DB", dict(row) if row else None)
    ents = c.execute(
        text(
            "select count(*) from entitlements e join users u on u.id=e.user_id "
            "where u.external_subject='e2e-user-001'"
        )
    ).scalar()
    print("entitlements", ents)

with httpx.Client(timeout=30) as c:
    hist = c.get(f"{BASE}/v1/history", headers=H)
    items = hist.json()["items"]
    print("history", hist.status_code, any(i["analysis_id"] == AID for i in items))
    g = c.get(f"{BASE}/v1/analyses/{AID}", headers=H)
    print("get", g.status_code, g.json().get("status"))
    a = c.get(f"{BASE}/v1/analyses/{AID}/access", headers=H)
    print("access", a.status_code, a.json().get("song_detail_unlocked"))
    p = c.get(f"{BASE}/v1/analyses/{AID}/preview", headers=H)
    print("preview", p.status_code, p.headers.get("content-type"), len(p.content))
    sid = c.post(
        f"{BASE}/v1/diagnostic-sessions",
        headers=H,
        params={"source_analysis_id": AID},
    ).json()["session_id"]
    print("diag create", sid[:8])
    print("B diag get", c.get(f"{BASE}/v1/diagnostic-sessions/{sid}", headers=HB).status_code)

# production without DATABASE_URL must fail
code = """
import os
os.environ['VAGENT_ENV']='production'
os.environ.pop('DATABASE_URL', None)
from backend.app.main import _on_startup
from backend.app import main as m
# ensure database_url returns None
m.__dict__  # noqa
from backend.app import config
# clear any dotenv pollution by monkeypatching
import backend.app.main as main_mod
main_mod.database_url = lambda: None
main_mod.runtime_writable = lambda: True
main_mod.is_production = lambda: True
main_mod.log_startup_banner = lambda: None
main_mod.get_runtime_dir = lambda: None
try:
    main_mod._on_startup()
    print('STARTED_UNEXPECTEDLY')
except RuntimeError as e:
    print('FAILS', str(e))
"""
env = {**os.environ, "PYTHONPATH": r"C:\VocalAgent", "VAGENT_ENV": "production"}
env.pop("DATABASE_URL", None)
r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=r"C:\VocalAgent", env=env)
print((r.stdout or "").strip() or (r.stderr or "")[-800:])
