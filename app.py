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

from fastapi import Depends, FastAPI, HTTPException, Request
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
PAYMENT_AMOUNT_PAISE = 1900  # ₹19 (testing)

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
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    email: Optional[str] = None  # deprecated: email now comes from JWT

class CompatibilityRequest(BaseModel):
    date_of_birth: str
    time_of_birth: str
    place_of_birth: str
    partner_date_of_birth: str
    partner_time_of_birth: str
    partner_place_of_birth: str
    email: Optional[str] = None

class PartnerPredictionRequest(BaseModel):
    date_of_birth: str
    time_of_birth: str
    place_of_birth: str
    gender: str  # "male" or "female"
    email: Optional[str] = None

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


def get_current_user_required(token: str = Depends(oauth2_scheme),
                              db: Session = Depends(get_db)):
    """Returns User if token valid, else raises 401."""
    user = get_current_user_optional(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    return user

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
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"email": user.email, "full_name": user.full_name},
        "payment": {"paid": False, "expires_at": None},
    }


@app.post("/api/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not pwd_context.verify(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_token(user.id, user.email)
    payment_status = _check_payment(user.email, db, user_id=user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "full_name": user.full_name,
            "email": user.email,
            "date_of_birth": user.date_of_birth.isoformat() if user.date_of_birth else None,
            "time_of_birth": user.time_of_birth,
            "place_of_birth": user.place_of_birth,
        },
        "payment": payment_status,
    }


@app.get("/api/me")
def get_me(user=Depends(get_current_user_optional), db: Session = Depends(get_db)):
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payment_status = _check_payment(user.email, db, user_id=user.id)
    return {
        "full_name": user.full_name,
        "email": user.email,
        "date_of_birth": user.date_of_birth.isoformat() if user.date_of_birth else None,
        "time_of_birth": user.time_of_birth,
        "place_of_birth": user.place_of_birth,
        "payment": payment_status,
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

def _check_payment(email: str, db: Session, user_id: int = None) -> dict:
    """Check if the given email/user has an active (non-expired) payment.
    Returns {"paid": bool, "expires_at": str|None}.
    """
    if not email and not user_id:
        return {"paid": False, "expires_at": None}
    try:
        from sqlalchemy import or_
        filters = [Payment.status == "paid"]

        # Match by user_id OR email
        identity_filters = []
        if user_id:
            identity_filters.append(Payment.user_id == user_id)
        if email:
            identity_filters.append(Payment.email == email.lower().strip())
        filters.append(or_(*identity_filters))

        # Expiry check: expires_at is NULL (legacy) or in the future
        now = datetime.utcnow()
        filters.append(
            or_(Payment.expires_at == None, Payment.expires_at > now)
        )

        payment = db.query(Payment).filter(*filters).first()
        if payment:
            return {
                "paid": True,
                "expires_at": payment.expires_at.isoformat() if payment.expires_at else None,
            }
        return {"paid": False, "expires_at": None}
    except Exception:
        return {"paid": False, "expires_at": None}

# ---------------------------------------------------------------------------
# Razorpay payment endpoints
# ---------------------------------------------------------------------------

@app.post("/api/create-order")
def create_order(user=Depends(get_current_user_required), db: Session = Depends(get_db)):
    """Create a Razorpay order — requires login."""
    if not razorpay_client:
        raise HTTPException(500, "Payment gateway not configured")

    email = user.email.lower().strip()

    # Check if already paid (active subscription)
    payment_status = _check_payment(email, db, user_id=user.id)
    if payment_status["paid"]:
        return {"already_paid": True, "expires_at": payment_status["expires_at"]}

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
            user_id=user.id,
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
def verify_payment(req: VerifyPaymentRequest,
                   user=Depends(get_current_user_required),
                   db: Session = Depends(get_db)):
    """Verify Razorpay payment signature and activate 1-year subscription."""
    if not razorpay_client:
        raise HTTPException(500, "Payment gateway not configured")

    # Verify signature
    msg = f"{req.razorpay_order_id}|{req.razorpay_payment_id}"
    expected_sig = hmac.new(
        RAZORPAY_KEY_SECRET.encode(), msg.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, req.razorpay_signature):
        raise HTTPException(400, "Payment verification failed — invalid signature")

    email = user.email.lower().strip()
    expires_at = datetime.utcnow() + timedelta(days=365)

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
            payment.user_id = user.id
            payment.expires_at = expires_at
        else:
            payment = Payment(
                email=email,
                user_id=user.id,
                razorpay_order_id=req.razorpay_order_id,
                razorpay_payment_id=req.razorpay_payment_id,
                amount=PAYMENT_AMOUNT_PAISE,
                status="paid",
                expires_at=expires_at,
            )
            db.add(payment)
        db.commit()
    except Exception:
        db.rollback()

    return {"status": "paid", "email": email, "expires_at": expires_at.isoformat()}


@app.get("/api/check-payment")
def check_payment(user=Depends(get_current_user_required), db: Session = Depends(get_db)):
    """Check if the logged-in user has an active subscription."""
    result = _check_payment(user.email, db, user_id=user.id)
    return {"paid": result["paid"], "expires_at": result["expires_at"]}

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
    """Get a prediction — free users get a truncated preview."""
    if req.prediction_type not in ("daily", "monthly", "yearly"):
        raise HTTPException(400, "type must be daily, monthly, or yearly")
    if req.category not in ("career", "health", "love"):
        raise HTTPException(400, "category must be career, health, or love")

    is_paid = _check_payment(req.email or "", db, user_id=user.id if user else None)["paid"]

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

    # For unpaid users, truncate to ~50% to build curiosity
    preview = not is_paid
    if preview:
        words = prediction.split()
        half = max(len(words) // 2, 15)  # at least 15 words
        prediction = " ".join(words[:half]) + " ..."

    return {
        "prediction_type": req.prediction_type,
        "category": req.category,
        "period": target_period,
        "prediction": prediction,
        "preview": preview,
    }


@app.post("/api/best-days")
def get_best_days(req: BestDaysRequest, db: Session = Depends(get_db),
                  user=Depends(get_current_user_optional)):
    """Get best days of the month — requires payment."""
    if req.category not in ("career", "health", "love"):
        raise HTTPException(400, "category must be career, health, or love")

    # Payment gate
    if not _check_payment(req.email or "", db, user_id=user.id if user else None)["paid"]:
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
# Compatibility endpoints
# ---------------------------------------------------------------------------

@app.post("/api/compatibility")
def get_compatibility(req: CompatibilityRequest, db: Session = Depends(get_db),
                      user=Depends(get_current_user_optional)):
    """Calculate Ashtakoot Gun Milan + optional AI interpretation (paid)."""
    import time
    is_paid = _check_payment(req.email or "", db, user_id=user.id if user else None)["paid"]

    try:
        lat1, lon1, tz1, offset1, dob1 = _resolve_location(
            req.place_of_birth, req.date_of_birth, req.time_of_birth
        )
        time.sleep(1.1)  # respect Nominatim rate limit
        lat2, lon2, tz2, offset2, dob2 = _resolve_location(
            req.partner_place_of_birth, req.partner_date_of_birth,
            req.partner_time_of_birth
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Location error: {str(e)[:200]}")

    from astrology import generate_birth_chart, calculate_gun_milan

    boy_chart = generate_birth_chart(
        dob=dob1, tob=req.time_of_birth,
        latitude=lat1, longitude=lon1, utc_offset=offset1,
    )
    girl_chart = generate_birth_chart(
        dob=dob2, tob=req.partner_time_of_birth,
        latitude=lat2, longitude=lon2, utc_offset=offset2,
    )

    boy_moon_lon = boy_chart["natal_chart"]["moon_longitude"]
    girl_moon_lon = girl_chart["natal_chart"]["moon_longitude"]

    gun_milan = calculate_gun_milan(boy_moon_lon, girl_moon_lon)

    result = {
        "gun_milan": gun_milan,
        "preview": not is_paid,
    }

    if is_paid:
        try:
            from claude_client import get_compatibility_analysis
            user_id = user.id if user else 0
            narrative = get_compatibility_analysis(
                gun_milan, boy_chart, girl_chart, db, user_id
            )
            result["ai_interpretation"] = narrative
        except Exception as e:
            result["ai_interpretation"] = f"AI analysis unavailable: {str(e)[:100]}"
    else:
        result["ai_interpretation"] = None

    return result


@app.post("/api/partner-prediction")
def partner_prediction(req: PartnerPredictionRequest,
                       db: Session = Depends(get_db),
                       user=Depends(get_current_user_optional)):
    """AI prediction about ideal partner — payment required."""
    if req.gender not in ("male", "female"):
        raise HTTPException(400, "gender must be 'male' or 'female'")

    if not _check_payment(req.email or "", db, user_id=user.id if user else None)["paid"]:
        raise HTTPException(
            status_code=402,
            detail="Payment required to unlock partner predictions",
        )

    lat, lon, tz_str, utc_offset, dob = _resolve_location(
        req.place_of_birth, req.date_of_birth, req.time_of_birth
    )

    from astrology import generate_birth_chart, get_darakaraka
    chart_data = generate_birth_chart(
        dob=dob, tob=req.time_of_birth,
        latitude=lat, longitude=lon, utc_offset=utc_offset,
    )

    darakaraka = get_darakaraka(chart_data["natal_chart"]["planets"])
    user_id = user.id if user else 0

    try:
        from claude_client import get_partner_prediction
        prediction = get_partner_prediction(
            chart_data, darakaraka, req.gender, db, user_id
        )
    except Exception as e:
        error_msg = str(e)
        raise HTTPException(502, f"AI service error: {error_msg[:200]}")

    return {
        "gender": req.gender,
        "darakaraka": darakaraka,
        "seventh_house_lord": chart_data["natal_chart"]["house_lords"].get(7),
        "prediction": prediction,
    }


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
