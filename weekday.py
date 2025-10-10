from datetime import datetime, date
from typing import Optional

import zoneinfo
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse

# โหราศาสตร์แบบ lite (pure Python) อยู่ใน api/flatlib_lite/__init__.py
import flatlib_lite as astro_chart

# ถ้าคุณใช้ Pro-Auto (เลือกระบบราศีจากประเทศ) ให้เปิดบรรทัด geopy ด้านล่าง
from geopy.geocoders import Nominatim

app = FastAPI(title="Astro Weekday API", version="2.1.0")

# ------------------------------
# คงที่สำหรับภาษาไทย
# ------------------------------
DAYS_TH = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
MONTHS_TH_LONG = [
    "มกราคม","กุมภาพันธ์","มีนาคม","เมษายน","พฤษภาคม","มิถุนายน",
    "กรกฎาคม","สิงหาคม","กันยายน","ตุลาคม","พฤศจิกายน","ธันวาคม"
]
MONTHS_TH_SHORT = [
    "ม.ค.","ก.พ.","มี.ค.","เม.ย.","พ.ค.","มิ.ย.",
    "ก.ค.","ส.ค.","ก.ย.","ต.ค.","พ.ย.","ธ.ค."
]


# ------------------------------
# Utilities
# ------------------------------
def parse_ddmmyyyy_th(s: str) -> tuple[date, str]:
    """รับวันที่ DD/MM/YYYY (พ.ศ. หรือ ค.ศ.) -> (date(คริสต์ศักราช), "BE"/"CE")"""
    s = s.strip()
    try:
        d = datetime.strptime(s, "%d/%m/%Y").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="รูปแบบวันที่ไม่ถูกต้อง (ต้องเป็น DD/MM/YYYY)")
    calendar = "BE" if d.year >= 2400 else "CE"
    if calendar == "BE":
        # แปลง พ.ศ. เป็น ค.ศ.
        y = d.year - 543
        try:
            d = d.replace(year=y)
        except ValueError:
            # กันกรณี 29 ก.พ. แล้วปี ค.ศ. ไม่ leap
            d = d.replace(year=y, day=28)
    return d, calendar


def format_thai_date(d: date, style: str = "short") -> dict:
    """คืนรูปแบบภาษาไทย (ตรวจวันจริง + แปลง พ.ศ.)"""
    wd_full = DAYS_TH[d.weekday()]
    wd_compact = "พฤหัส" if wd_full == "พฤหัสบดี" else wd_full
    y_be = d.year + 543
    m_idx = d.month - 1
    m_short = MONTHS_TH_SHORT[m_idx]
    m_long = MONTHS_TH_LONG[m_idx]
    thai_short = f"วัน{wd_full}ที่ {d.day} {m_short} {y_be}"
    thai_long = f"วัน{wd_full}ที่ {d.day} {m_long} {y_be}"
    return {
        "weekday_full": wd_full,
        "weekday_compact": wd_compact,
        "thai_date_short": thai_short,
        "thai_date_long": thai_long,
        "thai_date": thai_long if style == "long" else thai_short
    }


def detect_zodiac_system(lat: float, lon: float, timezone: str) -> str:
    """
    เลือกระบบราศีอัตโนมัติ:
    - ถ้าพิกัดอยู่ในประเทศที่นิยมโหราศาสตร์นิรายนะ → sidereal
    - อื่น ๆ → tropical
    """
    # fallback จาก timezone ก่อน (กันกรณีเรียก geocode ไม่สำเร็จ)
    tz_lower = (timezone or "").lower()
    if any(x in tz_lower for x in [
        "bangkok", "kolkata", "yangon", "colombo", "phnom_penh",
        "vientiane", "hanoi", "jakarta", "kathmandu", "dhaka"
    ]):
        return "sidereal"

    try:
        geolocator = Nominatim(user_agent="astro_weekday_api")
        loc = geolocator.reverse((lat, lon), language="en", timeout=10)
        country = (loc.raw.get("address", {}).get("country", "") or "").lower()
        sidereal_countries = {
            "thailand", "laos", "myanmar", "burma", "cambodia",
            "india", "sri lanka", "nepal", "bangladesh"
        }
        return "sidereal" if any(c in country for c in sidereal_countries) else "tropical"
    except Exception:
        # ถ้าดูประเทศไม่ได้ ให้ใช้ heuristic จาก timezone
        return "sidereal" if "asia/" in tz_lower else "tropical"


# ------------------------------
# Root & Health
# ------------------------------
@app.get("/")
def root():
    return {"message": "Astro Weekday API is running 🚀"}

@app.get("/health")
def health():
    return {"ok": True}


# ------------------------------
# /api/weekday  — ตรวจวันจริง
# ------------------------------
@app.get("/api/weekday")
def get_weekday(date: str):
    d, cal = parse_ddmmyyyy_th(date)
    weekday = DAYS_TH[d.weekday()]
    return {
        "date": date,
        "weekday": weekday,
        "resolved_gregorian": d.isoformat(),
        "calendar": cal
    }


# ------------------------------
# /api/weekday-th  — ข้อความวันที่ไทยสำเร็จรูป
# ------------------------------
@app.get("/api/weekday-th")
def get_weekday_th(date: str, style: Optional[str] = "short"):
    d, cal = parse_ddmmyyyy_th(date)
    payload = format_thai_date(d, style or "short")
    return {
        "input": {"date": date, "style": style or "short"},
        "resolved_gregorian": d.isoformat(),
        "calendar": cal,
        **payload
    }


# ------------------------------
# /api/astro-weekday  — วัน+เวลา+ไทม์โซน+สถานที่
# ------------------------------
@app.get("/api/astro-weekday")
def get_astro_weekday(
    date: str,
    time: Optional[str] = None,
    timezone: Optional[s]()
