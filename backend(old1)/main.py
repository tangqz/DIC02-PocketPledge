# backend/main.py
from fastapi import FastAPI

from backend.models.database import init_db

app = FastAPI(title="Reward System MVP (Layered)")


@app.on_event("startup")
def on_startup():
    init_db()

from backend.api.routes_http import router as http_router
from backend.api.sessions import router as sessions_router

app.include_router(http_router)
app.include_router(sessions_router)