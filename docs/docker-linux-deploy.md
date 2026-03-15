# PocketPledge Linux Docker Deployment

This document provides a production-oriented Docker deployment for Linux.

## 1. Prerequisites

- Linux server with Docker Engine + Docker Compose plugin
- CPU architecture: x86_64 recommended
- Suggested resources for 0-3 real-time users: 4 vCPU, 8 GB RAM

## 2. Prepare model files on host

Create a host directory and place Sherpa model files inside:

- model.int8.onnx
- tokens.txt

Example path:

```bash
mkdir -p /opt/pocketpledge/models/sherpa-onnx-sense-voice
```

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

## 4. Start services

```bash
docker compose --env-file .env.docker up -d --build
```

Services:

- `frontend` exposed on `http://<server-ip>:8080`
- `backend` runs inside compose network and is reverse-proxied by nginx

## 5. Check health

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
```

Backend health endpoint (inside container):

- `GET /health`

## 6. Upgrade / restart

```bash
docker compose --env-file .env.docker pull
docker compose --env-file .env.docker up -d --build
```

## 7. Stop and cleanup

```bash
docker compose --env-file .env.docker down
```

To remove persistent sqlite data as well:

```bash
docker compose --env-file .env.docker down -v
```

## 8. Notes

- Frontend static assets are served by nginx and proxied to backend for:
  - REST: `/api/*`
  - WebSocket: `/ws`
- SQLite database and token logs persist in docker volume `backend-data`.
- Default WS URL now auto-follows current domain when `VITE_WS_URL` is empty.
