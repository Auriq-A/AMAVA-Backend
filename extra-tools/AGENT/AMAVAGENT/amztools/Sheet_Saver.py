import re
from pathlib import Path
from typing import Sequence

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_ID = "1vEiKej9FRISt8NynDNmVZy_M47nw-RrYSYeJIvubVwk"
HEADERS = ["Product Detail", "Product ASIN", "Status"]


def _worksheet_title(name: str) -> str:
    title = re.sub(r"[\[\]:*?/\\]", "_", name).strip()[:100]
    return title or "Products"


def Save(data: Sequence[Sequence[str]], worksheet_name: str) -> None:
    """Append product rows to the worksheet named for their brand or category."""
    if not data:
        return

    credentials_path = Path(__file__).resolve().with_name("credentials.json")
    credentials = Credentials.from_service_account_file(
        str(credentials_path), scopes=SCOPES
    )
    client = gspread.authorize(credentials)
    workbook = client.open_by_key(SHEET_ID)
    title = _worksheet_title(worksheet_name)

    try:
        worksheet = workbook.worksheet(title)
    except gspread.WorksheetNotFound:
        worksheet = workbook.add_worksheet(title=title, rows=100, cols=len(HEADERS))

    if not worksheet.get_all_values():
        worksheet.update(
            values=[HEADERS],
            range_name="A1:C1",
            value_input_option="RAW",
        )

    worksheet.append_rows(data, value_input_option="RAW")
