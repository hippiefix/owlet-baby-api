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
            print("=== /baby called ===")
            print(f"Region: {OWLET_REGION}, Email: {OWLET_EMAIL[:10]}...")  # Debug (partial email)

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
                print("No DSN found!")  # Debug
                raise HTTPException(500, "No Owlet base station found")

            print("Fetching live stats...")
            props = await api.get_properties(base_station_dsn)
            stats = props.get("properties", {})
            print(f"RAW STATS: {stats}")  # DEBUG: See exact keys/values

            # Safe conversion with debug
            hr_raw = stats.get("HEART_RATE", "—")
            print(f"HR raw: '{hr_raw}' (type: {type(hr_raw)})")  # Debug
            try:
                hr = int(hr_raw) if hr_raw != "—" else "—"
            except (ValueError, TypeError):
                hr = hr_raw

            o2_raw = stats.get("OXYGEN_LEVEL", "—")
            print(f"O2 raw: '{o2_raw}' (type: {type(o2_raw)})")  # Debug
            try:
                o2 = int(o2_raw) if o2_raw != "—" else "—"
            except (ValueError, TypeError):
                o2 = o2_raw

            mov_raw = stats.get("MOVEMENT", "—")
            print(f"MOV raw: '{mov_raw}' (type: {type(mov_raw)})")  # Debug
            try:
                mov = int(mov_raw) if mov_raw != "—" else 0
            except (ValueError, TypeError):
                mov = 0

            temp_raw = stats.get("BASE_STATION_TEMP", stats.get("SKIN_TEMP", "—"))
            print(f"Temp raw: '{temp_raw}' (type: {type(temp_raw)})")  # Debug
            try:
                temp = float(temp_raw) if temp_raw != "—" else "—"
            except (ValueError, TypeError):
                temp = temp_raw

            battery_raw = stats.get("BATTERY_LEVEL", "—")
            print(f"Battery raw: '{battery_raw}' (type: {type(battery_raw)})")  # Debug
            try:
                battery = int(battery_raw) if battery_raw != "—" else "—"
            except (ValueError, TypeError):
                battery = battery_raw

            print(f"Converted - HR: {hr} (type: {type(hr)}), MOV: {mov} (type: {type(mov)})")  # Debug

            # Now safe to compare
            status = "Sleeping" if mov == 0 else "Awake" if mov <= 3 else "Active"
            print(f"Status calculated: {status}")  # Debug

            lines = [f"**{BABY_NAME}** – Live Dream Sock 3"]
            lines.append(f"• HR: **{hr}** bpm | O₂: **{o2}%** | {status} | Temp: **{temp}°C** | Battery: **{battery}%**")

            if BABY_BIRTHDATE:
                try:
                    birth = datetime.strptime(BABY_BIRTHDATE, "%m/%d/%y")
                    age_days = (datetime.now() - birth).days
                    print(f"Age calculated: {age_days} days")  # Debug
                    lines.append(f"• Age: **{age_days} days old**")
                except Exception as age_err:
                    print(f"Age error: {age_err}")  # Debug
                    pass

            message = " | ".join(lines)
            print(f"SUCCESS: {message}")
            print("=== /baby done ===")
            return {"message": message}

        except Exception as e:
            print(f"FULL ERROR: {type(e).__name__}: {str(e)}")  # Debug: Full error
            print(f"Traceback: {e}")  # More debug
            raise HTTPException(500, f"Owlet error: {str(e)}")
