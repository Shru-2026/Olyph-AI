from flask import Flask, render_template, request, jsonify
from agent import handle_user_query
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # enables JS calls from the same host

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/ask', methods=['POST'])
def ask():
    try:
        user_input = request.json.get('message', '')
        if not user_input:
            return jsonify({'reply': "⚠️ Please enter a valid message."})

        response = handle_user_query(user_input)
        return jsonify({'reply': response})

    except Exception as e:
        print(f"❌ Error in /ask route: {e}")
        return jsonify({'reply': "⚠️ Something went wrong connecting to Olyph AI."})

if __name__ == '__main__':
    app.run(debug=True)
