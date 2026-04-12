# WarmBuddy


<div align="center">
  <strong>WarmBuddy</strong> is a local-first Live2D AI companion for emotional check-ins and real-time voice conversation.
</div>

<div align="center">
  <a href="README-zh.md">简体中文</a>
</div>

WarmBuddy pairs a React + Live2D frontend with a FastAPI WebSocket backend. After sign-in, opening the companion page immediately establishes the session, sends a one-shot `page-opened` event, and lets the selected character proactively greet the user in text and voice.

## Current Product Shape

- Proactive greeting on page open after authentication
- Live2D characters with streamed TTS, expressions, and tap interaction
- Realtime voice chat over WebSocket with local ASR and OpenAI-compatible LLM backends
- Periodic camera emotion updates plus on-demand `<<CAPTURE>>` visual context
- Mood logging, meal journal, and quick self-check overlays in the companion dashboard
- Bilingual experience in `zh` and `en`
- Local auth, SQLite persistence, and profile-memory rollover for long conversations


## Monorepo Layout

| Path | Stack | Responsibility |
| --- | --- | --- |
| `frontend/` | React 19, TypeScript 5.9, Vite 7, Zustand 5, Tailwind 4 | Live2D canvas, chat UI, voice capture, mood tools, and WebSocket client |
| `backend/` | FastAPI 0.116+, Python 3.12+, SQLAlchemy 2, Pydantic 2 | Auth, WebSocket orchestration, agent routing, ASR/TTS, persistence |
| `docs/` | Markdown + diagrams | API contract, WebSocket protocol, Docker deployment notes |
| `Open-LLM-VTuber/` | Upstream reference | Read-only reference for Live2D and voice integration patterns |

## Interaction Flow

1. The frontend restores or acquires a JWT and connects to `/ws` with `token`, `locale`, and `characterId`.
2. The backend hydrates recent chat history, returns `model-info`, and waits for client events.
3. The authenticated page sends `page-opened` exactly once per real page load.
4. The backend streams a short proactive greeting as text and audio.
5. Later turns reuse the same session for text input, VAD-based voice input, emotion updates, and `<<SYS>>` / `<<CAPTURE>>` follow-up actions.

## Quick Start

### Prerequisites

- Python 3.12+
- `uv`
- Node.js 20+
- `pnpm`
- At least one working local ASR configuration and one OpenAI-compatible model backend

### 1. Backend configuration

Duplicate `backend/.env.example` to `backend/.env`, then fill in your actual model endpoints and keys.

Minimum local setup:

```env
AGENT_BACKEND=local
AUTH_SECRET_KEY=replace-with-a-long-random-local-dev-secret

LOCAL_CHAT_API_KEY=sk-placeholder
LOCAL_CHAT_API_BASE=https://api.openai.com/v1
LOCAL_CHAT_MODEL=gpt-4o

LOCAL_VISION_API_KEY=sk-placeholder
LOCAL_VISION_API_BASE=https://api.openai.com/v1
LOCAL_VISION_MODEL=gpt-4o

LOCAL_AGENT_API_KEY=sk-placeholder
LOCAL_AGENT_API_BASE=https://api.openai.com/v1
LOCAL_AGENT_MODEL=gpt-4o
```

If you want Sherpa-ONNX instead of the example ASR setup, also configure:

```env
MEDIA_AI_ASR_PROVIDER=sherpa-onnx
MEDIA_AI_SHERPA_MODEL_PATH=/absolute/path/model.int8.onnx
MEDIA_AI_SHERPA_TOKENS_PATH=/absolute/path/tokens.txt
```

Install backend dependencies:

```bash
cd backend
uv sync
```

### 2. Frontend setup

```bash
cd frontend
pnpm install
```

### 3. Run the app

Manual start:

```bash
cd backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 12393 --reload --reload-dir app --reload-dir scripts
```

```bash
cd frontend
pnpm run dev
```

Windows combined start:

```cmd
.\start-dev.cmd
```

Open `http://localhost:5173/`, sign in, and the selected companion will greet you as soon as the authenticated page finishes mounting.

### 4. Docker on Linux

For Linux deployment, use:

```bash
chmod +x deploy-linux.sh
./deploy-linux.sh
```

The script can create `.env.docker`, generate `AUTH_SECRET_KEY`, download Sherpa model files, and start the compose stack. See [docs/docker-linux-deploy.md](docs/docker-linux-deploy.md) for details.

## Development Commands

Backend:

```bash
cd backend
uv run pytest tests/
uv run ruff check .
uv run ruff format --check .
```

Frontend:

```bash
cd frontend
pnpm run lint
pnpm run build
```

## Notes

- `Open-LLM-VTuber/` is reference code only. Do not modify it in normal product work.
- Keep `AUTH_SECRET_KEY` fixed in local development, or every backend reload will invalidate existing JWTs.
- The backend reload scope should stay on `app/` and `scripts/` to avoid noisy restarts.
- The frontend follows the current host for `/api` and `/ws`, which keeps localhost, LAN, and reverse-proxy setups aligned.

## Documentation

- [docs/api_contract.md](docs/api_contract.md)
- [docs/ws_protocol.md](docs/ws_protocol.md)
- [docs/docker-linux-deploy.md](docs/docker-linux-deploy.md)
- [frontend/docs/backend-interface.md](frontend/docs/backend-interface.md)
- [DevelopmentPlan/plan.md](DevelopmentPlan/plan.md)

## Acknowledgements

- [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) for upstream Live2D and voice-integration references
- [Live2D](https://www.live2d.com/) for the Web SDK and model ecosystem
- [Sherpa-ONNX](https://github.com/k2-fsa/sherpa-onnx) and [faster-whisper](https://github.com/SYSTRAN/faster-whisper) for local ASR options
