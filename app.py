# app.py
import os
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
from dotenv import load_dotenv

# Import agent functions and auth verify
from agent import handle_user_query, generate_report_bytes
from auth.auth import verify_user

load_dotenv()

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)


@app.route('/')
def home():
    try:
        return render_template('index.html')
    except Exception:
        return """
        <!doctype html><html><head><meta charset="utf-8"><title>Olyph AI</title></head>
        <body><h3>Olyph AI Backend</h3>
        <p>Open the frontend at / (templates/index.html)</p></body></html>
        """


@app.route('/ask', methods=['POST'])
def ask():
    try:
        user_input = request.json.get('message', '')
        if not user_input or not user_input.strip():
            return jsonify({'reply': "⚠️ Please enter a valid message."})
        response = handle_user_query(user_input)
        return jsonify({'reply': response})
    except Exception as e:
        print(f"❌ Error in /ask route: {type(e).__name__}: {e}")
        return jsonify({'reply': "⚠️ Something went wrong on the server. Check logs."})


@app.route('/api/report', methods=['POST'])
def api_report():
    """
    POST JSON expected:
    {
      "username": "<username>",        # required
      "password": "<password>",        # required
      "sheet_id": "<spreadsheetId>",   # optional - falls back to REPORT_SHEET_ID env
      "sheet": 0 or "<sheet name>",    # optional
      "format": "csv" or "xlsx"        # optional, default csv
    }
    """
    try:
        data = request.get_json(silent=True) or {}

        # --- Authentication ---
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        if not username or not password:
            return jsonify({"error": "Authentication required (username + password)."}), 401

        if not verify_user(username, password):
            return jsonify({"error": "Invalid username or password."}), 401

        # --- Report parameters ---
        sheet_id = data.get("sheet_id") or request.args.get("sheet_id")
        sheet = data.get("sheet", None)
        fmt = (data.get("format", "csv") or "csv").lower()

        # Generate and return file
        bio, filename, mimetype = generate_report_bytes(sheet_id=sheet_id, sheet=sheet, fmt=fmt)
        return send_file(bio, as_attachment=True, download_name=filename, mimetype=mimetype)

    except FileNotFoundError as e:
        # service account JSON not present
        msg = "Service account JSON not found. Ensure GOOGLE_SERVICE_ACCOUNT_JSON or creds/service_account.json exists."
        print("❌ /api/report FileNotFoundError:", e)
        return jsonify({"error": msg}), 500
    except PermissionError as e:
        # probably permissions reading file or gspread 403
        print("❌ /api/report PermissionError:", e)
        msg = ("Permission denied. Check that the service account JSON file is readable by the server "
               "and that the spreadsheet is shared with the service account email. "
               "Also confirm Google Sheets API & Drive API are enabled.")
        return jsonify({"error": msg}), 500
    except Exception as e:
        print("❌ /api/report error:", type(e).__name__, e)
        return jsonify({"error": f"Internal error: {type(e).__name__}: {str(e)}"}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
