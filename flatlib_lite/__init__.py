from datetime import datetime
import math

SIGNS_THAI = [
    "เมษ", "พฤษภ", "มิถุน", "กรกฎ", "สิงห์", "กันย์",
    "ตุล", "พิจิก", "ธนู", "มังกร", "กุมภ์", "มีน"
]

SIGNS_EN = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

PLANETS = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn"]

def _solar_longitude(year, month, day, zodiac_system):
    """จำลองตำแหน่งดวงอาทิตย์"""
    base = (month * 30 + day) % 365
    tropical_long = (base * 360 / 365.25)
    if zodiac_system == "sidereal":
        # ลดค่าพรีเซสชัน ~23° เพื่อเลียนแบบโหราศาสตร์ไทย
        return (tropical_long - 23.0) % 360
    return tropical_long % 360

def _planet_position(base_long, planet_index, offset):
    """จำลองการหมุนของดาว"""
    speed_factors = [1.0, 13.2, 4.7, 1.6, 0.8, 0.2, 0.1]  # อัตราหมุน Sun→Saturn
    lon = (base_long * speed_factors[planet_index] + offset * 5) % 360
    return lon

def _get_sign_name(longitude, zodiac_system):
    idx = int(longitude / 30) % 12
    return SIGNS_THAI[idx] if zodiac_system == "sidereal" else SIGNS_EN[idx]

def compute_chart(d, time, timezone, lat, lon, zodiac_system="sidereal"):
    """คำนวณตำแหน่งดวงดาวจำลอง"""
    try:
        hh, mm = [int(x) for x in time.split(":")]
    except Exception:
        hh, mm = 0, 0
    offset = (hh * 60 + mm) / 60.0

    base_long = _solar_longitude(d.year, d.month, d.day, zodiac_system)

    result = {}
    for i, p in enumerate(PLANETS):
        lon_val = _planet_position(base_long, i, offset)
        result[p] = {
            "sign": _get_sign_name(lon_val, zodiac_system),
            "lon": round(lon_val, 2)
        }

    # Ascendant (ลัคนา)
    asc_lon = (base_long + offset * (lat / 10)) % 360
    result["Ascendant"] = {
        "sign": _get_sign_name(asc_lon, zodiac_system),
        "lon": round(asc_lon, 2)
    }

    return result

