# WarmBuddy — Project Guidelines

AI 学习监督陪伴系统：Live2D 虚拟角色 + 实时语音对话 + 视觉分心检测 + 经济惩罚机制。

## Architecture

**Monorepo with 3 top-level modules:**

| Directory | Stack | Description |
|-----------|-------|-------------|
| `backend/` | FastAPI 0.116+, Python 3.12+, SQLAlchemy 2, Pydantic 2 | WebSocket gateway, REST API, AI agent orchestration, ASR/TTS |
| `frontend/` | React 19, TypeScript 5.9, Vite 7, Zustand 5, Tailwind 4 | Chat UI, Live2D rendering, VAD, media capture |
| `Open-LLM-VTuber/` | Upstream reference project (read-only) | Do NOT modify; reference only for Live2D SDK patterns |

### Dual-Brain Design

- **Black Brain (Supervisor)**: Stateless vision LLM — analyzes periodic screenshots, outputs JSON distraction decisions, triggers penalties silently.
- **White Brain (Companion)**: Empathetic chat LLM — speaks to user, reacts to system events. No tool calls; uses `<<SYS>>` marker to trigger system agent.

### Backend Module Map

```
backend/app/
├── main.py          # FastAPI app, CORS, middleware
├── auth/            # JWT (HS256) auth, PBKDF2 password hashing (stdlib only)
├── business/        # Wallet/penalty ledger, study plans, user profiles (SQLAlchemy)
├── gateway/         # WebSocket handler, SessionState machine (setup→active→paused→completed)
├── agent/           # OpenAI-compatible LLM client, tool definitions, prompts
├── media_ai/        # Sherpa-ONNX ASR, TTS, vision pipeline, client_factory singleton
└── system_agent/    # Directive executor (pause approval, plan CRUD, profile extraction)
```

### Frontend Module Map

```
frontend/src/
├── App.tsx           # Top-level gateway, WS init, VAD init, snapshot manager
├── stores/           # 6 Zustand stores: auth, session, media, chat, avatar, character
├── hooks/            # useWebSocket, useVAD, useSnapshot, useAudioQueue
├── components/       # SetupLayout, FocusLayout, SummaryLayout + shared UI
├── live2d/           # WebSDK wrapper, Live2D canvas, lip-sync, expression control
├── lib/              # protocol.ts (WS message types), i18n.tsx, API helpers
└── types/            # Shared TypeScript interfaces
```

## Build & Run

### Prerequisites

- **Python 3.12+** with `uv` (package manager)
- **Node.js 20+** with `pnpm` (npm/yarn 禁止使用)
- Sherpa-ONNX ASR model files configured in `backend/.env`

### Quick Start (Windows)

```cmd
.\start-dev.cmd
```

### Manual Start

```bash
# Backend (port 12393)
cd backend
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 12393 --reload --reload-dir app --reload-dir scripts

# Frontend (port 5173)
cd frontend
pnpm install
pnpm run dev
```

### Docker (Linux)

```bash
docker compose up --build
# nginx reverse-proxy: :80 → frontend + /api/ → backend + /ws → backend
```

### Testing

```bash
cd backend
uv run pytest tests/
```

### Linting

```bash
# Backend
cd backend && uv run ruff check . && uv run ruff format --check .

# Frontend
cd frontend && pnpm run lint
```

## Conventions

### Backend

- **Singleton clients**: Reuse `LocalLLMClient` via `client_factory`; never construct per-turn.
- **Timezone-aware UTC**: All timestamps must use `datetime.now(timezone.utc)`. Mixing naive/aware datetimes breaks session cleanup.
- **`<<SYS>>` marker**: May split across streamed chunks; gateway uses prefix-buffer detection. Never leak markers to frontend.
- **`<<CAPTURE>>`**: Case-insensitive. Triggers `request-visual-context` → frontend captures images → backend resumes with vision context.
- **Internal endpoints** (`/internal/...`): Secured by `INTERNAL_TOOL_BEARER_TOKEN` HMAC — for system agent only.
- **Auth**: stdlib-only PBKDF2-SHA256 (260K iterations). JWT HS256 with 24h expiry. Set `AUTH_SECRET_KEY` in `.env` to survive restarts.
- **DB**: SQLite for dev (`backend/reward.db`), auto-migrated on first start. System accounts seeded at IDs 0 (charity_sink) and 1 (reward_pool).

### Frontend

- **Path aliases**: `@` → `src/`, `@framework` → Live2D SDK, `@cubismsdksamples`.
- **State machine**: `supervisionState` is backend-driven only (`setup` → `active` → `paused` → `completed`). Frontend never sets state independently.
- **Media streams**: Use shared `mediaStore` cameraStream/screenStream. Never create duplicate `getUserMedia` calls.
- **WebSocket reconnect**: 3s delay, max 5 attempts, pending message queue. Stale-socket guards prevent old handlers from clearing newer connections.
- **Live2D canvas**: Singleton WebGL manager can hold detached canvas across layout remounts. Rebind against newly mounted DOM node when layout switches.
- **i18n**: `zh` / `en` via `useI18n()` hook. Locale sent to backend via `set-locale` WS message.

### General

- **Env files**: `backend/.env` is auto-loaded by `backend/app/__init__.py` (stdlib only). Existing process env vars take priority.
- **Dify workflow YAMLs**: Local archives only. After editing, Dify cloud apps need manual re-import/publish.
- **Uvicorn reload scope**: `--reload-dir app --reload-dir scripts` only. Wider scopes cause spurious restarts from `.venv/` changes.
- **Port 12393**: Default dev port. Avoid Windows excluded TCP ranges (check `netsh interface ipv4 show excludedportrange protocol=tcp`).

## Key Pitfalls

- If `DIFY_API_BASE` already includes `/v1`, per-feature endpoints must omit the `/v1/` prefix to avoid double-prefix URLs.
- Gemini via OpenAI-compatible tool calling: must preserve `extra_content.google.thought_signature` across rounds; re-serializing without it causes 400 errors.
- Live2D hit-area: Some model3 files leave HitArea Name empty; use hit-area ID fallback (`HitAreaHead`/`HitAreaBody`).
- Study plan `_normalize_plan` emits `formatVersion=2`; preserve schedule fields (date/dates/weekdays/repeatCount/startDate/endDate).
- `ws_router` follow-up must not re-detect `<<SYS>>` on tool_result turns to avoid recursive plan updates.

## Documentation

- [REST API Contract](docs/api_contract.md)
- [WebSocket Protocol](docs/ws_protocol.md)
- [Docker Linux Deploy](docs/docker-linux-deploy.md)
- [Frontend Backend Interface](frontend/docs/backend-interface.md)
- [Development Plan](DevelopmentPlan/plan.md)
