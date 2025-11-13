from fastapi import FastAPI, HTTPException
from pyowletapi.api import OwletAPI
import aiohttp
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

OWLET_REGION = os.getenv("OWLET_REGION")
OWLET_EMAIL = os.getenv("OWLET_EMAIL")
OWLET_PASSWORD = os.getenv("OWLET_PASSWORD")
BABY_NAME = os.getenv("BABY_NAME", "Baby")
BABY_BIRTHDATE = os.getenv("BABY_BIRTHDATE")

@app.get("/")
async def root():
    return {"message": "Owlet Baby API – use /baby for live stats"}

@app.get("/baby")
async def get_baby():
    async with aiohttp.ClientSession() as session:
        try:
            api = OwletAPI(OWLET_REGION, OWLET_EMAIL, OWLET_PASSWORD, session=session)
            await api.authenticate()

            # Find base station
            devices = await api.get_devices()
            base_station_dsn = None
            for item in devices.get("response", []):
                dev = item.get("device", {})
                if "Monitors" in dev.get("product_name", "") or "SS3" in dev.get("model", ""):
                    base_station_dsn = dev["dsn"]
                    break
            if not base_station_dsn:
                raise HTTPException(500, "No base station")

            # Get live stats
            props = await api.get_properties(base_station_dsn)
            stats = props.get("properties", {})

            # Extract stats with multiple key fallbacks
            hr = stats.get("HEART_RATE") or stats.get("heart_rate") or stats.get("hr") or "—"
            o2 = stats.get("OXYGEN_LEVEL") or stats.get("oxygen_level") or stats.get("o2") or "—"
            mov = stats.get("MOVEMENT") or stats.get("movement") or stats.get("mov") or 0
            temp = (
                stats.get("BASE_STATION_TEMP") or stats.get("base_station_temp") or
                stats.get("SKIN_TEMP") or stats.get("skin_temp") or stats.get("temp") or "—"
            )
            battery = stats.get("BATTERY_LEVEL") or stats.get("battery_level") or stats.get("bat") or "—"

            # Convert to numbers
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

            # Smart status
            if hr == "—" and o2 == "—":
                status = "Sock on – no signal"
            else:
                status = "Sleeping" if mov == 0 else "Awake" if mov <= 3 else "Active"

            # AGE: "2 months, 20 days"
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

            # Build message
            lines = [f"**{BABY_NAME}** – Live Dream Sock 3"]
            lines.append(f"• HR: **{hr}** bpm | O₂: **{o2}%** | {status} | Temp: **{temp}°C** | Battery: **{battery}%**")
            if age_str:
                lines.append(f"• Age: **{age_str}**")

            message = " | ".join(lines)
            return {"message": message}

        except Exception as e:
            raise HTTPException(500, f"Owlet error: {str(e)}")
