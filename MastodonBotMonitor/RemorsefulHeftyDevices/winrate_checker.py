import aiohttp
import logging

logger = logging.getLogger(__name__)

class WinrateChecker:
    BASE_URL = "[redacted]"

    @staticmethod
    async def fetch_holders(token_address, holders_count=10):
        """Fetch top holders of a token."""
        url = f"{WinrateChecker.BASE_URL}/token/profiler/tokenHolderList"
        params = {
            "token": token_address,
            "chain": "solana",
            "page_size": holders_count,
            "sort_order": "desc"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        logger.error(f"Failed to fetch holders: {resp.status}")
                        return None

                    data = await resp.json()
                    return [holder["wallet"] for holder in data.get("data", {}).get("list", [])[:holders_count]]

        except Exception as e:
            logger.error(f"Error fetching holders: {e}")
            return None

    @staticmethod
    async def fetch_wallet_winrate(wallet_address):
        """Fetch winrate for a specific wallet."""
        url = f"{WinrateChecker.BASE_URL}/dashboard/token/trading/stats"
        params = {
            "token": wallet_address,  # The API expects a wallet address in this case
            "chain": "solana"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        logger.error(f"Failed to fetch winrate for {wallet_address}: {resp.status}")
                        return None

                    data = await resp.json()
                    return data.get("data", {}).get("winrate_30d", "N/A")

        except Exception as e:
            logger.error(f"Error fetching winrate for {wallet_address}: {e}")
            return None

    @staticmethod
    async def get_holders_with_winrates(token_address):
        """Retrieve top holders along with their individual winrates."""
        holders = await WinrateChecker.fetch_holders(token_address)
        if not holders:
            return None

        winrate_results = []
        for wallet in holders:
            winrate = await WinrateChecker.fetch_wallet_winrate(wallet)
            winrate_results.append(f"{wallet} - {winrate}%")

        return winrate_results
