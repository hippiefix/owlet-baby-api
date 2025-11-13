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
            print("=== OWLET DEBUG START ===")
            api = OwletAPI(OWLET_REGION, OWLET_EMAIL, OWLET_PASSWORD, session=session)
            await api.authenticate()
            print("Authenticated")

            devices = await api.get_devices()
            print(f"Devices response: {devices}")  # FULL RAW

            base_station_dsn = None
            for item in devices.get("response", []):
                dev = item.get("device", {})
                print(f"Device: {dev.get('product_name')} | Model: {dev.get('model')} | DSN: {dev.get('dsn')}")
                if "Monitors" in dev.get("product_name", "") or "SS3" in dev.get("model", ""):
                    base_station_dsn = dev["dsn"]
                    print(f"USING DSN: {base_station_dsn}")
                    break

            if not base_station_dsn:
                raise HTTPException(500, "No base station found")

            props = await api.get_properties(base_station_dsn)
            print(f"FULL PROPERTIES: {props}")  # THIS IS KEY
            stats = props.get("properties", {})

            # Print EVERY key
            print("ALL STAT KEYS:")
            for k, v in stats.items():
                print(f"  {k}: {v} ({type(v)})")

            # Extract with fallbacks
            hr = stats.get("HEART_RATE") or stats.get("heart_rate") or "—"
            o2 = stats.get("OXYGEN_LEVEL") or stats.get("oxygen_level") or "—"
            mov = stats.get("MOVEMENT") or stats.get("movement") or 0
            temp = stats.get("BASE_STATION_TEMP") or stats.get("base_station_temp") or stats.get("SKIN_TEMP") or stats.get("skin_temp") or "—"
            battery = stats.get("BATTERY_LEVEL") or stats.get("battery_level") or "—"

            # Convert
            try: hr = int(hr) if hr != "—" else "—"
            except: hr = "—"
            try: o2 = int(o2) if o2 != "—" else "—"
            except: o2 = "—"
            try: mov = int(mov)
            except: mov = 0
            try: temp = float(temp) if temp != "—" else "—"
            except: temp = "—"
            try: battery = int(battery) if battery != "—" else "—"
            except: battery = "—"

            # Smart status
            if hr == "—" and o2 == "—":
                status = "Sock on but no signal"
            else:
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
            print(f"FINAL OUTPUT: {message}")
            print("=== OWLET DEBUG END ===\n")
            return {"message": message}

        except Exception as e:
            print(f"ERROR: {e}")
            raise HTTPException(500, f"Owlet error: {str(e)}")
