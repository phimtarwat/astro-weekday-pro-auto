# -*- coding: utf-8 -*-
"""
Astro Weekday API — Global Production (Offline + Auto-correct)
- ไม่พึ่งพา API ภายนอกเพื่อยืนยันวัน (ใช้ Local Calendar Engine 100%)
- รองรับ พ.ศ./ค.ศ./ปี 2 หลัก + timezone จริงตามประเทศ
- รองรับการพิมพ์ชื่อประเทศ/เมืองผิด (auto-correct) แบบ offline
- หา lat/lon จากชื่อเมืองแบบ offline
- มี cache ลดการคำนวณซ้ำ
"""

from __future__ import annotations
from datetime import datetime, date, time as dtime
from typing import Optional, Tuple, Dict
import re
import os
import difflib
import zoneinfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse

# ✅ โหราศาสตร์แบบ lite (pure Python)
import flatlib_lite as astro_chart

app = FastAPI(
    title="Astro Weekday API",
    version="3.0.0 (Global Offline + Auto-correct)"
)

# ------------------------------
# ค่าคงที่ภาษาไทย
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
# Cache (in-memory)
# ------------------------------
verify_cache: Dict[str, dict] = {}

# ------------------------------
# 1) Utilities: auto-correct ชื่อ
# ------------------------------
def autocorrect_name(name: str, valid_names: list[str]) -> str:
    if not name:
        return ""
    key = name.lower().strip()
    matches = difflib.get_close_matches(key, valid_names, n=1, cutoff=0.6)
    return matches[0] if matches else key

# ------------------------------
# 2) Offline timezone จากประเทศ (รองรับสะกดผิด)
# ------------------------------
_COUNTRY_TZ = {
    "thailand": "Asia/Bangkok",
    "usa": "America/New_York",
    "united states": "America/New_York",
    "canada": "America/Toronto",
    "uk": "Europe/London",
    "england": "Europe/London",
    "france": "Europe/Paris",
    "germany": "Europe/Berlin",
    "italy": "Europe/Rome",
    "spain": "Europe/Madrid",
    "russia": "Europe/Moscow",
    "china": "Asia/Shanghai",
    "japan": "Asia/Tokyo",
    "india": "Asia/Kolkata",
    "australia": "Australia/Sydney",
    "singapore": "Asia/Singapore",
    "malaysia": "Asia/Kuala_Lumpur",
    "indonesia": "Asia/Jakarta",
    "vietnam": "Asia/Ho_Chi_Minh",
    "philippines": "Asia/Manila",
    "nepal": "Asia/Kathmandu",
    "myanmar": "Asia/Yangon",
    "brazil": "America/Sao_Paulo",
    "mexico": "America/Mexico_City"
}

def detect_timezone_by_country(country_name: Optional[str]) -> str:
    if not country_name:
        return "Asia/Bangkok"
    corrected = autocorrect_name(country_name, list(_COUNTRY_TZ.keys()))
    return _COUNTRY_TZ.get(corrected, "Asia/Bangkok")

# ------------------------------
# 3) Offline lat/lon จากชื่อเมือง (รองรับสะกดผิด)
# ------------------------------
_CITY_COORDS: Dict[str, Tuple[float, float]] = {
    # --- Asia ---
    "bangkok": (13.75, 100.5),
    "chiang mai": (18.79, 98.98),
    "tokyo": (35.6895, 139.6917),
    "osaka": (34.6937, 135.5023),
    "seoul": (37.5665, 126.9780),
    "beijing": (39.9042, 116.4074),
    "shanghai": (31.2304, 121.4737),
    "hong kong": (22.3193, 114.1694),
    "hanoi": (21.0285, 105.8542),
    "jakarta": (-6.2088, 106.8456),
    "kuala lumpur": (3.1390, 101.6869),
    "manila": (14.5995, 120.9842),
    "mumbai": (19.0760, 72.8777),
    "delhi": (28.6139, 77.2090),
    "kolkata": (22.5726, 88.3639),
    "yangon": (16.8409, 96.1735),
    "colombo": (6.9271, 79.8612),
    "kathmandu": (27.7172, 85.3240),
    # --- Europe ---
    "london": (51.5072, -0.1276),
    "paris": (48.8566, 2.3522),
    "berlin": (52.5200, 13.4050),
    "rome": (41.9028, 12.4964),
    "madrid": (40.4168, -3.7038),
    "moscow": (55.7558, 37.6173),
    "amsterdam": (52.3676, 4.9041),
    # --- America ---
    "new york": (40.7128, -74.0060),
    "los angeles": (34.0522, -118.2437),
    "chicago": (41.8781, -87.6298),
    "toronto": (43.6532, -79.3832),
    "vancouver": (49.2827, -123.1207),
    "mexico city": (19.4326, -99.1332),
    "sao paulo": (-23.5505, -46.6333),
    "buenos aires": (-34.6037, -58.3816),
    # --- Oceania ---
    "sydney": (-33.8688, 151.2093),
    "melbourne": (-37.8136, 144.9631),
    "auckland": (-36.8485, 174.7633),
    # --- Africa ---
    "cairo": (30.0444, 31.2357),
    "johannesburg": (-26.2041, 28.0473),
    "nairobi": (-1.2921, 36.8219),
}

def get_city_coords(place: Optional[str]) -> Tuple[float, float]:
    if not place:
        return (13.75, 100.5)  # Bangkok default
    corrected = autocorrect_name(place, list(_CITY_COORDS.keys()))
    return _CITY_COORDS.get(corrected, (13.75, 100.5))

# ------------------------------
# 4) Parser/Formatter วันไทย
# ------------------------------
def parse_ddmmyyyy_th(s: str) -> dict:
    s = (s or "").strip()
    if not s:
        raise HTTPException(status_code=400, detail="กรุณาระบุวันที่")

    s = re.sub(r"[-. ]", "/", s)
    parts = [p for p in s.split("/") if p]
    if len(parts) != 3:
        raise HTTPException(status_code=400, detail="รูปแบบวันที่ไม่ถูกต้อง (เช่น 27/10/2568 หรือ 2000-10-27)")

    try:
        if len(parts[0]) == 4:  # YYYY/MM/DD
            year, month, day = map(int, parts)
        else:                   # DD/MM/YYYY or DD/MM/YY
            day, month, year = map(int, parts)
    except Exception:
        raise HTTPException(status_code=400, detail="รูปแบบวันที่ไม่ถูกต้อง (ตัวเลขไม่สมบูรณ์)")

    # รองรับทั้ง พ.ศ. / ค.ศ. / ปี 2 หลัก
    if year < 100:
        # สมมติเป็น พ.ศ. สองหลัก (68 → 2568)
        year += 2500
    if year > 2400:
        year_ce = year - 543
    else:
        year_ce = year
    year_be = year_ce + 543

    try:
        d = date(year_ce, month, day)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"วันที่ไม่ถูกต้อง: {e}")

    return {"date_obj": d, "calendar": "BE" if year > 2400 else "CE", "year_ce": year_ce, "year_be": year_be}

def get_local_weekday(d: date, timezone: str = "Asia/Bangkok", time_str: Optional[str] = "00:00") -> str:
    try:
        tz = zoneinfo.ZoneInfo(timezone)
    except Exception:
        tz = zoneinfo.ZoneInfo("Asia/Bangkok")
    t = datetime.strptime(time_str or "00:00", "%H:%M").time()
    dt_local = datetime.combine(d, t).replace(tzinfo=tz)
    return DAYS_TH[dt_local.weekday()]

def format_thai_date(d: date, style: str = "short", weekday_name: Optional[str] = None,
                     year_be: Optional[int] = None, year_ce: Optional[int] = None) -> dict:
    wd_full = weekday_name or DAYS_TH[d.weekday()]
    wd_compact = "พฤหัส" if wd_full == "พฤหัสบดี" else wd_full
    y_be = year_be or d.year + 543
    y_ce = year_ce or d.year
    m_idx = d.month - 1
    m_short, m_long = MONTHS_TH_SHORT[m_idx], MONTHS_TH_LONG[m_idx]
    thai_short = f"วัน{wd_full}ที่ {d.day} {m_short} {y_be} (ค.ศ. {y_ce})"
    thai_long = f"วัน{wd_full}ที่ {d.day} {m_long} {y_be} (ค.ศ. {y_ce})"
    return {
        "weekday_full": wd_full, "weekday_compact": wd_compact,
        "thai_date_short": thai_short, "thai_date_long": thai_long,
        "thai_date": thai_long if style == "long" else thai_short,
        "year_be": y_be, "year_ce": y_ce
    }

# ------------------------------
# 5) Local Calendar Engine (100% offline)
# ------------------------------
def local_verify_date(date_str: str, timezone: str = "Asia/Bangkok") -> dict:
    try:
        p = parse_ddmmyyyy_th(date_str)
        d = p["date_obj"]
        wd = get_local_weekday(d, timezone)
        thai_long = f"วัน{wd}ที่ {d.day} {MONTHS_TH_LONG[d.month-1]} {p['year_be']} (ค.ศ. {p['year_ce']})"
        return {"verified": True, "weekday_full": wd, "thai_date_long": thai_long,
                "verified_text": f"✅ ตรวจสอบวันสำเร็จ (Local Engine) → วัน{wd}"}
    except Exception as e:
        return {"verified": False, "verified_text": f"⚠️ Local verify error: {e}"}

def ensure_verified_date(date_str: str, timezone: str = "Asia/Bangkok") -> dict:
    key = f"{date_str}|{timezone}"
    if key in verify_cache:
        return verify_cache[key]
    result = local_verify_date(date_str, timezone)
    verify_cache[key] = result
    return result

# ------------------------------
# 6) เวลาเกิด → UTC
# ------------------------------
def convert_to_utc(d: date, time_str: str, tz_str: str):
    tz = zoneinfo.ZoneInfo(tz_str)
    t = datetime.strptime(time_str or "00:00", "%H:%M").time()
    local_dt = datetime.combine(d, t).replace(tzinfo=tz)
    return local_dt.astimezone(zoneinfo.ZoneInfo("UTC"))

# ------------------------------
# 7) ระบบโหราศาสตร์ (ไทย/สากล) อัตโนมัติ
# ------------------------------
def detect_zodiac_system(lat: float, lon: float, timezone: str, country: str = "") -> str:
    tz_lower = (timezone or "").lower()
    country_lower = (country or "").lower()
    sidereal_zones = [
        "bangkok", "kolkata", "yangon", "colombo", "phnom_penh",
        "vientiane", "hanoi", "jakarta", "kathmandu", "dhaka",
        "thailand", "myanmar", "burma", "cambodia", "laos", "india", "sri lanka", "nepal"
    ]
    if any(x in tz_lower or x in country_lower for x in sidereal_zones):
        return "sidereal"
    return "tropical"

# ------------------------------
# 8) Middleware: Auto validate ทุกครั้ง (ยกเว้น endpoint ตัวเอง)
# ------------------------------
@app.middleware("http")
async def auto_validate_middleware(request: Request, call_next):
    if request.method == "GET" and request.url.path not in ("/api/validate-weekday", "/health", "/"):
        q = dict(request.query_params)
        if "date" in q:
            tz = q.get("timezone", "Asia/Bangkok")
            validated = ensure_verified_date(q["date"], tz)
            request.state.validated_date = validated
    response = await call_next(request)
    # inject verified info ถ้า response เป็น JSON
    try:
        body = b"".join([chunk async for chunk in response.body_iterator])
        import json
        data = json.loads(body)
        if hasattr(request.state, "validated_date") and isinstance(data, dict):
            data.update(request.state.validated_date)
        if isinstance(data, dict) and not data.get("verified", False):
            data["verified_text"] = data.get("verified_text", "⚠️ ไม่สามารถยืนยันวันได้")
        return JSONResponse(content=data, status_code=response.status_code)
    except Exception:
        return response

# ------------------------------
# 9) Root & Health
# ------------------------------
@app.get("/")
def root():
    return {"message": "Astro Weekday API (v3.0.0 – Global Offline + Auto-correct) 🚀"}

@app.get("/health")
def health():
    return {"ok": True, "uptime": True, "version": "3.0.0"}

# ------------------------------
# 10) /api/validate-weekday
# ------------------------------
@app.get("/api/validate-weekday")
def validate_weekday(date: str, timezone: Optional[str] = "Asia/Bangkok"):
    return ensure_verified_date(date, timezone)

# ------------------------------
# 11) /api/weekday
# ------------------------------
@app.get("/api/weekday")
def get_weekday(date: str, timezone: Optional[str] = "Asia/Bangkok"):
    verified = ensure_verified_date(date, timezone)
    if not verified.get("verified", False):
        raise HTTPException(status_code=400, detail="ไม่สามารถยืนยันวันได้")
    p = parse_ddmmyyyy_th(date)
    d = p["date_obj"]
    weekday = get_local_weekday(d, timezone)
    result = {
        "date": date, "timezone": timezone, "weekday": weekday,
        "calendar": p["calendar"], "year_be": p["year_be"], "year_ce": p["year_ce"],
        "resolved_gregorian": d.isoformat()
    }
    result.update(verified)
    return result

# ------------------------------
# 12) /api/weekday-th
# ------------------------------
@app.get("/api/weekday-th")
def get_weekday_th(date: str, style: Optional[str] = "short", timezone: Optional[str] = "Asia/Bangkok"):
    verified = ensure_verified_date(date, timezone)
    if not verified.get("verified", False):
        raise HTTPException(status_code=400, detail="ไม่สามารถยืนยันวันได้")
    p = parse_ddmmyyyy_th(date)
    d = p["date_obj"]
    weekday_full = get_local_weekday(d, timezone)
    payload = format_thai_date(d, style, weekday_full, p["year_be"], p["year_ce"])
    payload.update(verified)
    return {"input": {"date": date, "style": style, "timezone": timezone}, **payload}

# ------------------------------
# 13) /api/astro-weekday (info)
# ------------------------------
@app.get("/api/astro-weekday")
def get_astro_weekday(date: str, time: Optional[str] = None,
                      timezone: Optional[str] = "Asia/Bangkok",
                      place: Optional[str] = None,
                      country: Optional[str] = "Thailand"):
    verified = ensure_verified_date(date, timezone or "Asia/Bangkok")
    if not verified.get("verified", False):
        raise HTTPException(status_code=400, detail="ไม่สามารถยืนยันวันได้")
    p = parse_ddmmyyyy_th(date)
    d = p["date_obj"]
    tz_str = timezone or detect_timezone_by_country(country)
    t = datetime.strptime(time or "00:00", "%H:%M").time()
    dt_local = datetime.combine(d, t).replace(tzinfo=zoneinfo.ZoneInfo(tz_str))
    dt_utc = dt_local.astimezone(zoneinfo.ZoneInfo("UTC"))
    weekday_th = DAYS_TH[dt_local.weekday()]
    return {
        "date": date, "time": time or "00:00", "timezone": tz_str, "country": country, "place": place or "-",
        "weekday": weekday_th, "calendar": p["calendar"],
        "year_be": p["year_be"], "year_ce": p["year_ce"],
        "local_datetime": dt_local.isoformat(), "utc_datetime": dt_utc.isoformat(),
        **verified
    }

# ------------------------------
# 14) /api/astro-chart (Global + Offline)
# ------------------------------
@app.get("/api/astro-chart")
def get_astro_chart(date: str, time: str,
                    timezone: Optional[str] = None,
                    lat: Optional[float] = None,
                    lon: Optional[float] = None,
                    country: Optional[str] = "Thailand",
                    place: Optional[str] = None):
    verified = ensure_verified_date(date, timezone or "Asia/Bangkok")
    if not verified.get("verified", False):
        raise HTTPException(status_code=400, detail="ไม่สามารถยืนยันวันได้")

    p = parse_ddmmyyyy_th(date)
    d = p["date_obj"]

    tz_str = timezone or detect_timezone_by_country(country)
    if place and (lat is None or lon is None):
        lat, lon = get_city_coords(place)
    lat = lat if lat is not None else 13.75
    lon = lon if lon is not None else 100.5

    dt_utc = convert_to_utc(d, time, tz_str)
    dt_local = dt_utc.astimezone(zoneinfo.ZoneInfo(tz_str))

    zodiac = detect_zodiac_system(lat, lon, tz_str, country)
    planets = astro_chart.compute_chart(d, time, tz_str, lat, lon, zodiac)

    return {
        "input": {
            "date": date, "time": time, "country": country, "place": place or "-",
            "timezone": tz_str, "lat": lat, "lon": lon, "system": zodiac
        },
        "calendar": p["calendar"], "year_be": p["year_be"], "year_ce": p["year_ce"],
        "local_datetime": dt_local.isoformat(), "utc_datetime": dt_utc.isoformat(),
        "planets": planets,
        **verified
    }

# ------------------------------
# 15) /api/astro-transit
# ------------------------------
@app.get("/api/astro-transit")
def get_astro_transit(base_date: str, base_time: str = "12:00",
                      target_date: Optional[str] = None,
                      lat: float = 13.75, lon: float = 100.5,
                      timezone: str = "Asia/Bangkok", country: str = "Thailand"):
    vb = ensure_verified_date(base_date, timezone or "Asia/Bangkok")
    if not vb.get("verified", False):
        raise HTTPException(status_code=400, detail="ไม่สามารถยืนยันวันเกิดได้")
    if target_date:
        vt = ensure_verified_date(target_date, timezone or "Asia/Bangkok")
        if not vt.get("verified", False):
            raise HTTPException(status_code=400, detail="ไม่สามารถยืนยันวันจรได้")

    bp = parse_ddmmyyyy_th(base_date)
    bd = bp["date_obj"]
    td = parse_ddmmyyyy_th(target_date)["date_obj"] if target_date else datetime.now(zoneinfo.ZoneInfo(timezone)).date()

    tz_str = timezone or detect_timezone_by_country(country)
    zodiac = detect_zodiac_system(lat, lon, tz_str, country)

    natal = astro_chart.compute_chart(bd, base_time, tz_str, lat, lon, zodiac)
    transit = astro_chart.compute_chart(td, "12:00", tz_str, lat, lon, zodiac)

    interactions = []
    for p_name, nval in natal.items():
        if p_name in transit:
            diff = abs(nval["lon"] - transit[p_name]["lon"])
            diff = diff if diff <= 180 else 360 - diff
            if diff <= 10:
                interactions.append(f"{p_name}: ดาวจรทับดาวเดิม (แรง)")
            elif 170 <= diff <= 190:
                interactions.append(f"{p_name}: ดาวจรเล็งดาวเดิม (กดดัน)")

    result = {
        "system": zodiac,
        "natal_date": base_date,
        "target_date": td.strftime("%d/%m/%Y"),
        "natal": natal,
        "transit": transit,
        "analysis": interactions
    }
    result.update(vb)
    return result

# ------------------------------
# 16) /api/astro-match
# ------------------------------
@app.get("/api/astro-match")
def get_astro_match(date1: str, time1: str, lat1: float, lon1: float,
                    date2: str, time2: str, lat2: float, lon2: float,
                    timezone: str = "Asia/Bangkok", country: str = "Thailand"):
    v1 = ensure_verified_date(date1, timezone or "Asia/Bangkok")
    v2 = ensure_verified_date(date2, timezone or "Asia/Bangkok")
    if not (v1.get("verified") and v2.get("verified")):
        raise HTTPException(status_code=400, detail="ไม่สามารถยืนยันวันใดวันหนึ่งได้")

    d1 = parse_ddmmyyyy_th(date1)["date_obj"]
    d2 = parse_ddmmyyyy_th(date2)["date_obj"]
    tz_str = timezone or detect_timezone_by_country(country)

    sys1 = detect_zodiac_system(lat1, lon1, tz_str, country)
    sys2 = detect_zodiac_system(lat2, lon2, tz_str, country)

    c1 = astro_chart.compute_chart(d1, time1, tz_str, lat1, lon1, sys1)
    c2 = astro_chart.compute_chart(d2, time2, tz_str, lat2, lon2, sys2)

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

    result = {
        "person1": {"date": date1, "time": time1, "system": sys1},
        "person2": {"date": date2, "time": time2, "system": sys2},
        "score": min(score, 100),
        "comments": comments
    }
    result.update(v1)
    return result

# ------------------------------
# 17) /openapi.yaml (ถ้ามีไฟล์)
# ------------------------------
@app.get("/openapi.yaml")
def get_openapi_yaml():
    path = os.path.join(os.path.dirname(__file__), "openapi.yaml")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="openapi.yaml not found")
    return FileResponse(path, media_type="text/yaml")

# ------------------------------
# Run local
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("weekday_global:app", host="0.0.0.0", port=8000, reload=True)

