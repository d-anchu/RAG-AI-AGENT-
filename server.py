from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from logistics_agent import LogisticsAgent
import os

app = Flask(__name__)
CORS(app)

# Initialize the agent once when the server starts
print("⚡ Initializing Logistics Nexus Core...")
agent = LogisticsAgent()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    user_input = request.json.get('message')
    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    response = agent.process_query(user_input)
    return jsonify(response)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Logistics Nexus Server Online at http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)
