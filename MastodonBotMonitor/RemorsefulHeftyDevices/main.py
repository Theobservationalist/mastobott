import discord
from discord.ext import commands
import asyncio
import json
import logging
import os
import pytz
from datetime import datetime
import aiohttp
from winrate_checker import WinrateChecker

# -------------------- Configuration --------------------
class Config:
    API_URL = "[redacted]"
    PARAMS = {
        "chain": "solana",
        "duration": "1m",
        "sort_field": "creation_timestamp",
        "sort_order": "desc",
        "filter": json.dumps({
            "liquidity": [50000, 1000000],
            "mkt_cap": [200000, 1000000],
            "holders": [400, 1e+308],
            "volume": [80000, 1e+308],
        }),
        "is_hide_honeypot": "true",
    }

    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "[redacted]")
    CHANNEL_ID = int(os.getenv("CHANNEL_ID", [redacted]))
    MOROCCO_TZ = pytz.timezone("Africa/Casablanca")
    CHECK_INTERVAL = 15  # seconds
    REQUIRED_SUFFIX = "pump"  # New required suffix
    BANNED_SUFFIX = "moon"    # Existing banned suffix

# -------------------- Logging Setup --------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# -------------------- Token Monitor --------------------
class TokenMonitor:
    def __init__(self):
        self.seen_addresses = self.load_persistence("seen_addresses.json")
        self.subscribed_users = self.load_persistence("subscribed_users.json")

    @staticmethod
    def load_persistence(filename):
        """Load persistent data from JSON file"""
        try:
            with open(filename, "r") as f:
                return set(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            return set()

    def save_persistence(self, data, filename):
        """Save data to JSON file"""
        with open(filename, "w") as f:
            json.dump(list(data), f)

    async def fetch_token_data(self):
        """Fetch and validate token data from API"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(Config.API_URL, params=Config.PARAMS) as resp:
                    if resp.status != 200:
                        logger.warning(f"API responded with status {resp.status}")
                        return None

                    data = await resp.json()
                    if not data.get("data") or len(data["data"]) == 0:
                        return None

                    token = data["data"][0]
                    return self.parse_token_data(token)

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error(f"Network error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
        return None

    def parse_token_data(self, token):
        """Extract and format token data with validation"""
        try:
            created_at = datetime.fromtimestamp(
                token["creation_timestamp"], tz=pytz.utc
            ).astimezone(Config.MOROCCO_TZ)

            return {
                "address": token["address"],
                "symbol": token["symbol"],
                "fdv": token["market_info"]["fdv"],
                "price": token["market_info"]["price"],
                "holders": token["market_info"]["holders"],
                "liquidity": token["pair_summary_info"]["liquidity"],
                "volume": token["market_info"]["volume"],
                "created_ago": created_at.strftime("%H:%M:%S"),
                "logo": token["logo"]
            }
        except KeyError as e:
            logger.error(f"Missing key in token data: {e}")
            return None

    async def send_alert(self, token_data):
        """Send formatted alert to Discord channel"""
        try:
            channel = await client.fetch_channel(Config.CHANNEL_ID)

            # Ensure the channel is a TextChannel
            if isinstance(channel, discord.TextChannel):
                embed = discord.Embed(
                    title="🚀 **MASTODON SCAN ALERT** 🚀",
                    color=discord.Color.green(),
                    description="Potential runner detected!",
                    timestamp=datetime.now(Config.MOROCCO_TZ)
                )

                # Validate token logo URL before setting it
                logo_url = token_data.get('logo', '')
                if logo_url.startswith("http://") or logo_url.startswith("https://"):
                    embed.set_thumbnail(url=logo_url)
                else:
                    logger.warning(f"Invalid or missing logo URL: {logo_url}")

                fields = [
                    ("✨ Symbol", token_data['symbol'], True),
                    ("🔗 Address", f"`{token_data['address']}`", False),
                    ("📊 Market Cap", f"${token_data['fdv']:,.2f}", True),
                    ("💰 Price", f"${token_data['price']:.4f}", True),
                    ("💸 24h Volume", f"${token_data['volume']:,.0f}", True),
                    ("👥 Holders", f"{token_data['holders']:,}", True),
                    ("🏦 Liquidity", f"${token_data['liquidity']:,.0f}", True),
                    ("⏰ Detected", token_data['created_ago'], True)
                ]

                for name, value, inline in fields:
                    embed.add_field(name=name, value=value, inline=inline)

                await channel.send(embed=embed)
                return True
            else:
                logger.warning(f"Channel with ID {Config.CHANNEL_ID} is not a text channel. Cannot send message.")
                return False

        except discord.DiscordException as e:
            logger.error(f"Discord API error: {e}")
            return False


    async def monitoring_loop(self):
        """Continuous monitoring with dual filters"""
        while True:
            try:
                # Fetch token data
                if token_data := await self.fetch_token_data():
                    address = token_data["address"]

                    # Check if address has been processed already (skipped or alerted)
                    if address in self.seen_addresses:
                        logger.info(f"Skipping already processed address: {address}")
                        continue  # Skip if the address has already been processed

                    # Check for non-pump tokens (check if address does not end with required suffix)
                    if not address.endswith(Config.REQUIRED_SUFFIX):
                        logger.info(f"Skipping non-pump token: {address}")
                        # Mark the address as processed and continue to the next token
                        self.seen_addresses.add(address)
                        self.save_persistence(self.seen_addresses, "seen_addresses.json")
                        continue  # Stop checking and move to the next token

                    # Check for banned tokens (if address ends with 'moon')
                    if address.endswith(Config.BANNED_SUFFIX):
                        logger.info(f"Skipping moon token: {address}")
                        # Mark the address as processed and continue to the next token
                        self.seen_addresses.add(address)
                        self.save_persistence(self.seen_addresses, "seen_addresses.json")
                        continue  # Stop checking and move to the next token

                    # If the address passes the checks, send the alert and track it
                    if await self.send_alert(token_data):
                        self.seen_addresses.add(address)
                        self.save_persistence(self.seen_addresses, "seen_addresses.json")
                        logger.info(f"New pump alert sent for {token_data['symbol']}")

                # Pause the loop for the set interval before checking again
                await asyncio.sleep(Config.CHECK_INTERVAL)

            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                await asyncio.sleep(30)




# -------------------- Bot Setup --------------------
intents = discord.Intents.default()
client = commands.Bot(command_prefix="!", intents=intents)
monitor = TokenMonitor()

@client.event
async def on_ready():
    logger.info(f"Logged in as {client.user}")
    if not hasattr(client, "monitor_task"):
        client.monitor_task = client.loop.create_task(monitor.monitoring_loop())

@client.command()
async def subscribe(ctx):
    """Subscribe to MASTODON alerts"""
    monitor.subscribed_users.add(ctx.author.id)
    monitor.save_persistence(monitor.subscribed_users, "subscribed_users.json")
    await ctx.send("✅ You've been subscribed to PUMP alerts!")

@client.command()
async def unsubscribe(ctx):
    """Unsubscribe from pump alerts"""
    monitor.subscribed_users.discard(ctx.author.id)
    monitor.save_persistence(monitor.subscribed_users, "subscribed_users.json")
    await ctx.send("❌ You've been unsubscribed from PUMP alerts.")

@client.event
async def on_command_error(ctx, error):
    """Handle command errors"""
    if isinstance(error, commands.CommandNotFound):
        return
    logger.error(f"Command error: {error}")
    await ctx.send(f"⚠️ Error: {str(error)}")


# -------------------- Main Execution --------------------
if __name__ == "__main__":
    try:
        client.run(Config.DISCORD_BOT_TOKEN)
    except KeyboardInterrupt:
        logger.info("Shutting down bot...")
        client.loop.run_until_complete(client.close())
        monitor.save_persistence(monitor.seen_addresses, "seen_addresses.json")
        monitor.save_persistence(monitor.subscribed_users, "subscribed_users.json")
