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

# ---------------------
# DISCORD BOT IMPORTS
# ---------------------
import discord
from discord.ext import commands
import threading

# Load .env
load_dotenv()

app = FastAPI()

# === CONFIG ===
OWLET_REGION = os.getenv("OWLET_REGION", "us")
OWLET_EMAIL = os.getenv("OWLET_EMAIL")
OWLET_PASSWORD = os.getenv("OWLET_PASSWORD")
BABY_NAME = os.getenv("BABY_NAME", "Baby")
BABY_BIRTHDATE = os.getenv("BABY_BIRTHDATE")  # MM/DD/YY
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")


# -----------------------------------
# FASTAPI ENDPOINTS
# -----------------------------------

@app.get("/")
async def root():
    return {"message": "Owlet Baby API – use /baby for live stats"}


@app.get("/baby")
async def get_baby():

    # ---------------------------
    # 0. CALCULATE AGE (PACIFIC)
    # ---------------------------
    age_str = "Age unavailable"

    if BABY_BIRTHDATE:
        try:
            pacific = ZoneInfo("America/Los_Angeles")

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
    # 1. OWLET LOGIN + DEVICE
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

            # No sock device → fallback
            if not sock_device:
                return PlainTextResponse(f"👶 Baby {BABY_NAME} is {age_str}")

            # ---------------------------
            # 2. FETCH LIVE DATA (NO RETRIES)
            # ---------------------------
            sock = Sock(api, sock_device)
            raw = {}

            try:
                props = await sock.update_properties()
                raw = props.get("properties", {}) or {}
            except Exception as e:
                print("Sock update error:", e)
                raw = {}

            # ---------------------------
            # 3. SOCK-OFF / FAILURE CHECK
            # ---------------------------
            hr = raw.get("heart_rate")
            o2 = raw.get("oxygen_saturation")
            sock_off = raw.get("sock_off")

            if (
                not raw
                or hr is None
                or o2 is None
                or (hr == 0 and o2 == 0)
                or sock_off == 1
            ):
                return PlainTextResponse(f"👶 Baby {BABY_NAME} is {age_str}")

            # ---------------------------
            # 4. VALUES + SLEEP LOGIC
            # ---------------------------
            sleep_state_code = raw.get("sleep_state")
            mov = int(raw.get("movement", 0))

            hr_val = int(hr) if hr is not None else "—"
            o2_val = int(o2) if o2 is not None else "—"

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

            if mov > 25 or hr_val > 150:
                status = "Awake"
                sleep_emoji = "👁️"

            # ---------------------------
            # 5. RETURN LIVE DATA
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


# -----------------------------------
# DISCORD BOT (PREFIX COMMAND !baby)
# -----------------------------------

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.command(name="baby")
async def baby_command(ctx):
    """Classic prefix command: !baby"""

    await ctx.trigger_typing()

    port = os.getenv("PORT", "10000")
    url = f"http://localhost:{port}/baby"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            text = await r.text()

    await ctx.reply(text)


def run_discord_bot():
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        print("⚠ NO DISCORD TOKEN FOUND — Discord bot not running")


# Run Discord bot in background thread so FastAPI still works
threading.Thread(target=run_discord_bot, daemon=True).start()


# ---------------------------
# OPTIONAL HELPER
# ---------------------------
def _fallback_sleep_status(mov_val):
    if mov_val <= 5:
        return "Sleeping", "😴"
    return "Awake", "👁️"
