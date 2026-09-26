from fastapi import FastAPI, Request, HTTPException, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
import json
import os
from pydantic import BaseModel
import base64
import sqlite3
import csv
from io import StringIO
import httpx
import gzip
import io
import requests
import time
from datetime import datetime
import uuid


app = FastAPI()

# Allow all origins for testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store raw data in memory (for now)
stored_raw_data = {"raw_string": "", "items_count": 0}
# Store search key data in memory
stored_search_key_data = {"data": [], "saved_at": None, "unit": "search_key"}
# Store Amazon checking status in memory
# This will hold the status of the Amazon checking process
amazon_checking_status = {"status": None, "updated_at": None}
# Store checked data in memory
stored_checked_data = {"results": {}, "skipped": [], "timestamp": None}
BASE_URL = "https://sellingpartnerapi-na.amazon.com"
LWA_CLIENT_ID = os.getenv("LWA_CLIENT_ID", "").strip()
LWA_CLIENT_SECRET = os.getenv("LWA_CLIENT_SECRET", "").strip()
LWA_REFRESH_TOKEN = os.getenv("LWA_REFRESH_TOKEN", "").strip()
DB_PATH = os.getenv("AMAVA_LEGACY_DB_PATH", "amava_data.db")

_access_token: str | None = None
_access_token_expires_at = 0.0


class Screenshot(BaseModel):
    image_data: str
    filename: str = None


SAVE_DIR = "screenshots"
LATEST_IMAGE_PATH = os.path.join(SAVE_DIR, "latest_screenshot.png")
os.makedirs(SAVE_DIR, exist_ok=True)
# Backend URL for agent communication
# This should be the URL where your agent backend is running
# Store Amazon checking status in memory
AGENT_BACKEND = "http://localhost:1483"


@app.post("/apps/{app_name}/users/{user_id}/sessions/{session_id}")
async def proxy_session(app_name: str, user_id: str, session_id: str, request: Request):
    body = await request.body()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{AGENT_BACKEND}/apps/{app_name}/users/{user_id}/sessions/{session_id}",
            content=body,
            headers=request.headers,
        )
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type"),
    )


@app.post("/run")
async def proxy_run(request: Request):
    body = await request.body()
    async with httpx.AsyncClient(timeout=60.0) as client:  # 60 seconds timeout
        try:
            resp = await client.post(
                f"{AGENT_BACKEND}/run", content=body, headers=request.headers
            )
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                media_type=resp.headers.get("content-type"),
            )
        except httpx.ReadTimeout:
            return JSONResponse(
                content={"status": "error", "error": "Backend timed out"},
                status_code=504,
            )
        except Exception as e:
            return JSONResponse(
                content={"status": "error", "error": str(e)}, status_code=500
            )


@app.post("/api/scraped_dataresults")
async def receive_scraped_data(request: Request):
    raw_text = await request.body()
    raw_str = raw_text.decode("utf-8")
    print(
        "Received raw scraped data:", raw_str[:200]
    )  # Print first 200 chars for debugging

    try:
        parsed_data = json.loads(raw_str)
        stored_raw_data["raw_string"] = raw_str
        stored_raw_data["items_count"] = len(parsed_data)

        # Save to DB
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO scraped_data (raw_string, items_count, saved_at) VALUES (?, ?, ?)",
            (raw_str, len(parsed_data), datetime.utcnow().isoformat()),
        )
        conn.commit()
        conn.close()

        return JSONResponse(
            content={
                "status": "success",
                "message": "Data stored successfully",
                "items_count": len(parsed_data),
            }
        )
    except Exception as e:
        return JSONResponse(
            content={"status": "error", "error": str(e)}, status_code=400
        )


@app.get("/api/get_scraped_data")
async def get_scraped_data():
    return JSONResponse(
        content={
            "status": "success",
            "raw_string": stored_raw_data["raw_string"],
            "items_count": stored_raw_data["items_count"],
        }
    )


@app.post("/upload-screenshot")
async def upload_screenshot(data: Screenshot):
    if not data.image_data.startswith("data:image/png;base64,"):
        raise HTTPException(status_code=400, detail="Invalid image data format")

    # Decode Base64 image
    try:
        header, encoded = data.image_data.split(",", 1)
        image_bytes = base64.b64decode(encoded)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Image decoding failed: {str(e)}")

    # Save the image (overwrite the latest every time)
    with open(LATEST_IMAGE_PATH, "wb") as f:
        f.write(image_bytes)

    return {"status": "success", "message": "Image saved", "path": LATEST_IMAGE_PATH}


@app.get("/get-screenshot")
async def get_screenshot():
    if not os.path.exists(LATEST_IMAGE_PATH):
        raise HTTPException(status_code=404, detail="No screenshot available")
    return FileResponse(LATEST_IMAGE_PATH, media_type="image/png")


@app.post("/checkeddata")
async def receive_checked_data(request: Request):
    try:
        data = await request.json()
        # Store in memory
        stored_checked_data["results"] = data.get("results", {})
        stored_checked_data["skipped"] = data.get("skipped", [])
        stored_checked_data["timestamp"] = datetime.utcnow().isoformat()
        stored_checked_data["unit"] = data.get("unit", "search_key")
        # Save to DB
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO checked_data (results, skipped, timestamp) VALUES (?, ?, ?)",
            (
                json.dumps(stored_checked_data["results"]),
                json.dumps(stored_checked_data["skipped"]),
                stored_checked_data["timestamp"],
            ),
        )
        conn.commit()
        conn.close()
        return {"status": "success", "message": "Checked data received and stored."}
    except Exception as e:
        return JSONResponse(
            content={"status": "error", "error": str(e)}, status_code=400
        )


@app.get("/checkeddata")
async def get_checked_data():

    if not stored_checked_data["results"]:
        return JSONResponse(
            content={"status": "empty", "message": "No checked data available."},
            status_code=404,
        )
    return JSONResponse(
        content={"status": "success", "checked_data": stored_checked_data}
    )


@app.get("/exceldata")
async def get_merged_excel_data():
    # Try to get scraped data from multiple possible locations
    scraped = []
    # 1. Try raw_string (current in-memory)
    try:
        if stored_raw_data.get("raw_string"):
            scraped = json.loads(stored_raw_data["raw_string"])
            # print("Loaded scraped from raw_string:", type(scraped), scraped if not isinstance(scraped, list) else len(scraped))
    except Exception as e:
        print("Error loading scraped from raw_string:", e)
        scraped = []
    # If scraped is a dict with a 'data' key, use that
    if isinstance(scraped, dict) and "data" in scraped:
        scraped = scraped["data"]
        print("Extracted scraped['data']:", type(scraped), len(scraped))
    # 2. If still empty, try to get latest from DB
    if not scraped:
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT raw_string FROM scraped_data ORDER BY id DESC LIMIT 1")
            row = c.fetchone()
            if row and row[0]:
                scraped = json.loads(row[0])
                # print("Loaded scraped from DB:", type(scraped), scraped if not isinstance(scraped, list) else len(scraped))
            conn.close()
        except Exception as e:
            print("Error loading scraped from DB:", e)
            scraped = []
        if isinstance(scraped, dict) and "data" in scraped:
            scraped = scraped["data"]
            print("Extracted scraped['data'] from DB:", type(scraped), len(scraped))
    # 3. If still empty, try search_key_data (if you want to support that as a fallback)
    # if not scraped and stored_search_key_data.get("data"):
    #     scraped = stored_search_key_data["data"]

    # Ensure amazon is a dict, not a string
    amazon = stored_checked_data.get("results", {})
    # if isinstance(amazon, str):
    #     try:
    #         amazon = json.loads(amazon)
    #         print("Loaded amazon from string.")
    #     except Exception as e:
    #         print("Error loading amazon from string:", e)
    #         amazon = {}

    # print("Final scraped:", type(scraped), len(scraped) if isinstance(scraped, list) else scraped)
    # print("Final amazon:", type(amazon), len(amazon) if isinstance(amazon, dict) else amazon)

    merged = []
    for item in scraped:
        if not isinstance(item, dict):
            print("Skipping non-dict item in scraped:", item)
            continue  # Skip if item is not a dict
        search_key = item.get("search_key") or item.get("unit")
        amazon_data = amazon.get(search_key, [])

        # Filter out unwanted statuses
        filtered_amazon_data = [
            d
            for d in amazon_data
            # if d.get("status") not in ["Copy Listing", "Apply to sell"]
        ]
        item_with_amazon = dict(item)
        item_with_amazon["amazon_data"] = filtered_amazon_data
        merged.append(item_with_amazon)

    print("Merged count:", len(merged))
    if merged:
        print("Fifth merged item:", merged[6])

    return JSONResponse(
        content={
            "status": "success",
            "merged_data": merged,
            "scraped_count": len(scraped),
            "merged_count": len(merged),
        }
    )


def get_merged_forcal():
    # Try to get scraped data from multiple possible locations
    scraped = []
    # 1. Try raw_string (current in-memory)
    try:
        if stored_raw_data.get("raw_string"):
            scraped = json.loads(stored_raw_data["raw_string"])
            # print("Loaded scraped from raw_string:", type(scraped), scraped if not isinstance(scraped, list) else len(scraped))
    except Exception as e:
        print("Error loading scraped from raw_string:", e)
        scraped = []
    # If scraped is a dict with a 'data' key, use that
    if isinstance(scraped, dict) and "data" in scraped:
        scraped = scraped["data"]
        # print("Extracted scraped['data']:", type(scraped), len(scraped))
    # 2. If still empty, try to get latest from DB
    if not scraped:
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT raw_string FROM scraped_data ORDER BY id DESC LIMIT 1")
            row = c.fetchone()
            if row and row[0]:
                scraped = json.loads(row[0])
                # print("Loaded scraped from DB:", type(scraped), scraped if not isinstance(scraped, list) else len(scraped))
            conn.close()
        except Exception as e:
            print("Error loading scraped from DB:", e)
            scraped = []
        if isinstance(scraped, dict) and "data" in scraped:
            scraped = scraped["data"]
            print("Extracted scraped['data'] from DB:", type(scraped), len(scraped))
    # 3. If still empty, try search_key_data (if you want to support that as a fallback)
    # if not scraped and stored_search_key_data.get("data"):
    #     scraped = stored_search_key_data["data"]

    # Ensure amazon is a dict, not a string
    amazon = stored_checked_data.get("results", {})
    # if isinstance(amazon, str):
    #     try:
    #         amazon = json.loads(amazon)
    #         print("Loaded amazon from string.")
    #     except Exception as e:
    #         print("Error loading amazon from string:", e)
    #         amazon = {}

    # print("Final scraped:", type(scraped), len(scraped) if isinstance(scraped, list) else scraped)
    # print("Final amazon:", type(amazon), len(amazon) if isinstance(amazon, dict) else amazon)

    merged = []
    for item in scraped:
        if not isinstance(item, dict):
            print("Skipping non-dict item in scraped:", item)
            continue  # Skip if item is not a dict
        search_key = item.get("search_key") or item.get("unit")
        amazon_data = amazon.get(search_key, [])

        # Filter out unwanted statuses
        filtered_amazon_data = [
            d
            for d in amazon_data
            # if d.get("status") not in ["Copy Listing", "Apply to sell"]
        ]
        item_with_amazon = dict(item)
        item_with_amazon["amazon_data"] = filtered_amazon_data
        merged.append(item_with_amazon)

    print("Merged count:", len(merged))
    if merged:
        print("Fifth merged item:", merged[6])

    merged_data = {
        "status": "success",
        "merged_data": merged,
        "scraped_count": len(scraped),
        "merged_count": len(merged),
    }
    return merged_data


@app.get("/excelcsv")
async def get_merged_csv():
    # Get merged data as in /exceldata
    try:
        scraped = (
            json.loads(stored_raw_data["raw_string"])
            if stored_raw_data["raw_string"]
            else []
        )
    except Exception:
        scraped = []
    checked = stored_checked_data.get("results", {})
    skipped = stored_checked_data.get("skipped", [])

    merged = []
    for item in scraped:
        search_key = item.get("search_key")
        merged_item = dict(item)
        checked_info = checked.get(search_key, [])
        merged_item["amazon_results"] = checked_info
        merged.append(merged_item)
    scraped_upcs = {item.get("search_key") for item in scraped}
    for skip in skipped:
        search_key = skip.get("productUPC")
        if search_key and search_key not in scraped_upcs:
            merged.append(
                {"search_key": search_key, "amazon_results": [], "skipped": True}
            )

    # Prepare CSV
    output = StringIO()
    fieldnames = list(merged[0].keys()) if merged else []
    # Flatten amazon_results for CSV
    if "amazon_results" in fieldnames:
        fieldnames.remove("amazon_results")
        fieldnames += ["amazon_asin", "amazon_status", "amazon_salesrank"]

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in merged:
        base = {k: v for k, v in row.items() if k != "amazon_results"}
        results = row.get("amazon_results", [])
        if results:
            for res in results:
                outrow = dict(base)
                outrow["amazon_asin"] = res.get("productASIN")
                outrow["amazon_status"] = res.get("status")
                outrow["amazon_salesrank"] = res.get("salesrank")
                writer.writerow(outrow)
        else:
            outrow = dict(base)
            outrow["amazon_asin"] = ""
            outrow["amazon_status"] = ""
            outrow["amazon_salesrank"] = ""
            writer.writerow(outrow)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=merged_data.csv"},
    )


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Table for scraped data
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS scraped_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_string TEXT,
            items_count INTEGER,
            saved_at TEXT
        )
    """
    )
    # Table for checked data
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS checked_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            results TEXT,
            skipped TEXT,
            timestamp TEXT
        )
    """
    )
    conn.commit()
    conn.close()


init_db()


def restore_last_data():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Restore scraped data
    c.execute(
        "SELECT raw_string, items_count FROM scraped_data ORDER BY id DESC LIMIT 1"
    )
    row = c.fetchone()
    if row:
        stored_raw_data["raw_string"], stored_raw_data["items_count"] = row
    # Restore checked data
    c.execute(
        "SELECT results, skipped, timestamp FROM checked_data ORDER BY id DESC LIMIT 1"
    )
    row = c.fetchone()
    if row:
        stored_checked_data["results"] = json.loads(row[0])
        stored_checked_data["skipped"] = json.loads(row[1])
        stored_checked_data["timestamp"] = row[2]
    conn.close()


restore_last_data()


def merge_scraped_and_amazon(
    scraped_path, amazon_path, output_path="merged_output.json"
):
    with open(scraped_path, "r", encoding="utf-8") as f:
        scraped = json.load(f)
    with open(amazon_path, "r", encoding="utf-8") as f:
        amazon = json.load(f)

    merged = []
    for item in scraped:
        search_key = item.get("search_key")
        amazon_data = amazon.get(search_key, [])
        # Filter out unwanted statuses
        filtered_amazon_data = [
            d
            for d in amazon_data
            if d.get("status") not in ["Copy Listing", "Apply to sell"]
        ]
        if filtered_amazon_data:
            item["amazon_data"] = filtered_amazon_data
            merged.append(item)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2)
    print(f"Merged data saved to {output_path}")


# Example usage:
# merge_scraped_and_amazon("scraped.json", "amazon_checked.json")
@app.post("/amazon-checking-status")
async def set_amazon_checking_status(request: Request):
    try:
        data = await request.json()
        status = data.get("status")
        if not status:
            return JSONResponse(
                content={"status": "error", "error": "Missing 'status' field."},
                status_code=400,
            )
        amazon_checking_status["status"] = status
        amazon_checking_status["updated_at"] = datetime.utcnow().isoformat()
        return JSONResponse(
            content={"status": "success", "message": f"Status set to '{status}'."}
        )
    except Exception as e:
        return JSONResponse(
            content={"status": "error", "error": str(e)}, status_code=400
        )


@app.get("/amazon-checking-status")
async def get_amazon_checking_status():
    return JSONResponse(
        content={"status": "success", "amazon_checking_status": amazon_checking_status}
    )


@app.post("/search-key")
async def save_search_key(request: Request):
    print("/search-key endpoint called.")
    try:
        data = await request.json()
        # Accept both legacy (list) and new (dict) formats
        if isinstance(data, dict) and "values" in data:
            values = data["values"]
        elif isinstance(data, list):
            values = data
        else:
            return JSONResponse(
                content={
                    "status": "error",
                    "error": "Input must be a list or dict with 'values'.",
                },
                status_code=400,
            )

        if not isinstance(values, list):
            return JSONResponse(
                content={"status": "error", "error": "'values' must be a list."},
                status_code=400,
            )

        stored_search_key_data["data"] = values
        stored_search_key_data["saved_at"] = datetime.utcnow().isoformat()
        stored_search_key_data["unit"] = data["unit"]
        # write stored_search_key_data to a file
        with open("search_key_data.json", "w") as f:
            json.dump(stored_search_key_data, f, indent=2)

        # Save to DB
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS search_key_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT,
                saved_at TEXT
            )
        """
        )
        c.execute(
            "INSERT INTO search_key_data (data, saved_at) VALUES (?, ?)",
            (json.dumps(values), stored_search_key_data["saved_at"]),
        )
        conn.commit()
        conn.close()

        return JSONResponse(
            content={
                "status": "success",
                "message": "Search key data saved.",
                "count": len(values),
            }
        )
    except Exception as e:
        return JSONResponse(
            content={"status": "error", "error": str(e)}, status_code=400
        )


@app.get("/search-key")
async def get_search_key():
    return JSONResponse(
        content={
            "status": "success",
            "data": stored_search_key_data["data"],
            "unit": stored_search_key_data["unit"],
            "saved_at": stored_search_key_data["saved_at"],
        }
    )


@app.delete("/remove-checkeddata")
async def remove_checked_data():
    # Clear in-memory checked data
    stored_checked_data["results"] = {}
    stored_checked_data["skipped"] = []
    stored_checked_data["timestamp"] = None

    # Delete all checked data from the database
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM checked_data")
    conn.commit()
    conn.close()

    return {"status": "success", "message": "All checked data removed."}


def get_access_token() -> str:
    """Return a cached LWA token, refreshing it shortly before expiration."""
    global _access_token, _access_token_expires_at

    if _access_token and time.time() < _access_token_expires_at - 60:
        return _access_token

    missing = [
        name
        for name, value in (
            ("LWA_CLIENT_ID", LWA_CLIENT_ID),
            ("LWA_CLIENT_SECRET", LWA_CLIENT_SECRET),
            ("LWA_REFRESH_TOKEN", LWA_REFRESH_TOKEN),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing legacy SP-API environment variables: " + ", ".join(missing)
        )

    response = requests.post(
        "https://api.amazon.com/auth/o2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": LWA_REFRESH_TOKEN,
            "client_id": LWA_CLIENT_ID,
            "client_secret": LWA_CLIENT_SECRET,
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    _access_token = payload["access_token"]
    _access_token_expires_at = time.time() + int(payload.get("expires_in", 3600))
    return _access_token


def get_spapi_headers(**extra: str) -> dict[str, str]:
    return {
        "accept": "application/json",
        "x-amz-access-token": get_access_token(),
        **extra,
    }


MARKETPLACE_ID = "ATVPDKIKX0DER"


def request_today_orders_report():
    now = datetime.utcnow()
    start_time = (
        now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + "Z"
    )
    end_time = (
        now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat() + "Z"
    )
    payload = {
        "reportType": "GET_FLAT_FILE_ALL_ORDERS_DATA_BY_ORDER_DATE_GENERAL",
        "marketplaceIds": ["ATVPDKIKX0DER"],
        "dataStartTime": start_time,
        "dataEndTime": end_time,
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "x-amz-access-token": get_access_token(),
    }
    resp = requests.post(
        f"{BASE_URL}/reports/2021-06-30/reports", json=payload, headers=headers
    )
    return resp.json().get("reportId")


def check_report_status(report_id):
    headers = {"accept": "application/json", "x-amz-access-token": get_access_token()}
    url = f"{BASE_URL}/reports/2021-06-30/reports/{report_id}"
    resp = requests.get(url, headers=headers)
    return resp.json().get("reportDocumentId")


def download_report_csv(report_document_id):
    headers = {"accept": "application/json", "x-amz-access-token": get_access_token()}
    url = f"{BASE_URL}/reports/2021-06-30/documents/{report_document_id}"
    resp = requests.get(url, headers=headers)
    data = resp.json()
    download_url = data.get("url")
    compression = data.get("compressionAlgorithm")

    if not download_url:
        return None

    file_response = requests.get(download_url)
    if compression == "GZIP":
        content = gzip.decompress(file_response.content).decode("utf-8")
    else:
        content = file_response.text

    return content


@app.get("/todays-sales")
async def get_todays_sales():
    try:
        report_id = request_today_orders_report()
        if not report_id:
            return JSONResponse(
                {"status": "error", "message": "Failed to request report."}, 500
            )

        # Poll for report readiness
        document_id = None
        for _ in range(10):
            time.sleep(5)
            document_id = check_report_status(report_id)
            if document_id:
                break

        if not document_id:
            return JSONResponse(
                {"status": "error", "message": "Report not ready in time."}, 504
            )

        # Download and parse
        csv_text = download_report_csv(document_id)
        if not csv_text:
            return JSONResponse({"status": "error", "message": "Download failed."}, 500)

        reader = csv.DictReader(io.StringIO(csv_text), delimiter="\t")
        sales_data = []

        for idx, row in enumerate(reader):
            sales_data.append(
                {
                    "id": idx + 1,
                    "amazon_order_id": row.get("amazon-order-id", "").strip(),
                    "purchase_date": row.get("purchase-date", "").strip(),
                    "order_status": row.get("order-status", "").strip(),
                    "product_name": row.get("product-name", "").strip(),
                    "sku": row.get("sku", "").strip(),
                    "asin": row.get("asin", "").strip(),
                    "quantity": int(row.get("quantity", "0")),
                    "currency": row.get("currency", "USD").strip(),
                    "item_price": float(row.get("item-price", "0") or 0),
                    "ship_city": row.get("ship-city", "").strip(),
                    "ship_state": row.get("ship-state", "").strip(),
                    "ship_postal_code": row.get("ship-postal-code", "").strip(),
                    "ship_country": row.get("ship-country", "").strip(),
                    "fulfillment_channel": row.get("fulfillment-channel", "").strip(),
                    "sales_channel": row.get("sales-channel", "").strip(),
                    "ship_service_level": row.get("ship-service-level", "").strip(),
                }
            )

        return JSONResponse({"status": "success", "sales_data": sales_data})

    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, 500)


@app.get("/sales-metrics")
def get_sales_metrics(start_date: str = Query(...), end_date: str = Query(...)):
    try:
        # Define time window (last 7 days)
        start_time = datetime.fromisoformat(start_date)
        end_time = datetime.fromisoformat(end_date)
        interval = f"{start_time.isoformat()}Z--{end_time.isoformat()}Z"

        url = "https://sellingpartnerapi-na.amazon.com/sales/v1/orderMetrics"
        params = {
            # "sellerId": SELLER_ID,
            "marketplaceIds": "ATVPDKIKX0DER",
            "granularity": "Day",
            "granularityTimeZone": "UTC",
            "interval": interval,
        }

        headers = {"Accept": "application/json", "x-amz-access-token": get_access_token()}

        resp = requests.get(url, params=params, headers=headers)
        resp.raise_for_status()

        data = resp.json().get("payload", [])
        return JSONResponse(content={"status": "success", "data": data})

    except requests.RequestException as e:
        return JSONResponse(
            content={"status": "error", "message": str(e)}, status_code=500
        )


def get_lowest_fba_price(asin):
    url = f"{BASE_URL}/products/pricing/v0/items/{asin}/offers"
    params = {"MarketplaceId": MARKETPLACE_ID, "ItemCondition": "New"}
    resp = requests.get(url, headers=get_spapi_headers(), params=params)
    data = resp.json()
    # print(json.dumps(data, indent=2))
    try:
        summary = data["payload"]["Summary"]
        lowest_prices = summary.get("LowestPrices", [])
        fba_prices = []
        FBMorFBA = None
        for p in lowest_prices:
            if p.get("fulfillmentChannel") == "Amazon":
                fba_prices.append(p["LandedPrice"]["Amount"])
                FBMorFBA = True
            elif p.get("fulfillmentChannel") == "Merchant":
                # Assume $4 shipping for Merchant
                fba_prices.append(p["LandedPrice"]["Amount"] - 4.00)
                FBMorFBA = False

        print(fba_prices, FBMorFBA)

        return (
            min(fba_prices) if fba_prices else None
        ), FBMorFBA  # Get if FBA or MFN "Amazon" if fba_prices else "Merchant" False

    except Exception as e:
        print("Error extracting FBA price:", e)
        return None


def get_fba_fees(asin, price, IsAmazonFulfilled):
    url = f"{BASE_URL}/products/fees/v0/items/{asin}/feesEstimate"
    request_id = str(uuid.uuid4())

    payload = {
        "FeesEstimateRequest": {
            "MarketplaceId": MARKETPLACE_ID,
            "IdType": "ASIN",
            "IdValue": asin,
            "IsAmazonFulfilled": IsAmazonFulfilled,
            "PriceToEstimateFees": {
                "ListingPrice": {"CurrencyCode": "USD", "Amount": price}
            },
            "Identifier": request_id,
        }
    }

    resp = requests.post(url, headers=get_spapi_headers(), json=payload)
    data = resp.json()
    # print(json.dumps(data, indent=2))

    try:
        fees = data["payload"]["FeesEstimateResult"]["FeesEstimate"]
        total_fee = float(fees["TotalFeesEstimate"]["Amount"])

        # Extract fulfilment fee specifically
        fulfilment_fee = 0.0
        for fee in fees.get("FeeDetailList", []):
            if fee["FeeType"] == "FBAFees":
                for included in fee.get("IncludedFeeList", []):
                    if included["FeeType"] == "FBAPerUnitFulfillmentFee":
                        fulfilment_fee = float(included["FinalFee"]["Amount"])

        return {"total_fee": total_fee, "fulfilment_fee": fulfilment_fee}
    except Exception as e:
        print("Error extracting FBA fee:", e)
        return None


def calculate_asin_profit(asin, cost_price):
    price, IsAmazonFulfilled = get_lowest_fba_price(asin)
    print(price, cost_price)
    if price is None:
        print("❌ No valid FBA price found.")
        return
    fees = get_fba_fees(asin, price, IsAmazonFulfilled)
    if not fees:
        return
    profit = round(price - fees["total_fee"] - cost_price, 2)

    print(
        f"ASIN: {asin} | Price: {price:.2f} | Fulfilment: {fees['fulfilment_fee']:.2f} | "
        f"Total Fees: {fees['total_fee']:.2f} | Cost: {cost_price:.2f} => Net: {profit:.2f}"
    )

    result = {
        "asin": asin,
        "price": price,
        "fees": fees["total_fee"],
        "cost": cost_price,
        "profit": profit,
    }
    return result


class ProfitRequest(BaseModel):
    asin: str
    cost: float


@app.post("/fba-profit-calculator")
async def fba_profit_calculator(data: ProfitRequest):
    try:
        result = calculate_asin_profit(data.asin, data.cost)
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(
            content={"status": "error", "message": str(e)}, status_code=500
        )


@app.post("/revcalall")
async def revcalall():
    try:
        print("Waiting for 3 seconds to ensure data is ready...")
        # ✅ Await the async function
        print("Fetching merged data for revenue calculation...")
        merged_response = get_merged_forcal()
        merged_data = merged_response
        print("Fetched merged data successfully.")
        # print(merged_data["merged_data"])
        # print("Sample merged_data:", type(merged_data["merged_data"]))

        # print(
        #     f"item: type:{merged_data['merged_data'][6]['Our Price']} ",
        #     merged_data["merged_data"][6],
        # )
        results = []
        for item in merged_data["merged_data"]:
            asin = item.get("search_key") or item.get("ASIN")
            cost = item.get("Unit Price") or item.get("Our Price") or 0.0
            # 🔍 Debug: Print first 3 entries
            # print("Sample merged_data:", merged_data[:3])

            if asin and cost:
                try:
                    profit_data = calculate_asin_profit(asin, float(cost))
                    # wait 3 seconds after each call of calculate_asin_profit
                    time.sleep(1)
                    if profit_data:
                        results.append(profit_data)
                except Exception as e:
                    print(f"Error calculating profit for {asin}: {e}")
        # Add the results to merged_data then save that merged_data to DB
        merged_data["prices"] = results
        print("Calculated profits for all items.", merged_data["prices"])
        # Also save the results to a JSON file for reference
        with open("fba_profit_results.json", "w") as f:
            json.dump(merged_data, f, indent=2)
        return JSONResponse(content={"status": "success", "data": results})

    except Exception as e:
        print(str(e))
        return JSONResponse(
            content={"status": "error", "message": str(e)}, status_code=500
        )


def get_inventory_summaries():
    url = f"{BASE_URL}/fba/inventory/v1/summaries"
    params = {
        "details": True,
        "marketplaceIds": [MARKETPLACE_ID],
        "granularityType": "Marketplace",
        "granularityId": MARKETPLACE_ID,
        "startDateTime": "2025-01-01T00:00:00Z",  # you can adjust timeframe
    }

    resp = requests.get(url, headers=get_spapi_headers(), params=params)
    data = resp.json()

    items = []
    for record in data.get("payload", {}).get("inventorySummaries", []):
        items.append(
            {
                "asin": record.get("asin"),
                "sku": record.get("sellerSku"),
                "quantity": record.get("totalQuantity", 0),
            }
        )
    return items


def extract_price(price_obj):
    """Safely extract numeric price from Amazon price dict."""
    if isinstance(price_obj, dict):
        return float(price_obj.get("Amount", 0))
    return 0.0


def get_catalog_item(asin: str):
    url = f"{BASE_URL}/catalog/2022-04-01/items/{asin}"
    params = {"marketplaceIds": [MARKETPLACE_ID]}
    resp = requests.get(url, headers=get_spapi_headers(), params=params)
    data = resp.json()
    payload = data.get("payload", {})

    summaries = payload.get("summaries", [])
    item_name = summaries[0].get("itemName") if summaries else None
    brand = summaries[0].get("brand") if summaries else None

    return {
        "title": item_name,
        "brand": brand,
        "raw": payload,  # keep raw for debugging if needed
    }


@app.get("/myinventory")
async def my_inventory():
    try:
        url = f"{BASE_URL}/fba/inventory/v1/summaries"
        params = {
            "details": "true",
            "granularityType": "Marketplace",
            "granularityId": MARKETPLACE_ID,
            "marketplaceIds": [MARKETPLACE_ID],
        }
        resp = requests.get(url, headers=get_spapi_headers(), params=params)
        data = resp.json()
        # Save data in json file too
        with open("inventory_data.json", "w") as f:
            json.dump(data, f, indent=2)

        summaries = data.get("payload", {}).get("inventorySummaries", [])

        inventory = []
        for item in summaries:
            asin = item.get("asin")

            # Catalog API → title, brand
            cat_url = f"{BASE_URL}/catalog/2022-04-01/items/{asin}"
            cat_resp = requests.get(
                cat_url,
                headers=get_spapi_headers(),
                params={
                    "marketplaceIds": MARKETPLACE_ID,
                    "includedData": "summaries,images",
                },
            )
            cat_data = cat_resp.json()
            title = None
            brand = None
            image = None
            try:
                if "summaries" in cat_data and len(cat_data["summaries"]) > 0:
                    summary = cat_data["summaries"][0]
                    title = summary.get("itemName")
                    brand = summary.get("brand")
                if "images" in cat_data and len(cat_data["images"]) > 0:
                    image = cat_data["images"][0]["images"][0].get("link")
            except Exception:
                pass

            # Pricing API → FBA price
            price_url = f"{BASE_URL}/products/pricing/v0/items/{asin}/offers"
            price_resp = requests.get(
                price_url,
                headers=get_spapi_headers(),
                params={"MarketplaceId": MARKETPLACE_ID, "ItemCondition": "New"},
            )
            price_data = price_resp.json()
            fba_price = None
            try:
                lowest = price_data["payload"]["Summary"]["LowestPrices"]
                fba_offers = [
                    p["LandedPrice"]["Amount"]
                    for p in lowest
                    if p.get("condition") == "new"
                    and p.get("fulfillmentChannel") == "Amazon"
                ]
                if fba_offers:
                    fba_price = min(fba_offers)
            except Exception:
                pass

            # Add these to inventory json file
            with open("detailed_inventory_data.json", "a") as f:
                json.dump(
                    {
                        "asin": asin,
                        "title": title,
                        "brand": brand,
                        "image": image,
                        "fba_price": fba_price,
                    },
                    f,
                )
                f.write("\n")

            inventory.append(
                {
                    "asin": asin,
                    "title": title,
                    "brand": brand,
                    "image": image,
                    "fba_price": fba_price,
                }
            )

        return JSONResponse(content={"status": "success", "inventory": inventory})

    except Exception as e:
        return JSONResponse(
            content={"status": "error", "message": str(e)}, status_code=500
        )


@app.get("/myinventory-csv")
async def myinventory_csv():
    try:
        # 1. Fetch inventory (your existing function)
        inventory = get_inventory_summaries()  # should return list of ASINs + SKUs

        # Create CSV buffer
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "id",
                "type",
                "sku",
                "name",
                "short_description",
                "description",
                "price",
                "regular_price",
                "sale_price",
                "categories",
                "images",
                "stock_status",
                "manage_stock",
                "stock_quantity",
                "weight",
                "length",
                "width",
                "height",
                "brand",
                "visibility",
                "tax_class",
                "shipping_class",
                "backorders",
                "sold_individually",
                "upsell_ids",
                "cross_sell_ids",
                "external_url",
            ],
        )
        writer.writeheader()

        # 2. Loop through inventory ASINs
        for i, item in enumerate(inventory, start=1):
            asin = item.get("asin")
            sku = item.get("sku")

            # Get catalog details
            catalog = get_catalog_item(asin)
            summaries = catalog.get("summaries", [{}])
            summary = summaries[0] if summaries else {}

            # Get pricing
            price = None
            try:
                price = get_lowest_fba_price(asin)
            except:
                price = None

            # Image
            images = catalog.get("images", [])
            image_url = images[0]["images"][0]["link"] if images else ""

            # Write row to CSV
            writer.writerow(
                {
                    "id": i,
                    "type": "simple",
                    "sku": sku or "",
                    "name": summary.get("itemName", ""),
                    "short_description": summary.get("brand", ""),
                    "description": f"ASIN: {asin}",
                    "price": price or "",
                    "regular_price": price or "",
                    "sale_price": "",
                    "categories": summary.get("websiteDisplayGroupName", ""),
                    "images": image_url,
                    "stock_status": "instock",
                    "manage_stock": "yes",
                    "stock_quantity": item.get("quantity", ""),
                    "weight": "",
                    "length": "",
                    "width": "",
                    "height": "",
                    "brand": summary.get("brand", ""),
                    "visibility": "visible",
                    "tax_class": "",
                    "shipping_class": "",
                    "backorders": "no",
                    "sold_individually": "no",
                    "upsell_ids": "",
                    "cross_sell_ids": "",
                    "external_url": "",
                }
            )

            # 3. Sleep to respect API rate limits
            time.sleep(1)

        output.seek(0)

        # Return CSV as downloadable file
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=myinventory.csv"},
        )

    except Exception as e:
        return {"error": str(e)}


app.get("/allfbashipments")


async def all_fba_shipments():
    url = f"{BASE_URL}/fba/inbound/v0/shipments"
    params = {"ShipmentStatusList": "WORKING,SHIPPED,RECEIVING,CLOSED"}
    r = requests.get(url, headers=get_spapi_headers(), params=params)
    r.raise_for_status()
    return r.json()


app.get("/getfbashipment/{shipment_id}")


async def get_fba_shipment(shipment_id: str):
    # 1. Shipment header info
    url1 = f"{BASE_URL}/fba/inbound/v0/shipments"
    params1 = {"ShipmentIdList": shipment_id}
    r1 = requests.get(url1, headers=get_spapi_headers(), params=params1)
    r1.raise_for_status()
    shipment_summary = r1.json()

    # 2. Shipment items
    url2 = f"{BASE_URL}/fba/inbound/v0/shipments/{shipment_id}/items"
    r2 = requests.get(url2, headers=get_spapi_headers())
    r2.raise_for_status()
    shipment_items = r2.json()

    # 3. Shipment tracking
    url3 = f"{BASE_URL}/fba/inbound/v0/shipments/{shipment_id}/tracking"
    r3 = requests.get(url3, headers=get_spapi_headers())
    if r3.status_code == 200:
        shipment_tracking = r3.json()
    else:
        shipment_tracking = {"message": "No tracking available"}

    return {
        "summary": shipment_summary,
        "items": shipment_items,
        "tracking": shipment_tracking,
    }
