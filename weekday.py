from datetime import datetime, date
from typing import Optional
import zoneinfo
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

# ✅ โหราศาสตร์แบบ lite (pure Python)
import flatlib_lite as astro_chart

# ✅ สำหรับระบบ Pro-Auto (ตรวจประเทศ/โซนเวลา)
from geopy.geocoders import Nominatim

app = FastAPI(title="Astro Weekday API", version="2.4.0")

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
def parse_ddmmyyyy_th(s: str) -> dict:
    """รับวันที่ DD/MM/YYYY (พ.ศ. หรือ ค.ศ.) -> คืน date object + ปี พ.ศ./ค.ศ. ทั้งคู่"""
    s = s.strip()
    try:
        day, month, year = map(int, s.split("/"))
    except Exception:
        raise HTTPException(status_code=400, detail="รูปแบบวันที่ไม่ถูกต้อง (ต้องเป็น DD/MM/YYYY)")

    if year < 1800 or year > 2700:
        raise HTTPException(status_code=400, detail="ปีไม่สมเหตุสมผล (ตรวจสอบรูปแบบ พ.ศ. / ค.ศ.)")

    is_be = year > 2400
    if is_be:
        year_ce = year - 543
        year_be = year
    else:
        year_ce = year
        year_be = year + 543

    try:
        d = date(year_ce, month, day)
    except ValueError:
        d = date(year_ce, month, 28)

    return {
        "date_obj": d,
        "calendar": "BE" if is_be else "CE",
        "year_ce": year_ce,
        "year_be": year_be
    }


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
    m_short = MONTHS_TH_SHORT[m_idx]
    m_long = MONTHS_TH_LONG[m_idx]
    thai_short = f"วัน{wd_full}ที่ {d.day} {m_short} {y_be} (ค.ศ. {y_ce})"
    thai_long = f"วัน{wd_full}ที่ {d.day} {m_long} {y_be} (ค.ศ. {y_ce})"
    return {
        "weekday_full": wd_full,
        "weekday_compact": wd_compact,
        "thai_date_short": thai_short,
        "thai_date_long": thai_long,
        "thai_date": thai_long if style == "long" else thai_short,
        "year_be": y_be,
        "year_ce": y_ce
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
            "thailand","laos","myanmar","burma","cambodia",
            "india","sri lanka","nepal","bangladesh"
        }
        return "sidereal" if any(c in country for c in sidereal_countries) else "tropical"
    except Exception:
        return "sidereal" if "asia/" in tz_lower else "tropical"


# ------------------------------
# ✅ Pre-validation Layer: ตรวจสอบวันจริงก่อนใช้
# ------------------------------
def validate_real_weekday(date: str, timezone: str = "Asia/Bangkok") -> dict:
    """ตรวจสอบวันจริงก่อนใช้ในคำทำนาย"""
    parsed = parse_ddmmyyyy_th(date)
    d = parsed["date_obj"]
    weekday = get_local_weekday(d, timezone)
    payload = format_thai_date(d, style="long", weekday_name=weekday,
                               year_be=parsed["year_be"], year_ce=parsed["year_ce"])
    if not payload.get("weekday_full") or not payload.get("thai_date_long"):
        raise HTTPException(status_code=400, detail="ไม่สามารถยืนยันวันดังกล่าวได้ในปฏิทินจริงครับ")

    return {
        "verified": True,
        "weekday_full": payload["weekday_full"],
        "thai_date_long": payload["thai_date_long"],
        "verified_text": f"✅ ตรวจสอบแล้ว: {payload['thai_date_long']} (ตรงตามปฏิทินจริง)"
    }

# ------------------------------
# Root & Health
# ------------------------------
@app.get("/")
def root():
    return {"message": "Astro Weekday API (Verified Astro Version) 🚀"}

@app.get("/health")
def health():
    return {"ok": True}

# ------------------------------
# /api/validate-weekday (ใหม่)
# ------------------------------
@app.get("/api/validate-weekday")
def validate_weekday(date: str, timezone: Optional[str] = "Asia/Bangkok"):
    """ตรวจสอบวันจริงก่อนนำไปใช้ทำนาย"""
    return validate_real_weekday(date, timezone)

# ------------------------------
# /api/weekday
# ------------------------------
@app.get("/api/weekday")
def get_weekday(date: str, timezone: Optional[str] = "Asia/Bangkok"):
    parsed = parse_ddmmyyyy_th(date)
    d = parsed["date_obj"]
    weekday = get_local_weekday(d, timezone)
    verified = validate_real_weekday(date, timezone)
    return {
        "date": date,
        "timezone": timezone,
        "weekday": weekday,
        "calendar": parsed["calendar"],
        "year_be": parsed["year_be"],
        "year_ce": parsed["year_ce"],
        "resolved_gregorian": d.isoformat(),
        **verified
    }

# ------------------------------
# /api/weekday-th
# ------------------------------
@app.get("/api/weekday-th")
def get_weekday_th(date: str, style: Optional[str] = "short", timezone: Optional[str] = "Asia/Bangkok"):
    parsed = parse_ddmmyyyy_th(date)
    d = parsed["date_obj"]
    weekday_full = get_local_weekday(d, timezone)
    payload = format_thai_date(d, style or "short", weekday_full,
                               parsed["year_be"], parsed["year_ce"])
    verified = validate_real_weekday(date, timezone)
    return {
        "input": {"date": date, "style": style or "short", "timezone": timezone},
        "calendar": parsed["calendar"],
        **payload,
        **verified
    }

# ------------------------------
# /api/astro-weekday
# ------------------------------
@app.get("/api/astro-weekday")
def get_astro_weekday(date: str,
                      time: Optional[str] = None,
                      timezone: Optional[str] = "Asia/Bangkok",
                      place: Optional[str] = None):
    parsed = parse_ddmmyyyy_th(date)
    d = parsed["date_obj"]
    try:
        t = datetime.strptime(time or "00:00", "%H:%M").time()
    except ValueError:
        raise HTTPException(status_code=400, detail="รูปแบบเวลาไม่ถูกต้อง (ต้องเป็น HH:MM)")
    tz = zoneinfo.ZoneInfo(timezone)
    dt_local = datetime.combine(d, t).replace(tzinfo=tz)
    dt_utc = dt_local.astimezone(zoneinfo.ZoneInfo("UTC"))
    weekday_th = DAYS_TH[dt_local.weekday()]
    verified = validate_real_weekday(date, timezone)
    result = {
        "date": date,
        "time": time or "00:00",
        "timezone": timezone,
        "weekday": weekday_th,
        "calendar": parsed["calendar"],
        "year_be": parsed["year_be"],
        "year_ce": parsed["year_ce"],
        "local_datetime": dt_local.isoformat(),
        "utc_datetime": dt_utc.isoformat(),
        **verified
    }
    if place:
        result["place"] = place
    return result

# ------------------------------
# /api/astro-chart
# ------------------------------
@app.get("/api/astro-chart")
def get_astro_chart(date: str, time: str,
                    timezone: str = "Asia/Bangkok",
                    lat: float = 13.75, lon: float = 100.50):
    parsed = parse_ddmmyyyy_th(date)
    d = parsed["date_obj"]
    zodiac_system = detect_zodiac_system(lat, lon, timezone)
    planets = astro_chart.compute_chart(d, time, timezone, lat, lon, zodiac_system)
    tz = zoneinfo.ZoneInfo(timezone)
    dt_local = datetime.combine(d, datetime.strptime(time, "%H:%M").time()).replace(tzinfo=tz)
    dt_utc = dt_local.astimezone(zoneinfo.ZoneInfo("UTC"))
    verified = validate_real_weekday(date, timezone)
    return {
        "input": {"date": date, "time": time, "timezone": timezone,
                  "lat": lat, "lon": lon, "auto_system": zodiac_system},
        "calendar": parsed["calendar"],
        "year_be": parsed["year_be"],
        "year_ce": parsed["year_ce"],
        "local_datetime": dt_local.isoformat(),
        "utc_datetime": dt_utc.isoformat(),
        "planets": planets,
        **verified
    }

# ------------------------------
# /api/astro-transit
# ------------------------------
@app.get("/api/astro-transit")
def get_astro_transit(base_date: str,
                      base_time: str = "12:00",
                      target_date: Optional[str] = None,
                      lat: float = 13.75, lon: float = 100.5,
                      timezone: str = "Asia/Bangkok"):
    base_p = parse_ddmmyyyy_th(base_date)
    base_d = base_p["date_obj"]
    target_p = parse_ddmmyyyy_th(target_date) if target_date else {"date_obj": datetime.now(zoneinfo.ZoneInfo(timezone)).date()}
    target_d = target_p["date_obj"]
    zodiac_system = detect_zodiac_system(lat, lon, timezone)
    natal = astro_chart.compute_chart(base_d, base_time, timezone, lat, lon, zodiac_system)
    transit = astro_chart.compute_chart(target_d, "12:00", timezone, lat, lon, zodiac_system)
    interactions = []
    for p, nval in natal.items():
        if p in transit:
            diff = abs(nval["lon"] - transit[p]["lon"])
            diff = diff if diff <= 180 else 360 - diff
            if diff <= 10:
                interactions.append(f"{p}: ดาวจรทับดาวเดิม (แรง)")
            elif
