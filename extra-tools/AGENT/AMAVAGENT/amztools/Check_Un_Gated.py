import time
import re
import json
import requests
from collections import defaultdict
from time import sleep as wait
import os

if __package__:
    from .Sheet_Saver import Save
else:
    from Sheet_Saver import Save

# --- CONFIG ---
SERVER_URL = "http://localhost:51483"
WAIT_TIME = 2  # seconds between actions

resultData = defaultdict(list)
skippedProducts = defaultdict(list)

LWA_CLIENT_ID = "amzn1.application-oa2-client.5b8b71c8ff56492cbfe3e76508df84b9"
LWA_CLIENT_SECRET = (
    "amzn1.oa2-cs.v1.490ef4076b35d6f4568dab6be8a0b99b299cd4cb74fdf2029d8a1cec41833d1d"
)

LWA_REFRESH_TOKEN = "Atzr|IwEBIB8BOjVaAouBA6Nj_ZImCwWr9HdUDLKF2TONnTOaGS1VRvXwW1TjLHe5l3ZRub1gSjRDBg3fYSeqJAVENFF9Ehb7EY-t-mqblkmHX6DiUykKUOSFTdwghwgjMeuzRsaKjrrRSgjk2ucab5D1P2knb9vHnoUxyi_QJRnN7L1C9U0EZdkm7QLaVuWYSxfyt0dMuzYQBnbSuRfRR0ynUE1nHNpVcKG6c8TS78Acusqram9x7ZNtWvaAkuyl1rsePhiz7kLJAHGgMkvFVSt30gjkWu2m4xvuxAoMyNC7s3_KxqL0y8UHWMwg8jKivjQwE7ZHOqU"


class AmazonProductChecker:
    def __init__(self, client_id, client_secret, refresh_token, server_url, wait_time):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.server_url = server_url
        self.wait_time = wait_time
        self.access_token = self.get_access_token()
        self.result_data = defaultdict(list)
        self.skipped_products = defaultdict(list)

    def get_access_token(self):
        url = "https://api.amazon.com/auth/o2/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        response = requests.post(url, data=data)
        print("Access token response:", response.text)
        response.raise_for_status()
        return response.json()["access_token"]

    def refresh_access_token(self):
        self.access_token = self.get_access_token()
        print("Access token refreshed.")

    def identifier_to_asin(
        self, identifier, identifier_type="UPC", marketplace_id="ATVPDKIKX0DER"
    ):
        url = (
            f"https://sellingpartnerapi-na.amazon.com/catalog/2022-04-01/items"
            f"?identifiers={requests.utils.quote(identifier)}&identifiersType={identifier_type}&marketplaceIds={marketplace_id}"
        )
        headers = {
            "accept": "application/json",
            "x-amz-access-token": self.access_token,
        }

        try:
            response = requests.get(url, headers=headers)
            data = response.json()

            if "items" in data and len(data["items"]) > 0:
                asin = data["items"][0].get("asin")
                return asin
            else:
                print(f"No ASIN found for identifier: {identifier}")
                return None
        except Exception as e:
            print(f"Error searching identifier '{identifier}': {e}")
            return None

    def title_to_asin(self, title, marketplace_id="ATVPDKIKX0DER"):
        url = (
            f"https://sellingpartnerapi-na.amazon.com/catalog/2022-04-01/items"
            f"?keywords={requests.utils.quote(title)}&marketplaceIds={marketplace_id}"
        )
        headers = {
            "accept": "application/json",
            "x-amz-access-token": self.access_token,
        }

        try:
            response = requests.get(url, headers=headers)
            data = response.json()

            if "items" in data and len(data["items"]) > 0:
                asin = data["items"][0].get("asin")
                return asin
            else:
                print(f"No ASIN found for title: {title}")
                return None
        except Exception as e:
            print(f"Error searching title '{title}': {e}")
            return None

    def search_key_to_asin(self, search_key, marketplace_id="ATVPDKIKX0DER"):
        key = str(search_key).strip()
        if not key:
            return None

        if re.fullmatch(r"[0-9]{8,14}", key):
            return self.identifier_to_asin(
                key, identifier_type="UPC", marketplace_id=marketplace_id
            )

        if re.fullmatch(r"[A-Z0-9]{10}", key, re.IGNORECASE):
            return key.upper()

        return self.title_to_asin(key, marketplace_id=marketplace_id)

    def check_restrictions(self, asin):
        url = f"https://sellingpartnerapi-na.amazon.com/listings/2021-08-01/restrictions?asin={asin}&conditionType=new_new&sellerId=A2TR1ONI5QOLW4&marketplaceIds=ATVPDKIKX0DER&reasonLocale=en_US"

        headers = {
            "accept": "application/json",
            "x-amz-access-token": self.access_token,
        }

        try:
            response = requests.get(url, headers=headers)
            data = response.json()
            print(f"Response for ASIN {asin}: {data}")
            if "errors" in data and data["errors"][0].get("code") == "Unauthorized":
                print("Access token expired, refreshing...")
                self.refresh_access_token()
                # Retry once
                response = requests.get(url, headers=headers)
                data = response.json()
            return data
        except Exception as e:
            print(f"Unexpected error checking ASIN {asin}: {e}")
            return {"errors": [{"message": str(e)}]}

    def fetch_search_keys_from_server(self):
        try:
            resp = requests.get(f"{self.server_url}/search-key")
            data = resp.json()
            print(data)
            if isinstance(data.get("data"), list):
                return [str(s).strip() for s in data["data"] if str(s).strip()]
            return []
        except Exception as e:
            print(f"Failed to fetch search key from server: {e}")
            return []

    def send_checked_data_to_server(self, results, skipped):
        with open("resultData.json", "r") as f:
            existing_data = json.load(f)
            payload = {"results": existing_data, "skipped": []}

        try:
            resp = requests.post(
                f"{self.server_url}/checkeddata",
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
            )
            if resp.status_code == 200:
                print("✅ Checked data sent to server.")
            else:
                print(
                    f"⚠️ Server responded with status {resp.status_code}: {resp.text}"
                )
        except Exception as e:
            print(f"❌ Failed to send checked data to server: {e}")

    def process_titles(self, titles):
        self._process_titles(titles)

    def process_titles_and_save(self, titles, worksheet_name, batch_size=10):
        if (
            not isinstance(batch_size, int)
            or isinstance(batch_size, bool)
            or batch_size < 1
        ):
            raise ValueError("batch_size must be a positive integer")
        self._process_titles(titles, worksheet_name, batch_size)

    def _process_titles(self, titles, worksheet_name=None, batch_size=10):
        counter = 0
        batch_rows = []

        for title in titles:
            counter += 1
            if counter % 100 == 0:
                print("Refreshing access token...")
                self.refresh_access_token()
            asin = self.search_key_to_asin(title)
            if not asin:
                print(f"No ASIN found for title/UPC: {title}, skipping...")
                self.skipped_products["skipped"].append({"productUPC": title})
                row = [title, "", "ASIN not found"]
            else:
                wait(self.wait_time + 1)
                print(f"Checking: {title} - ASIN: {asin}")
                data = self.check_restrictions(asin)

                # Ensure asinsdata.json exists
                if not os.path.exists("asinsdata.json"):
                    with open("asinsdata.json", "w") as f:
                        json.dump({}, f)

                # Load old data
                try:
                    with open("asinsdata.json", "r") as f:
                        old_data = json.load(f)
                except (FileNotFoundError, json.JSONDecodeError):
                    old_data = {}

                # Merge
                old_data[title] = data
                with open("asinsdata.json", "w") as f:
                    json.dump(old_data, f, indent=4)

                if "errors" in data:
                    self.skipped_products["skipped"].append({"productUPC": title})
                    row = [title, asin, "Restriction check failed"]
                elif not data.get("restrictions"):
                    self.result_data[title].append(
                        {
                            "productASIN": asin,
                            "status": "✅ You can sell this item!",
                        }
                    )
                    row = [title, asin, self.result_data[title][-1]["status"]]
                else:
                    reason_info = data["restrictions"][0].get("reasons", [])[0]
                    reason_code = reason_info.get("reasonCode", "")
                    message = reason_info.get("message", "")

                    if reason_code == "NOT_ELIGIBLE":
                        status = (
                            f"❌ {message} You are not eligible to sell this product."
                        )
                    elif reason_code == "APPROVAL_REQUIRED":
                        status = (
                            "⚠️ Apply to sell. Approval is required. "
                            f"{message}"
                        )
                    else:
                        status = f"ℹ️ Status unknown. Reason: {message}"

                    self.result_data[title].append(
                        {"productASIN": asin, "status": status}
                    )
                    row = [title, asin, status]

            if worksheet_name is not None:
                batch_rows.append(row)
                if len(batch_rows) == batch_size:
                    self._save_result_data()
                    Save(batch_rows, worksheet_name)
                    batch_rows = []

        if worksheet_name is not None and batch_rows:
            self._save_result_data()
            Save(batch_rows, worksheet_name)

        self._save_result_data()

        # Optionally send to server
        # self.send_checked_data_to_server(dict(self.result_data), self.skipped_products["skippid"])

    def _save_result_data(self):
        # Save resultData.json
        with open("resultData.json", "w") as f:
            json.dump(dict(self.result_data), f, indent=4)


# --- CONFIG ---
# LWA_CLIENT_ID = "amzn1.application-oa2-client.5b8b71c8ff56492cbfe3e76508df84b9"
# LWA_CLIENT_SECRET = (
#     "amzn1.oa2-cs.v1.125f7e93012c23220035b57432b735034172c90f8adfa7e8d02c97404102dec6"
# )
# LWA_REFRESH_TOKEN = "Atzr|IwEBIIoBKW7BXRrH_RjDUHWYBtJKOwtqYxX9q5nmnuMa1xmvhkamOJGkVoDNrDoWVuHQ6ZFPGPeTJTCVigrQXOcoKniwmrkZyiFrg1chn0O0rfoi7_Rycfu6RwjgT73m-Tnf4lq60O8_gIhMrDjX-aCsKe7vI8MKMTyypijJTP6m19P5n0nzCP03RgTaRa-i_zztsWxy3cPPMLnbv0KiagmsuiXhvTv6Idp7OWkdMK6inBqTm3c6xdhRH5Qz6NvDcbiHPOJl68bvDdtDleZO9Xe_Ijw1Z29oOfRWyOqSEtNRc0nhmCXCDhwAy11gM067l_Wtfz2JwjxgthxW1oRgP29IvHig"
# SERVER_URL = "http://localhost:51483"
WAIT_TIME = 2  # seconds between actions

# Create resultData.json if not exists
if not os.path.exists("resultData.json"):
    with open("resultData.json", "w", encoding="utf-8") as f:
        json.dump({}, f, indent=4)


def Check_On_Amazon() -> str:
    """Legacy ADK compatibility tool backed by the current API endpoint.

    The current backend reads the user's stored /search-key values, uses that
    user's encrypted SP-API credentials, and persists the results. Keeping the
    network call here avoids duplicating credentials and restriction logic in
    the legacy agent package.
    """
    try:
        response = requests.post(f"{SERVER_URL}/check-products", json={}, timeout=3600)
        response.raise_for_status()
        payload = response.json()
        summary = payload.get("summary") or {}
        return json.dumps(
            {
                "status": payload.get("status", "success"),
                "message": "Amazon gated/ungated check completed.",
                "summary": summary,
            }
        )
    except Exception as exc:
        return json.dumps({"status": "error", "message": str(exc)})


def main():
    checker = AmazonProductChecker(
        client_id=LWA_CLIENT_ID,
        client_secret=LWA_CLIENT_SECRET,
        refresh_token=LWA_REFRESH_TOKEN,
        server_url=SERVER_URL,
        wait_time=WAIT_TIME,
    )
    brand_dict = {}
    category_dict = {
        "Mixed_EANs": """cat listt"""
        
    }
    if brand_dict:
    # Run The Check for each brand at the same time using asynchronous calls and save the results in different json files for each brand with name starting with the brand name and ending with _resultData.json
        for brand, search_keys_str in brand_dict.items():
            search_keys = [key.strip() for key in search_keys_str.splitlines() if key.strip()]
            print(f"Found {len(search_keys)} search keys to check on Amazon for brand {brand}.")
            checker.result_data.clear()
            checker.skipped_products.clear()
            checker.process_titles_and_save(search_keys, brand)
            # Save the resultData.json to a new file with the brand name
            with open(f"{brand}_resultData.json", "w", encoding="utf-8") as f:
                json.dump(dict(checker.result_data), f, indent=4)
    if category_dict:
        for category, search_keys_str in category_dict.items():
            search_keys = [key.strip() for key in search_keys_str.splitlines() if key.strip()]
            print(f"Found {len(search_keys)} search keys to check on Amazon for category {category}.")
            checker.result_data.clear()
            checker.skipped_products.clear()
            checker.process_titles_and_save(search_keys, category)
            # Save the resultData.json to a new file with the category name
            with open(f"{category}_resultData.json", "w", encoding="utf-8") as f:
                json.dump(dict(checker.result_data), f, indent=4)

    # search_keys = checker.fetch_search_keys_from_server()
#     search_keys_str = """asin list""
#     search_keys = [key.strip() for key in search_keys_str.splitlines() if key.strip()]

    # print(f"Found {len(search_keys)} search keys to check on Amazon.")
    # checker.process_titles(search_keys)


if __name__ == "__main__":
    print("Checking un-gated products on Amazon...")
    main()
