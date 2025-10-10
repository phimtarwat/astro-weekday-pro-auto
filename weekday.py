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

# ------------------------------
# 🪐 Transit: ดาวจรประจำวัน
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
    """
    แสดงตำแหน่งดาวจรเทียบกับพื้นดวง
    - base_date = วันเกิด
    - target_date = วันที่ต้องการดูดาวจร (ไม่ใส่ = วันนี้)
    """
    base_d, _ = parse_ddmmyyyy_th(base_date)
    zodiac_system = detect_zodiac_system(lat, lon)

    # วันที่เป้าหมาย (default = วันนี้)
    if target_date:
        target_d, _ = parse_ddmmyyyy_th(target_date)
    else:
        target_d = datetime.utcnow()

    # ดาวพื้นดวง
    natal = astro_chart.compute_chart(base_d, base_time, timezone, lat, lon, zodiac_system)
    # ดาวจร
    transit = astro_chart.compute_chart(target_d, "12:00", timezone, lat, lon, zodiac_system)

    # วิเคราะห์เบื้องต้น
    interactions = []
    for p in natal:
        if p in transit:
            diff = abs(natal[p]["lon"] - transit[p]["lon"])
            if diff < 10 or diff > 350:
                interactions.append(f"{p}: ดาวจรทับดาวเดิม")
            elif 170 < diff < 190:
                interactions.append(f"{p}: ดาวจรเล็งดาวเดิม")

    return {
        "system": zodiac_system,
        "natal_date": base_date,
        "target_date": target_d.strftime("%d/%m/%Y"),
        "natal": natal,
        "transit": transit,
        "analysis": interactions
    }


# ------------------------------
# 💞 Match: เปรียบเทียบดวงคู่
# ------------------------------
@app.get("/api/astro-match")
def get_astro_match(
    date1: str, time1: str, lat1: float, lon1: float,
    date2: str, time2: str, lat2: float, lon2: float,
    timezone: str = "Asia/Bangkok"
):
    """
    วิเคราะห์ดวงคู่แบบง่าย ๆ
    - ดูว่าดาวของแต่ละคนสัมพันธ์กันอย่างไร
    """
    d1, _ = parse_ddmmyyyy_th(date1)
    d2, _ = parse_ddmmyyyy_th(date2)

    zodiac_system1 = detect_zodiac_system(lat1, lon1)
    zodiac_system2 = detect_zodiac_system(lat2, lon2)

    chart1 = astro_chart.compute_chart(d1, time1, timezone, lat1, lon1, zodiac_system1)
    chart2 = astro_chart.compute_chart(d2, time2, timezone, lat2, lon2, zodiac_system2)

    # วิเคราะห์ความสัมพันธ์ (ดูราศีดาวสำคัญ)
    score = 0
    comments = []
    key_planets = ["Sun", "Moon", "Venus", "Mars"]
    for p in key_planets:
        if chart1[p]["sign"] == chart2[p]["sign"]:
            score += 25
            comments.append(f"{p}: อยู่ราศีเดียวกัน (เข้าใจกันง่าย)")
        elif abs(chart1[p]["lon"] - chart2[p]["lon"]) < 30:
            score += 15
            comments.append(f"{p}: ดาวใกล้กัน (สัมพันธ์ดี)")
        else:
            comments.append(f"{p}: ดาวอยู่ต่างราศี (อาจต้องปรับตัว)")

    return {
        "person1": {"date": date1, "time": time1, "system": zodiac_system1},
        "person2": {"date": date2, "time": time2, "system": zodiac_system2},
        "score": min(score, 100),
        "comments": comments
    }

