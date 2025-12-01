# app.py
import os
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
from dotenv import load_dotenv

# Import agent functions
from agent import handle_user_query, generate_report_bytes

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
    Request body (JSON) - all fields optional because server will fall back to env:
    {
      "sheet_id": "<spreadsheetId>",  # optional, if not provided uses REPORT_SHEET_ID from .env
      "sheet": 0 or "<sheet name>",   # optional, default from REPORT_SHEET_NAME_OR_INDEX or 0
      "format": "csv" or "xlsx"       # optional, default csv
    }
    """
    try:
        data = request.get_json(silent=True) or {}
        sheet_id = data.get("sheet_id") or request.args.get("sheet_id")  # may be None
        sheet = data.get("sheet", None)
        fmt = (data.get("format", "csv") or "csv").lower()

        bio, filename, mimetype = generate_report_bytes(sheet_id=sheet_id, sheet=sheet, fmt=fmt)
        return send_file(bio, as_attachment=True, download_name=filename, mimetype=mimetype)
    except Exception as e:
        print(f"❌ /api/report error: {type(e).__name__}: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)