from fastapi import FastAPI
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

# Load .env
load_dotenv()

app = FastAPI()

# === CONFIG ===
OWLET_REGION = os.getenv("OWLET_REGION", "us")
OWLET_EMAIL = os.getenv("OWLET_EMAIL")
OWLET_PASSWORD = os.getenv("OWLET_PASSWORD")
BABY_NAME = os.getenv("BABY_NAME", "Baby")
BABY_BIRTHDATE = os.getenv("BABY_BIRTHDATE")  # MM/DD/YY


# ===========================
# ROOT ENDPOINT
# ===========================
@app.get("/")
async def root():
    return {"message": "Owlet Baby API – use /baby for live stats"}


# ===========================
# BABY DATA ENDPOINT
# ===========================
@app.get("/baby")
async def get_baby():

    # ---------------------------
    # 0. CALCULATE AGE (PACIFIC)
    # ---------------------------
    age_str = "Age unavailable"

    if BABY_BIRTHDATE:
        try:
            pacific = ZoneInfo("America/Los_Angeles")

            # Parse MM/DD/YY
            birth = datetime.strptime(BABY_BIRTHDATE, "%m/%d/%y").replace(tzinfo=pacific)
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

    # ---------------------------
    # 1. OWLET LOGIN + DEVICE FIND
    # ---------------------------
    async with aiohttp.ClientSession() as session:
        try:
            api = OwletAPI(OWLET_REGION, OWLET_EMAIL, OWLET_PASSWORD, session=session)
            await api.authenticate()

            devices = await api.get_devices()
            sock_device = None

            for item in devices.get("response", []):
                dev = item.get("device", {})
                name = dev.get("product_name", "")
                model = dev.get("model", "")

                if "Monitors" in name or "SS3" in model:
                    sock_device = dev
                    break

            # If no sock device → fallback
            if not sock_device:
                return PlainTextResponse(f"👶 Baby {BABY_NAME} is {age_str}")

            # ---------------------------
            # 2. FETCH LIVE DATA W/ RETRY (SAFE)
            # ---------------------------
            sock = Sock(api, sock_device)
            raw = {}

            for attempt in range(3):
                try:
                    props = await sock.update_properties()
                    raw = props.get("properties", {}) or {}

                    print("Raw properties (attempt", attempt + 1, "):", raw)

                    # If ANY real data appears → stop retry
                    if (
                        raw.get("heart_rate") is not None
                        or raw.get("oxygen_saturation") is not None
                    ):
                        break

                except Exception as inner_e:
                    print(f"Sock update error (attempt {attempt + 1}):", inner_e)

                if attempt < 2:
                    await asyncio.sleep(10)

            # ---------------------------
            # 3. SOCK-OFF DETECTION
            # ---------------------------
            hr = raw.get("heart_rate")
            o2 = raw.get("oxygen_saturation")
            sock_off = raw.get("sock_off")

            # If sock unavailable OR data empty → fallback
            if (
                not raw
                or hr is None
                or o2 is None
                or (hr == 0 and o2 == 0)
                or sock_off == 1
            ):
                print("Sock offline/unavailable – showing name + age only")
                return PlainTextResponse(f"👶 Baby {BABY_NAME} is {age_str}")

            # ---------------------------
            # 4. LIVE VALUES
            # ---------------------------
            sleep_state_code = raw.get("sleep_state")
            mov = int(raw.get("movement", 0))

            hr_val = int(hr) if hr is not None else "—"
            o2_val = int(o2) if o2 is not None else "—"

            # ---------------------------
            # 5. IMPROVED SLEEP LOGIC
            # ---------------------------
            # Movement > 2 → awake override
            if mov > 2:
                status = "Awake"
                sleep_emoji = "👁️"
            else:
                if sleep_state_code == 0:
                    status = "Awake"
                    sleep_emoji = "👁️"
                else:
                    status = "Sleeping"
                    sleep_emoji = "😴"

            # Extreme overrides
            if mov > 25 or hr_val > 150:
                status = "Awake"
                sleep_emoji = "👁️"

            # ---------------------------
            # 6. FINAL MESSAGE
            # ---------------------------
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


# Helper (kept for future use)
def _fallback_sleep_status(mov_val):
    if mov_val <= 5:
        return "Sleeping", "😴"
    return "Awake", "👁️"
