"""
Vedic Astrology Engine
Calculates birth charts, dashas, transits, and best days using PyEphem.
All positions are sidereal (Lahiri ayanamsa).
"""

import calendar
import math
from datetime import date, datetime, timedelta, timezone

import ephem

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

# (name, ruling_planet, dasha_years)
NAKSHATRAS = [
    ("Ashwini", "Ketu", 7),
    ("Bharani", "Venus", 20),
    ("Krittika", "Sun", 6),
    ("Rohini", "Moon", 10),
    ("Mrigashira", "Mars", 7),
    ("Ardra", "Rahu", 18),
    ("Punarvasu", "Jupiter", 16),
    ("Pushya", "Saturn", 19),
    ("Ashlesha", "Mercury", 17),
    ("Magha", "Ketu", 7),
    ("Purva Phalguni", "Venus", 20),
    ("Uttara Phalguni", "Sun", 6),
    ("Hasta", "Moon", 10),
    ("Chitra", "Mars", 7),
    ("Swati", "Rahu", 18),
    ("Vishakha", "Jupiter", 16),
    ("Anuradha", "Saturn", 19),
    ("Jyeshtha", "Mercury", 17),
    ("Moola", "Ketu", 7),
    ("Purva Ashadha", "Venus", 20),
    ("Uttara Ashadha", "Sun", 6),
    ("Shravana", "Moon", 10),
    ("Dhanishta", "Mars", 7),
    ("Shatabhisha", "Rahu", 18),
    ("Purva Bhadrapada", "Jupiter", 16),
    ("Uttara Bhadrapada", "Saturn", 19),
    ("Revati", "Mercury", 17),
]

DASHA_SEQUENCE = [
    "Ketu", "Venus", "Sun", "Moon", "Mars",
    "Rahu", "Jupiter", "Saturn", "Mercury",
]

DASHA_YEARS = {
    "Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7,
    "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17,
}

# Gochar: favorable transit houses counted from natal Moon sign
TRANSIT_FAVORABLE = {
    "Sun":     [3, 6, 10, 11],
    "Moon":    [1, 3, 6, 7, 10, 11],
    "Mars":    [3, 6, 11],
    "Mercury": [2, 4, 6, 8, 10, 11],
    "Jupiter": [2, 5, 7, 9, 11],
    "Venus":   [1, 2, 3, 4, 5, 8, 9, 11, 12],
    "Saturn":  [3, 6, 11],
    "Rahu":    [3, 6, 10, 11],
    "Ketu":    [3, 6, 11],
}

# Houses most relevant to each prediction category
PREDICTION_HOUSES = {
    "career": [10, 6, 2, 11],
    "health": [1, 6, 8],
    "love":   [5, 7, 12, 4],
}

# Planet importance weights per category
PLANET_WEIGHTS = {
    "career": {
        "Sun": 1.5, "Moon": 1.0, "Mars": 1.0, "Mercury": 1.2,
        "Jupiter": 1.3, "Venus": 0.8, "Saturn": 1.5, "Rahu": 1.0, "Ketu": 0.5,
    },
    "health": {
        "Sun": 1.5, "Moon": 1.2, "Mars": 1.3, "Mercury": 0.8,
        "Jupiter": 1.0, "Venus": 0.8, "Saturn": 1.3, "Rahu": 1.0, "Ketu": 1.0,
    },
    "love": {
        "Sun": 0.8, "Moon": 1.5, "Mars": 1.0, "Mercury": 0.8,
        "Jupiter": 1.3, "Venus": 2.0, "Saturn": 0.5, "Rahu": 0.5, "Ketu": 0.5,
    },
}

# ---------------------------------------------------------------------------
# Gun Milan (Ashtakoot) compatibility tables
# ---------------------------------------------------------------------------

# Varna: Brahmin(4) > Kshatriya(3) > Vaishya(2) > Shudra(1) by rashi
VARNA_TABLE = [
    3,  # Aries - Kshatriya
    2,  # Taurus - Vaishya
    1,  # Gemini - Shudra
    4,  # Cancer - Brahmin
    3,  # Leo - Kshatriya
    2,  # Virgo - Vaishya
    1,  # Libra - Shudra
    4,  # Scorpio - Brahmin
    3,  # Sagittarius - Kshatriya
    2,  # Capricorn - Vaishya
    1,  # Aquarius - Shudra
    4,  # Pisces - Brahmin
]

# Vashya categories: 0=Chatushpada, 1=Manava, 2=Jalachara, 3=Vanachara, 4=Keeta
VASHYA_TABLE = [
    0,  # Aries - Chatushpada
    0,  # Taurus - Chatushpada
    1,  # Gemini - Manava
    2,  # Cancer - Jalachara
    3,  # Leo - Vanachara
    1,  # Virgo - Manava
    1,  # Libra - Manava
    4,  # Scorpio - Keeta
    0,  # Sagittarius - Chatushpada
    2,  # Capricorn - Jalachara
    1,  # Aquarius - Manava
    2,  # Pisces - Jalachara
]

# Vashya compatibility matrix [boy_vashya][girl_vashya] -> score (out of 2)
VASHYA_SCORE = [
    [2, 0, 0, 1, 0],  # Chatushpada vs all
    [1, 2, 1, 0, 0],  # Manava vs all
    [0, 1, 2, 0, 1],  # Jalachara vs all
    [0, 0, 1, 2, 1],  # Vanachara vs all
    [0, 1, 0, 0, 2],  # Keeta vs all
]

# Yoni: each nakshatra (0-26) mapped to animal index
# Animals: 0=Horse, 1=Elephant, 2=Sheep, 3=Serpent, 4=Dog, 5=Cat,
#          6=Rat, 7=Cow, 8=Buffalo, 9=Tiger, 10=Deer, 11=Monkey,
#          12=Mongoose, 13=Lion
YONI_ANIMAL = [
    0,   # Ashwini - Horse
    1,   # Bharani - Elephant
    2,   # Krittika - Sheep
    3,   # Rohini - Serpent
    3,   # Mrigashira - Serpent
    4,   # Ardra - Dog
    5,   # Punarvasu - Cat
    2,   # Pushya - Sheep
    5,   # Ashlesha - Cat
    6,   # Magha - Rat
    6,   # Purva Phalguni - Rat
    7,   # Uttara Phalguni - Cow
    8,   # Hasta - Buffalo
    9,   # Chitra - Tiger
    8,   # Swati - Buffalo
    9,   # Vishakha - Tiger
    10,  # Anuradha - Deer
    10,  # Jyeshtha - Deer
    4,   # Moola - Dog
    11,  # Purva Ashadha - Monkey
    12,  # Uttara Ashadha - Mongoose
    11,  # Shravana - Monkey
    13,  # Dhanishta - Lion
    0,   # Shatabhisha - Horse
    13,  # Purva Bhadrapada - Lion
    7,   # Uttara Bhadrapada - Cow
    1,   # Revati - Elephant
]

# Yoni enemy pairs: mutual enemies scoring 0
YONI_ENEMIES = {
    frozenset({0, 8}),    # Horse - Buffalo
    frozenset({1, 13}),   # Elephant - Lion
    frozenset({2, 11}),   # Sheep - Monkey
    frozenset({3, 12}),   # Serpent - Mongoose
    frozenset({4, 10}),   # Dog - Deer
    frozenset({5, 6}),    # Cat - Rat
    frozenset({7, 9}),    # Cow - Tiger
}

# Gana: each nakshatra mapped to 0=Deva, 1=Manushya, 2=Rakshasa
GANA_TABLE = [
    0, 1, 2,   # Ashwini(Deva), Bharani(Manushya), Krittika(Rakshasa)
    0, 0, 1,   # Rohini(Deva), Mrigashira(Deva), Ardra(Manushya)
    0, 0, 2,   # Punarvasu(Deva), Pushya(Deva), Ashlesha(Rakshasa)
    2, 1, 0,   # Magha(Rakshasa), P.Phalguni(Manushya), U.Phalguni(Deva)
    0, 2, 0,   # Hasta(Deva), Chitra(Rakshasa), Swati(Deva)
    2, 0, 2,   # Vishakha(Rakshasa), Anuradha(Deva), Jyeshtha(Rakshasa)
    2, 1, 0,   # Moola(Rakshasa), P.Ashadha(Manushya), U.Ashadha(Deva)
    0, 2, 2,   # Shravana(Deva), Dhanishta(Rakshasa), Shatabhisha(Rakshasa)
    1, 1, 0,   # P.Bhadrapada(Manushya), U.Bhadrapada(Manushya), Revati(Deva)
]

# Gana scoring matrix [boy_gana][girl_gana] -> score out of 6
GANA_SCORE = [
    [6, 5, 1],  # Deva boy
    [5, 6, 0],  # Manushya boy
    [1, 0, 6],  # Rakshasa boy
]

# Nadi: each nakshatra mapped to 0=Aadi(Vata), 1=Madhya(Pitta), 2=Antya(Kapha)
NADI_TABLE = [
    0, 1, 2, 2, 1, 0, 0, 1, 2,   # Ashwini..Ashlesha
    0, 1, 2, 2, 1, 0, 0, 1, 2,   # Magha..Jyeshtha
    0, 1, 2, 2, 1, 0, 0, 1, 2,   # Moola..Revati
]

# Planet natural friendship: 2=Friend, 1=Neutral, 0=Enemy
PLANET_FRIENDSHIP = {
    "Sun":     {"Moon": 2, "Mars": 2, "Jupiter": 2, "Venus": 0, "Saturn": 0, "Mercury": 1},
    "Moon":    {"Sun": 2, "Mars": 1, "Jupiter": 1, "Venus": 1, "Saturn": 1, "Mercury": 0},
    "Mars":    {"Sun": 2, "Moon": 2, "Jupiter": 2, "Venus": 1, "Saturn": 0, "Mercury": 0},
    "Mercury": {"Sun": 2, "Moon": 0, "Mars": 1, "Jupiter": 1, "Venus": 2, "Saturn": 1},
    "Jupiter": {"Sun": 2, "Moon": 2, "Mars": 2, "Venus": 0, "Saturn": 1, "Mercury": 0},
    "Venus":   {"Sun": 0, "Moon": 1, "Mars": 1, "Jupiter": 1, "Saturn": 2, "Mercury": 2},
    "Saturn":  {"Sun": 0, "Moon": 0, "Mars": 0, "Jupiter": 1, "Venus": 2, "Mercury": 2},
}

# Dignity tables (sign index 0-11, Aries=0 .. Pisces=11)
EXALTATION = {
    "Sun": 0, "Moon": 1, "Mars": 9, "Mercury": 5,
    "Jupiter": 3, "Venus": 11, "Saturn": 6,
}
DEBILITATION = {
    "Sun": 6, "Moon": 7, "Mars": 3, "Mercury": 11,
    "Jupiter": 9, "Venus": 5, "Saturn": 0,
}
OWN_SIGNS = {
    "Sun": [4], "Moon": [3], "Mars": [0, 7], "Mercury": [2, 5],
    "Jupiter": [8, 11], "Venus": [1, 6], "Saturn": [9, 10],
}

# House lords (which planet rules each sign, by sign index 0-11)
SIGN_LORDS = [
    "Mars", "Venus", "Mercury", "Moon", "Sun", "Mercury",
    "Venus", "Mars", "Jupiter", "Saturn", "Saturn", "Jupiter",
]

# Ephem body constructors for the 7 visible planets
_EPHEM_BODIES = {
    "Sun": ephem.Sun,
    "Moon": ephem.Moon,
    "Mars": ephem.Mars,
    "Mercury": ephem.Mercury,
    "Jupiter": ephem.Jupiter,
    "Venus": ephem.Venus,
    "Saturn": ephem.Saturn,
}

# ---------------------------------------------------------------------------
# Ayanamsa & coordinate helpers
# ---------------------------------------------------------------------------

# Reference epoch for Lahiri ayanamsa
_J2000 = ephem.Date("2000/1/1 12:00:00")
_LAHIRI_AT_J2000 = 23.8570       # degrees at J2000.0
_PRECESSION_RATE = 50.2790 / 3600.0  # degrees per year (~0.01397)


def _lahiri_ayanamsa(ephem_date) -> float:
    """Compute Lahiri ayanamsa in degrees for a given ephem date."""
    years_from_j2000 = (ephem_date - _J2000) / 365.25
    return _LAHIRI_AT_J2000 + years_from_j2000 * _PRECESSION_RATE


def _tropical_lon(body, obs) -> float:
    """Get tropical ecliptic longitude in degrees for a computed body."""
    ecl = ephem.Ecliptic(body)
    return math.degrees(ecl.lon) % 360.0


def _to_sidereal(tropical_lon: float, ayanamsa: float) -> float:
    """Convert tropical longitude to sidereal by subtracting ayanamsa."""
    return (tropical_lon - ayanamsa) % 360.0


def _mean_rahu_lon(ephem_date) -> float:
    """Compute the mean longitude of Rahu (ascending lunar node) in tropical degrees.

    Standard formula from Meeus / Indian Ephemeris:
      Omega = 125.04452 - 0.0529539222 * d   (degrees, d = days from J2000.0)
    This gives the *mean* ascending node, which is what traditional Vedic
    astrology uses.
    """
    d = ephem_date - _J2000
    return (125.04452 - 0.0529539222 * d) % 360.0


def _compute_ascendant(obs) -> float:
    """Compute the tropical ascendant longitude for an observer/time.

    Uses the standard formula:
      ASC = atan2(cos(LST), -(sin(LST)*cos(eps) - tan(lat)*sin(eps)))
    where LST = Local Sidereal Time, eps = obliquity, lat = geographic latitude.
    """
    lst = float(obs.sidereal_time())  # radians
    T = (obs.date - _J2000) / 36525.0  # Julian centuries
    eps = math.radians(23.439291 - 0.013004167 * T)  # obliquity
    lat = float(obs.lat)  # radians

    y = math.cos(lst)
    x = -(math.sin(lst) * math.cos(eps) - math.tan(lat) * math.sin(eps))
    asc = math.degrees(math.atan2(y, x)) % 360.0
    return asc


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _lon_to_sign(longitude: float):
    """Return (sign_index, sign_name, degrees_in_sign) for a sidereal longitude."""
    sign_idx = int(longitude // 30) % 12
    return sign_idx, SIGNS[sign_idx], longitude % 30


def _check_dignity(planet: str, sign_idx: int) -> str:
    if planet in ("Rahu", "Ketu"):
        return "neutral"
    if EXALTATION.get(planet) == sign_idx:
        return "exalted"
    if DEBILITATION.get(planet) == sign_idx:
        return "debilitated"
    if sign_idx in OWN_SIGNS.get(planet, []):
        return "own_sign"
    return "neutral"


def _make_observer(ephem_date, latitude: float = 0.0,
                   longitude: float = 0.0):
    """Create an ephem.Observer for a date and location."""
    obs = ephem.Observer()
    obs.lat = str(latitude)
    obs.lon = str(longitude)
    obs.date = ephem_date
    obs.pressure = 0  # disable atmospheric refraction
    return obs


# ---------------------------------------------------------------------------
# Core calculations
# ---------------------------------------------------------------------------

def _local_to_ephem_date(year: int, month: int, day: int,
                         hour: int, minute: int, utc_offset: float):
    """Convert local date/time to an ephem.Date in UT."""
    local_dt = datetime(year, month, day, hour, minute,
                        tzinfo=timezone(timedelta(hours=utc_offset)))
    utc_dt = local_dt.astimezone(timezone.utc)
    return ephem.Date(utc_dt)


def calculate_planet_positions(ephem_date, latitude: float = 0.0,
                               longitude: float = 0.0) -> dict:
    """Compute sidereal positions of all 9 Vedic grahas."""
    obs = _make_observer(ephem_date, latitude, longitude)
    ayanamsa = _lahiri_ayanamsa(ephem_date)
    positions = {}

    # Also compute positions for the previous day to estimate speed
    obs_prev = _make_observer(ephem_date - 1, latitude, longitude)

    for name, body_cls in _EPHEM_BODIES.items():
        body = body_cls()
        body.compute(obs)
        trop_lon = _tropical_lon(body, obs)
        sid_lon = _to_sidereal(trop_lon, ayanamsa)

        # Speed: difference from previous day (degrees/day)
        body_prev = body_cls()
        body_prev.compute(obs_prev)
        trop_lon_prev = _tropical_lon(body_prev, obs_prev)
        # Handle wrap-around at 0/360
        speed = trop_lon - trop_lon_prev
        if speed > 180:
            speed -= 360
        elif speed < -180:
            speed += 360

        sign_idx, sign_name, deg = _lon_to_sign(sid_lon)
        positions[name] = {
            "longitude": sid_lon,
            "sign": sign_name,
            "sign_index": sign_idx,
            "degree": round(deg, 4),
            "speed": speed,
            "retrograde": speed < 0,
            "dignity": _check_dignity(name, sign_idx),
        }

    # Rahu (mean ascending node)
    rahu_trop = _mean_rahu_lon(ephem_date)
    rahu_sid = _to_sidereal(rahu_trop, ayanamsa)
    sign_idx, sign_name, deg = _lon_to_sign(rahu_sid)
    positions["Rahu"] = {
        "longitude": rahu_sid,
        "sign": sign_name,
        "sign_index": sign_idx,
        "degree": round(deg, 4),
        "speed": -0.053,  # mean node is always retrograde
        "retrograde": True,
        "dignity": "neutral",
    }

    # Ketu = Rahu + 180
    ketu_sid = (rahu_sid + 180.0) % 360.0
    sign_idx, sign_name, deg = _lon_to_sign(ketu_sid)
    positions["Ketu"] = {
        "longitude": ketu_sid,
        "sign": sign_name,
        "sign_index": sign_idx,
        "degree": round(deg, 4),
        "speed": -0.053,
        "retrograde": True,
        "dignity": "neutral",
    }

    return positions


def calculate_houses(ephem_date, latitude: float,
                     longitude: float) -> dict:
    """Calculate ascendant and Whole Sign houses."""
    obs = _make_observer(ephem_date, latitude, longitude)
    ayanamsa = _lahiri_ayanamsa(ephem_date)

    asc_tropical = _compute_ascendant(obs)
    asc_sidereal = _to_sidereal(asc_tropical, ayanamsa)

    asc_sign_idx, asc_sign, asc_deg = _lon_to_sign(asc_sidereal)
    house_signs = [SIGNS[(asc_sign_idx + i) % 12] for i in range(12)]

    return {
        "ascendant": {
            "longitude": asc_sidereal,
            "sign": asc_sign,
            "sign_index": asc_sign_idx,
            "degree": round(asc_deg, 4),
        },
        "house_signs": house_signs,
        "ascendant_sign_index": asc_sign_idx,
    }


def assign_planets_to_houses(planets: dict, asc_sign_idx: int) -> None:
    """Mutate *planets* to add a ``house`` key (1-12) for each planet."""
    for data in planets.values():
        data["house"] = ((data["sign_index"] - asc_sign_idx) % 12) + 1


# ---------------------------------------------------------------------------
# Nakshatra & Dasha
# ---------------------------------------------------------------------------

def get_nakshatra(moon_longitude: float) -> dict:
    """Return nakshatra info for a given Moon longitude."""
    nak_span = 360.0 / 27.0  # 13.3333...
    idx = int(moon_longitude / nak_span)
    if idx >= 27:
        idx = 26
    name, ruler, years = NAKSHATRAS[idx]
    pos_in_nak = (moon_longitude - idx * nak_span) / nak_span  # 0..1
    return {
        "index": idx,
        "name": name,
        "ruling_planet": ruler,
        "dasha_years": years,
        "fraction_completed": pos_in_nak,
    }


def calculate_vimshottari_dasha(moon_longitude: float,
                                 birth_date: date) -> list:
    """Build a complete Mahadasha + Antardasha timeline from birth."""
    nak = get_nakshatra(moon_longitude)
    start_lord = nak["ruling_planet"]
    start_idx = DASHA_SEQUENCE.index(start_lord)

    remaining_fraction = 1.0 - nak["fraction_completed"]
    balance_years = DASHA_YEARS[start_lord] * remaining_fraction

    dashas = []
    current_start = birth_date

    for i in range(9):
        lord_idx = (start_idx + i) % 9
        lord = DASHA_SEQUENCE[lord_idx]
        if i == 0:
            dur_years = balance_years
        else:
            dur_years = DASHA_YEARS[lord]
        dur_days = dur_years * 365.25
        end = current_start + timedelta(days=dur_days)

        # Compute antardashas (sub-periods)
        ad_start_idx = DASHA_SEQUENCE.index(lord)
        antardashas = []
        ad_current = current_start
        for j in range(9):
            ad_lord = DASHA_SEQUENCE[(ad_start_idx + j) % 9]
            ad_dur_years = (dur_years * DASHA_YEARS[ad_lord]) / 120.0
            ad_dur_days = ad_dur_years * 365.25
            ad_end = ad_current + timedelta(days=ad_dur_days)
            antardashas.append({
                "lord": ad_lord,
                "start": ad_current,
                "end": ad_end,
            })
            ad_current = ad_end

        dashas.append({
            "lord": lord,
            "start": current_start,
            "end": end,
            "duration_years": round(dur_years, 2),
            "antardashas": antardashas,
        })
        current_start = end

    return dashas


def get_current_dasha(dashas: list, target: date) -> dict:
    """Find the active Mahadasha and Antardasha for a given date."""
    for md in dashas:
        if md["start"] <= target < md["end"]:
            for ad in md["antardashas"]:
                if ad["start"] <= target < ad["end"]:
                    return {
                        "mahadasha_lord": md["lord"],
                        "antardasha_lord": ad["lord"],
                        "mahadasha_start": md["start"].isoformat(),
                        "mahadasha_end": md["end"].isoformat(),
                        "antardasha_start": ad["start"].isoformat(),
                        "antardasha_end": ad["end"].isoformat(),
                    }
            # Fallback: return first antardasha if exact match not found
            return {
                "mahadasha_lord": md["lord"],
                "antardasha_lord": md["antardashas"][0]["lord"],
                "mahadasha_start": md["start"].isoformat(),
                "mahadasha_end": md["end"].isoformat(),
                "antardasha_start": md["antardashas"][0]["start"].isoformat(),
                "antardasha_end": md["antardashas"][0]["end"].isoformat(),
            }
    # If target date is beyond computed range, return last dasha
    last = dashas[-1]
    return {
        "mahadasha_lord": last["lord"],
        "antardasha_lord": last["antardashas"][-1]["lord"],
        "mahadasha_start": last["start"].isoformat(),
        "mahadasha_end": last["end"].isoformat(),
        "antardasha_start": last["antardashas"][-1]["start"].isoformat(),
        "antardasha_end": last["antardashas"][-1]["end"].isoformat(),
    }


# ---------------------------------------------------------------------------
# Transits
# ---------------------------------------------------------------------------

def calculate_current_transits(target_date: date) -> dict:
    """Get current sidereal planetary positions for transit analysis."""
    ephem_date = ephem.Date(f"{target_date.year}/{target_date.month}/{target_date.day} 12:00:00")
    return calculate_planet_positions(ephem_date)


def analyze_transits(natal_moon_sign_idx: int, transit_planets: dict) -> list:
    """Determine which transits are favorable/unfavorable from natal Moon."""
    results = []
    for name, data in transit_planets.items():
        house_from_moon = ((data["sign_index"] - natal_moon_sign_idx) % 12) + 1
        is_favorable = house_from_moon in TRANSIT_FAVORABLE.get(name, [])
        results.append({
            "planet": name,
            "transit_sign": data["sign"],
            "house_from_moon": house_from_moon,
            "is_favorable": is_favorable,
            "retrograde": data["retrograde"],
            "dignity": data["dignity"],
        })
    return results


def detect_sade_sati(natal_moon_sign_idx: int,
                     transit_saturn_sign_idx: int):
    """Check if Saturn is in Sade Sati position relative to natal Moon."""
    offset = (transit_saturn_sign_idx - natal_moon_sign_idx) % 12
    if offset == 11:
        return "Rising (12th from Moon) - mental stress and anxiety phase"
    elif offset == 0:
        return "Peak (over Moon) - direct challenges to self and health"
    elif offset == 1:
        return "Setting (2nd from Moon) - financial and family pressure"
    return None


# ---------------------------------------------------------------------------
# Yoga Detection
# ---------------------------------------------------------------------------

def detect_yogas(planets: dict, asc_sign_idx: int) -> list:
    """Detect basic Vedic yogas from planetary positions."""
    yogas = []
    kendra_houses = [1, 4, 7, 10]

    # 1. Pancha Mahapurusha Yogas
    mahapurusha = {
        "Mars":    ("Ruchaka Yoga",  "Courage, authority, leadership strength"),
        "Mercury": ("Bhadra Yoga",   "Intelligence, communication, business acumen"),
        "Jupiter": ("Hamsa Yoga",    "Wisdom, spirituality, good fortune"),
        "Venus":   ("Malavya Yoga",  "Luxury, beauty, artistic talent, romance"),
        "Saturn":  ("Sasa Yoga",     "Discipline, authority over masses, persistence"),
    }
    for planet, (yoga_name, desc) in mahapurusha.items():
        p = planets[planet]
        if p["house"] in kendra_houses and p["dignity"] in ("exalted", "own_sign"):
            yogas.append({
                "name": yoga_name,
                "description": desc,
                "planets": [planet],
                "type": "mahapurusha",
            })

    # 2. Gajakesari Yoga: Jupiter in kendra from Moon
    moon_idx = planets["Moon"]["sign_index"]
    jup_idx = planets["Jupiter"]["sign_index"]
    if (jup_idx - moon_idx) % 12 in [0, 3, 6, 9]:
        yogas.append({
            "name": "Gajakesari Yoga",
            "description": "Fame, wisdom, lasting prosperity",
            "planets": ["Jupiter", "Moon"],
            "type": "wealth",
        })

    # 3. Budhaditya Yoga: Sun and Mercury in same sign
    if planets["Sun"]["sign_index"] == planets["Mercury"]["sign_index"]:
        yogas.append({
            "name": "Budhaditya Yoga",
            "description": "Sharp intellect, fame through knowledge",
            "planets": ["Sun", "Mercury"],
            "type": "intelligence",
        })

    # 4. Chandra-Mangal Yoga: Moon and Mars in same sign
    if planets["Moon"]["sign_index"] == planets["Mars"]["sign_index"]:
        yogas.append({
            "name": "Chandra-Mangal Yoga",
            "description": "Wealth through determination, entrepreneurial spirit",
            "planets": ["Moon", "Mars"],
            "type": "wealth",
        })

    # 5. Amala Yoga: Benefic in 10th house
    for planet in ["Jupiter", "Venus", "Mercury"]:
        if planets[planet]["house"] == 10:
            yogas.append({
                "name": "Amala Yoga",
                "description": f"Virtuous reputation and good character ({planet} in 10th)",
                "planets": [planet],
                "type": "character",
            })
            break

    return yogas


# ---------------------------------------------------------------------------
# Gun Milan (Ashtakoot) Compatibility
# ---------------------------------------------------------------------------

def calculate_gun_milan(boy_moon_lon: float, girl_moon_lon: float) -> dict:
    """Calculate Ashtakoot Gun Milan (36-point compatibility system).

    Args:
        boy_moon_lon: Sidereal Moon longitude of person 1 (0-360)
        girl_moon_lon: Sidereal Moon longitude of person 2 (0-360)

    Returns:
        dict with total_score, max_score, percentage, kutas (8 components),
        nadi_dosha flag, verdict, and both nakshatras/rashis.
    """
    boy_nak = get_nakshatra(boy_moon_lon)
    girl_nak = get_nakshatra(girl_moon_lon)
    boy_rashi = int(boy_moon_lon // 30) % 12
    girl_rashi = int(girl_moon_lon // 30) % 12
    boy_nak_idx = boy_nak["index"]
    girl_nak_idx = girl_nak["index"]

    kutas = []

    # 1. Varna (max 1) — spiritual compatibility
    boy_varna = VARNA_TABLE[boy_rashi]
    girl_varna = VARNA_TABLE[girl_rashi]
    varna_score = 1 if boy_varna >= girl_varna else 0
    kutas.append({"name": "Varna", "max": 1, "score": varna_score,
                  "description": "Spiritual compatibility"})

    # 2. Vashya (max 2) — mutual attraction & dominance
    boy_vashya = VASHYA_TABLE[boy_rashi]
    girl_vashya = VASHYA_TABLE[girl_rashi]
    vashya_score = VASHYA_SCORE[boy_vashya][girl_vashya]
    kutas.append({"name": "Vashya", "max": 2, "score": vashya_score,
                  "description": "Mutual attraction & dominance"})

    # 3. Tara (max 3) — destiny & luck compatibility
    tara_count = ((boy_nak_idx - girl_nak_idx) % 27) + 1
    tara_remainder = tara_count % 9
    fwd_good = tara_remainder in (0, 2, 4, 6, 8)
    tara_count_rev = ((girl_nak_idx - boy_nak_idx) % 27) + 1
    tara_remainder_rev = tara_count_rev % 9
    rev_good = tara_remainder_rev in (0, 2, 4, 6, 8)
    if fwd_good and rev_good:
        tara_score = 3
    elif fwd_good or rev_good:
        tara_score = 1.5
    else:
        tara_score = 0
    kutas.append({"name": "Tara", "max": 3, "score": tara_score,
                  "description": "Destiny & luck compatibility"})

    # 4. Yoni (max 4) — physical & sexual compatibility
    boy_animal = YONI_ANIMAL[boy_nak_idx]
    girl_animal = YONI_ANIMAL[girl_nak_idx]
    if boy_animal == girl_animal:
        yoni_score = 4
    elif frozenset({boy_animal, girl_animal}) in YONI_ENEMIES:
        yoni_score = 0
    else:
        yoni_score = 2
    kutas.append({"name": "Yoni", "max": 4, "score": yoni_score,
                  "description": "Physical & sexual compatibility"})

    # 5. Graha Maitri (max 5) — mental compatibility & friendship
    boy_lord = SIGN_LORDS[boy_rashi]
    girl_lord = SIGN_LORDS[girl_rashi]
    if boy_lord == girl_lord:
        maitri_score = 5
    else:
        b2g = PLANET_FRIENDSHIP.get(boy_lord, {}).get(girl_lord, 1)
        g2b = PLANET_FRIENDSHIP.get(girl_lord, {}).get(boy_lord, 1)
        total_f = b2g + g2b
        if total_f >= 4:
            maitri_score = 5
        elif total_f == 3:
            maitri_score = 4
        elif total_f == 2:
            maitri_score = 3
        elif total_f == 1:
            maitri_score = 1
        else:
            maitri_score = 0
    kutas.append({"name": "Graha Maitri", "max": 5, "score": maitri_score,
                  "description": "Mental compatibility & friendship"})

    # 6. Gana (max 6) — temperament & behavior
    boy_gana = GANA_TABLE[boy_nak_idx]
    girl_gana = GANA_TABLE[girl_nak_idx]
    gana_score = GANA_SCORE[boy_gana][girl_gana]
    kutas.append({"name": "Gana", "max": 6, "score": gana_score,
                  "description": "Temperament & behavior"})

    # 7. Bhakoot (max 7) — health, wealth & family happiness
    diff = (boy_rashi - girl_rashi) % 12
    rev_diff = (girl_rashi - boy_rashi) % 12
    bad_bhakoot = {(1, 11), (11, 1), (5, 7), (7, 5)}
    bhakoot_score = 0 if (diff, rev_diff) in bad_bhakoot else 7
    kutas.append({"name": "Bhakoot", "max": 7, "score": bhakoot_score,
                  "description": "Health, wealth & family happiness"})

    # 8. Nadi (max 8) — health & gene compatibility
    boy_nadi = NADI_TABLE[boy_nak_idx]
    girl_nadi = NADI_TABLE[girl_nak_idx]
    nadi_score = 0 if boy_nadi == girl_nadi else 8
    nadi_dosha = (boy_nadi == girl_nadi)
    kutas.append({"name": "Nadi", "max": 8, "score": nadi_score,
                  "description": "Health & gene compatibility"})

    total = sum(k["score"] for k in kutas)

    if total >= 28:
        verdict = "Excellent Match"
    elif total >= 21:
        verdict = "Good Match"
    elif total >= 18:
        verdict = "Average Match - proceed with caution"
    else:
        verdict = "Below Average - seek remedies before proceeding"

    return {
        "total_score": total,
        "max_score": 36,
        "percentage": round((total / 36) * 100, 1),
        "kutas": kutas,
        "nadi_dosha": nadi_dosha,
        "verdict": verdict,
        "boy_nakshatra": boy_nak["name"],
        "girl_nakshatra": girl_nak["name"],
        "boy_rashi": SIGNS[boy_rashi],
        "girl_rashi": SIGNS[girl_rashi],
    }


def get_darakaraka(planets: dict) -> dict:
    """Find the Darakaraka (planet with lowest degree, excluding Rahu/Ketu)."""
    candidates = {
        name: data for name, data in planets.items()
        if name not in ("Rahu", "Ketu")
    }
    dk = min(candidates.items(), key=lambda x: x[1]["degree"])
    return {
        "planet": dk[0],
        "sign": dk[1]["sign"],
        "house": dk[1]["house"],
        "degree": dk[1]["degree"],
    }


# ---------------------------------------------------------------------------
# Master chart generation
# ---------------------------------------------------------------------------

def generate_birth_chart(dob: date, tob: str, latitude: float,
                         longitude: float, utc_offset: float) -> dict:
    """Build complete chart data for Claude interpretation."""
    hour, minute = map(int, tob.split(":"))
    ephem_date = _local_to_ephem_date(dob.year, dob.month, dob.day,
                                       hour, minute, utc_offset)

    planets = calculate_planet_positions(ephem_date, latitude, longitude)
    houses = calculate_houses(ephem_date, latitude, longitude)
    assign_planets_to_houses(planets, houses["ascendant_sign_index"])

    moon_lon = planets["Moon"]["longitude"]
    nakshatra = get_nakshatra(moon_lon)
    dashas = calculate_vimshottari_dasha(moon_lon, dob)
    current_dasha = get_current_dasha(dashas, date.today())

    transit_planets = calculate_current_transits(date.today())
    natal_moon_sign_idx = planets["Moon"]["sign_index"]
    transit_analysis = analyze_transits(natal_moon_sign_idx, transit_planets)

    saturn_transit_idx = transit_planets["Saturn"]["sign_index"]
    sade_sati = detect_sade_sati(natal_moon_sign_idx, saturn_transit_idx)

    # Detect yogas
    asc_idx = houses["ascendant_sign_index"]
    yogas = detect_yogas(planets, asc_idx)

    # Determine house lords for key houses
    house_lords = {}
    for h in range(1, 13):
        sign_idx = (asc_idx + h - 1) % 12
        house_lords[h] = SIGN_LORDS[sign_idx]

    # Build complete dasha timeline (Mahadasha + Antardasha)
    dasha_timeline = []
    for md in dashas:
        md_entry = {
            "lord": md["lord"],
            "start": md["start"].isoformat(),
            "end": md["end"].isoformat(),
            "duration_years": md["duration_years"],
            "is_current": md["start"] <= date.today() < md["end"],
            "antardashas": [
                {
                    "lord": ad["lord"],
                    "start": ad["start"].isoformat(),
                    "end": ad["end"].isoformat(),
                    "is_current": ad["start"] <= date.today() < ad["end"],
                }
                for ad in md["antardashas"]
            ],
        }
        dasha_timeline.append(md_entry)

    return {
        "natal_chart": {
            "ascendant": houses["ascendant"],
            "planets": {
                name: {
                    "sign": d["sign"],
                    "degree": d["degree"],
                    "house": d["house"],
                    "retrograde": d["retrograde"],
                    "dignity": d["dignity"],
                }
                for name, d in planets.items()
            },
            "house_signs": houses["house_signs"],
            "house_lords": house_lords,
            "moon_nakshatra": {
                "name": nakshatra["name"],
                "ruling_planet": nakshatra["ruling_planet"],
            },
            "moon_longitude": moon_lon,
        },
        "dasha": current_dasha,
        "dasha_timeline": dasha_timeline,
        "transits": transit_analysis,
        "sade_sati": sade_sati,
        "yogas": yogas,
    }


# ---------------------------------------------------------------------------
# Best days of the month
# ---------------------------------------------------------------------------

def calculate_best_days(natal_moon_sign_idx: int, year: int, month: int,
                        category: str) -> list:
    """Score each day of a month and return the top 5 for a category."""
    relevant_houses = PREDICTION_HOUSES[category]
    weights = PLANET_WEIGHTS[category]
    num_days = calendar.monthrange(year, month)[1]

    day_scores = []

    for day in range(1, num_days + 1):
        target = date(year, month, day)
        transits = calculate_current_transits(target)
        score = 0.0
        key_transits = []

        for name, data in transits.items():
            house_from_moon = ((data["sign_index"] - natal_moon_sign_idx) % 12) + 1
            is_favorable = house_from_moon in TRANSIT_FAVORABLE.get(name, [])

            # Base score
            base = 1.0 if is_favorable else -0.5

            # Category relevance multiplier
            if house_from_moon in relevant_houses:
                base *= 2.0

            # Planet importance
            base *= weights.get(name, 1.0)

            # Dignity bonus
            if data["dignity"] == "exalted":
                base += 0.5
            elif data["dignity"] == "debilitated":
                base -= 0.5

            # Retrograde penalty (not for Rahu/Ketu which are always retrograde)
            if data["retrograde"] and name not in ("Rahu", "Ketu"):
                base -= 0.3

            score += base

            if is_favorable and house_from_moon in relevant_houses:
                key_transits.append(f"{name} favorable in house {house_from_moon}")

        day_scores.append({
            "day": day,
            "date": target.isoformat(),
            "score": round(score, 1),
            "key_transits": ", ".join(key_transits[:3]) if key_transits else "Mixed planetary influences",
        })

    # Sort by score descending, return top 5
    day_scores.sort(key=lambda x: x["score"], reverse=True)
    return day_scores[:5]
