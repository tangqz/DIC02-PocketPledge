import os
from datetime import datetime
from typing import Generator

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, create_engine, Boolean
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./reward.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), nullable=False, unique=True)
    email = Column(String(255), nullable=True, unique=True)
    password_hash = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    role = Column(String(50), nullable=False, default="user")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    wallet = relationship("Wallet", back_populates="user", uselist=False, cascade="all, delete-orphan")


class Wallet(Base):
    __tablename__ = "wallets"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    balance = Column(Integer, nullable=False, default=0)

    user = relationship("User", back_populates="wallet")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String(64), primary_key=True)
    tx_type = Column(String(50), nullable=False)
    from_user_id = Column(Integer, nullable=True)
    to_user_id = Column(Integer, nullable=True)
    amount = Column(Integer, nullable=False)
    reason = Column(String(255), nullable=False)
    session_ref = Column(String(100), nullable=True)
    meta_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class StudyPlan(Base):
    __tablename__ = "study_plans"

    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False, default="active")
    plan_json = Column(Text, nullable=False, default="{}")
    source = Column(String(50), nullable=False, default="system_agent")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PauseRequest(Base):
    __tablename__ = "pause_requests"

    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_ref = Column(String(100), nullable=True)
    requested_text = Column(Text, nullable=False)
    approved = Column(Boolean, nullable=False, default=False)
    pause_seconds = Column(Integer, nullable=True)
    decision_reason = Column(String(255), nullable=False, default="")
    meta_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class UserProfileDocument(Base):
    __tablename__ = "user_profile_documents"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    content = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SessionSummary(Base):
    __tablename__ = "session_summaries"

    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_ref = Column(String(100), nullable=True)
    summary_text = Column(Text, nullable=False)
    meta_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_ref = Column(String(100), nullable=True)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _seed_user_with_wallet(db: Session, user_id: int, username: str, role: str, balance: int) -> None:
    user = db.get(User, user_id)
    if not user:
        user = User(id=user_id, username=username, role=role)
        db.add(user)
        db.flush()

    wallet = db.get(Wallet, user_id)
    if not wallet:
        wallet = Wallet(user_id=user_id, balance=balance)
        db.add(wallet)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # 系统账户
        _seed_user_with_wallet(db, 0, "charity_sink", "system_charity", 0)
        _seed_user_with_wallet(db, 1, "reward_pool", "system_pool", 0)

        # 测试用户，可删
        _seed_user_with_wallet(db, 2, "demo_user_2", "user", 3000)

        db.commit()
    finally:
        db.close()