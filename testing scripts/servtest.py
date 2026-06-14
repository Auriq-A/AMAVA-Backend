import requests
from aws_requests_auth.aws_auth import AWSRequestsAuth
import time

BASE_URL = "https://sellingpartnerapi-na.amazon.com"
LWA_CLIENT_ID = "amzn1.application-oa2-client.5b8b71c8ff56492cbfe3e76508df84b9"
LWA_CLIENT_SECRET = (
    "amzn1.oa2-cs.v1.2d2fd30e37ba9966fee4bc759d190e2095c35a5c39457340451f814df0d6007f"
)
LWA_REFRESH_TOKEN = "Atzr|IwEBIHZkHHtNUrquPqy4ula75o7X__Doy_xrd3HFdCqeKnflMjrs1Dov8yahP8dgpgUGb5MSPnLi36Z82eP_d0xzGJLT5DfrvYnv2FX8DbAHH9Bn5MjgBr2IESXt40_3PgsrIUaHrQ33bnrEvye3s7qm89_2oFAdrFYxMshI5HaysTjv3XroGIYd1HSsBf55E8N4cbQ4mT5a6P523faqOlNsTGW2IXYI07sgJCU7YzE6h_nXJAjt679JXqr4UhUm27hVcHbsAxV_mkk5tYu9Ih_DZBDtdaRVgCkx-o4VTRyINCD2iXgDPxjaxVo8Yz4Zx-WS1c02cL8yFgdCo7ne63AkfA-7"


def get_access_token():
    url = "https://api.amazon.com/auth/o2/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": LWA_REFRESH_TOKEN,
        "client_id": LWA_CLIENT_ID,
        "client_secret": LWA_CLIENT_SECRET,
    }
    response = requests.post(url, data=data)
    response.raise_for_status()
    return response.json()["access_token"]


BASE_URL = "https://sellingpartnerapi-na.amazon.com"
marketplace_id = "ATVPDKIKX0DER"
ACCESS_TOKEN = get_access_token()
print(ACCESS_TOKEN)
BASE_URL = "https://sellingpartnerapi-na.amazon.com"
HEADERS = {"accept": "application/json", "x-amz-access-token": ACCESS_TOKEN}
MARKETPLACE_ID = "ATVPDKIKX0DER"
AWS_API_KEY_NAME = "spapi-user-at-927374824677"
Access_key_ID = "AKIA5P26Y2TS44JJFSVX"
AWS_API_KEY = "ABSKc3BhcGktdXNlci1hdC05MjczNzQ4MjQ2Nzc6QnlqVnRvVklYZUQya21qUmYza0g3TGJ3Q1ZHUzFOdU9IdGd4UWJhRktmM1hzbEJSOTZncDFpRzkwZkk9"
Secret_access_key = "5N0ny4dctdJqM2AIr18dUaKfuNCSH1IABPpIqaa3"
AWS_ACCESS_KEY = AWS_API_KEY
AWS_SECRET_KEY = Secret_access_key
REGION = "us-east-1"
SERVICE = "execute-api"
auth = AWSRequestsAuth(
    aws_access_key=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    aws_host="sellingpartnerapi-na.amazon.com",
    aws_region=REGION,
    aws_service=SERVICE,
)


def get_shipments():
    url = f"{BASE_URL}/fba/inbound/v0/shipments"
    params = {"ShipmentStatusList": "WORKING,SHIPPED,RECEIVING,CLOSED"}
    r = requests.get(url, headers=HEADERS, params=params)
    r.raise_for_status()
    return r.json()


# shipments = get_shipments()
# print(shipments)
import requests

BASE_URL = "https://sellingpartnerapi-na.amazon.com"


def get_shipment_info(shipment_id):
    # 1. Shipment header info
    url1 = f"{BASE_URL}/fba/inbound/v0/shipments"
    params1 = {"ShipmentIdList": shipment_id}
    r1 = requests.get(url1, headers=HEADERS, params=params1)
    r1.raise_for_status()
    shipment_summary = r1.json()

    # 2. Shipment items
    url2 = f"{BASE_URL}/fba/inbound/v0/shipments/{shipment_id}/items"
    r2 = requests.get(url2, headers=HEADERS)
    r2.raise_for_status()
    shipment_items = r2.json()

    # 3. Shipment tracking
    url3 = f"{BASE_URL}/fba/inbound/v0/shipments/{shipment_id}/tracking"
    r3 = requests.get(url3, headers=HEADERS)
    if r3.status_code == 200:
        shipment_tracking = r3.json()
    else:
        shipment_tracking = {"message": "No tracking available"}

    return {
        "summary": shipment_summary,
        "items": shipment_items,
        "tracking": shipment_tracking,
    }


# print(get_shipment_info("FBA18ZD88842"))


def get_shipment_problems(shipment_id):
    # Step 1: Request a new report (receipt data)
    url = f"{BASE_URL}/reports/2021-06-30/reports"
    payload = {
        "reportType": "GET_FBA_FULFILLMENT_INBOUND_NONCOMPLIANCE_DATA",
        "marketplaceIds": [marketplace_id],
        "fba-shipment-id": shipment_id,
        # "reportOptions": {"fba-shipment-id": shipment_id},
    }
    r = requests.post(url, auth=auth, headers=HEADERS, json=payload)
    r.raise_for_status()
    report_id = r.json()["reportId"]

    # Step 2: Poll until report is ready
    status_url = f"{BASE_URL}/reports/2021-06-30/reports/{report_id}"
    report_document_id = None
    while not report_document_id:
        r = requests.get(status_url, auth=auth, headers=HEADERS)
        r.raise_for_status()
        status = r.json()
        if status["processingStatus"] == "DONE":
            report_document_id = status["reportDocumentId"]
        elif status["processingStatus"] in ["CANCELLED", "FATAL"]:
            print(status)
            raise Exception("Report generation failed")
        else:
            time.sleep(10)  # wait and poll again

    # Step 3: Get the report document (download link)
    doc_url = f"{BASE_URL}/reports/2021-06-30/documents/{report_document_id}"
    r = requests.get(doc_url, headers=HEADERS)
    r.raise_for_status()
    doc_info = r.json()
    download_url = doc_info["url"]

    # Step 4: Download and parse the report data
    report_response = requests.get(download_url)
    report_response.raise_for_status()
    report_text = report_response.text  # Usually CSV or tab-delimited

    return report_text


# print(get_shipment_problems("FBA18ZD88842"))
# NEED AWS ACCOUNT WITH SP API ROLE TO TEST
def create_inbound_noncompliance_report(access_token, marketplace_id, signer_auth):
    url = "https://sellingpartnerapi-na.amazon.com/reports/2021-06-30/reports"
    headers = {"accept": "application/json", "x-amz-access-token": access_token}
    payload = {
        "reportType": "GET_FBA_FULFILLMENT_INBOUND_NONCOMPLIANCE_DATA",
        "marketplaceIds": [marketplace_id],
    }
    # `signer_auth` is your requests-compatible auth that performs SigV4
    r = requests.post(url, headers=headers, json=payload, auth=signer_auth)
    r.raise_for_status()
    return r.json()["reportId"]


# After download, simple filtering (CSV / tab-delimited):
def filter_report_for_shipment(report_text: str, shipment_id: str):
    # Split into lines
    lines = report_text.splitlines()
    if not lines:
        return []

    # First row is header
    header = lines[0].split("\t")

    # Safety check: make sure shipment-id column exists
    try:
        idx = header.index("fba-shipment-id")
    except ValueError:
        raise ValueError("Column 'fba-shipment-id' not found in report header")

    # Parse rows into dicts
    results = []
    for line in lines[1:]:
        if not line.strip():
            continue
        cols = line.split("\t")
        row = dict(zip(header, cols))
        if row.get("fba-shipment-id") == shipment_id:
            results.append(row)

    return results


reportid = create_inbound_noncompliance_report(ACCESS_TOKEN, MARKETPLACE_ID, auth)
print(reportid)
status_url = f"{BASE_URL}/reports/2021-06-30/reports/{reportid}"
report_document_id = None
while not report_document_id:
    r = requests.get(
        status_url, headers={"x-amz-access-token": ACCESS_TOKEN}, auth=auth
    )
    r.raise_for_status()
    status = r.json()
    if status["processingStatus"] == "DONE":
        report_document_id = status["reportDocumentId"]
    elif status["processingStatus"] in ["CANCELLED", "FATAL"]:
        raise Exception("Report generation failed")
    else:
        time.sleep(10)

doc_url = f"{BASE_URL}/reports/2021-06-30/documents/{report_document_id}"
r = requests.get(doc_url, headers={"x-amz-access-token": ACCESS_TOKEN}, auth=auth)
r.raise_for_status()
doc_info = r.json()
download_url = doc_info["url"]
report_response = requests.get(download_url)
report_response.raise_for_status()
report_text = report_response.text  # Usually CSV or tab-delimited
# Save to file for inspection
with open("report.txt", "w", encoding="utf-8") as f:
    f.write(report_text)

# print(filter_report_for_shipment(report_text="testing", shipment_id="FBA18ZD88842"))
