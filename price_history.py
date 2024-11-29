import httpx
import json
from datetime import datetime, timedelta
from fake_useragent import UserAgent
from decimal import Decimal
from curl_cffi import requests
from decimal import Decimal


class PriceData:
    def __init__(self):
        self.price_data = {}
        self.ua = UserAgent()

    def fetch_data(self, url, headers=None, bypass_cloudflare=False):
        if headers is None:
            headers = {"User-Agent": self.ua.chrome}
        try:
            if bypass_cloudflare:
                response = requests.get(url, impersonate="chrome")
                return response.json()
            else:
                with httpx.Client(headers=headers) as client:
                    response = client.get(url)
                    return response.json()
        except httpx.HTTPStatusError as e:
            print(f"HTTP error occurred: {e}")
        except Exception as e:
            print(f"An error occurred: {e}")
        return None

    def format_price(self, price):
        if isinstance(price, float):
            # Convert float to Decimal with more precision
            price = Decimal(str(price))
        return format(price, "f")

    def search_dexscreen(self, contract_address: str) -> dict:
        search_url = (
            f"https://api.dexscreener.com/latest/dex/search?q={contract_address}"
        )
        data = self.fetch_data(search_url)
        if not data or "pairs" not in data or not data["pairs"]:
            return None
        print(f"Blockchain found: {data["pairs"][0].get("chainId").title()}")

        return {
            "contract_address": contract_address,
            "chain_id": data["pairs"][0].get("chainId"),
            "pair_address": data["pairs"][0].get("pairAddress"),
            "symbol_pair": f"{data['pairs'][0]['baseToken'].get('symbol')}/{data['pairs'][0]['quoteToken'].get('symbol')}",
        }

    def pump_price_data(self, pump_address: str):
        print("Address ends with 'pump'. Checking price data from pump.fun")
        pump_price_url = f"https://frontend-api.pump.fun/candlesticks/{pump_address}?offset=0&limit=100000"
        pump_info_url = f"https://frontend-api.pump.fun/coins/{pump_address}"
        pump_info = self.fetch_data(pump_info_url)
        pump_price_data = self.fetch_data(pump_price_url)
        dex_info = self.search_dexscreen(pump_address)
        if dex_info is not None:
            pair_address = dex_info.get("pair_address", pump_address)
            chain_id = dex_info["chain_id"]
        else:
            pair_address = pump_address
            chain_id = "solana"
        coingecko_info_url = (
            f"https://app.geckoterminal.com/api/p1/{chain_id}/pools/{pair_address}"
        )

        coingecko_info = self.fetch_data(coingecko_info_url, bypass_cloudflare=True)
        if coingecko_info is not None and coingecko_info.get("errors", None) is None:
            from_timestamp = (
                datetime.fromisoformat(
                    coingecko_info["data"]["attributes"]["pool_created_at"].replace(
                        "Z", "+00:00"
                    )
                )
                - timedelta(days=1)
            ).timestamp()
            coingecko_price_url = f"https://app.geckoterminal.com/api/p1/candlesticks/{coingecko_info['data']['id']}/{coingecko_info['data']['relationships']['pairs']['data'][0]['id']}?resolution=1D&from_timestamp={from_timestamp}&to_timestamp={datetime.now().timestamp()}"
            coingecko_price_data = self.fetch_data(
                coingecko_price_url, bypass_cloudflare=True
            )["data"]
            pump_price_data = []
            for candle in coingecko_price_data:
                pump_price_data.append(
                    {
                        "timestamp": datetime.fromisoformat(
                            candle["dt"].replace("Z", "+00:00")
                        ).timestamp(),
                        "open": candle["o"],
                        "close": candle["c"],
                        "high": candle["h"],
                        "low": candle["l"],
                    }
                )

        if pump_info and (int(pump_info["usd_market_cap"]) >= 69000):
            print("Market Cap over $69,000. Checking DexTools for price data.")
            if pair_address is not None:
                self.dextools_price_data(pair_address)

        if pair_address not in self.price_data:
            self.price_data[pair_address] = {}
        if "price_data" not in self.price_data[pair_address]:
            self.price_data[pair_address]["price_data"] = {}

        self.price_data[pair_address]["price_data"]["pump"] = [
            {
                "date": datetime.fromtimestamp(candle["timestamp"]).strftime(
                    "%Y-%m-%d"
                ),
                "open_price": self.format_price(candle["open"]),
                "close_price": self.format_price(candle["close"]),
                "high_price": self.format_price(candle["high"]),
                "low_price": self.format_price(candle["low"]),
            }
            for candle in pump_price_data
        ]

    def dextools_price_data(
        self, pair_address: str, symbol_pair=None, chain_id="solana"
    ):
        current_datetime = datetime.now().timestamp()
        candles_url = (
            f"https://core-api.dextools.io/pool/candles/{chain_id}/{pair_address}/usd/1d/month"
            f"?ts={current_datetime}&tz=0"
        )
        resp = self.fetch_data(
            candles_url, headers={"User-Agent": self.ua.chrome, "X-API-VERSION": "1"}
        )
        if not resp or "data" not in resp or "candles" not in resp["data"]:
            print("No candle data found on Dextools.")
            return None
        candle_data = resp["data"]["candles"]
        # inception = resp["data"].get("first")
        if pair_address not in self.price_data:
            self.price_data[pair_address] = {}
        if "price_data" not in self.price_data[pair_address]:
            self.price_data[pair_address]["price_data"] = {}
        self.price_data[pair_address]["price_data"]["dex_tools"] = [
            {
                "date": datetime.fromtimestamp(candle["ts"] / 1000).strftime(
                    "%Y-%m-%d"
                ),
                "open_price": self.format_price(candle["open"]),
                "close_price": self.format_price(candle["close"]),
                "high_price": self.format_price(candle["high"]),
                "low_price": self.format_price(candle["low"]),
            }
            for candle in candle_data
        ]

    def fetch_price_data(self, contract_address: str):
        dex_data = self.search_dexscreen(contract_address)

        if not contract_address.endswith("pump"):
            if dex_data is None:
                # Check pump if Dextools has no data
                self.pump_price_data(contract_address)
                return
            self.dextools_price_data(
                dex_data["chain_id"], dex_data["pair_address"], dex_data["symbol_pair"]
            )

        elif contract_address.endswith("pump"):
            self.pump_price_data(contract_address)

        with open("PriceData.json", "w") as f:
            print("Writing results to 'PriceData.json'...")
            f.write(json.dumps(self.price_data, indent=4))
            print("Done")


if __name__ == "__main__":
    contract_address = input("Address to search: ").strip()
    price_data_instance = PriceData()
    price_data_instance.fetch_price_data(contract_address)
