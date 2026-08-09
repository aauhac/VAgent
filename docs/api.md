# API

Base URL: `http://localhost:8000`

## GET /health

```json
{"status":"ok","service":"vocalfb","analysis_version":"2.0"}
```

## POST /v1/analyses

`multipart/form-data`

| field | type | default |
|-------|------|---------|
| file | audio file | required |
| separate | bool | false |
| include_feedback | bool | false |

Response:

```json
{"analysis_id":"...","status":"queued"}
```

## GET /v1/analyses/{analysis_id}

While running:

```json
{"status":"analyzing","stage":"features","progress":55}
```

Completed:

```json
{
  "status": "completed",
  "analysis_status": "completed",
  "feedback_status": "completed|failed|skipped",
  "result": { "...public schema..." }
}
```

LLM failure does **not** fail DSP analysis (`feedback_status: failed`).

## DELETE /v1/analyses/{analysis_id}

Deletes runtime files for the job.
