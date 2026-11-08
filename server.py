import sys, os, io
import threading
import tempfile
import requests
import tempfile

import zipfile
import json
from datetime import datetime, timezone

from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
from pathlib import Path

from openpyxl import load_workbook

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "LocalLLM"))   # para encontrar o pacote complyai
sys.path.insert(0, str(BASE / "PDF Extractor"))

from complyai.export import export_matrix
from complyai.store import Store
from complyai import config, engine, llm

from extrator.docling_converter import convert_pdf_to_docling_json, save_paragraphs
from complyai.docling_adapter import parse_docling, parse_paragraphs

PORT = 9000

FILES_DIR = "files"

#indica que recebe um ficheiro excel
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

#if len(sys.argv) < 2:
#    print("Uso: python server.py IP")
#    sys.exit(1)
#URL = f"http://{sys.argv[1]}:{PORT}/message"

app = Flask(__name__)
#logging.getLogger("werkzeug").setLevel(logging.ERROR)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024


def get_client_dir(client):
    path = os.path.join(FILES_DIR, secure_filename(client))
    return path if os.path.isdir(path) else None

#def load_requirements(folder):
#    requirements={}
#    for name in sorted(os.listdir(folder)):
#        if name.lower().endswith((".json")):
#            with open(os.path.join(folder, name), encoding="utf-8") as f:
#                requirements[name] = f.read()
#    return requirements


def excel_to_dict(path):
    excel = load_workbook(path, data_only=True)
    output = {}
    for worksheet in excel.worksheets:
        rows = [row for row in worksheet.iter_rows(values_only=True) if any(col is not None for col in row)]
        if worksheet.title == "Matrix":
            output[worksheet.title] = [list(row) for row in rows]
        elif rows:
            header, *body = rows
            output[worksheet.title] = [dict(zip(header, row)) for row in body]
            
    return output
    

@app.route("/files/<client>/requirements_pdf", methods=["POST"])
def receive_pdf_to_extractor(client):
    folder = get_client_dir(client)
    if folder is None:
        return jsonify({"error": f"Cliente '{client}' não existe"}), 404
    
    file = request.files.get("file")
    
    name = secure_filename(file.filename)
    pdf_path = os.path.join(folder, name)
    file.save(pdf_path)
    
    try:
        docling_json = convert_pdf_to_docling_json(pdf_path, Path(folder) / "extracted" / f"{Path(name).stem}.json")
        docling_json_par = save_paragraphs(docling_json, Path(folder) / "paragraphs" / f"{Path(name).stem}.json")
    except Exception as e:
        return jsonify({"error": f"Falha ao extrair requisitos: {e}"}), 500
    
    try:   # JSON Docling -> ParsedDocument -> ingestão + análise
        parsed = parse_paragraphs(docling_json_par, name)
        res = engine.ingest_csr(Store(), parsed, client=client)
    except Exception as e:
        return jsonify({"error": f"Falha na ingestão: {e}"}), 500

    if res.get("status") not in ("ok", "resumed"):
        return jsonify({"error": "Ingestão não concluída", "result": res}), 422
    
    return jsonify({"client": client, "filename": name, "doc_id": res["doc_id"]}), 201
    


@app.route("/files/<client>/matrix/<int:doc_id>", methods=["GET", "POST"])
def get_matrix(client, doc_id):
    if get_client_dir(client) is None:
        return jsonify({"error": f"Cliente {client} não existe"}), 404
    
    as_json = request.args.get("format") == "json"
    
    #requirements = load_requirements(files_folder)
    
    with tempfile.TemporaryDirectory() as temp:
        output = os.path.join(temp, "matrix.xlsx")
        
        try:
            store = Store(config.DB_PATH)
            export_matrix(store, doc_id, output)
        except ValueError as e:
            return jsonify({"error": str(e)}), 404
        except Exception as e:
            return jsonify({"error": f"Falha ao gerar matriz."}), 404
    
        if as_json:
            return jsonify({"client": client, "doc_id": doc_id, "matrix": excel_to_dict(output)})
        
        with open(output, "rb") as file:
                data = io.BytesIO(file.read())
            
        return send_file(data, mimetype=XLSX_MIME, as_attachment=True, download_name=f"Matriz_{client}_{doc_id}.xlsx")

### Get list of projects and handle selected project
@app.route("/projects", methods=["GET"])
def get_projects():

    if not os.path.isdir(FILES_DIR):
        return jsonify({"projects": []})

    projects = []

    for name in os.listdir(FILES_DIR):

        path = os.path.join(FILES_DIR, name)

        if os.path.isdir(path):
            projects.append(name)

    projects.sort()

    return jsonify({
        "projects": projects
})

@app.route("/projects/<client>/download", methods=["GET"])
def download_project(client):

    folder = get_client_dir(client)

    if folder is None:
        return jsonify({
            "error": "Projeto não encontrado"
        }), 404

    folder_path = Path(folder).resolve()

    memory_file = io.BytesIO()

    with zipfile.ZipFile(
        memory_file,
        "w",
        compression=zipfile.ZIP_DEFLATED
    ) as archive:

        for file_path in folder_path.rglob("*"):

            if not file_path.is_file():
                continue

            resolved_file = file_path.resolve()

            try:
                relative_path = resolved_file.relative_to(folder_path)
            except ValueError:
                continue

            if relative_path.as_posix() == "last_loaded.json":
                continue

            archive.write(
                resolved_file,
                arcname=file_path.relative_to(folder_path)
            )

    memory_file.seek(0)

    return send_file(
        memory_file,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{client}.zip"
    )

@app.route("/projects/<client>/loaded", methods=["POST"])
def project_loaded(client):

    folder = get_client_dir(client)

    if folder is None:
        return jsonify({
            "error": "Projeto não encontrado"
        }), 404

    # Hora oficial do servidor
    loaded_at = datetime.now(timezone.utc).isoformat()

    record = {
        "project": client,
        "loaded_at": loaded_at
    }

    record_path = os.path.join(
        folder,
        "last_loaded.json"
    )

    with open(
        record_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            record,
            file,
            ensure_ascii=False,
            indent=4
        )

    return jsonify({
        "status": "ok",
        "project": client,
        "loaded_at": loaded_at
    })

### "Server" Side - Receive Messages

@app.route("/message", methods=["POST"])
def receive_msg():
    data = request.get_json(silent=True) or {}
    print(f"\n[Outro PC] {data.get('texto', '')}")
    print("Mensagem (ou 'out'): ", end="", flush=True)
    return jsonify({"resposta": "recebido"})


def run_server():
    llm.check()
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)

#threading.Thread(target=run_server, daemon=True).start()

if __name__ == "__main__":
    run_server()


### "Client" Side - Send Messages

#session = requests.Session()
#session.trust_env = False  # ignora proxies do sistema

#while True:
#    text = input("Mensagem (ou 'out'): ")
#    if text.lower() == "out":
#        break
#    try:
#        r = session.post(URL, json={"texto": text}, timeout=5)
#        print("Resposta:", r.json()["resposta"])
#    except requests.RequestException as e:
#        print("Falha ao enviar:", e)