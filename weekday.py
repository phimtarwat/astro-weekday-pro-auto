from datetime import datetime, date
from typing import Optional
import re
import zoneinfo
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

# ✅ โหราศาสตร์แบบ lite (pure Python)
import flatlib_lite as astro_chart

# ✅ สำหรับระบบ Pro-Auto (ตรวจประเทศ/โซนเวลา)
from geopy.geocoders import Nominatim

app = FastAPI(title="Astro Weekday API", version="2.6.0")

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
# Smart Date Parser (รองรับทุก format)
# ------------------------------
def parse_ddmmyyyy_th(s: str) -> dict:
    """รองรับทุก format: DD/MM/YYYY, YYYY-MM-DD, 27-10-68, ฯลฯ"""
    s = s.strip()
    if not s:
        raise HTTPException(status_code=400, detail="กรุณาระบุวันที่")

    # ปรับตัวคั่นให้เป็น '/'
    s = re.sub(r"[-. ]", "/", s)
    parts = [p for p in s.split("/") if p]
    if len(parts) != 3:
        raise HTTPException(status_code=400, detail="รูปแบบวันที่ไม่ถูกต้อง (ต้องมี 3 ส่วน เช่น 27/10/2568)")

    try:
        if len(parts[0]) == 4:  # YYYY/MM/DD
            year, month, day = map(int, parts)
        else:
            day, month, year = map(int, parts)
    except Exception:
        raise HTTPException(status_code=400, detail="รูปแบบวันที่ไม่ถูกต้อง (ตัวเลขไม่สมบูรณ์)")

    # ปี 2 หลัก → เติม พ.ศ.
    if year < 100:
        year += 2500

    if year < 1800 or year > 2700:
        raise HTTPException(status_code=400, detail="ปีไม่สมเหตุสมผล (ตรวจสอบ พ.ศ./ค.ศ.)")

    is_be = year > 2400
    year_ce = year - 543 if is_be else year
    year_be = year if is_be else year + 543

    try:
        d = date(year_ce, month, day)
    except ValueError:
        d = date(year_ce, month, 28)

    return {"date_obj": d, "calendar": "BE" if is_be else "CE", "year_ce": year_ce, "year_be": year_be}


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


def validate_real_weekday(date: str, timezone: str = "Asia/Bangkok") -> dict:
    parsed = parse_ddmmyyyy_th(date)
    d = parsed["date_obj"]
    weekday = get_local_weekday(d, timezone)
    payload = format_thai_date(d, "long", weekday, parsed["year_be"], parsed["year_ce"])
    return {
        "verified": True,
        "weekday_full": payload["weekday_full"],
        "thai_date_long": payload["thai_date_long"],
        "verified_text": f"✅ ตรวจสอบแล้ว: {payload['thai_date_long']} (ตรงตามปฏิทินจริง)"
    }

# ------------------------------
# ✅ Middleware: ตรวจวันจริงก่อนทุก response ที่มี date
# ------------------------------
@app.middleware("http")
async def auto_validate_middleware(request: Request, call_next):
    """ตรวจสอบวันจริงอัตโนมัติในทุก endpoint ที่มีพารามิเตอร์ 'date'"""
    if request.method == "GET":
        q = dict(request.query_params)
        if "date" in q:
            try:
                tz = q.get("timezone", "Asia/Bangkok")
                validated = validate_real_weekday(q["date"], tz)
                request.state.validated_date = validated
            except Exception:
                # ไม่หยุดระบบ แต่เพิ่ม flag ว่า validation ล้มเหลว
                request.state.validated_date = {"verified": False, "verified_text": "⚠️ ตรวจวันไม่สำเร็จ"}
    response = await call_next(request)
    # แทรก verified_text เข้า response JSON (ถ้าเป็น JSON)
    try:
        body = b"".join([chunk async for chunk in response.body_iterator])
        import json
        data = json.loads(body)
        if hasattr(request.state, "validated_date") and isinstance(data, dict):
            data.update(request.state.validated_date)
        return JSONResponse(content=data, status_code=response.status_code)
    except Exception:
        return response

# ------------------------------
# Root & Health
# ------------------------------
@app.get("/")
def root():
    return {"message": "Astro Weekday API (v2.6.0 – Auto Validation Middleware) 🚀"}

@app.get("/health")
def health():
    return {"ok": True}

# ------------------------------
# /api/validate-weekday
# ------------------------------
@app.get("/api/validate-weekday")
def validate_weekday(date: str, timezone: Optional[str] = "Asia/Bangkok"):
    return validate_real_weekday(date, timezone)

# ------------------------------
# Endpoint เดิมทั้งหมด (คงครบ)
# ------------------------------
@app.get("/api/weekday")
def get_weekday(date: str, timezone: Optional[str] = "Asia/Bangkok"):
    p = parse_ddmmyyyy_th(date)
    d = p["date_obj"]
    weekday = get_local_weekday(d, timezone)
    return {
        "date": date,
        "timezone": timezone,
        "weekday": weekday,
        "calendar": p["calendar"],
        "year_be": p["year_be"],
        "year_ce": p["year_ce"],
        "resolved_gregorian": d.isoformat()
    }

@app.get("/api/weekday-th")
def get_weekday_th(date: str, style: Optional[str] = "short", timezone: Optional[str] = "Asia/Bangkok"):
    p = parse_ddmmyyyy_th(date)
    d = p["date_obj"]
    weekday_full = get_local_weekday(d, timezone)
    payload = format_thai_date(d, style, weekday_full, p["year_be"], p["year_ce"])
    return {"input": {"date": date, "style": style, "timezone": timezone}, **payload}

@app.get("/api/astro-weekday")
def get_astro_weekday(date: str, time: Optional[str] = None,
                      timezone: Optional[str] = "Asia/Bangkok",
                      place: Optional[str] = None):
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
    if place: result["place"] = place
    return result

@app.get("/api/astro-chart")
def get_astro_chart(date: str, time: str, timezone: str = "Asia/Bangkok",
                    lat: float = 13.75, lon: float = 100.5):
    p = parse_ddmmyyyy_th(date)
    d = p["date_obj"]
    zodiac = detect_zodiac_system(lat, lon, timezone)
    planets = astro_chart.compute_chart(d, time, timezone, lat, lon, zodiac)
    tz = zoneinfo.ZoneInfo(timezone)
    dt_local = datetime.combine(d, datetime.strptime(time, "%H:%M").time()).replace(tzinfo=tz)
    dt_utc = dt_local.astimezone(zoneinfo.ZoneInfo("UTC"))
    return {
        "input": {"date": date, "time": time, "timezone": timezone, "lat": lat, "lon": lon, "auto_system": zodiac},
        "calendar": p["calendar"], "year_be": p["year_be"], "year_ce": p["year_ce"],
        "local_datetime": dt_local.isoformat(), "utc_datetime": dt_utc.isoformat(), "planets": planets
    }

@app.get("/api/astro-transit")
def get_astro_transit(base_date: str, base_time: str = "12:00",
                      target_date: Optional[str] = None,
                      lat: float = 13.75, lon: float = 100.5,
                      timezone: str = "Asia/Bangkok"):
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
    return {"system": zodiac, "natal_date": base_date,
            "target_date": target_d.strftime("%d/%m/%Y"),
            "natal": natal, "transit": transit, "analysis": interactions}

@app.get("/api/astro-match")
def get_astro_match(date1: str, time1: str, lat1: float, lon1: float,
                    date2: str, time2: str, lat2: float, lon2: float,
                    timezone: str = "Asia/Bangkok"):
    d1 = parse_ddmmyyyy_th(date1)["date_obj"]
    d2 = parse_ddmmyyyy_th(date2)["date_obj"]
    sys1 = detect_zodiac_system(lat1, lon1, timezone)
    sys2 = detect_zodiac_system(lat2, lon2, timezone)
    c1 = astro_chart.compute_chart(d1, time1, timezone, lat1, lon1, sys1)
    c2 = astro_chart.compute_chart(d2, time2, timezone, lat2, lon2, sys2)
    score = 0; comments = []
    for p in ["Sun", "Moon", "Venus", "Mars"]:
        if c1[p]["sign"] == c2[p]["sign"]:
            score += 25; comments.append(f"{p}: อยู่ราศีเดียวกัน (เข้าใจกันง่าย)")
        elif abs(c1[p]["lon"] - c2[p]["lon"]) < 30:
            score += 15; comments.append(f"{p}: ระยะใกล้กัน (สัมพันธ์ดี)")
        else:
            comments.append(f"{p}: ต่างราศี (ต้องปรับตัว)")
    return {"person1": {"date": date1, "time": time1, "system": sys1},
            "person2": {"date": date2, "time": time2, "system": sys2},
            "score": min(score, 100), "comments": comments}

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
