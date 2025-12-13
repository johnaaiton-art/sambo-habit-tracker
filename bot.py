# bot.py — MINIMAL TEST VERSION
from flask import Flask
app = Flask(__name__)

@app.route('/health')
def health():
    return {"status": "Flask is running!"}

@app.route('/webhook', methods=['POST'])
def webhook():
    return {"status": "webhook received"}, 200

if __name__ == '__main__':
    print("✅ Starting minimal Flask server...")
    app.run(host='0.0.0.0', port=8080)
