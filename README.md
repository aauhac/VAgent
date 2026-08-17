# 노래 실력 진단받기 (VAgent v2)

**서비스명:** 노래 실력 진단받기  
**appName:** `vocalfb`  
**영문 표시명:** Vocal Skill Test

사용자가 노래를 녹음·업로드하면 음향 특성을 분석하고, deterministic 점수와(선택) LLM 설명을 제공합니다.

> 이 서비스는 **원곡 음정/박자 정확도**를 평가하지 않습니다.  
> F0는 지속음 안정성·비브라토·유성음 판정 등에만 사용합니다.  
> **의료 진단 서비스가 아닙니다.**

점수는 `vocal-score-v2.0` / `calibration_status: uncalibrated` 입니다.

---

## Architecture

```
Audio → Quality Gate → Features (waveform/spectral/phonation)
      → Scoring v2 (4 axes) → Issues/Timeline → optional LLM → API → Toss Mini App
```

Analysis signal과 Preview signal은 분리됩니다. EQ/컴프레서/강한 dereverb는 preview 전용입니다.

자세한 내용: [docs/architecture.md](docs/architecture.md), [docs/scoring.md](docs/scoring.md), [docs/api.md](docs/api.md)

---

## 설치 (Windows PowerShell)

```powershell
cd C:\VocalAgent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Demucs 보컬 분리가 필요하면:
# pip install -r requirements-optional.txt
copy .env.example .env
# .env 에 OPENAI_API_KEY / FFMPEG_PATH 등을 채웁니다 (secret을 커밋하지 마세요)
```

### FFmpeg

m4a/aac 변환에 FFmpeg가 필요합니다.

```powershell
# PATH에 ffmpeg 가 있거나
$env:FFMPEG_PATH = "C:\path\to\ffmpeg.exe"
```

---

## CLI

```powershell
python main.py sample.m4a --output runtime
python main.py sample.m4a --feedback
python main.py sample.m4a --separate
python main.py sample.m4a --json
python main.py sample.m4a --visualize --show
```

---

## FastAPI

```powershell
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

- `GET /health`
- `POST /v1/analyses`
- `GET /v1/analyses/{id}`
- `DELETE /v1/analyses/{id}`

---

## MiniApp (Toss WebView)

```powershell
cd miniapp
npm install
npm run dev
```

Build:

```powershell
npm run build:web    # Vite/TS web bundle
npm run build:toss   # build:web + ait build (.ait for Apps in Toss)
```

- `appName`: **vocalfb**
- SDK: `@apps-in-toss/web-framework` **^2.6.0** (stable 2.x; do not use `*`)
- `granite.config.ts` uses official `defineConfig`
- 브라우저 로컬 개발은 Vite proxy로 `http://127.0.0.1:8000` API를 사용합니다

### FastAPI notes

- MVP is **single-process / single-worker** (`ThreadPoolExecutor(max_workers=1)`).
- `uvicorn --workers > 1` splits the in-memory job registry — avoid until a shared store exists.
- CORS: development default localhost:5173. Production default is the verified vocalfb Toss origins. No `allow_origins=*`.

---

## 분석 항목 (사용자 4축)

| 영역 | 표시명 |
|------|--------|
| stability | 발성 안정성 |
| projection | 목소리 전달력 |
| resonance | 공명 균형 |
| dynamic_control | 강약 컨트롤 |

비브라토는 참고 분석만 하며 overall 점수에 넣지 않습니다.  
녹음 노이즈/클리핑/무음은 Quality Gate로 분리합니다.

---

## 테스트

```powershell
pytest -q
```

---

## 면책

- 의료기기/진단이 아닙니다.
- 성대 질환·결절 등 의학적 표현을 하지 않습니다.
- 점수는 미보정(uncalibrated) 잠정값입니다.
