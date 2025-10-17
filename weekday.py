from datetime import datetime, date
from typing import Optional
import re
import zoneinfo
import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

# ✅ โหราศาสตร์แบบ lite (pure Python)
import flatlib_lite as astro_chart

# ✅ สำหรับระบบตรวจประเทศ/โซนเวลา
from geopy.geocoders import Nominatim

app = FastAPI(title="Astro Weekday API", version="2.6.4 (Full Dual Calendar + Fallback)")

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
# ✅ ตรวจสอบวันจริงผ่าน API กลาง (มี Fallback ภายใน)
# ------------------------------
def ensure_verified_date(date_str: str, timezone: str = "Asia/Bangkok") -> dict:
    """พยายามยืนยันวันจริงจาก API กลางก่อน
    ถ้าไม่ได้ (timeout/ไม่รองรับ พ.ศ.) จะใช้ระบบ local verify สำรองที่รองรับทั้ง พ.ศ./ค.ศ.
    """
    try:
        url = "https://astro-weekday-pro-auto.vercel.app/api/validate-weekday"
        resp = requests.get(url, params={"date": date_str, "timezone": timezone}, timeout=5)
        data = resp.json()
        if data.get("verified", False):
            return data
        else:
            raise ValueError("external_verify_fail")
    except Exception:
        # Local fallback (รองรับ พ.ศ./ค.ศ.)
        try:
            p = parse_ddmmyyyy_th(date_str)
            d = p["date_obj"]
            weekday = get_local_weekday(d, timezone)
            thai_long = f"วัน{weekday}ที่ {d.day} {MONTHS_TH_LONG[d.month-1]} {p['year_be']} (ค.ศ. {p['year_ce']})"
            return {
                "verified": True,
                "weekday_full": weekday,
                "thai_date_long": thai_long,
                "verified_text": "✅ ตรวจวันสำเร็จ (Local Fallback)"
            }
        except Exception:
            return {"verified": False, "verified_text": "⚠️ ไม่สามารถยืนยันวันได้"}

# ------------------------------
# Smart Date Parser (รองรับทุก format, ทั้ง พ.ศ. / ค.ศ.)
# ------------------------------
def parse_ddmmyyyy_th(s: str) -> dict:
    s = (s or "").strip()
    if not s:
        raise HTTPException(status_code=400, detail="กรุณาระบุวันที่")
    # ปรับตัวคั่นให้เป็น '/'
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
        # สมมติเป็น พ.ศ. 2 หลัก (เช่น 68 -> 2568)
        year += 2500

    # ช่วงปีที่ยอมรับ: ค.ศ. 1800–2100 หรือ พ.ศ. 2400–2700
    if 1800 <= year <= 2100:
        is_be = False
    elif 2400 <= year <= 2700:
        is_be = True
    else:
        raise HTTPException(status_code=400, detail="ปีไม่สมเหตุสมผล (ตรวจสอบ พ.ศ./ค.ศ.)")

    year_ce = year - 543 if is_be else year
    year_be = year if is_be else year + 543

    # สร้างวันที่ ปรับปลายเดือนให้ไม่ error
    try:
        d = date(year_ce, month, day)
    except ValueError:
        d = date(year_ce, month, 28)

    return {"date_obj": d, "calendar": "BE" if is_be else "CE", "year_ce": year_ce, "year_be": year_be}

# ------------------------------
# Utilities
# ------------------------------
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

def detect_zodiac_system(lat: float, lon: float, timezone: str) -> str:
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
        return "sidereal" if "asia/" in tz_lower else "tropical"

# ------------------------------
# Middleware: ตรวจวันจริงก่อน response ทุก endpoint (กัน loop)
# ------------------------------
@app.middleware("http")
async def auto_validate_middleware(request: Request, call_next):
    if request.method == "GET":
        # กัน recursive validation ของ endpoint ตัวเอง
        if request.url.path == "/api/validate-weekday":
            return await call_next(request)
        q = dict(request.query_params)
        if "date" in q:
            tz = q.get("timezone", "Asia/Bangkok")
            validated = ensure_verified_date(q["date"], tz)
            request.state.validated_date = validated
    response = await call_next(request)
    # แทรก verified_text เข้า response JSON (ถ้าเป็น JSON)
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
# Root & Health
# ------------------------------
@app.get("/")
def root():
    return {"message": "Astro Weekday API (v2.6.4 – Full Dual Calendar + Fallback) 🚀"}

@app.get("/health")
def health():
    return {"ok": True}

# ------------------------------
# /api/validate-weekday
# ------------------------------
@app.get("/api/validate-weekday")
def validate_weekday(date: str, timezone: Optional[str] = "Asia/Bangkok"):
    return ensure_verified_date(date, timezone)

# ------------------------------
# /api/weekday
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
# /api/weekday-th
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
# /api/astro-weekday
# ------------------------------
@app.get("/api/astro-weekday")
def get_astro_weekday(date: str, time: Optional[str] = None,
                      timezone: Optional[str] = "Asia/Bangkok",
                      place: Optional[str] = None):
    verified = ensure_verified_date(date, timezone)
    if not verified.get("verified", False):
        raise HTTPException(status_code=400, detail="ไม่สามารถยืนยันวันได้")
    p = parse_ddmmyyyy_th(date)
    d = p["date_obj"]
    t = datetime.strptime(time or "00:00", "%H:%M").time()
    tz = zoneinfo.ZoneInfo(timezone)
    dt_local = datetime.combine(d, t).replace(tzinfo=tz)
    dt_utc = dt_local.astimezone(zoneinfo.ZoneInfo("UTC"))
    weekday_th = DAYS_TH[dt_local.weekday()]
    result = {
        "date": date, "time": time or "00:00", "timezone": timezone,
        "weekday": weekday_th, "calendar": p["calendar"],
        "year_be": p["year_be"], "year_ce": p["year_ce"],
        "local_datetime": dt_local.isoformat(), "utc_datetime": dt_utc.isoformat()
    }
    if place:
        result["place"] = place
    result.update(verified)
    return result

# ------------------------------
# /api/astro-chart
# ------------------------------
@app.get("/api/astro-chart")
def get_astro_chart(date: str, time: str, timezone: str = "Asia/Bangkok",
                    lat: float = 13.75, lon: float = 100.5):
    verified = ensure_verified_date(date, timezone)
    if not verified.get("verified", False):
        raise HTTPException(status_code=400, detail="ไม่สามารถยืนยันวันได้")
    p = parse_ddmmyyyy_th(date)
    d = p["date_obj"]
    zodiac = detect_zodiac_system(lat, lon, timezone)
    planets = astro_chart.compute_chart(d, time, timezone, lat, lon, zodiac)
    tz = zoneinfo.ZoneInfo(timezone)
    dt_local = datetime.combine(d, datetime.strptime(time, "%H:%M").time()).replace(tzinfo=tz)
    dt_utc = dt_local.astimezone(zoneinfo.ZoneInfo("UTC"))
    result = {
        "input": {"date": date, "time": time, "timezone": timezone, "lat": lat, "lon": lon, "auto_system": zodiac},
        "calendar": p["calendar"], "year_be": p["year_be"], "year_ce": p["year_ce"],
        "local_datetime": dt_local.isoformat(), "utc_datetime": dt_utc.isoformat(), "planets": planets
    }
    result.update(verified)
    return result

# ------------------------------
# /api/astro-transit
# ------------------------------
@app.get("/api/astro-transit")
def get_astro_transit(base_date: str, base_time: str = "12:00",
                      target_date: Optional[str] = None,
                      lat: float = 13.75, lon: float = 100.5,
                      timezone: str = "Asia/Bangkok"):
    verified_base = ensure_verified_date(base_date, timezone)
    if not verified_base.get("verified", False):
        raise HTTPException(status_code=400, detail="ไม่สามารถยืนยันวันเกิดได้")
    if target_date:
        verified_target = ensure_verified_date(target_date, timezone)
        if not verified_target.get("verified", False):
            raise HTTPException(status_code=400, detail="ไม่สามารถยืนยันวันจรได้")
    base_p = parse_ddmmyyyy_th(base_date)
    base_d = base_p["date_obj"]
    target_p = parse_ddmmyyyy_th(target_date) if target_date else {"date_obj": datetime.now(zoneinfo.ZoneInfo(timezone)).date()}
    target_d = target_p["date_obj"]
    zodiac = detect_zodiac_system(lat, lon, timezone)
    natal = astro_chart.compute_chart(base_d, base_time, timezone, lat, lon, zodiac)
    transit = astro_chart.compute_chart(target_d, "12:00", timezone, lat, lon, zodiac)
    interactions = []
    for p, nval in natal.items():
        if p in transit:
            diff = abs(nval["lon"] - transit[p]["lon"])
            diff = diff if diff <= 180 else 360 - diff
            if diff <= 10:
                interactions.append(f"{p}: ดาวจรทับดาวเดิม (แรง)")
            elif 170 <= diff <= 190:
                interactions.append(f"{p}: ดาวจรเล็งดาวเดิม (กดดัน)")
    result = {"system": zodiac, "natal_date": base_date,
              "target_date": target_d.strftime("%d/%m/%Y"),
              "natal": natal, "transit": transit, "analysis": interactions}
    result.update(verified_base)
    return result

# ------------------------------
# /api/astro-match
# ------------------------------
@app.get("/api/astro-match")
def get_astro_match(date1: str, time1: str, lat1: float, lon1: float,
                    date2: str, time2: str, lat2: float, lon2: float,
                    timezone: str = "Asia/Bangkok"):
    verified1 = ensure_verified_date(date1, timezone)
    verified2 = ensure_verified_date(date2, timezone)
    if not (verified1.get("verified") and verified2.get("verified")):
        raise HTTPException(status_code=400, detail="ไม่สามารถยืนยันวันใดวันหนึ่งได้")
    d1 = parse_ddmmyyyy_th(date1)["date_obj"]
    d2 = parse_ddmmyyyy_th(date2)["date_obj"]
    sys1 = detect_zodiac_system(lat1, lon1, timezone)
    sys2 = detect_zodiac_system(lat2, lon2, timezone)
    c1 = astro_chart.compute_chart(d1, time1, timezone, lat1, lon1, sys1)
    c2 = astro_chart.compute_chart(d2, time2, timezone, lat2, lon2, sys2)
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
    result = {"person1": {"date": date1, "time": time1, "system": sys1},
              "person2": {"date": date2, "time": time2, "system": sys2},
              "score": min(score, 100), "comments": comments}
    result.update(verified1)
    return result

# ------------------------------
# /openapi.yaml
# ------------------------------
@app.get("/openapi.yaml")
def get_openapi_yaml():
    import os
    path = os.path.join(os.path.dirname(__file__), "openapi.yaml")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="openapi.yaml not found")
    return FileResponse(path, media_type="text/yaml")

# ------------------------------
# Run local
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("weekday:app", host="0.0.0.0", port=8000, reload=True)
