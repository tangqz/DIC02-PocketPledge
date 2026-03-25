# PocketPledge Linux Docker Deployment

This document provides a production-oriented Docker deployment for Linux.

## 1. Prerequisites

- Linux server with Docker Engine + Docker Compose plugin
- CPU architecture: x86_64 recommended
- Suggested resources for 0-3 real-time users: 4 vCPU, 8 GB RAM

## 2. Model download mode

Model files are downloaded automatically from Hugging Face during deployment.

Default source:

- Repository: csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17
- Revision: 2365baeacb507f821a0c8120fcee3d484dba7a07

Target host path is controlled by SHERPA_MODEL_DIR.

## 3. Prepare environment file

From project root:

```bash
cp .env.docker.example .env.docker
```

Edit `.env.docker` and set:

- `AUTH_SECRET_KEY`
- `ALLOWED_ORIGINS` (your public URL)
- `SHERPA_MODEL_DIR` (absolute host path)
- `LOCAL_*` model API settings

## 4. One-command deployment (recommended)

```bash
chmod +x deploy-linux.sh
./deploy-linux.sh
```

What this script does:

- Creates .env.docker from template when missing
- Generates AUTH_SECRET_KEY automatically when placeholder is found
- Runs model-downloader service to fetch model.int8.onnx and tokens.txt
- Builds and starts backend and frontend

You can use a custom env file:

```bash
./deploy-linux.sh .env.prod
```

## 5. Manual deployment (optional)

```bash
docker compose --env-file .env.docker run --rm model-downloader
docker compose --env-file .env.docker up -d --build
```

Services:

- `frontend` exposed on `http://<server-ip>:8080`
- `backend` runs inside compose network and is reverse-proxied by nginx

## 6. Check health

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
```

Backend health endpoint (inside container):

- `GET /health`

## 7. Upgrade / restart

```bash
docker compose --env-file .env.docker pull
docker compose --env-file .env.docker up -d --build
```

## 8. Stop and cleanup

```bash
docker compose --env-file .env.docker down
```

To remove persistent sqlite data as well:

```bash
docker compose --env-file .env.docker down -v
```

## 9. Notes

- Frontend static assets are served by nginx and proxied to backend for:
  - REST: `/api/*`
  - WebSocket: `/ws`
- SQLite database and token logs persist in docker volume `backend-data`.
- Default WS URL now auto-follows current domain when `VITE_WS_URL` is empty.
- If your server has difficulty reaching huggingface.co, set HF_ENDPOINT to a reachable mirror in .env.docker.
