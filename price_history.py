import httpx
import json
from datetime import datetime, timedelta
from fake_useragent import UserAgent
from decimal import Decimal
from curl_cffi import requests


class PriceData:
    def __init__(self):
        self.price_data = {}
        self.ua = UserAgent()

    def fetch_data(self, url, headers=None, bypass_cloudflare=False):
        headers = headers or {"User-Agent": self.ua.chrome}
        try:
            if bypass_cloudflare:
                response = requests.get(url, impersonate="chrome")
            else:
                with httpx.Client(headers=headers) as client:
                    response = client.get(url)
            return response.json()
        except (httpx.HTTPStatusError, requests.exceptions.RequestException) as e:
            print(f"HTTP error occurred: {e}")
        except Exception as e:
            print(f"An error occurred: {e}")
        return None

    def format_price(self, price):
        return format(Decimal(str(price)), "f") if isinstance(price, float) else price

    def search_all_platforms(self, query: str):
        all_info = {
            "searched_address": query,
            "dextools_data": False,
            "dexscreen_data": False,
            "pump_data": False,
            "geckoterminal_data": False,
        }

        dextools_info = self.search_dextools(query.lower().strip())
        dexscreen_info = self.search_dexscreen(query)
        geckoterminal_info = self.search_geckoterminal(query)
        
        if query.endswith("pump"):
            pump_info = self.search_pump(query)
        else:
            pump_info = self.search_pump(f"{query}")
            if pump_info is None:
                pump_info = self.search_pump(f"{query}pump")
        if len(dextools_info.get("results", [])) == 0:
            dextools_results = None
        else:
            dextools_results = dextools_info.get("results")
            all_info["dextools_data"] = True
            all_info["chain_id"] = dextools_results[0]["id"]["chain"]
            all_info["symbol"] = dextools_results[0]["symbol"]
            all_info["name"] = dextools_results[0]["name"]
            if len(dextools_results) == 1:
                all_info["pair_address"] = dextools_results[0]["id"]["pair"]
            else:
                for res in dextools_results:
                    if res.get("redirectToPool", None) is not None:
                        all_info["pair_address"] = res["redirectToPool"]

        if dexscreen_info is not None:
            all_info["dexscreen_data"] = True
            if all_info.get("pair_address", None) is None:
                all_info["pair_address"] = dexscreen_info["pair_address"]

        if pump_info is not None:
            all_info["pump_data"] = True
            if all_info.get("symbol", None) is None:
                all_info["symbol"] = pump_info["symbol"]
                all_info["name"] = pump_info["name"]
                all_info["chain_id"] = "solana"
        
        if geckoterminal_info is not None:
            all_info['geckoterminal_data'] = True

        filenames = {
            "dextools.json": dextools_results,
            "dexscreen.json": dexscreen_info,
            "pump.json": pump_info,
            "geckoterminal.json": geckoterminal_info
        }
        for name, result in filenames.items():
            with open(name, "w") as f:
                f.write(json.dumps(result, indent=4))

        return all_info

    def search_geckoterminal(self, query: str):
        geckoterminal_url = (
            f"https://app.geckoterminal.com/api/p1/search?query={query.strip()}"
        )
        data = self.fetch_data(geckoterminal_url, bypass_cloudflare=True)
        for _, v in data.get("data",{}).get("attributes", {}).items():
            if len(v) >= 1:
                return data.get("data", {}).get("attributes", None)
        return None

    def search_dexscreen(self, contract_address: str) -> dict:
        search_url = (
            f"https://api.dexscreener.com/latest/dex/search?q={contract_address}"
        )
        data = self.fetch_data(search_url)

        if not data or "pairs" not in data or not data["pairs"]:
            return None
        pair_data = data["pairs"][0]
        return {
            "contract_address": contract_address,
            "chain_id": pair_data.get("chainId"),
            "pair_address": pair_data.get("pairAddress"),
            "symbol_pair": f"{pair_data['baseToken'].get('symbol')}/{pair_data['quoteToken'].get('symbol')}",
        }

    def search_dextools(self, query: str):
        headers = {
            "Accept": "application/json",
            "Referer": "https://www.dextools.io/app/en/solana/pair-explorer/",
            "User-Agent": self.ua.chrome,
        }
        dextools_search_url = (
            f"https://www.dextools.io/shared/search/pair?query={query}"
        )
        return self.fetch_data(dextools_search_url, headers=headers)

    def search_pump(self, query: str):
        data = self.fetch_data(f"https://frontend-api.pump.fun/coins/{query}")
        if data.get("statusCode", 200) == 500:
            return None
        return data

    def pump_price_data(self, pump_address: str):
        pump_info = self.fetch_data(
            f"https://frontend-api.pump.fun/coins/{pump_address}"
        )
        pump_price_data = self.fetch_data(
            f"https://frontend-api.pump.fun/candlesticks/{pump_address}?offset=0&limit=100000"
        )
        dex_info = self.search_dexscreen(pump_address)

        pair_address = (
            dex_info.get("pair_address", pump_address) if dex_info else pump_address
        )
        chain_id = dex_info["chain_id"] if dex_info else "solana"
        self.price_data.setdefault(pair_address, {})["pump_pair_symbol"] = (
            f"{pump_info['symbol']}/SOL"
        )
        coingecko_info = self.fetch_data(
            f"https://app.geckoterminal.com/api/p1/{chain_id}/pools/{pair_address}",
            bypass_cloudflare=True,
        )

        if coingecko_info and not coingecko_info.get("errors"):
            self.price_data[pair_address]["pump_pair_symbol"] = coingecko_info["data"][
                "attributes"
            ]["name"].replace(" ", "")

            from_timestamp = (
                datetime.fromisoformat(
                    coingecko_info["data"]["attributes"]["pool_created_at"].replace(
                        "Z", "+00:00"
                    )
                )
                - timedelta(days=1)
            ).timestamp()
            coingecko_price_data = self.fetch_data(
                f"https://app.geckoterminal.com/api/p1/candlesticks/{coingecko_info['data']['id']}/{coingecko_info['data']['relationships']['pairs']['data'][0]['id']}?resolution=1D&from_timestamp={from_timestamp}&to_timestamp={datetime.now().timestamp()}",
                bypass_cloudflare=True,
            )["data"]
            pump_price_data = [
                {
                    "timestamp": datetime.fromisoformat(
                        candle["dt"].replace("Z", "+00:00")
                    ).timestamp(),
                    "open": candle["o"],
                    "close": candle["c"],
                    "high": candle["h"],
                    "low": candle["l"],
                }
                for candle in coingecko_price_data
            ]

        if pump_info and int(pump_info["usd_market_cap"]) >= 69000:
            print("Market Cap over $69,000. Checking DexTools for price data.")
            self.dextools_price_data(pair_address)

        # Group candles by date and get the latest timestamp for each date
        latest_timestamps_by_date = {}
        for candle in pump_price_data:
            date_str = datetime.fromtimestamp(candle["timestamp"]).strftime("%Y-%m-%d")
            if (
                date_str not in latest_timestamps_by_date
                or candle["timestamp"] > latest_timestamps_by_date[date_str]
            ):
                latest_timestamps_by_date[date_str] = candle["timestamp"]

        # Filter the candles to only include those with the latest timestamp for each date
        latest_candles_by_date = {
            date_str: next(
                candle
                for candle in pump_price_data
                if datetime.fromtimestamp(candle["timestamp"]).strftime("%Y-%m-%d")
                == date_str
                and candle["timestamp"] == latest_timestamps_by_date[date_str]
            )
            for date_str in latest_timestamps_by_date
        }

        self.price_data.setdefault(pair_address, {}).setdefault("price_data", {})[
            "pump"
        ] = [
            {
                "date": date_str,
                "open_price": self.format_price(candle["open"]),
                "close_price": self.format_price(candle["close"]),
                "high_price": self.format_price(candle["high"]),
                "low_price": self.format_price(candle["low"]),
            }
            for date_str, candle in latest_candles_by_date.items()
        ]

    def dextools_price_data(
        self, pair_address: str, symbol_pair=None, chain_id="solana"
    ):
        current_datetime = datetime.now().timestamp()
        candles_url = f"https://core-api.dextools.io/pool/candles/{chain_id}/{pair_address}/usd/1d/month?ts={current_datetime}&tz=0"
        resp = self.fetch_data(
            candles_url, headers={"User-Agent": self.ua.chrome, "X-API-VERSION": "1"}
        )
        if not resp or "data" not in resp or "candles" not in resp["data"]:
            print("No candle data found on Dextools.")
            return None
        candle_data = resp["data"]["candles"]
        self.price_data.setdefault(pair_address, {}).setdefault("price_data", {})[
            "dex_tools"
        ] = [
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
        all_info = self.search_all_platforms(contract_address)
        self.price_data["contract_address"] = all_info["searched_address"]
        print(all_info)
        if not contract_address.endswith("pump"):
            if all_info.get("pair_address", None) is None:
                self.pump_price_data(contract_address)
                self.write_results()
                return
            self.dextools_price_data(all_info["pair_address"], all_info["chain_id"])
        else:
            print("Address ends with 'pump'. Checking price data from pump.fun")

            self.pump_price_data(contract_address)
            self.write_results()

    def write_results(self):
        with open("PriceData.json", "w") as f:
            print("Writing results to 'PriceData.json'...")
            json.dump(self.price_data, f, indent=4)
            print("Done")


if __name__ == "__main__":
    contract_address = input("Address to search: ").strip()
    price_data_instance = PriceData()
    price_data_instance.fetch_price_data(contract_address)
