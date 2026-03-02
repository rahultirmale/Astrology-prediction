"""
Vedic Astrology Prediction App - FastAPI Application
"""

import os
from datetime import date, datetime, timedelta
from pathlib import Path

import pytz
from dotenv import load_dotenv

# Load .env from the same directory as this file (works regardless of CWD)
_BASE_DIR = Path(__file__).resolve().parent
load_dotenv(_BASE_DIR / ".env", override=True)
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from geopy.geocoders import Nominatim
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from timezonefinder import TimezoneFinder

from database import PredictionCache, User, get_db, init_db

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

IS_VERCEL = os.getenv("VERCEL", "") == "1"

app = FastAPI(title="Jyotish AI - Vedic Astrology Predictions")

# Local dev: serve static files and templates via FastAPI
# Vercel: these are served directly by Vercel from public/
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


def get_current_user(token: str = Depends(oauth2_scheme),
                     db: Session = Depends(get_db)) -> User:
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
def startup():
    init_db()

# ---------------------------------------------------------------------------
# Page routes (only needed for local dev; Vercel serves from public/)
# ---------------------------------------------------------------------------

if not IS_VERCEL:
    @app.get("/", response_class=HTMLResponse)
    async def index_page(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard_page(request: Request):
        return templates.TemplateResponse("dashboard.html", {"request": request})

# ---------------------------------------------------------------------------
# Auth endpoints
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
    return {"access_token": token, "token_type": "bearer"}

# ---------------------------------------------------------------------------
# User profile
# ---------------------------------------------------------------------------

@app.get("/api/me")
def get_me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "has_birth_details": user.date_of_birth is not None,
        "date_of_birth": user.date_of_birth.isoformat() if user.date_of_birth else None,
        "time_of_birth": user.time_of_birth,
        "place_of_birth": user.place_of_birth,
    }

# ---------------------------------------------------------------------------
# Birth details
# ---------------------------------------------------------------------------

@app.put("/api/birth-details")
def save_birth_details(req: BirthDetailsRequest,
                       user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    # Geocode the place
    location = geolocator.geocode(req.place_of_birth)
    if not location:
        raise HTTPException(status_code=400,
                            detail=f"Could not find location: {req.place_of_birth}")

    lat = location.latitude
    lon = location.longitude

    # Resolve timezone
    timezone_str = tf.timezone_at(lat=lat, lng=lon)
    if not timezone_str:
        raise HTTPException(status_code=400,
                            detail="Could not determine timezone for this location")

    # Calculate UTC offset for the birth date (handles historical DST)
    dob = datetime.strptime(req.date_of_birth, "%Y-%m-%d").date()
    hour, minute = map(int, req.time_of_birth.split(":"))
    tz = pytz.timezone(timezone_str)
    birth_dt = datetime(dob.year, dob.month, dob.day, hour, minute)
    localized = tz.localize(birth_dt)
    utc_offset = localized.utcoffset().total_seconds() / 3600

    # Update user record
    user.date_of_birth = dob
    user.time_of_birth = req.time_of_birth
    user.place_of_birth = req.place_of_birth
    user.birth_latitude = lat
    user.birth_longitude = lon
    user.birth_timezone = timezone_str
    user.birth_utc_offset = utc_offset

    # Invalidate prediction cache
    db.query(PredictionCache).filter(PredictionCache.user_id == user.id).delete()
    db.commit()

    return {
        "status": "ok",
        "resolved_location": {
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "timezone": timezone_str,
            "utc_offset": utc_offset,
        },
    }

# ---------------------------------------------------------------------------
# Predictions
# ---------------------------------------------------------------------------

def _ensure_birth_details(user: User):
    if not user.date_of_birth:
        raise HTTPException(
            status_code=400,
            detail="Please save your birth details first",
        )


def _get_chart(user: User) -> dict:
    from astrology import generate_birth_chart
    return generate_birth_chart(
        dob=user.date_of_birth,
        tob=user.time_of_birth,
        latitude=user.birth_latitude,
        longitude=user.birth_longitude,
        utc_offset=user.birth_utc_offset,
    )


@app.get("/api/predictions")
def get_predictions(
    type: str = Query(..., pattern="^(daily|monthly|yearly)$"),
    category: str = Query(..., pattern="^(career|health|love)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_birth_details(user)
    chart_data = _get_chart(user)

    today = date.today()
    if type == "daily":
        target_period = today.isoformat()
    elif type == "monthly":
        target_period = today.strftime("%Y-%m")
    else:
        target_period = str(today.year)

    try:
        from claude_client import get_prediction
        prediction = get_prediction(chart_data, type, category, target_period, db, user.id)
    except Exception as e:
        error_msg = str(e)
        if "authentication" in error_msg.lower() or "api key" in error_msg.lower():
            raise HTTPException(status_code=502, detail="AI service authentication failed. Check your API key.")
        elif "rate" in error_msg.lower():
            raise HTTPException(status_code=429, detail="AI service rate limit reached. Please wait a moment and try again.")
        else:
            raise HTTPException(status_code=502, detail=f"AI service error: {error_msg[:200]}")

    return {
        "prediction_type": type,
        "category": category,
        "period": target_period,
        "prediction": prediction,
    }


@app.get("/api/best-days")
def get_best_days(
    category: str = Query(..., pattern="^(career|health|love)$"),
    month: str = Query(None),  # "YYYY-MM" format, defaults to current month
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_birth_details(user)
    chart_data = _get_chart(user)

    if month:
        year, mon = map(int, month.split("-"))
    else:
        today = date.today()
        year, mon = today.year, today.month
        month = today.strftime("%Y-%m")

    from astrology import calculate_best_days, SIGNS
    moon_sign = chart_data["natal_chart"]["planets"]["Moon"]["sign"]
    natal_moon_idx = SIGNS.index(moon_sign)

    best_days = calculate_best_days(natal_moon_idx, year, mon, category)

    try:
        from claude_client import get_best_days_prediction
        narrative = get_best_days_prediction(
            chart_data, category, best_days, month, db, user.id
        )
    except Exception as e:
        error_msg = str(e)
        if "authentication" in error_msg.lower() or "api key" in error_msg.lower():
            raise HTTPException(status_code=502, detail="AI service authentication failed. Check your API key.")
        else:
            raise HTTPException(status_code=502, detail=f"AI service error: {error_msg[:200]}")

    return {
        "month": month,
        "category": category,
        "best_days": best_days,
        "narrative": narrative,
    }


@app.get("/api/chart-summary")
def get_chart_summary(user: User = Depends(get_current_user)):
    _ensure_birth_details(user)
    return _get_chart(user)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
