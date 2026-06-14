import json
import sys
from openpyxl import Workbook


def extract_rows(data):
    rows = []

    for item in data:
        title = item.get("title", "")
        price = item.get("price", "")
        stock = item.get("stock", "")
        url = item.get("product_url", "")
        if url == "":
            url = item.get("url", "")
        

        amazon_entries = item.get("amazon_data", [])

        for entry in amazon_entries:
            rows.append({
                "Title": title,
                "Price": price,
                "Stock": stock,
                "ASIN": entry.get("productASIN", ""),
                "Status": entry.get("status", ""),
                "Product URL": url
            })

    return rows


def json_to_excel(input_file, output_file):
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    rows = extract_rows(data)

    wb = Workbook()
    ws = wb.active
    ws.title = "Merged Data"

    headers = ["Title", "Price", "Stock", "ASIN", "Status", "Product URL"]
    ws.append(headers)

    for row in rows:
        ws.append([
            row["Title"],
            row["Price"],
            row["Stock"],
            row["ASIN"],
            row["Status"],
            row["Product URL"]
        ])

    wb.save(output_file)
    print(f"✅ Excel created: {output_file} ({len(rows)} rows)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python script.py input.json output.xlsx")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    json_to_excel(input_file, output_file)