"""FastAPI application entrypoint for the backend service."""

from fastapi import FastAPI

from app.gateway.ws_router import router as gateway_router

from fastapi.middleware.cors import CORSMiddleware

from app.business.api import router as business_router
from app.business.models import init_db

# Create app instance and register websocket gateway routes.
app = FastAPI()
app.include_router(gateway_router)


app = FastAPI(title="Study Buddy Backend - Developer C")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"ok": True, "service": "developer_c_business"}


app.include_router(business_router)