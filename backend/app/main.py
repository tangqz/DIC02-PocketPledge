from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.business.api import router as business_router
from app.business.models import init_db

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