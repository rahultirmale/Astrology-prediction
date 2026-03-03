import os
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, Text,
    UniqueConstraint, create_engine
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func

# On Vercel, /tmp is the only writable directory
if os.getenv("VERCEL", "").strip() == "1":
    _default_db = "sqlite:////tmp/vedic_astro.db"
else:
    _default_db = "sqlite:///./vedic_astro.db"

DATABASE_URL = os.getenv("DATABASE_URL", _default_db)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)

    # Birth details (nullable until user saves them)
    date_of_birth = Column(Date, nullable=True)
    time_of_birth = Column(String(10), nullable=True)       # "14:30" (24hr)
    place_of_birth = Column(String(255), nullable=True)

    # Resolved geocoding (cached after first lookup)
    birth_latitude = Column(Float, nullable=True)
    birth_longitude = Column(Float, nullable=True)
    birth_timezone = Column(String(100), nullable=True)      # "Asia/Kolkata"
    birth_utc_offset = Column(Float, nullable=True)          # 5.5 for IST

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class PredictionCache(Base):
    __tablename__ = "predictions_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    prediction_type = Column(String(20), nullable=False)     # daily/monthly/yearly/best_days
    category = Column(String(20), nullable=False)            # career/health/love
    period_key = Column(String(30), nullable=False)          # "2026-02-28", "2026-02", "2026"
    prediction_text = Column(Text, nullable=False)
    astro_data_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "prediction_type", "category", "period_key",
                         name="uq_user_prediction"),
    )


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), index=True, nullable=False)
    razorpay_order_id = Column(String(100), nullable=False)
    razorpay_payment_id = Column(String(100), nullable=True)
    amount = Column(Integer, nullable=False)          # in paise (49900 = ₹499)
    status = Column(String(20), default="created")    # created / paid / failed
    created_at = Column(DateTime, default=func.now())


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
