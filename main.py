import os
import aiohttp
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from dateutil.relativedelta import relativedelta

from fastapi import FastAPI
from starlette.responses import PlainTextResponse

# Owlet API
from pyowletapi.api import OwletAPI
from pyowletapi.sock import Sock

# Discord bot
import discord
from discord.ext import commands

# Load env vars
load_dotenv()

app = FastAPI()

# === OWLET CONFIG ===
OWLET_REGION = os.getenv("OWLET_REGION", "us")
OWLET_EMAIL = os.getenv("OWLET_EMAIL")
OWLET_PASSWORD = os.getenv("OWLET_PASSWORD")
BABY_NAME = os.getenv("BABY_NAME", "Baby")
BABY_BIRTHDATE = os.getenv("BABY_BIRTHDATE")
PORT = os.getenv("PORT", "10000")

# === DISCORD CONFIG ===
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True  # REQUIRED for '!baby'
bot = commands.Bot(command_prefix="!", intents=intents)


# -------------------------
# ROOT
# -------------------------
@app.get("/")
async def root():
    return {"message": "Owlet Baby API – use /baby"}


# -------------------------
# BABY ENDPOINT
# -------------------------
@app.get("/baby")
async def get_baby():

    # ---- Calculate Baby Age (Pacific Time)
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
        except:
            age_str = "Age error"

    # ---- Connect to Owlet
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

            # No sock paired
            if not sock_device:
                return PlainTextResponse(f"👶 Baby {BABY_NAME} is {age_str}")

            # ---- Live Data (NO RETRIES)
            sock = Sock(api, sock_device)
            raw = {}

            try:
                props = await sock.update_properties()
                raw = props.get("properties", {}) or {}
            except:
                raw = {}

            # ---- If sock offline → only age
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

            # ---- Sleep Logic
            sleep_state_code = raw.get("sleep_state")
            mov = int(raw.get("movement", 0))

            hr_val = int(hr)
            o2_val = int(o2)

            if mov > 2:
                status = "Awake"
                emoji = "👁️"
            else:
                if sleep_state_code == 0:
                    status = "Awake"
                    emoji = "👁️"
                else:
                    status = "Sleeping"
                    emoji = "😴"

            if mov > 25 or hr_val > 150:
                status = "Awake"
                emoji = "👁️"

            message = (
                f"👶 Baby {BABY_NAME} is {age_str} "
                f"❤️ Heart: {hr_val} BPM "
                f"🫁 Oxygen: {o2_val}% "
                f"{emoji} {status}"
            )

            return PlainTextResponse(message)

        except:
            return PlainTextResponse(f"👶 Baby {BABY_NAME} is {age_str}")


# -------------------------
# DISCORD BOT
# -------------------------
@bot.event
async def on_ready():
    print(f"🤖 Discord bot logged in as {bot.user}")


@bot.command(name="baby")
async def baby_command(ctx):
    # typing indicator
    async with ctx.channel.typing():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:{PORT}/baby") as resp:
                    text = await resp.text()
        except:
            text = "Baby status unavailable right now."

    await ctx.send(text)


# -------------------------
# START EVERYTHING
# -------------------------
def start_discord_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bot.run(DISCORD_TOKEN)


# Run discord bot in background
import threading
threading.Thread(target=start_discord_bot, daemon=True).start()
