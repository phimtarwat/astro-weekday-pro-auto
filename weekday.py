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
    timezone: Optional[str] = "Asia/Bangkok",
    place: Optional[str] = None
):
    d, cal = parse_ddmmyyyy_th(date)

    # เวลา
    if time:
        try:
            t = datetime.strptime(time, "%H:%M").time()
        except ValueError:
            raise HTTPException(status_code=400, detail="รูปแบบเวลาไม่ถูกต้อง (ต้องเป็น HH:MM)")
    else:
        t = datetime.min.time()  # 00:00

    # timezone
    try:
        tz = zoneinfo.ZoneInfo(timezone)
    except Exception:
        raise HTTPException(status_code=400, detail=f"ไม่รู้จัก timezone: {timezone}")

    dt_local = datetime.combine(d, t).replace(tzinfo=tz)
    dt_utc = dt_local.astimezone(zoneinfo.ZoneInfo("UTC"))
    weekday_th = DAYS_TH[dt_local.weekday()]

    result = {
        "date": date,
        "time": time or "00:00",
        "timezone": timezone,
        "weekday": weekday_th,
        "resolved_gregorian": d.isoformat(),
        "calendar": cal,
        "local_datetime": dt_local.isoformat(),
        "utc_datetime": dt_utc.isoformat(),
    }
    if place:
        result["place"] = place
    return result


# ------------------------------
# /api/astro-chart  — ดวงพื้นดวง (auto sidereal/tropical)
# ------------------------------
@app.get("/api/astro-chart")
def get_astro_chart(
    date: str,
    time: str,
    timezone: str = "Asia/Bangkok",
    lat: float = 13.75,
    lon: float = 100.50
):
    d, cal = parse_ddmmyyyy_th(date)
    # เลือกระบบราศีอัตโนมัติ
    zodiac_system = detect_zodiac_system(lat, lon, timezone)

    try:
        planets = astro_chart.compute_chart(d, time, timezone, lat, lon, zodiac_system)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"compute_chart error: {e}")

    # แถมเวลา UTC/Local ไว้อ้างอิง
    try:
        tz = zoneinfo.ZoneInfo(timezone)
        dt_local = datetime.combine(d, datetime.strptime(time, "%H:%M").time()).replace(tzinfo=tz)
        dt_utc = dt_local.astimezone(zoneinfo.ZoneInfo("UTC"))
    except Exception:
        dt_local = None
        dt_utc = None

    return {
        "input": {
            "date": date, "time": time, "timezone": timezone,
            "lat": lat, "lon": lon, "auto_system": zodiac_system
        },
        "resolved_gregorian": d.isoformat(),
        "local_datetime": dt_local.isoformat() if dt_local else None,
        "utc_datetime": dt_utc.isoformat() if dt_utc else None,
        "planets": planets
    }


# ------------------------------
# /api/astro-transit — ดาวจรเทียบพื้นดวง
# ------------------------------
@app.get("/api/astro-transit")
def get_astro_transit(
    base_date: str,
    base_time: str = "12:00",
    target_date: Optional[str] = None,
    lat: float = 13.75,
    lon: float = 100.5,
    timezone: str = "Asia/Bangkok"
):
    base_d, _ = parse_ddmmyyyy_th(base_date)
    if target_date:
        target_d, _ = parse_ddmmyyyy_th(target_date)
    else:
        # ใช้วันที่ปัจจุบันตาม timezone ที่ระบุ
        now_local = datetime.now(zoneinfo.ZoneInfo(timezone)).date()
        target_d = now_local

    zodiac_system = detect_zodiac_system(lat, lon, timezone)

    natal = astro_chart.compute_chart(base_d, base_time, timezone, lat, lon, zodiac_system)
    transit = astro_chart.compute_chart(target_d, "12:00", timezone, lat, lon, zodiac_system)

    # วิเคราะห์เบื้องต้นแบบง่าย (ทับ / เล็ง)
    interactions = []
    for p, nval in natal.items():
        if p in transit:
            diff = abs(nval["lon"] - transit[p]["lon"])
            diff = diff if diff <= 180 else 360 - diff
            if diff <= 10:
                interactions.append(f"{p}: ดาวจรทับดาวเดิม (แรง)")
            elif 170 <= diff <= 190:
                interactions.append(f"{p}: ดาวจรเล็งดาวเดิม (กดดัน)")

    return {
        "system": zodiac_system,
        "natal_date": base_date,
        "target_date": target_d.strftime("%d/%m/%Y"),
        "natal": natal,
        "transit": transit,
        "analysis": interactions
    }


# ------------------------------
# /api/astro-match — วิเคราะห์ดวงคู่
# ------------------------------
@app.get("/api/astro-match")
def get_astro_match(
    date1: str, time1: str, lat1: float, lon1: float,
    date2: str, time2: str, lat2: float, lon2: float,
    timezone: str = "Asia/Bangkok"
):
    d1, _ = parse_ddmmyyyy_th(date1)
    d2, _ = parse_ddmmyyyy_th(date2)

    sys1 = detect_zodiac_system(lat1, lon1, timezone)
    sys2 = detect_zodiac_system(lat2, lon2, timezone)

    c1 = astro_chart.compute_chart(d1, time1, timezone, lat1, lon1, sys1)
    c2 = astro_chart.compute_chart(d2, time2, timezone, lat2, lon2, sys2)

    # ให้คะแนนง่าย ๆ จาก Sun/Moon/Venus/Mars
    score = 0
    comments = []
    for p in ["Sun", "Moon", "Venus", "Mars"]:
        if c1[p]["sign"] == c2[p]["sign"]:
            score += 25
            comments.append(f"{p}: อยู่ราศีเดียวกัน (เข้าใจกันง่าย)")
        elif abs(c1[p]["lon"] - c2[p]["lon"]) < 30:
            score += 15
            comments.append(f"{p}: ระยะใกล้กัน (สัมพันธ์ดี)")
        else:
            comments.append(f"{p}: ต่างราศี (ต้องปรับตัว)")

    return {
        "person1": {"date": date1, "time": time1, "system": sys1},
        "person2": {"date": date2, "time": time2, "system": sys2},
        "score": min(score, 100),
        "comments": comments
    }


# ------------------------------
# /openapi.yaml — เสิร์ฟ schema (ถ้าคุณวางไฟล์นี้ข้างๆ weekday.py)
# ------------------------------
@app.get("/openapi.yaml")
def get_openapi_yaml():
    import os
    file_path = os.path.join(os.path.dirname(__file__), "openapi.yaml")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="openapi.yaml not found")
    return FileResponse(file_path, media_type="text/yaml")


# ------------------------------
# run local (dev only)
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("weekday:app", host="0.0.0.0", port=8000, reload=True)
