# report_agent.py
"""
Report agent for Olyph AI.

- Handles Google Service Account auth.
- Fetches Google Sheet into pandas DataFrame.
- Exposes helper to return CSV/XLSX as BytesIO for download or further processing.
"""

import os
import io
import json
from datetime import datetime

import pandas as pd
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import AuthorizedSession

load_dotenv(dotenv_path="./.env")

# Scopes required
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

def _get_service_account_credentials():
    """
    Returns google.oauth2.service_account.Credentials by checking:
      1) GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT (raw JSON string)
      2) GOOGLE_SERVICE_ACCOUNT_JSON (a file path)
      3) /etc/secrets/service_account.json (Render Secret File)
      4) ./creds/service_account.json (local fallback)
    """
    # 1) Raw JSON content
    content = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT", "").strip()
    if content:
        try:
            info = json.loads(content)
            print("🔐 Using GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT")
            return Credentials.from_service_account_info(info, scopes=SCOPES)
        except Exception as e:
            raise RuntimeError(f"Invalid GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT: {e}")

    # 2) Explicit path from env var
    path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if path:
        if os.path.exists(path):
            print(f"🔐 Using GOOGLE_SERVICE_ACCOUNT_JSON at: {path}")
            return Credentials.from_service_account_file(path, scopes=SCOPES)
        else:
            print(f"⚠️ GOOGLE_SERVICE_ACCOUNT_JSON set but file not found: {path}")

    # 3) Render secret default location
    render_default = "/etc/secrets/service_account.json"
    if os.path.exists(render_default):
        print(f"🔐 Using Render Secret File: {render_default}")
        return Credentials.from_service_account_file(render_default, scopes=SCOPES)

    # 4) Local fallback (development)
    local_path = os.path.join(os.getcwd(), "creds", "service_account.json")
    if os.path.exists(local_path):
        print(f"🔐 Using local creds: {local_path}")
        return Credentials.from_service_account_file(local_path, scopes=SCOPES)

    # Nothing found
    raise FileNotFoundError(
        "Service account JSON not found. Ensure GOOGLE_SERVICE_ACCOUNT_JSON or "
        "GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT is set, or upload a Render Secret "
        "File named 'service_account.json', or place creds/service_account.json locally."
    )

def get_gspread_client():
    """
    Create a gspread client authenticated with the service account.
    Attach an AuthorizedSession so HTTP calls include OAuth2 tokens.
    """
    creds = _get_service_account_credentials()
    client = gspread.Client(auth=creds)
    client.session = AuthorizedSession(creds)
    return client

def fetch_sheet_as_dataframe(
    sheet_id=None,
    sheet_name_or_index=None,
    value_render_option="FORMATTED_VALUE",
) -> pd.DataFrame:
    """
    Fetch a sheet and return a pandas DataFrame.
    Falls back to REPORT_SHEET_ID and REPORT_SHEET_NAME_OR_INDEX env vars.
    """
    if not sheet_id:
        sheet_id = os.getenv("REPORT_SHEET_ID", "").strip()
        if not sheet_id:
            raise ValueError("No sheet_id provided and REPORT_SHEET_ID is not set in environment.")

    # determine sheet index/name
    if sheet_name_or_index is None:
        env_sheet = os.getenv("REPORT_SHEET_NAME_OR_INDEX", "").strip()
        if env_sheet != "":
            try:
                sheet_name_or_index = int(env_sheet)
            except ValueError:
                sheet_name_or_index = env_sheet
        else:
            sheet_name_or_index = 0

    client = get_gspread_client()
    spreadsheet = client.open_by_key(sheet_id)

    if isinstance(sheet_name_or_index, int):
        worksheet = spreadsheet.get_worksheet(sheet_name_or_index)
    else:
        worksheet = spreadsheet.worksheet(sheet_name_or_index)

    values = worksheet.get_all_values()
    if not values:
        return pd.DataFrame()

    header = values[0]
    rows = values[1:]
    df = pd.DataFrame(rows, columns=header)
    return df


def dataframe_to_csv_bytes(df: pd.DataFrame):
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return buf

def dataframe_to_excel_bytes(df: pd.DataFrame):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    buf.seek(0)
    return buf

def generate_report_bytes(sheet_id=None, sheet=None, fmt="csv"):
    """
    Main helper to produce BytesIO, filename, mimetype.
    Can be used by Flask routes to send downloadable CSV/XLSX.
    """
    df = fetch_sheet_as_dataframe(sheet_id=sheet_id, sheet_name_or_index=sheet)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    chosen_id = sheet_id or os.getenv("REPORT_SHEET_ID", "unknown")

    fmt_lower = fmt.lower()
    if fmt_lower in ("csv", "text/csv"):
        bio = dataframe_to_csv_bytes(df)
        filename = f"sheet_{chosen_id}_{timestamp}.csv"
        mimetype = "text/csv"
    elif fmt_lower in ("xlsx", "excel"):
        bio = dataframe_to_excel_bytes(df)
        filename = f"sheet_{chosen_id}_{timestamp}.xlsx"
        mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        raise ValueError("Unsupported format. Use 'csv' or 'xlsx'.")

    return bio, filename, mimetype
