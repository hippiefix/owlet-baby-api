from fastapi import FastAPI, HTTPException
from pyowletapi.api import OwletAPI
import aiohttp
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
app = FastAPI()

OWLET_REGION = os.getenv("OWLET_REGION")
OWLET_EMAIL = os.getenv("OWLET_EMAIL")
OWLET_PASSWORD = os.getenv("OWLET_PASSWORD")
BABY_NAME = os.getenv("BABY_NAME", "Baby")
BABY_BIRTHDATE = os.getenv("BABY_BIRTHDATE")

owlet_api = None
base_station_dsn = None

@app.on_event("startup")
async def startup():
    global owlet_api, base_station_dsn
    async with aiohttp.ClientSession() as session:
        owlet_api = OwletAPI(OWLET_REGION, OWLET_EMAIL, OWLET_PASSWORD, session=session)
        try:
            await owlet_api.authenticate()
            print("Owlet login successful")
            devices = await owlet_api.get_devices()
            print(f"Found {len(devices.get('response', []))} devices")
            for item in devices.get("response", []):
                dev = item.get("device", {})
                if "Monitors" in dev.get("product_name", "") or "SS3" in dev.get("model", ""):
                    base_station_dsn = dev["dsn"]
                    print(f"Base station DSN: {base_station_dsn}")
                    break
        except Exception as e:
            print(f"Startup failed: {e}")

@app.get("/")
async def root():
    return {"message": "Owlet Baby API – use /baby for live stats"}

@app.get("/baby")
async def get_baby():
    if not base_station_dsn:
        raise HTTPException(500, "No base station – check Owlet app")

    try:
        props = await owlet_api.get_properties(base_station_dsn)
        stats = props.get("properties", {})

        hr = stats.get("HEART_RATE", "—")
        o2 = stats.get("OXYGEN_LEVEL", "—")
        mov = stats.get("MOVEMENT", "—")
        temp = stats.get("BASE_STATION_TEMP", stats.get("SKIN_TEMP", "—"))
        battery = stats.get("BATTERY_LEVEL", "—")
        status = "Sleeping" if mov == 0 else "Awake" if mov <= 3 else "Active"

        lines = [f"**{BABY_NAME}** – Live Dream Sock 3"]
        lines.append(f"• HR: **{hr}** bpm | O₂: **{o2}%** | {status} | Temp: **{temp}°C** | Battery: **{battery}%**")

        if BABY_BIRTHDATE:
            try:
                birth = datetime.strptime(BABY_BIRTHDATE, "%m/%d/%y")
                age_days = (datetime.now() - birth).days
                lines.append(f"• Age: **{age_days} days old**")
            except:
                pass

        return {"message": " | ".join(lines)}
    except Exception as e:
        raise HTTPException(500, f"Owlet error: {e}")