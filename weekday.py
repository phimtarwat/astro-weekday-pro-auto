from fastapi import FastAPI, HTTPException
from datetime import datetime
from geopy.geocoders import Nominatim
from typing import Optional
import flatlib_lite as astro_chart

app = FastAPI(title="Astro Weekday API", version="2.0.0")

# ------------------------------
# 🔹 Utility: แปลงวันที่ไทย/สากล
# ------------------------------
def parse_ddmmyyyy_th(date_str: str):
    """แปลงวันที่จาก DD/MM/YYYY (รองรับ พ.ศ. / ค.ศ.)"""
    day, month, year = [int(x) for x in date_str.split("/")]
    if year > 2400:  # แปลง พ.ศ. → ค.ศ.
        year -= 543
    return datetime(year, month, day), "BE" if year < 2400 else "AD"

# ------------------------------
# 🔹 เลือกระบบราศีอัตโนมัติ (จาก lat/lon)
# ------------------------------
def detect_zodiac_system(lat: float, lon: float) -> str:
    geolocator = Nominatim(user_agent="astro_api")
    try:
        location = geolocator.reverse((lat, lon), language="en")
        country = location.raw["address"].get("country", "").lower()
    except Exception:
        return "sidereal"  # fallback ไทย

    sidereal_countries = [
        "thailand", "laos", "myanmar", "burma", "cambodia",
        "india", "sri lanka", "nepal", "bangladesh"
    ]

    for name in sidereal_countries:
        if name in country:
            return "sidereal"
    return "tropical"

# ------------------------------
# 🔹 API หลัก
# ------------------------------
@app.get("/api/astro-chart")
def get_astro_chart(
    date: str,
    time: str,
    timezone: str = "Asia/Bangkok",
    lat: float = 13.75,
    lon: float = 100.5
):
    """คำนวณดวงดาวอัตโนมัติ — ใช้ราศีตามประเทศเกิด"""
    d, cal = parse_ddmmyyyy_th(date)
    zodiac_system = detect_zodiac_system(lat, lon)

    try:
        result = astro_chart.compute_chart(d, time, timezone, lat, lon, zodiac_system)
        return {
            "input": {
                "date": date, "time": time, "timezone": timezone,
                "lat": lat, "lon": lon, "auto_system": zodiac_system
            },
            "planets": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ------------------------------
# 🔹 ตรวจสอบวัน
# ------------------------------
@app.get("/api/weekday")
def get_weekday(date: str):
    """ตรวจสอบวันจริงจากวันที่ (ไทย/สากล)"""
    d, cal = parse_ddmmyyyy_th(date)
    weekday_th = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
    wd = weekday_th[d.weekday()]
    return {"date": date, "weekday": wd}

