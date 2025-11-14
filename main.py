from fastapi import FastAPI, HTTPException
from starlette.responses import PlainTextResponse
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
    # 0. CALCULATE AGE (always shown, done early)
    age_str = "Age unavailable"
    if BABY_BIRTHDATE:
        try:
            birth = datetime.strptime(BABY_BIRTHDATE, "%m/%d/%y")
            delta = datetime.now() - birth
            total_days = delta.days
            months = total_days // 30
            days = total_days % 30
            age_str = f"{months} month{'' if months == 1 else 's'}, {days} day{'' if days == 1 else 's'} old"
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
                # Fallback: name + age on no device
                return PlainTextResponse(f":baby: Baby {BABY_NAME} is {age_str}")

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

            # 4. CHECK IF SOCK IS OFF (new reliable logic)
            hr = raw.get("heart_rate")
            o2 = raw.get("oxygen_saturation")
            sock_off = raw.get("sock_off")  # Secondary check if available

            # Sock off if: both HR/O2 are 0, OR sock_off == 1
            if (hr == 0 and o2 == 0) or sock_off == 1:
                print("Sock detected as OFF – showing name + age only")
                return PlainTextResponse(f":baby: Baby {BABY_NAME} is {age_str}")

            # 5. SOCK IS ON → extract other values
            sleep_state_code = raw.get("sleep_state")
            mov = raw.get("movement", 0)

            hr_val = int(hr) if hr is not None else "—"
            o2_val = int(o2) if o2 is not None else "—"
            mov_val = int(mov)

            # 6. DETERMINE SLEEP STATUS
            if hr_val == "—" and o2_val == "—":
                status = "Sock on – no signal"
                sleep_emoji = "👶"
            else:
                if sleep_state_code is not None:
                    if sleep_state_code == 0:
                        status = "Awake"
                        sleep_emoji = "👁️"
                    else:
                        status = "Sleeping"
                        sleep_emoji = "😴"
                else:
                    status, sleep_emoji = _fallback_sleep_status(mov_val)

            # 7. FINAL MESSAGE (with live data)
            baby_emoji = "👶"
            heart_emoji = "❤️"
            lungs_emoji = "🫁"
            message = (
                f"{baby_emoji} Baby {BABY_NAME} is {age_str} "
                f"{heart_emoji} Heart: {hr_val} BPM "
                f"{lungs_emoji} Oxygen: {o2_val}% "
                f"{sleep_emoji} {status}"
            )
            return PlainTextResponse(message)

        except Exception as e:
            print("Owlet error:", e)
            # Fallback: always show name + age
            return PlainTextResponse(f":baby: Baby {BABY_NAME} is {age_str}")


# Helper: fallback when sleep_state is missing
def _fallback_sleep_status(mov_val):
    if mov_val <= 3:
        return "Sleeping", "😴"
    else:
        return "Awake", "👁️"
