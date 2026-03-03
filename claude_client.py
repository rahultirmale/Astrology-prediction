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


def build_compatibility_prompt(gun_milan: dict, boy_chart: dict,
                                girl_chart: dict) -> str:
    """Build prompt for AI interpretation of Gun Milan results."""
    lines = [
        "Analyze the following Ashtakoot Gun Milan compatibility results between two "
        "people and provide an insightful Vedic astrology interpretation.",
        "",
        "=== GUN MILAN SCORES ===",
        f"Total Score: {gun_milan['total_score']} / {gun_milan['max_score']} "
        f"({gun_milan['percentage']}%)",
        f"Verdict: {gun_milan['verdict']}",
        f"Nadi Dosha: {'YES - Present' if gun_milan['nadi_dosha'] else 'No'}",
        "",
        "Individual Kuta Scores:",
    ]
    for k in gun_milan["kutas"]:
        lines.append(f"  {k['name']}: {k['score']}/{k['max']} - {k['description']}")

    boy_natal = boy_chart["natal_chart"]
    girl_natal = girl_chart["natal_chart"]
    lines += [
        "",
        f"Person 1 Moon: {gun_milan['boy_rashi']} ({gun_milan['boy_nakshatra']})",
        f"Person 2 Moon: {gun_milan['girl_rashi']} ({gun_milan['girl_nakshatra']})",
        "",
        "=== PERSON 1 KEY CHART DETAILS ===",
        f"Ascendant: {boy_natal['ascendant']['sign']}",
        f"Venus: {boy_natal['planets']['Venus']['sign']} "
        f"(House {boy_natal['planets']['Venus']['house']})",
        f"7th House Lord: {boy_natal['house_lords'].get(7, 'N/A')}",
        "",
        "=== PERSON 2 KEY CHART DETAILS ===",
        f"Ascendant: {girl_natal['ascendant']['sign']}",
        f"Venus: {girl_natal['planets']['Venus']['sign']} "
        f"(House {girl_natal['planets']['Venus']['house']})",
        f"7th House Lord: {girl_natal['house_lords'].get(7, 'N/A')}",
        "",
        "=== ANALYSIS REQUEST ===",
        "Provide a warm, balanced interpretation of this compatibility. Cover:",
        "1. Overall compatibility assessment based on the total score",
        "2. Strongest areas (highest-scoring kutas) and what they mean for the couple",
        "3. Areas needing attention (lowest-scoring kutas) with remedies",
        "4. If Nadi Dosha is present, explain its significance and traditional remedies",
        "5. Brief practical advice for the couple",
        "",
        "Keep tone warm and constructive. Plain text, no markdown. 200-300 words.",
    ]
    return "\n".join(lines)


def build_partner_prediction_prompt(chart_data: dict, darakaraka: dict,
                                     gender: str) -> str:
    """Build prompt for partner prediction from a single chart."""
    natal = chart_data["natal_chart"]
    dasha = chart_data["dasha"]

    seventh_lord = natal["house_lords"].get(7, "Unknown")
    seventh_lord_data = natal["planets"].get(seventh_lord, {})

    if gender == "male":
        sig = "Venus"
        sig_label = "Venus (Kalatra Karaka for males)"
    else:
        sig = "Jupiter"
        sig_label = "Jupiter (Kalatra Karaka for females)"
    sig_data = natal["planets"].get(sig, {})

    lines = [
        f"Based on this natal chart, predict the nature of the ideal life partner "
        f"for this {'male' if gender == 'male' else 'female'} native.",
        "",
        "=== NATAL CHART ===",
        f"Ascendant: {natal['ascendant']['sign']}",
        f"Moon Sign: {natal['planets']['Moon']['sign']}",
        f"Moon Nakshatra: {natal['moon_nakshatra']['name']}",
        "",
        "=== 7th HOUSE ANALYSIS (Marriage House) ===",
        f"7th House Lord: {seventh_lord}",
        f"7th Lord Placement: {seventh_lord_data.get('sign', 'N/A')} "
        f"(House {seventh_lord_data.get('house', 'N/A')})",
        f"7th Lord Dignity: {seventh_lord_data.get('dignity', 'N/A')}",
        "",
        f"=== {sig_label} ===",
        f"Sign: {sig_data.get('sign', 'N/A')} (House {sig_data.get('house', 'N/A')})",
        f"Dignity: {sig_data.get('dignity', 'N/A')}",
        f"Retrograde: {'Yes' if sig_data.get('retrograde') else 'No'}",
        "",
        "=== DARAKARAKA (Jaimini Spouse Significator) ===",
        f"Planet: {darakaraka['planet']}",
        f"Sign: {darakaraka['sign']} (House {darakaraka['house']})",
        "",
        f"=== CURRENT DASHA ===",
        f"{dasha['mahadasha_lord']}-{dasha['antardasha_lord']}",
        "",
        "=== PREDICTION REQUEST ===",
        "Based on the 7th house lord, its placement, the karaka planet, and the "
        "Darakaraka, describe:",
        "1. Physical and personality traits of the likely partner",
        "2. How and where the native may meet their partner",
        "3. The timing window for marriage based on current dasha",
        "4. Strengths of the marriage and potential challenges",
        "5. Any remedies to strengthen marriage prospects",
        "",
        "Keep tone warm and empowering. Plain text, no markdown. 200-300 words.",
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


def get_compatibility_analysis(gun_milan: dict, boy_chart: dict,
                                girl_chart: dict, db: Session,
                                user_id: int) -> str:
    """Get AI interpretation of gun milan results with caching."""
    period_key = f"compat_{gun_milan['boy_nakshatra']}_{gun_milan['girl_nakshatra']}"
    data_hash = _cache_key_hash(gun_milan, "compatibility", "love", period_key)

    try:
        cached = (
            db.query(PredictionCache)
            .filter_by(user_id=user_id, prediction_type="compatibility",
                       category="love", period_key=period_key)
            .first()
        )
        if cached and cached.astro_data_hash == data_hash:
            return cached.prediction_text
    except Exception:
        cached = None

    prompt = build_compatibility_prompt(gun_milan, boy_chart, girl_chart)
    message = _get_client().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=700,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    text = message.content[0].text

    try:
        if cached:
            cached.prediction_text = text
            cached.astro_data_hash = data_hash
        else:
            cached = PredictionCache(
                user_id=user_id, prediction_type="compatibility",
                category="love", period_key=period_key,
                prediction_text=text, astro_data_hash=data_hash,
            )
            db.add(cached)
        db.commit()
    except Exception:
        db.rollback()

    return text


def get_partner_prediction(chart_data: dict, darakaraka: dict,
                            gender: str, db: Session,
                            user_id: int) -> str:
    """Get AI partner prediction with caching."""
    period_key = f"partner_{gender}_{chart_data['natal_chart']['ascendant']['sign']}"
    data_hash = _cache_key_hash(chart_data, "partner", "love", period_key)

    try:
        cached = (
            db.query(PredictionCache)
            .filter_by(user_id=user_id, prediction_type="partner",
                       category="love", period_key=period_key)
            .first()
        )
        if cached and cached.astro_data_hash == data_hash:
            return cached.prediction_text
    except Exception:
        cached = None

    prompt = build_partner_prediction_prompt(chart_data, darakaraka, gender)
    message = _get_client().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=700,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    text = message.content[0].text

    try:
        if cached:
            cached.prediction_text = text
            cached.astro_data_hash = data_hash
        else:
            cached = PredictionCache(
                user_id=user_id, prediction_type="partner",
                category="love", period_key=period_key,
                prediction_text=text, astro_data_hash=data_hash,
            )
            db.add(cached)
        db.commit()
    except Exception:
        db.rollback()

    return text
