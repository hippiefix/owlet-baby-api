from fastapi import FastAPI, HTTPException
from pyowletapi.api import OwletAPI
from pyowletapi.sock import Sock
import aiohttp
import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# === CONFIG ===
OWLET_REGION = os.getenv("OWLET_REGION", "us")
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
            # === 1. LOGIN ===
            api = OwletAPI(OWLET_REGION, OWLET_EMAIL, OWLET_PASSWORD, session=session)
            await api.authenticate()

            # === 2. FIND DREAM SOCK 3 (base station) ===
            devices = await api.get_devices()
            sock_device = None
            for item in devices.get("response", []):
                dev = item.get("device", {})
                if "Monitors" in dev.get("product_name", "") or "SS3" in dev.get("model", ""):
                    sock_device = dev
                    break
            if not sock_device:
                raise HTTPException(500, "No Dream Sock 3 found")

            # === 3. USE Sock CLASS + 3X RETRY FOR LIVE DATA ===
            sock = Sock(api, sock_device)
            stats = {}

            for attempt in range(3):
                props = await sock.update_properties()
                raw_props = props.get("properties", {})
                print("Raw Owlet properties:", raw_props)   # <-- DEBUG LOG

                # Dream Sock 3 uses these exact keys:
                hr = raw_props.get("HEART_RATE")
                o2 = raw_props.get("OXYGEN_SATURATION")
                mov = raw_props.get("MOVEMENT", 0)

                if hr is not None or o2 is not None:
                    stats = raw_props
                    break

                if attempt < 2:
                    await asyncio.sleep(5)

            # === 4. EXTRACT VALUES (fallback to "—" only if truly missing) ===
            hr_val = int(stats.get("HEART_RATE")) if stats.get("HEART_RATE") is not None else "—"
            o2_val = int(stats.get("OXYGEN_SATURATION")) if stats.get("OXYGEN_SATURATION") is not None else "—"
            mov_val = int(stats.get("MOVEMENT", 0))

            # === 5. SMART STATUS ===
            if hr_val == "—" and o2_val == "—":
                status = "Sock on – no signal"
            else:
                if mov_val == 0:
                    status = "Sleeping"
                elif mov_val <= 3:
                    status = "Awake"
                else:
                    status = "Active"

            # === 6. AGE CALCULATION ===
            age_str = ""
            if BABY_BIRTHDATE:
                try:
                    birth = datetime.strptime(BABY_BIRTHDATE, "%m/%d/%y")
                    delta = datetime.now() - birth
                    total_days = delta.days
                    months = total_days // 30
                    days = total_days % 30
                    age_str = f"{months} month{'' if months == 1 else 's'}, {days} day{'' if days == 1 else 's'} old"
                except Exception:
                    age_str = "Age error"

            # === 7. BUILD FINAL MESSAGE (NO TEMP, NO BATTERY) ===
            lines = [
                f"**{BABY_NAME}** – Live Dream Sock 3",
                f"• HR: **{hr_val}** bpm | O₂: **{o2_val}%** | {status}",
            ]
            if age_str:
                lines.append(f"• Age: **{age_str}**")

            message = " | ".join(lines)

            return {"message": message}

        except Exception as e:
            print("Owlet error:", e)  # <-- DEBUG LOG
            raise HTTPException(500, f"Owlet error: {str(e)}")
