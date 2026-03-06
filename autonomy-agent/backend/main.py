# backend/main.py
from fastapi import FastAPI

from backend.api.routes_http import router
from backend.models.database import init_db

app = FastAPI(title="Reward System MVP (Layered)")

@app.on_event("startup")
def on_startup():
    init_db()

app.include_router(router)