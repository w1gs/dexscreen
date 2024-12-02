import httpx
import json
from datetime import datetime, timedelta
from fake_useragent import UserAgent
from decimal import Decimal
from curl_cffi import requests

ua = UserAgent()
def fetch_data(url, headers={}, bypass_cloudflare=False):
        if headers.get("User-Agent", None) is None:
            headers.update({"User-Agent": ua.chrome})
        try:
            if bypass_cloudflare:
                response = requests.get(url, impersonate="chrome")
            else:
                with httpx.Client(headers=headers) as client:
                    response = client.get(url)
            return response
        except (httpx.HTTPStatusError, requests.exceptions.RequestException) as e:
            print(f"HTTP error occurred: {e}")
        except Exception as e:
            print(f"An error occurred: {e}")
        return None
contract = "BGWms7SStYYj2w7QXMvAmpTWCX4o6ibGBcBW3maGpump"
url = f"https://app.geckoterminal.com/api/p1/search?query=9vcqCACTyRaP3Ay1LxuDZ4szfguZUaz7wavLQRSHcGX5"



resp = fetch_data(url, bypass_cloudflare=True)
print(json.dumps(resp.json(), indent=4))