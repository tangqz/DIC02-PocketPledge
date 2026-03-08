"""FastAPI application entrypoint for the backend service."""

from fastapi import FastAPI

from app.gateway.ws_router import router as gateway_router

# Create app instance and register websocket gateway routes.
app = FastAPI()
app.include_router(gateway_router)
