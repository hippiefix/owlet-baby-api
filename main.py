from fastapi import FastAPI, HTTPException
from pyowletapi.api import OwletAPI
import aiohttp
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

# Config
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
    # Create fresh session every time
    async with aiohttp.ClientSession() as session:
        try:
            print("Logging into Owlet...")
            api = OwletAPI(OWLET_REGION, OWLET_EMAIL, OWLET_PASSWORD, session=session)
            await api.authenticate()
            print("Login successful")

            print("Fetching devices...")
            devices = await api.get_devices()
            base_station_dsn = None
            for item in devices.get("response", []):
                dev = item.get("device", {})
                if "Monitors" in dev.get("product_name", "") or "SS3" in dev.get("model", ""):
                    base_station_dsn = dev["dsn"]
                    print(f"Found base station: {base_station_dsn}")
                    break

            if not base_station_dsn:
                raise HTTPException(500, "No Owlet base station found")

            print("Fetching live stats...")
            props = await api.get_properties(base_station_dsn)
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

            message = " | ".join(lines)
            print(f"Success: {message}")
            return {"message": message}

        except Exception as e:
            print(f"Owlet error: {e}")
            raise HTTPException(500, f"Owlet error: {str(e)}")
