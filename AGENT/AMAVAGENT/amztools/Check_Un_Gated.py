import time
import re
import json
import requests
from collections import defaultdict
from time import sleep as wait
import os
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

    def identifier_to_asin(self, identifier, identifier_type="UPC", marketplace_id="ATVPDKIKX0DER"):
        url = (
            f"https://sellingpartnerapi-na.amazon.com/catalog/2022-04-01/items"
            f"?identifiers={requests.utils.quote(identifier)}&identifiersType={identifier_type}&marketplaceIds={marketplace_id}"
        )
        headers = {"accept": "application/json", "x-amz-access-token": self.access_token}

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
        headers = {"accept": "application/json", "x-amz-access-token": self.access_token}

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
            return self.identifier_to_asin(key, identifier_type="UPC", marketplace_id=marketplace_id)

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
                print(f"⚠️ Server responded with status {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"❌ Failed to send checked data to server: {e}")

    def process_titles(self, titles):
        counter = 0
        for title in titles:
            counter += 1
            if counter % 100 == 0:
                print("Refreshing access token...")
                self.refresh_access_token()
            asin = self.search_key_to_asin(title)
            if not asin:
                print(f"No ASIN found for title/UPC: {title}, skipping...")
                self.skipped_products["skipped"].append({"productUPC": title})
                continue
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
            elif not data.get("restrictions"):
                self.result_data[title].append(
                    {
                        "productASIN": asin,
                        "status": "✅ You can sell this item!",
                    }
                )
            else:
                reason_info = data["restrictions"][0].get("reasons", [])[0]
                reason_code = reason_info.get("reasonCode", "")
                message = reason_info.get("message", "")

                if reason_code == "NOT_ELIGIBLE":
                    self.result_data[title].append(
                        {
                            "productASIN": asin,
                            "status": f"❌ {message} You are not eligible to sell this product.",
                        }
                    )
                elif reason_code == "APPROVAL_REQUIRED":
                    self.result_data[title].append(
                        {
                            "productASIN": asin,
                            "status": f"⚠️ Apply to sell. Approval is required. {message}",
                        }
                    )
                else:
                    self.result_data[title].append(
                        {
                            "productASIN": asin,
                            "status": f"ℹ️ Status unknown. Reason: {message}",
                        }
                    )

        # Save resultData.json
        with open("resultData.json", "w") as f:
            json.dump(dict(self.result_data), f, indent=4)

        # Optionally send to server
        # self.send_checked_data_to_server(dict(self.result_data), self.skipped_products["skippid"])


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
        return json.dumps({
            "status": payload.get("status", "success"),
            "message": "Amazon gated/ungated check completed.",
            "summary": summary,
        })
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

    # search_keys = checker.fetch_search_keys_from_server()
    search_keys =  [
        "729305001733",
"729305002174",
"729305001320",
"729305001979",
"729305004222",
"729305004031",
"729305004314",
"25215190315",
"25215196270",
"634343281255",
"634343270648",
"885170046368",
"68888901802",
"68888907330",
"68888901796",
"68888898324",
"68889023367",
"68888896665",
"68888896658",
"68888896641",
"68888897433",
"68888717083",
"68888712835",
"68889023497",
"68888988889",
"68888885935",
"68888737760",
"79000403234",
"79000403265",
"44476042546",
"44476042553",
"44476043024",
"44476060984",
"44476060977",
"44476061004",
"79000403333",
"44476066399",
"44476060991",
"79000403340",
"79000310297",
"79000403814",
"79000303473",
"44476042539",
"79000308621",
"79000403364",
"79000403401",
"79000403425",
"79000403463",
"79000403562",
"729288029212",
"37332121912",
"37332121929",
"37332140746",
"37332174161",
"37332184603",
"37332164698",
"37332175571",
"37332012142",
"37332137951",
"37332137852",
"37332137944",
"37332165503",
"615798101084",
"846788042524",
"846788042531",
"846788042548",
"846788042555",
"846788042609",
"68888901543",
"68888738309",
"68888994675",
"68889008487",
"68888758482",
"68888754828",
"68888754835",
"68888737777",
"68888743327",
"729288014058",
"747705204356",
"879408009720",
"21299175545",
"68888744416",
"639131901131",
"639131751064",
"79000316114",
"79000316091",
"44476046148",
"44476049064",
"79000320593",
"79000320609",
"79000320616",
"846788042906",
"846788042937",
"846788042944",
"46838074998",
"68888762397",
"68888760164",
"729305004482",
"68888772525",
"68888762410",
"601430003021",
"601430003083",
"601430003120",
"601430003038",
"879408007115",
"68888769426",
"68888769433",
"68888770149",
"816983010055",
"86429333936",
"44476127243",
"44476127250",
"783250689408",
"46838064258",
"68888760454",
"727932014218",
"783250926916",
"783250926503",
"68888758321",
"68888896672",
"37332191571",
"68888759496",
"79000403852",
"79000403906",
"37332134622",
"37332174178",
"37332140739",
"44476128066",
"68889023480",
"86429344772",
"86429344826",
"86429344758",
"68888777988",
"846788024049",
]

    print(f"Found {len(search_keys)} search keys to check on Amazon.")
    checker.process_titles(search_keys)


if __name__ == "__main__":
    print("Checking un-gated products on Amazon...")
    main()

