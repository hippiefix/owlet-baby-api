from fastapi import FastAPI, HTTPException
from starlette.responses import PlainTextResponse
from pyowletapi.api import OwletAPI
from pyowletapi.sock import Sock
import aiohttp
import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv
from dateutil.relativedelta import relativedelta
from zoneinfo import ZoneInfo

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

    # 0. CALCULATE AGE (PACIFIC TIME)
    age_str = "Age unavailable"
    if BABY_BIRTHDATE:
        try:
            pacific = ZoneInfo("America/Los_Angeles")

            # Parse birthdate and attach PT timezone
            birth = datetime.strptime(BABY_BIRTHDATE, "%m/%d/%y")
            birth = birth.replace(tzinfo=pacific)

            # Now in Pacific time
            now = datetime.now(pacific)

            rd = relativedelta(now, birth)
            total_months = rd.years * 12 + rd.months

            age_str = (
                f"{total_months} month{'s' if total_months != 1 else ''}, "
                f"{rd.days} day{'s' if rd.days != 1 else ''} old"
            )
        except Exception as e:
            print("Age parse error:", e)
            age_str = "Age error"

    async with aiohttp.ClientSession() as session:
        try:
            # 1. LOGIN
            api = OwletAPI(OWLET_REGION, OWLET_EMAIL, OWLET_PASSWORD, session=session)
            await api.authenticate()

            # 2. FIND DREAM SOCK 3
            devices = await api.get_devices()
            sock_device = None
            for item in devices.get("response", []):
                dev = item.get("device", {})
                if "Monitors" in dev.get("product_name", "") or "SS3" in dev.get("model", ""):
                    sock_device = dev
                    break

            if not sock_device:
                return PlainTextResponse(f"👶 Baby {BABY_NAME} is {age_str}")

            # 3. FETCH LIVE DATA WITH RETRY
            sock = Sock(api, sock_device)
            raw = {}
            for attempt in range(3):
                props = await sock.update_properties()
                raw = props.get("properties", {})
                print("Raw properties (attempt", attempt + 1, "):", raw)

                if raw.get("heart_rate") is not None or raw.get("oxygen_saturation") is not None:
                    break

                if attempt < 2:
                    await asyncio.sleep(10)

            # 4. CHECK IF SOCK IS OFF
            hr = raw.get("heart_rate")
            o2 = raw.get("oxygen_saturation")
            sock_off = raw.get("sock_off")

            if (hr == 0 and o2 == 0) or sock_off == 1:
                print("Sock detected as OFF – showing name + age only")
                return PlainTextResponse(f"👶 Baby {BABY_NAME} is {age_str}")

            # 5. VALUES
            sleep_state_code = raw.get("sleep_state")
            mov = raw.get("movement", 0)

            hr_val = int(hr) if hr is not None else "—"
            o2_val = int(o2) if o2 is not None else "—"
            mov_val = int(mov)

            # 6. IMPROVED SLEEP LOGIC (Option 3)
            # If movement is above 2, force awake
            if mov_val > 2:
                status = "Awake"
                sleep_emoji = "👁️"
            else:
                # movement <= 2 → fall back to Owlet sleep_state
                if sleep_state_code == 0:
                    status = "Awake"
                    sleep_emoji = "👁️"
                else:
                    status = "Sleeping"
                    sleep_emoji = "😴"

            # EXTREME OVERRIDE
            if mov_val > 25 or hr_val > 150:
                status = "Awake"
                sleep_emoji = "👁️"

            # 7. FINAL MESSAGE
            message = (
                f"👶 Baby {BABY_NAME} is {age_str} "
                f"❤️ Heart: {hr_val} BPM "
                f"🫁 Oxygen: {o2_val}% "
                f"{sleep_emoji} {status}"
            )

            return PlainTextResponse(message)

        except Exception as e:
            print("Owlet error:", e)
            return PlainTextResponse(f"👶 Baby {BABY_NAME} is {age_str}")


# Helper (kept for future expansion)
def _fallback_sleep_status(mov_val):
    if mov_val <= 5:
        return "Sleeping", "😴"
    else:
        return "Awake", "👁️"
