import os
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from dateutil.relativedelta import relativedelta

# FastAPI / Owlet imports
from fastapi import FastAPI
from starlette.responses import PlainTextResponse
from pyowletapi.api import OwletAPI
from pyowletapi.sock import Sock
import aiohttp

# Discord imports
import discord
from discord import app_commands
from discord.ext import commands

load_dotenv()

app = FastAPI()

# ===== CONFIG =====
OWLET_REGION = os.getenv("OWLET_REGION", "us")
OWLET_EMAIL = os.getenv("OWLET_EMAIL")
OWLET_PASSWORD = os.getenv("OWLET_PASSWORD")
BABY_NAME = os.getenv("BABY_NAME", "Baby")
BABY_BIRTHDATE = os.getenv("BABY_BIRTHDATE")  # MM/DD/YY
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# ================================
# FASTAPI ENDPOINT (unchanged)
# ================================
@app.get("/")
async def root():
    return {"message": "Owlet Baby API – use /baby for live stats"}


@app.get("/baby")
async def get_baby():

    # 0. AGE (PST)
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

    # 1. OWLET LOGIN + DEVICE
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

            if not sock_device:
                return PlainTextResponse(f"👶 Baby {BABY_NAME} is {age_str}")

            # 2. FETCH LIVE DATA
            sock = Sock(api, sock_device)
            try:
                props = await sock.update_properties()
                raw = props.get("properties", {}) or {}
            except:
                raw = {}

            hr = raw.get("heart_rate")
            o2 = raw.get("oxygen_saturation")
            sock_off = raw.get("sock_off")

            # Sock offline fallback
            if (
                not raw
                or hr is None
                or o2 is None
                or (hr == 0 and o2 == 0)
                or sock_off == 1
            ):
                return PlainTextResponse(f"👶 Baby {BABY_NAME} is {age_str}")

            # 3. STATUS LOGIC
            mov = int(raw.get("movement", 0))
            sleep_state = raw.get("sleep_state")

            hr_val = int(hr)
            o2_val = int(o2)

            if mov > 2:
                status = "Awake"
                emoji = "👁️"
            else:
                if sleep_state == 0:
                    status = "Awake"
                    emoji = "👁️"
                else:
                    status = "Sleeping"
                    emoji = "😴"

            # Extreme motion override
            if mov > 25 or hr_val > 150:
                status = "Awake"
                emoji = "👁️"

            msg = (
                f"👶 Baby {BABY_NAME} is {age_str} "
                f"❤️ Heart: {hr_val} BPM "
                f"🫁 Oxygen: {o2_val}% "
                f"{emoji} {status}"
            )

            return PlainTextResponse(msg)

        except:
            return PlainTextResponse(f"👶 Baby {BABY_NAME} is {age_str}")


# ============================================================
# DISCORD BOT — Slash Command /baby (calls your FastAPI)
# ============================================================

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree


@tree.command(name="baby", description="Get live Owlet baby stats")
async def slash_baby(interaction: discord.Interaction):
    """Calls your own /baby HTTP endpoint and returns the text."""
    await interaction.response.defer()

    url = "http://localhost:10000/baby"  # Render will override this with correct port
    # Render injects PORT, so we dynamically adapt:
    port = os.getenv("PORT")
    if port:
        url = f"http://localhost:{port}/baby"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            text = await r.text()

    await interaction.followup.send(text)


async def start_discord_bot():
    await bot.start(DISCORD_TOKEN)


# =========================================
# RUN FASTAPI + DISCORD TOGETHER ON RENDER
# =========================================
def start():
    """Starts both FastAPI (via uvicorn) and Discord bot."""
    import uvicorn

    loop = asyncio.get_event_loop()

    # Start Discord bot in background
    loop.create_task(start_discord_bot())

    # Start FastAPI normally
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))


if __name__ == "__main__":
    start()
