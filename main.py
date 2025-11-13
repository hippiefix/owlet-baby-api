from fastapi import FastAPI, HTTPException
from pyowletapi.api import OwletAPI
from pyowletapi.sock import Sock  # <-- Better live data
import aiohttp
import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

# === CONFIG ===
OWLET_REGION = os.getenv("OWLET_REGION", "us")  # Try 'us' if 'world' fails
OWLET_EMAIL = os.getenv("OWLET_EMAIL")
OWLET_PASSWORD = os.getenv("OWLET_PASSWORD")
BABY_NAME = os.getenv("BABY_NAME", "Baby")
BABY_BIRTHDATE = os.getenv("BABY_BIRTHDATE")  # MM/DD/YY

@app.get("/")
async def root():
    return {"message": "Owlet Baby API – use /baby for live stats"}

@app.get("/baby")
async def get_baby():
    async with aiohttp.ClientSession() as session:
        try:
            # === LOGIN ===
            api = OwletAPI(OWLET_REGION, OWLET_EMAIL, OWLET_PASSWORD, session=session)
            await api.authenticate()

            # === FIND BASE STATION ===
            devices = await api.get_devices()
            base_station_dsn = None
            sock_device = None
            for item in devices.get("response", []):
                dev = item.get("device", {})
                if "Monitors" in dev.get("product_name", "") or "SS3" in dev.get("model", ""):
                    base_station_dsn = dev["dsn"]
                    sock_device = dev
                    break
            if not base_station_dsn:
                raise HTTPException(500, "No Owlet base station found")

            # === USE SOCK CLASS + 3X RETRY FOR LIVE DATA ===
            sock = Sock(api, sock_device)
            stats = {}
            for attempt in range(3):
                props = await sock.update_properties()
                stats = props.get("properties", {})
                if stats.get("HEART_RATE") or stats.get("OXYGEN_LEVEL"):
                    break  # Got live data!
                if attempt < 2:
                    await asyncio.sleep(5)  # Wait 5 sec

            # === EXTRACT STATS (WITH ALL KEY VARIATIONS) ===
            hr = (
                stats.get("HEART_RATE") or stats.get("heart_rate") or
                stats.get("hr") or stats.get("HR") or "—"
            )
            o2 = (
                stats.get("OXYGEN_LEVEL") or stats.get("oxygen_level") or
                stats.get("o2") or stats.get("O2") or "—"
            )
            mov = (
                stats.get("MOVEMENT") or stats.get("movement") or
                stats.get("mov") or stats.get("MOV") or 0
            )
            temp = (
                stats.get("BASE_STATION_TEMP") or stats.get("base_station_temp") or
                stats.get("SKIN_TEMP") or stats.get("skin_temp") or
                stats.get("temp") or stats.get("TEMP") or "—"
            )
            battery = (
                stats.get("BATTERY_LEVEL") or stats.get("battery_level") or
                stats.get("bat") or stats.get("BAT") or "—"
            )

            # === CONVERT TO NUMBERS ===
            try: hr = int(hr) if hr != "—" else "—"
            except: hr = "—"
            try: o2 = int(o2) if o2 != "—" else "—"
            except: o2 = "—"
            try: mov = int(mov)
            except: mov = 0
            try: temp = round(float(temp), 1) if temp != "—" else "—"
            except: temp = "—"
            try: battery = int(battery) if battery != "—" else "—"
            except: battery = "—"

            # === SMART STATUS ===
            if hr == "—" and o2 == "—":
                status = "Sock on – no signal"
            else:
                status = "Sleeping" if mov == 0 else "Awake" if mov <= 3 else "Active"

            # === AGE: "2 months, 21 days old" ===
            age_str = ""
            if BABY_BIRTHDATE:
                try:
                    birth = datetime.strptime(BABY_BIRTHDATE, "%m/%d/%y")
                    delta = datetime.now() - birth
                    total_days = delta.days
                    months = total_days // 30
                    days = total_days % 30
                    if months > 0:
                        age_str = f"{months} month{'' if months == 1 else 's'}, {days} day{'' if days == 1 else 's'} old"
                    else:
                        age_str = f"{days} day{'' if days == 1 else 's'} old"
                except:
                    age_str = "Age error"

            # === BUILD MESSAGE ===
            lines = [f"**{BABY_NAME}** – Live Dream Sock 3"]
            lines.append(f"• HR: **{hr}** bpm | O₂: **{o2}%** | {status} | Temp: **{temp}°C** | Battery: **{battery}%**")
            if age_str:
                lines.append(f"• Age: **{age_str}**")

            message = " | ".join(lines)
            return {"message": message}

        except Exception as e:
            raise HTTPException(500, f"Owlet error: {str(e)}")
