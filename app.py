"""
Vedic Astrology Prediction App - FastAPI Application
"""

import logging
import os
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pytz
from dotenv import load_dotenv

# Load .env from the same directory as this file (works regardless of CWD)
_BASE_DIR = Path(__file__).resolve().parent
load_dotenv(_BASE_DIR / ".env", override=True)

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from geopy.geocoders import Nominatim
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session
from timezonefinder import TimezoneFinder

import hmac
import hashlib

import razorpay

from database import Payment, PredictionCache, User, get_db, init_db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

IS_VERCEL = os.getenv("VERCEL", "").strip() == "1"

app = FastAPI(title="Jyotish AI - Vedic Astrology Predictions")

if not IS_VERCEL:
    os.makedirs("static", exist_ok=True)
    os.makedirs("templates", exist_ok=True)
    app.mount("/static", StaticFiles(directory="static"), name="static")
    templates = Jinja2Templates(directory="templates")
else:
    templates = None

# ---------------------------------------------------------------------------
# Auth config
# ---------------------------------------------------------------------------

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key-in-production")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login", auto_error=False)

# Geocoding
geolocator = Nominatim(user_agent="jyotish-ai-vedic-astro")
tf = TimezoneFinder()

# Razorpay
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
razorpay_client = (
    razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET
    else None
)
PAYMENT_AMOUNT_PAISE = 49900  # ₹499

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str

class LoginRequest(BaseModel):
    email: str
    password: str

class BirthDetailsRequest(BaseModel):
    date_of_birth: str   # "YYYY-MM-DD"
    time_of_birth: str   # "HH:MM"
    place_of_birth: str  # "Mumbai, India"

class PredictRequest(BaseModel):
    date_of_birth: str
    time_of_birth: str
    place_of_birth: str
    prediction_type: str  # daily / monthly / yearly
    category: str         # career / health / love
    target_date: Optional[str] = None  # "YYYY-MM-DD" for custom date readings
    email: Optional[str] = None       # for payment verification

class BestDaysRequest(BaseModel):
    date_of_birth: str
    time_of_birth: str
    place_of_birth: str
    category: str
    month: Optional[str] = None  # "YYYY-MM", defaults to current
    email: Optional[str] = None  # for payment verification

class ChartRequest(BaseModel):
    date_of_birth: str
    time_of_birth: str
    place_of_birth: str

class CreateOrderRequest(BaseModel):
    email: str

class VerifyPaymentRequest(BaseModel):
    email: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def create_token(user_id: int, email: str) -> str:
    payload = {
        "sub": email,
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user_optional(token: str = Depends(oauth2_scheme),
                              db: Session = Depends(get_db)):
    """Returns User if token valid, else None. Never raises."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if user_id is None:
            return None
        return db.query(User).filter(User.id == user_id).first()
    except JWTError:
        return None

# ---------------------------------------------------------------------------
# Geocoding helper (shared by auth and anonymous endpoints)
# ---------------------------------------------------------------------------

def _resolve_location(place: str, dob_str: str, tob_str: str):
    """Geocode a place and resolve timezone. Returns (lat, lon, tz, offset)."""
    location = geolocator.geocode(place)
    if not location:
        raise HTTPException(status_code=400,
                            detail=f"Could not find location: {place}")
    lat = location.latitude
    lon = location.longitude

    timezone_str = tf.timezone_at(lat=lat, lng=lon)
    if not timezone_str:
        raise HTTPException(status_code=400,
                            detail="Could not determine timezone for this location")

    dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
    hour, minute = map(int, tob_str.split(":"))
    tz = pytz.timezone(timezone_str)
    birth_dt = datetime(dob.year, dob.month, dob.day, hour, minute)
    localized = tz.localize(birth_dt)
    utc_offset = localized.utcoffset().total_seconds() / 3600

    return lat, lon, timezone_str, utc_offset, dob

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
def startup():
    init_db()

# ---------------------------------------------------------------------------
# Page routes (local dev only; Vercel serves from public/)
# ---------------------------------------------------------------------------

if not IS_VERCEL:
    @app.get("/", response_class=HTMLResponse)
    async def index_page(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

# ---------------------------------------------------------------------------
# Auth endpoints (optional — for users who want to save their data)
# ---------------------------------------------------------------------------

@app.post("/api/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=req.email,
        hashed_password=pwd_context.hash(req.password),
        full_name=req.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_token(user.id, user.email)
    return {"access_token": token, "token_type": "bearer"}


@app.post("/api/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not pwd_context.verify(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_token(user.id, user.email)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "full_name": user.full_name,
            "date_of_birth": user.date_of_birth.isoformat() if user.date_of_birth else None,
            "time_of_birth": user.time_of_birth,
            "place_of_birth": user.place_of_birth,
        },
    }


@app.get("/api/me")
def get_me(user=Depends(get_current_user_optional)):
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "full_name": user.full_name,
        "date_of_birth": user.date_of_birth.isoformat() if user.date_of_birth else None,
        "time_of_birth": user.time_of_birth,
        "place_of_birth": user.place_of_birth,
    }

# ---------------------------------------------------------------------------
# Health check / debug endpoint
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health_check():
    """Quick health check — verifies imports work on Vercel."""
    checks = {}
    try:
        from astrology import generate_birth_chart
        checks["astrology"] = "ok"
    except Exception as e:
        checks["astrology"] = str(e)
    try:
        from claude_client import _get_client
        checks["claude_client"] = "ok"
    except Exception as e:
        checks["claude_client"] = str(e)
    try:
        from database import init_db
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = str(e)
    checks["VERCEL"] = os.getenv("VERCEL", "not set")
    checks["ANTHROPIC_KEY_SET"] = "yes" if os.getenv("ANTHROPIC_API_KEY") else "no"
    return checks

# ---------------------------------------------------------------------------
# Payment helper
# ---------------------------------------------------------------------------

def _check_payment(email: str, db: Session) -> bool:
    """Check if the given email has a successful payment."""
    if not email:
        return False
    try:
        paid = (
            db.query(Payment)
            .filter(Payment.email == email.lower().strip(),
                    Payment.status == "paid")
            .first()
        )
        return paid is not None
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Razorpay payment endpoints
# ---------------------------------------------------------------------------

@app.post("/api/create-order")
def create_order(req: CreateOrderRequest, db: Session = Depends(get_db)):
    """Create a Razorpay order for ₹499."""
    if not razorpay_client:
        raise HTTPException(500, "Payment gateway not configured")

    email = req.email.lower().strip()

    # Check if already paid
    if _check_payment(email, db):
        return {"already_paid": True}

    try:
        order = razorpay_client.order.create({
            "amount": PAYMENT_AMOUNT_PAISE,
            "currency": "INR",
            "receipt": f"jyotish_{email[:20]}_{int(datetime.utcnow().timestamp())}",
            "notes": {"email": email, "product": "jyotish_ai_predictions"},
        })
    except Exception as e:
        logger.error(f"Razorpay order creation failed: {e}")
        raise HTTPException(502, "Failed to create payment order")

    # Save order record
    try:
        payment = Payment(
            email=email,
            razorpay_order_id=order["id"],
            amount=PAYMENT_AMOUNT_PAISE,
            status="created",
        )
        db.add(payment)
        db.commit()
    except Exception:
        db.rollback()

    return {
        "order_id": order["id"],
        "amount": PAYMENT_AMOUNT_PAISE,
        "currency": "INR",
        "key_id": RAZORPAY_KEY_ID,
    }


@app.post("/api/verify-payment")
def verify_payment(req: VerifyPaymentRequest, db: Session = Depends(get_db)):
    """Verify Razorpay payment signature and mark as paid."""
    if not razorpay_client:
        raise HTTPException(500, "Payment gateway not configured")

    # Verify signature
    msg = f"{req.razorpay_order_id}|{req.razorpay_payment_id}"
    expected_sig = hmac.new(
        RAZORPAY_KEY_SECRET.encode(), msg.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, req.razorpay_signature):
        raise HTTPException(400, "Payment verification failed — invalid signature")

    email = req.email.lower().strip()

    # Update payment record
    try:
        payment = (
            db.query(Payment)
            .filter(Payment.razorpay_order_id == req.razorpay_order_id)
            .first()
        )
        if payment:
            payment.razorpay_payment_id = req.razorpay_payment_id
            payment.status = "paid"
        else:
            payment = Payment(
                email=email,
                razorpay_order_id=req.razorpay_order_id,
                razorpay_payment_id=req.razorpay_payment_id,
                amount=PAYMENT_AMOUNT_PAISE,
                status="paid",
            )
            db.add(payment)
        db.commit()
    except Exception:
        db.rollback()

    return {"status": "paid", "email": email}


@app.get("/api/check-payment")
def check_payment(email: str = Query(...), db: Session = Depends(get_db)):
    """Check if an email has an active payment."""
    return {"paid": _check_payment(email, db)}

# ---------------------------------------------------------------------------
# Anonymous prediction endpoints (payment-gated AI predictions)
# ---------------------------------------------------------------------------

@app.post("/api/chart")
def get_chart(req: ChartRequest):
    """Get natal chart data — no auth required."""
    try:
        lat, lon, tz_str, utc_offset, dob = _resolve_location(
            req.place_of_birth, req.date_of_birth, req.time_of_birth
        )
        from astrology import generate_birth_chart
        return generate_birth_chart(
            dob=dob, tob=req.time_of_birth,
            latitude=lat, longitude=lon, utc_offset=utc_offset,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chart error: {traceback.format_exc()}")
        raise HTTPException(500, f"Chart calculation failed: {str(e)[:300]}")


@app.post("/api/predict")
def predict(req: PredictRequest, db: Session = Depends(get_db),
            user=Depends(get_current_user_optional)):
    """Get a prediction for one category — requires payment."""
    if req.prediction_type not in ("daily", "monthly", "yearly"):
        raise HTTPException(400, "type must be daily, monthly, or yearly")
    if req.category not in ("career", "health", "love"):
        raise HTTPException(400, "category must be career, health, or love")

    # Payment gate
    if not _check_payment(req.email or "", db):
        raise HTTPException(
            status_code=402,
            detail="Payment required to unlock AI predictions",
        )

    lat, lon, tz_str, utc_offset, dob = _resolve_location(
        req.place_of_birth, req.date_of_birth, req.time_of_birth
    )

    from astrology import generate_birth_chart
    chart_data = generate_birth_chart(
        dob=dob, tob=req.time_of_birth,
        latitude=lat, longitude=lon, utc_offset=utc_offset,
    )

    # Use custom target date if provided, else today
    if req.target_date:
        try:
            target = datetime.strptime(req.target_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "target_date must be YYYY-MM-DD format")
    else:
        target = date.today()

    if req.prediction_type == "daily":
        target_period = target.isoformat()
    elif req.prediction_type == "monthly":
        target_period = target.strftime("%Y-%m")
    else:
        target_period = str(target.year)

    # If logged in, use cache; otherwise call Claude directly
    user_id = user.id if user else 0

    # Save birth details for logged-in users
    if user and not user.date_of_birth:
        user.date_of_birth = dob
        user.time_of_birth = req.time_of_birth
        user.place_of_birth = req.place_of_birth
        user.birth_latitude = lat
        user.birth_longitude = lon
        user.birth_timezone = tz_str
        user.birth_utc_offset = utc_offset
        db.commit()

    try:
        from claude_client import get_prediction
        prediction = get_prediction(
            chart_data, req.prediction_type, req.category,
            target_period, db, user_id,
        )
    except Exception as e:
        error_msg = str(e)
        if "authentication" in error_msg.lower() or "api key" in error_msg.lower():
            raise HTTPException(502, "AI service authentication failed. Check API key.")
        elif "rate" in error_msg.lower():
            raise HTTPException(429, "Rate limit reached. Please wait and try again.")
        else:
            raise HTTPException(502, f"AI service error: {error_msg[:200]}")

    return {
        "prediction_type": req.prediction_type,
        "category": req.category,
        "period": target_period,
        "prediction": prediction,
    }


@app.post("/api/best-days")
def get_best_days(req: BestDaysRequest, db: Session = Depends(get_db),
                  user=Depends(get_current_user_optional)):
    """Get best days of the month — requires payment."""
    if req.category not in ("career", "health", "love"):
        raise HTTPException(400, "category must be career, health, or love")

    # Payment gate
    if not _check_payment(req.email or "", db):
        raise HTTPException(
            status_code=402,
            detail="Payment required to unlock AI predictions",
        )

    lat, lon, tz_str, utc_offset, dob = _resolve_location(
        req.place_of_birth, req.date_of_birth, req.time_of_birth
    )

    from astrology import generate_birth_chart, calculate_best_days, SIGNS
    chart_data = generate_birth_chart(
        dob=dob, tob=req.time_of_birth,
        latitude=lat, longitude=lon, utc_offset=utc_offset,
    )

    if req.month:
        year, mon = map(int, req.month.split("-"))
    else:
        today = date.today()
        year, mon = today.year, today.month
        req.month = today.strftime("%Y-%m")

    moon_sign = chart_data["natal_chart"]["planets"]["Moon"]["sign"]
    natal_moon_idx = SIGNS.index(moon_sign)
    best_days = calculate_best_days(natal_moon_idx, year, mon, req.category)

    user_id = user.id if user else 0

    try:
        from claude_client import get_best_days_prediction
        narrative = get_best_days_prediction(
            chart_data, req.category, best_days, req.month, db, user_id,
        )
    except Exception as e:
        error_msg = str(e)
        if "authentication" in error_msg.lower() or "api key" in error_msg.lower():
            raise HTTPException(502, "AI service authentication failed. Check API key.")
        else:
            raise HTTPException(502, f"AI service error: {error_msg[:200]}")

    return {
        "month": req.month,
        "category": req.category,
        "best_days": best_days,
        "narrative": narrative,
    }


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
