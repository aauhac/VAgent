# Backend

## FastAPI (VAgent v2)

### Run (PowerShell)

```powershell
cd C:\VocalAgent
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

### Endpoints

- `GET /health`
- `POST /v1/analyses` multipart `file`, optional `separate`, `include_feedback`
- `GET /v1/analyses/{analysis_id}`
- `DELETE /v1/analyses/{analysis_id}`

Runtime files are stored under `runtime/<uuid>/` (gitignored).
