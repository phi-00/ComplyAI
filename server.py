import sys
import threading
import logging
import requests
import os
import tempfile
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename

from docling_converter import convert_pdf_to_docling_json

PORT = 9000

FILES_DIR = "files"

if len(sys.argv) < 2:
    print("Uso: python server.py IP")
    sys.exit(1)
URL = f"http://{sys.argv[1]}:{PORT}/message"

app = Flask(__name__)
#logging.getLogger("werkzeug").setLevel(logging.ERROR)


def get_client_dir(client):
    path = os.path.join(FILES_DIR, client)
    return path if os.path.isdir(path) else None

def load_requirements(folder):
    requirements={}
    for name in sorted(os.listdir(folder)):
        if name.lower().endswith((".json")):
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                requirements[name] = f.read()
    return requirements


@app.route("/files/<client-name>/requirements_pdf", methods=["POST"])
def receive_pdf_to_extractor(client):
    if get_client_dir(client) is None:
        return jsonify({"error": f"Cliente '{client}' não existe"}), 404
    
    file = request.files.get("file")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, secure_filename(file.filename))
        file.save(path)
        try:
            result = convert_pdf_to_docling_json(path)   # necessário ajustar extrator
        except Exception as e:
            return jsonify({"error": f"Falha no extrator: {e}"}), 500

    return jsonify({"client": client, "filename": file.filename, "result": result}), 200


@app.route("/files/<client-name>/matrix", methods=["POST"])
def get_matrix(client):
    files_folder = get_client_dir(client)
    if files_folder is None:
        return jsonify({"error": f"Cliente {client} não existe"}), 404
    
    requirements = load_requirements(files_folder)
    
    try:
        project_matrix = generate_matrix(requirements) ## adaptar com parte da IA (to be changed)
    except Exception as e:
        return jsonify({"error": f"Falha na IA"}), 500
    
    return jsonify({"client": client, "matrix": project_matrix}), 200
        


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