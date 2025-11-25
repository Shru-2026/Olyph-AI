# app.py
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from agent import handle_user_query

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)  # allow cross-origin JS calls from the same host

@app.route('/')
def home():
    # if you have templates/index.html, Flask will serve it
    try:
        return render_template('index.html')
    except Exception:
        # fallback simple HTML so you can test without templates
        return """
        <!doctype html>
        <html>
        <head><meta charset="utf-8"><title>Olyph AI</title></head>
        <body>
          <h3>Olyph AI Backend</h3>
          <form id="chatForm">
            <input id="msg" placeholder="Ask something" style="width:300px"/>
            <button type="button" onclick="send()">Send</button>
          </form>
          <div id="reply"></div>
          <script>
            async function send(){
              const m = document.getElementById('msg').value;
              const res = await fetch('/ask', {
                method: 'POST', headers: {'Content-Type':'application/json'},
                body: JSON.stringify({message: m})
              });
              const j = await res.json();
              document.getElementById('reply').innerText = j.reply || 'No reply';
            }
          </script>
        </body>
        </html>
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
        # log and return friendly message
        print(f"❌ Error in /ask route: {type(e).__name__}: {e}")
        return jsonify({'reply': "⚠️ Something went wrong on the server. Check logs."})

if __name__ == '__main__':
    # For local testing. Use production server (gunicorn/uvicorn) in production.
    app.run(host='0.0.0.0', port=5000, debug=True)
