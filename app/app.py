from flask import Flask, jsonify

app = Flask(__name__)

@app.get("/healthz")
def healthz():
    return jsonify(ok=True)

@app.get("/")
def index():
    return "CBS minimal stack is running. Visit /healthz for JSON.", 200
