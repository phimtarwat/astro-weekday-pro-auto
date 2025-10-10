from datetime import datetime, date
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
import zoneinfo

# 🌟 สำหรับโหราศาสตร์แบบจำลอง (ไม่ใช้ swisseph)
from flatlib_lite import get_chart

app = FastAPI()

DAYS_TH = ["จันทร์","อังคาร","พุธ","พฤหัสบดี","ศุกร์","เสาร์","อาทิตย์"]
MONTHS_TH_LONG = [
    "มกราคม","กุมภาพันธ์","มีนาคม","เมษายน","พฤษภาคม","มิถุนายน",
    "กรกฎาคม","สิงหาคม","กันยายน","ตุลาคม","พฤศจิกายน","ธันวาคม"
]
MONTHS_TH_SHORT = [
    "ม.ค.","ก.พ.","มี.ค.","เม.ย.","พ.ค.","มิ.ย.",
    "ก.ค.","ส.ค.","ก.ย.","ต.ค.","พ.ย.","ธ.ค."
]

# ------------------------------
# ฟังก์ชัน: แปลง พ.ศ. / ค.ศ.
# ------------------------------
def parse_ddmmyyyy_th(s: str) -> tuple[date, str]:
    s = s.strip()
    try:
        d = datetime.strptime(s, "%d/%m/%Y").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="รูปแบบวันที่ไม่ถูกต้อง (ต้องเป็น DD/MM/YYYY)")
    calendar = "BE" if d.year >= 2400 else "CE"
    if calendar == "BE":
        d = d.replace(year=d.year - 543)
    return d, calendar


# ------------------------------
# ✅ /api/weekday
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
# ✅ /api/weekday-th  (ใหม่)
# ------------------------------
@app.get("/api/weekday-th")
def get_weekday_th(date: str, style: Optional[str] = "short"):
    d, cal = parse_ddmmyyyy_th(date)
    wd = DAYS_TH[d.weekday()]
    wd_compact = "พฤหัส" if wd == "พฤหัสบดี" else wd
    y_be = d.year + 543
    m_idx = d.month - 1
    m_short = MONTHS_TH_SHORT[m_idx]
    m_long = MONTHS_TH_LONG[m_idx]
    thai_short = f"วัน{wd}ที่ {d.day} {m_short} {y_be}"
    thai_long = f"วัน{wd}ที่ {d.day} {m_long} {y_be}"
    return {
        "input": {"date": date, "style": style},
        "weekday_full": wd,
        "weekday_compact": wd_compact,
        "thai_date": thai_long if style == "long" else thai_short,
        "resolved_gregorian": d.isoformat(),
        "calendar": cal
    }


# ------------------------------
# ✅ /api/astro-chart
# ------------------------------
@app.get("/api/astro-chart")
def get_astro_chart(date: str, time: str, timezone: str = "Asia/Bangkok",
                    lat: float = 13.75, lon: float = 100.5):
    d, cal = parse_ddmmyyyy_th(date)
    tz = zoneinfo.ZoneInfo(timezone)
    dt = datetime.combine(d, datetime.strptime(time, "%H:%M").time())
    dt = dt.replace(tzinfo=tz)
    utc_dt = dt.astimezone(zoneinfo.ZoneInfo("UTC"))

    chart_data = get_chart(date, time, lat, lon)

    return {
        "input": {
            "date": date, "time": time, "timezone": timezone,
            "lat": lat, "lon": lon
        },
        "resolved_gregorian": d.isoformat(),
        "utc_datetime": utc_dt.isoformat(),
        "planets": chart_data
    }
