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
                raise HTTPException(500, "No Dream Sock 3 found")

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

            # 4. EXTRACT VALUES
            hr = raw.get("heart_rate")
            o2 = raw.get("oxygen_saturation")
            sleep_state_code = raw.get("sleep_state")
            mov = raw.get("movement", 0)

            hr_val = int(hr) if hr is not None else "—"
            o2_val = int(o2) if o2 is not None else "—"
            mov_val = int(mov)

            # 5. DETERMINE SLEEP STATUS — sleep_state first
            if hr_val == "—" and o2_val == "—":
                status = "Sock on – no signal"
                sleep_emoji = "👶"
            else:
                if sleep_state_code is not None:
                    if sleep_state_code == 8:
                        status = "Deep Sleep"
                        sleep_emoji = "😴"
                    elif 1 <= sleep_state_code <= 7:
                        status = "Light Sleep"
                        sleep_emoji = "😴"
                    elif sleep_state_code == 0:
                        status = "Awake"
                        sleep_emoji = "👁️"
                    else:
                        # Invalid code → fallback to movement
                        status, sleep_emoji = _fallback_sleep_status(mov_val)
                else:
                    # No sleep_state → fallback to movement
                    status, sleep_emoji = _fallback_sleep_status(mov_val)

            # 6. CALCULATE AGE
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

            # 7. FINAL MESSAGE WITH TWITCH SHORTCODES
            baby_emoji = "👶"
            heart_emoji = "❤️"
            lungs_emoji = "🫁"

            message = (
                f"{baby_emoji} Baby {BABY_NAME} is {age_str} "
                f"{heart_emoji} Heart: {hr_val} BPM "
                f"{lungs_emoji} O2: {o2_val}% "
                f"{sleep_emoji} {status}"
            )

            return PlainTextResponse(message)

        except Exception as e:
            print("Owlet error:", e)
            return PlainTextResponse("Baby stats unavailable")


# Helper: fallback when sleep_state is missing or invalid
def _fallback_sleep_status(mov_val):
    if mov_val == 0:
        return "Deep Sleep", "😴"
    elif mov_val <= 3:
        return "Light Sleep", "🥱"
    else:
        return "Awake", "👁️"
