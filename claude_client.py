"""
Claude API integration for Vedic astrology predictions.
Builds structured prompts from chart data and caches responses.
"""

import hashlib
import json
import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from astrology import PREDICTION_HOUSES
from database import PredictionCache

# Ensure .env is loaded (in case this module is imported before app.py runs)
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

_client = None

def _get_client():
    """Lazy-initialize the Anthropic client so the API key is always available."""
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set. Add it to your .env file.")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client

SYSTEM_PROMPT = """You are an expert Vedic astrologer (Jyotishi) with deep knowledge of \
Parashari and Jaimini systems. You provide insightful, personalized predictions based on \
precise astronomical data.

Rules:
- Base ALL predictions on the provided astronomical data. Do not make up positions.
- Use traditional Vedic astrology interpretation principles.
- Be specific and actionable, not vague.
- Reference the actual planets, signs, houses, and dashas in your explanations.
- Keep the tone warm, empowering, and constructive even for challenging placements.
- For unfavorable periods, always include remedial suggestions (mantras, gemstones, fasting days, charity).
- Structure your response with the prediction followed by brief astrological reasoning.
- Do NOT use markdown formatting. Use plain text with line breaks.
- Keep predictions between 150-250 words.
- Always mention the current Mahadasha-Antardasha influence.
- For health predictions, add a disclaimer that this is for entertainment and not medical advice."""


def build_prompt(chart_data: dict, prediction_type: str,
                 category: str, target_period: str) -> str:
    """Build a structured prompt from chart data for Claude."""
    natal = chart_data["natal_chart"]
    dasha = chart_data["dasha"]

    lines = [
        f"Generate a {prediction_type} Vedic astrology prediction for {category.upper()}.",
        "",
        "=== NATAL CHART ===",
        f"Ascendant (Lagna): {natal['ascendant']['sign']} at "
        f"{natal['ascendant']['degree']:.1f} degrees",
        "",
        "Planetary Positions:",
    ]

    for name, p in natal["planets"].items():
        retro = " [Retrograde]" if p["retrograde"] else ""
        dignity = f" [{p['dignity']}]" if p["dignity"] != "neutral" else ""
        lines.append(
            f"  {name}: {p['sign']} ({p['degree']:.1f} deg) "
            f"in House {p['house']}{retro}{dignity}"
        )

    lines += [
        "",
        f"Moon Nakshatra: {natal['moon_nakshatra']['name']} "
        f"(ruled by {natal['moon_nakshatra']['ruling_planet']})",
        "",
        "=== CURRENT DASHA PERIOD ===",
        f"Mahadasha: {dasha['mahadasha_lord']} "
        f"({dasha['mahadasha_start']} to {dasha['mahadasha_end']})",
        f"Antardasha: {dasha['antardasha_lord']} "
        f"({dasha['antardasha_start']} to {dasha['antardasha_end']})",
        "",
        "=== CURRENT TRANSITS ===",
    ]

    for t in chart_data["transits"]:
        fav = "FAVORABLE" if t["is_favorable"] else "UNFAVORABLE"
        retro = " [R]" if t["retrograde"] else ""
        lines.append(
            f"  {t['planet']}: transiting {t['transit_sign']} "
            f"(House {t['house_from_moon']} from Moon) - {fav}{retro}"
        )

    if chart_data["sade_sati"]:
        lines.append(f"\n*** SADE SATI ACTIVE: {chart_data['sade_sati']} ***")

    relevant = ", ".join(str(h) for h in PREDICTION_HOUSES[category])
    lines += [
        "",
        "=== PREDICTION REQUEST ===",
        f"Category: {category}",
        f"Relevant houses: {relevant}",
        f"Type: {prediction_type}",
        f"Period: {target_period}",
        "",
        f"Provide a personalized {prediction_type} {category} prediction based on "
        f"the above chart data. Focus on planets in houses {relevant} and their "
        f"current transit effects. Include the influence of the "
        f"{dasha['mahadasha_lord']}-{dasha['antardasha_lord']} dasha period "
        f"on {category}.",
    ]

    return "\n".join(lines)


def build_best_days_prompt(chart_data: dict, category: str,
                           best_days: list[dict], month_str: str) -> str:
    """Build a prompt for best-days narrative."""
    natal = chart_data["natal_chart"]
    dasha = chart_data["dasha"]

    lines = [
        f"Based on this natal chart and transit analysis, explain why these are the "
        f"best days of {month_str} for {category.upper()}.",
        "",
        "=== NATAL CHART (key details) ===",
        f"Ascendant: {natal['ascendant']['sign']}",
        f"Moon Sign: {natal['planets']['Moon']['sign']}",
        f"Moon Nakshatra: {natal['moon_nakshatra']['name']}",
        f"Current Dasha: {dasha['mahadasha_lord']}-{dasha['antardasha_lord']}",
        "",
        f"=== BEST DAYS FOR {category.upper()} ===",
    ]

    for d in best_days:
        lines.append(f"  Day {d['day']} ({d['date']}): Score {d['score']}/10 | "
                      f"{d['key_transits']}")

    lines += [
        "",
        f"For each day, provide a 1-2 sentence explanation of why it is favorable "
        f"for {category} based on the specific transits active that day. "
        f"Be concise and actionable. Do NOT use markdown. Keep total under 300 words.",
    ]

    return "\n".join(lines)


def _cache_key_hash(chart_data: dict, prediction_type: str,
                    category: str, period: str) -> str:
    """Create a hash of the input data for cache invalidation."""
    raw = json.dumps(
        {"chart": chart_data, "type": prediction_type,
         "category": category, "period": period},
        sort_keys=True, default=str,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def get_prediction(chart_data: dict, prediction_type: str, category: str,
                   target_period: str, db: Session, user_id: int) -> str:
    """Get a prediction, using cache when available."""
    data_hash = _cache_key_hash(chart_data, prediction_type, category, target_period)

    # Try cache read (graceful — skip if DB is read-only)
    try:
        cached = (
            db.query(PredictionCache)
            .filter_by(user_id=user_id, prediction_type=prediction_type,
                       category=category, period_key=target_period)
            .first()
        )
        if cached and cached.astro_data_hash == data_hash:
            return cached.prediction_text
    except Exception:
        cached = None

    prompt = build_prompt(chart_data, prediction_type, category, target_period)

    message = _get_client().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    prediction_text = message.content[0].text

    # Try cache write (graceful — don't crash if DB is read-only)
    try:
        if cached:
            cached.prediction_text = prediction_text
            cached.astro_data_hash = data_hash
        else:
            cached = PredictionCache(
                user_id=user_id,
                prediction_type=prediction_type,
                category=category,
                period_key=target_period,
                prediction_text=prediction_text,
                astro_data_hash=data_hash,
            )
            db.add(cached)
        db.commit()
    except Exception:
        db.rollback()

    return prediction_text


def get_best_days_prediction(chart_data: dict, category: str,
                             best_days: list[dict], month_str: str,
                             db: Session, user_id: int) -> str:
    """Get a best-days narrative, using cache when available."""
    period_key = f"best_{month_str}_{category}"
    data_hash = _cache_key_hash(chart_data, "best_days", category, month_str)

    try:
        cached = (
            db.query(PredictionCache)
            .filter_by(user_id=user_id, prediction_type="best_days",
                       category=category, period_key=period_key)
            .first()
        )
        if cached and cached.astro_data_hash == data_hash:
            return cached.prediction_text
    except Exception:
        cached = None

    prompt = build_best_days_prompt(chart_data, category, best_days, month_str)

    message = _get_client().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=800,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    narrative = message.content[0].text

    try:
        if cached:
            cached.prediction_text = narrative
            cached.astro_data_hash = data_hash
        else:
            cached = PredictionCache(
                user_id=user_id,
                prediction_type="best_days",
                category=category,
                period_key=period_key,
                prediction_text=narrative,
                astro_data_hash=data_hash,
            )
            db.add(cached)
        db.commit()
    except Exception:
        db.rollback()

    return narrative
