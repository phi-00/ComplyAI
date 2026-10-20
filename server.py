import sys
import threading
import logging
import requests
from flask import Flask, request, jsonify

PORT = 9000

if len(sys.argv) < 2:
    print("Uso: python server.py IP")
    sys.exit(1)
URL = f"http://{sys.argv[1]}:{PORT}/message"

app = Flask(__name__)
#logging.getLogger("werkzeug").setLevel(logging.ERROR)

### "Server" Side - Receive Messages

@app.route("/message", methods=["POST"])
def receive_msg():
    data = request.get_json(silent=True) or {}
    print(f"\n[Outro PC] {data.get('texto', '')}")
    print("Mensagem (ou 'out'): ", end="", flush=True)
    return jsonify({"resposta": "recebido"})


def run_server():
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)

threading.Thread(target=run_server, daemon=True).start()


### "Client" Side - Send Messages

session = requests.Session()
session.trust_env = False  # ignora proxies do sistema

while True:
    text = input("Mensagem (ou 'out'): ")
    if text.lower() == "out":
        break
    try:
        r = session.post(URL, json={"texto": text}, timeout=5)
        print("Resposta:", r.json()["resposta"])
    except requests.RequestException as e:
        print("Falha ao enviar:", e)