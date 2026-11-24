import io
import json
import os
import sys
import threading
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename

from openpyxl import load_workbook

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "LocalLLM"))   # para encontrar o pacote complyai
sys.path.insert(0, str(BASE / "PDF Extractor"))
# Um dos pedidos paralelos do servidor LLM fica reservado para o chat: o processamento de documentos usa no máximo
# os restantes (complyai config.CHAT_SLOTS), por isso uma pergunta no chat começa logo em vez de esperar pelo documento.
os.environ.setdefault("COMPLYAI_CHAT_SLOTS", "1")

from complyai.export import export_matrix
from complyai.store import Store
from complyai import chat, config, engine, llm

from extrator.docling_converter import convert_pdf_to_docling_json, save_paragraphs
from complyai.docling_adapter import parse_docling, parse_paragraphs

PORT = 9000

FILES_DIR = "files"

# Folha Excel recebida pela aplicação.
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

app = Flask(__name__)
#logging.getLogger("werkzeug").setLevel(logging.ERROR)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

processing_jobs = {}
processing_jobs_lock = threading.Lock()


def clean_context_text(value):
    if value is None:
        return ""
    text = str(value).replace("\ufffd", "")
    return " ".join(text.split())


def fit_context_text(value, limit=11000):
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[contexto truncado por limite de segurança]"


def ensure_manual_overrides(store):
    store.db.execute(
        """
        CREATE TABLE IF NOT EXISTS manual_overrides (
            id INTEGER PRIMARY KEY,
            doc_id INTEGER NOT NULL,
            section TEXT,
            process TEXT,
            wsd TEXT,
            wptgu TEXT,
            updated_at TEXT,
            updated_by TEXT,
            UNIQUE(doc_id, section)
        )
        """
    )
    store.commit()


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
    if file is None or file.filename == "":
        return jsonify({"error": "Nenhum ficheiro PDF foi enviado"}), 400
    
    name = secure_filename(file.filename)
    pdf_path = os.path.join(folder, name)
    file.save(pdf_path)

    job_id = str(uuid.uuid4())

    def process_pdf():
        try:
            with processing_jobs_lock:
                processing_jobs[job_id] = {"status": "processing", "progress": 10}

            docling_json = convert_pdf_to_docling_json(
                pdf_path,
                Path(folder) / "extracted" / f"{Path(name).stem}.json",
            )
            with processing_jobs_lock:
                processing_jobs[job_id]["progress"] = 35

            docling_json_par = save_paragraphs(
                docling_json,
                Path(folder) / "paragraphs" / f"{Path(name).stem}.json",
            )
            with processing_jobs_lock:
                processing_jobs[job_id]["progress"] = 55

            parsed = parse_paragraphs(docling_json_par, name)
            with processing_jobs_lock:
                processing_jobs[job_id]["progress"] = 75

            res = engine.ingest_csr(Store(), parsed, client=client)
            if res.get("status") not in ("ok", "resumed", "skipped"):
                raise RuntimeError("Ingestão não concluída")

            with processing_jobs_lock:
                processing_jobs[job_id].update({
                    "status": "completed",
                    "progress": 100,
                    "client": client,
                    "filename": name,
                    "doc_id": res["doc_id"],
                })
        except Exception as e:
            with processing_jobs_lock:
                processing_jobs[job_id].update({
                    "status": "failed",
                    "progress": 100,
                    "error": str(e),
                })

    threading.Thread(target=process_pdf, daemon=True).start()
    return jsonify({
        "status": "accepted",
        "job_id": job_id,
        "message": "O PDF foi recebido e está a ser processado",
    }), 202


@app.route("/jobs/<job_id>", methods=["GET"])
def get_processing_job(job_id):
    with processing_jobs_lock:
        job = processing_jobs.get(job_id)
    if job is None:
        return jsonify({"error": "Processamento não encontrado"}), 404
    return jsonify(job)


@app.route("/projects/<client>/documents", methods=["GET"])
def get_project_documents(client):
    if get_client_dir(client) is None:
        return jsonify({"error": f"Projeto '{client}' não existe"}), 404

    store = Store(config.DB_PATH)
    all_rows = store.q(
        """
        SELECT id, kind, code, title, client, version, source_file,
               ingested_at, status
        FROM documents
        WHERE kind='CSR'
        ORDER BY ingested_at DESC, id DESC
        """
    )

    folder = Path(get_client_dir(client))
    available_files = {
        path.name.lower()
        for path in folder.rglob("*")
        if path.is_file()
    }

    name_aliases = {
        secure_filename(client).lower(),
        client.lower(),
    }
    normalized_aliases = {
        alias.replace("catterpillar", "caterpillar")
        for alias in name_aliases
    }

    rows = []
    for row in all_rows:
        source_name = (row["source_file"] or "").lower()
        db_client = (row["client"] or "").lower()
        db_aliases = {
            secure_filename(row["client"] or "").lower(),
            db_client,
        }
        db_aliases |= {
            alias.replace("catterpillar", "caterpillar")
            for alias in db_aliases
        }

        matches_project_file = (
            bool(source_name)
            and (
                source_name in available_files
                or Path(source_name).name in available_files
            )
        )
        matches_project_name = (
            bool(name_aliases.intersection(db_aliases))
            or bool(normalized_aliases.intersection(db_aliases))
        )

        if matches_project_file or matches_project_name:
            rows.append(row)

    documents = [dict(row) for row in rows]
    return jsonify({
        "project": client,
        "documents": documents,
        "active_document_id": documents[0]["id"] if documents else None,
    })


@app.route("/projects/<client>/documents/<int:doc_id>/findings", methods=["GET"])
def get_findings(client, doc_id):
    if get_client_dir(client) is None:
        return jsonify({"error": f"Projeto '{client}' não existe"}), 404

    store = Store(config.DB_PATH)
    document = store.one("SELECT * FROM documents WHERE id=? AND kind='CSR'", (doc_id,))
    if document is None:
        return jsonify({"error": "Documento não encontrado"}), 404

    rows = store.q(
        """
        SELECT * FROM findings
        WHERE doc_id=?
        ORDER BY CASE severity
            WHEN 'high' THEN 0 WHEN 'medium' THEN 1
            WHEN 'low' THEN 2 ELSE 3 END, id DESC
        """,
        (doc_id,),
    )
    return jsonify({"project": client, "doc_id": doc_id, "findings": [dict(row) for row in rows]})


@app.route("/projects/<client>/chat", methods=["POST"])
def chat_project(client):
    if get_client_dir(client) is None:
        return jsonify({"error": f"Projeto '{client}' não existe"}), 404

    data = request.get_json(silent=True) or {}
    message = (data.get("message") or data.get("text") or "").strip()
    if not message:
        return jsonify({"error": "Mensagem vazia"}), 400

    store = Store(config.DB_PATH)
    folder = Path(get_client_dir(client))
    available_files = {
        path.name.lower()
        for path in folder.rglob("*")
        if path.is_file()
    }
    client_aliases = {
        secure_filename(client).lower(),
        client.lower(),
    }
    client_aliases |= {
        alias.replace("catterpillar", "caterpillar")
        for alias in client_aliases
    }

    all_documents = store.q(
        """
        SELECT id, kind, code, title, client, version, source_file,
               ingested_at, status, meta_json
        FROM documents
        WHERE kind='CSR'
        ORDER BY ingested_at DESC, id DESC
        """
    )
    project_documents = []
    for document in all_documents:
        source_name = (document["source_file"] or "").lower()
        db_aliases = {
            secure_filename(document["client"] or "").lower(),
            (document["client"] or "").lower(),
        }
        db_aliases |= {
            alias.replace("catterpillar", "caterpillar")
            for alias in db_aliases
        }
        matches_file = (
            bool(source_name)
            and (
                source_name in available_files
                or Path(source_name).name in available_files
            )
        )
        matches_name = bool(client_aliases.intersection(db_aliases))
        if matches_file or matches_name:
            project_documents.append(document)

    if not project_documents:
        return jsonify({
            "answer": "Este projeto ainda não tem documentos CSR processados com contexto pesquisável.",
            "sources": [],
        })

    # O contexto que o modelo recebe (conversa, requisitos, alertas, ITs, glossário) é montado em complyai/chat.py
    try:
        return jsonify(chat.answer(store, client, project_documents, message, data.get("history") or [],
                                   project_dir=get_client_dir(client)))
    except Exception as e:
        return jsonify({
            "answer": "Não foi possível consultar o assistente local neste momento.",
            "sources": [],
            "error": str(e),
        }), 503


@app.route("/projects/<client>/documents/<int:doc_id>/matrix", methods=["PATCH"])
def patch_matrix(client, doc_id):
    if get_client_dir(client) is None:
        return jsonify({"error": f"Projeto '{client}' não existe"}), 404

    data = request.get_json(silent=True) or {}
    section = (data.get("section") or "").strip()
    if not section:
        return jsonify({"error": "A secção é obrigatória"}), 400

    store = Store(config.DB_PATH)
    ensure_manual_overrides(store)
    store.db.execute(
        """
        INSERT INTO manual_overrides
            (doc_id, section, process, wsd, wptgu, updated_at, updated_by)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(doc_id, section) DO UPDATE SET
            process=excluded.process,
            wsd=excluded.wsd,
            wptgu=excluded.wptgu,
            updated_at=excluded.updated_at,
            updated_by=excluded.updated_by
        """,
        (
            doc_id,
            section,
            data.get("process"),
            data.get("wsd"),
            data.get("wptgu"),
            datetime.now(timezone.utc).isoformat(),
            data.get("updated_by") or "app",
        ),
    )
    store.commit()
    return jsonify({"status": "ok", "doc_id": doc_id, "section": section})


@app.route("/projects/<client>/documents/<int:doc_id>/requirements/<int:req_id>", methods=["PATCH"])
def patch_requirement(client, doc_id, req_id):
    if get_client_dir(client) is None:
        return jsonify({"error": f"Projeto '{client}' não existe"}), 404

    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in ("approved", "rejected", "pending"):
        return jsonify({"error": "Estado inválido"}), 400

    store = Store(config.DB_PATH)
    requirement = store.one(
        "SELECT * FROM requirements WHERE id=? AND doc_id=?",
        (req_id, doc_id),
    )
    if requirement is None:
        return jsonify({"error": "Requisito não encontrado"}), 404

    cols = {row[1] for row in store.db.execute("PRAGMA table_info(requirements)").fetchall()}
    if "review_status" not in cols:
        store.db.execute("ALTER TABLE requirements ADD COLUMN review_status TEXT")
    if "reviewed_at" not in cols:
        store.db.execute("ALTER TABLE requirements ADD COLUMN reviewed_at TEXT")
    if "reviewed_by" not in cols:
        store.db.execute("ALTER TABLE requirements ADD COLUMN reviewed_by TEXT")

    store.update(
        "requirements",
        req_id,
        review_status=status,
        reviewed_at=datetime.now(timezone.utc).isoformat(),
        reviewed_by=data.get("reviewed_by") or "app",
    )
    for link in store.q("SELECT id FROM req_it_links WHERE req_id=?", (req_id,)):
        store.update(
            "req_it_links",
            link["id"],
            verified=1 if status == "approved" else (0 if status == "rejected" else None),
        )
    store.commit()
    return jsonify({"status": "ok", "requirement_id": req_id, "review_status": status})


@app.route("/projects/<client>/documents/<int:doc_id>/changes", methods=["PATCH"])
def patch_document_changes(client, doc_id):
    if get_client_dir(client) is None:
        return jsonify({"error": f"Projeto '{client}' não existe"}), 404

    data = request.get_json(silent=True) or {}
    store = Store(config.DB_PATH)
    ensure_manual_overrides(store)
    store.db.execute(
        """
        CREATE TABLE IF NOT EXISTS document_changes (
            id INTEGER PRIMARY KEY,
            doc_id INTEGER NOT NULL,
            change_type TEXT NOT NULL,
            item_id TEXT,
            changes_json TEXT NOT NULL,
            updated_at TEXT,
            updated_by TEXT
        )
        """
    )

    now_text = datetime.now(timezone.utc).isoformat()
    updated_by = data.get("updated_by") or "app"
    requirements = data.get("requirements") or {}
    instructions = data.get("instructions") or {}

    for item_id, raw_change in requirements.items():
        try:
            change = json.loads(raw_change) if isinstance(raw_change, str) else raw_change
        except Exception:
            change = {"value": raw_change}

        store.insert(
            "document_changes",
            doc_id=doc_id,
            change_type="requirement",
            item_id=str(item_id),
            changes_json=json.dumps(change, ensure_ascii=False),
            updated_at=now_text,
            updated_by=updated_by,
        )

        try:
            requirement_id = int(item_id)
            requirement = store.one(
                "SELECT id FROM requirements WHERE id=? AND doc_id=?",
                (requirement_id, doc_id),
            )
            if requirement and isinstance(change, dict) and change.get("requirement"):
                cols = {
                    row[1]
                    for row in store.db.execute(
                        "PRAGMA table_info(requirements)"
                    ).fetchall()
                }
                if "reviewed_at" not in cols:
                    store.db.execute(
                        "ALTER TABLE requirements ADD COLUMN reviewed_at TEXT"
                    )
                if "reviewed_by" not in cols:
                    store.db.execute(
                        "ALTER TABLE requirements ADD COLUMN reviewed_by TEXT"
                    )
                store.update(
                    "requirements",
                    requirement_id,
                    statement=change["requirement"],
                    reviewed_at=now_text,
                    reviewed_by=updated_by,
                )
        except Exception:
            pass

    for item_id, raw_change in instructions.items():
        try:
            change = json.loads(raw_change) if isinstance(raw_change, str) else raw_change
        except Exception:
            change = {"value": raw_change}

        store.insert(
            "document_changes",
            doc_id=doc_id,
            change_type="instruction",
            item_id=str(item_id),
            changes_json=json.dumps(change, ensure_ascii=False),
            updated_at=now_text,
            updated_by=updated_by,
        )

    store.commit()
    return jsonify({
        "status": "ok",
        "doc_id": doc_id,
        "requirements_saved": len(requirements),
        "instructions_saved": len(instructions),
    })


@app.route("/projects/<client>/documents/<int:doc_id>/conflict-resolutions", methods=["PATCH"])
def patch_conflict_resolutions(client, doc_id):
    if get_client_dir(client) is None:
        return jsonify({"error": f"Projeto '{client}' não existe"}), 404

    data = request.get_json(silent=True) or {}
    resolutions = data.get("resolutions") or []
    if not isinstance(resolutions, list):
        return jsonify({"error": "Formato de resoluções inválido"}), 400

    store = Store(config.DB_PATH)
    cols = {row[1] for row in store.db.execute("PRAGMA table_info(findings)").fetchall()}
    if "resolution" not in cols:
        store.db.execute("ALTER TABLE findings ADD COLUMN resolution TEXT")
    if "resolved_at" not in cols:
        store.db.execute("ALTER TABLE findings ADD COLUMN resolved_at TEXT")
    if "resolved_by" not in cols:
        store.db.execute("ALTER TABLE findings ADD COLUMN resolved_by TEXT")

    store.db.execute(
        """
        CREATE TABLE IF NOT EXISTS document_changes (
            id INTEGER PRIMARY KEY,
            doc_id INTEGER NOT NULL,
            change_type TEXT NOT NULL,
            item_id TEXT,
            changes_json TEXT NOT NULL,
            updated_at TEXT,
            updated_by TEXT
        )
        """
    )

    now_text = datetime.now(timezone.utc).isoformat()
    updated_by = data.get("updated_by") or "app"
    saved = 0
    for resolution in resolutions:
        if not isinstance(resolution, dict):
            continue
        text = (resolution.get("resolution") or "").strip()
        if not text:
            continue

        finding_id = resolution.get("finding_id")
        if finding_id is not None:
            try:
                finding = store.one(
                    "SELECT id FROM findings WHERE id=? AND doc_id=?",
                    (int(finding_id), doc_id),
                )
                if finding:
                    store.update(
                        "findings",
                        int(finding_id),
                        resolution=text,
                        resolved_at=now_text,
                        resolved_by=updated_by,
                        status="resolved",
                    )
            except Exception:
                pass

        store.insert(
            "document_changes",
            doc_id=doc_id,
            change_type="conflict_resolution",
            item_id=str(resolution.get("section") or finding_id or saved),
            changes_json=json.dumps(resolution, ensure_ascii=False),
            updated_at=now_text,
            updated_by=updated_by,
        )
        saved += 1

    store.commit()
    return jsonify({"status": "ok", "doc_id": doc_id, "resolutions_saved": saved})


@app.route("/projects/<client>/documents/<int:doc_id>/refresh", methods=["POST"])
def refresh_document(client, doc_id):
    if get_client_dir(client) is None:
        return jsonify({"error": f"Projeto '{client}' não existe"}), 404

    store = Store(config.DB_PATH)
    document = store.one("SELECT * FROM documents WHERE id=? AND kind='CSR'", (doc_id,))
    if document is None:
        return jsonify({"error": "Documento não encontrado"}), 404

    job_id = str(uuid.uuid4())

    def refresh():
        try:
            with processing_jobs_lock:
                processing_jobs[job_id] = {"status": "processing", "progress": 10}
            folder = get_client_dir(client)
            pdf_path = Path(folder) / (document["source_file"] or "")
            if not pdf_path.exists():
                possible = [
                    path for path in Path(folder).glob("*")
                    if path.is_file() and path.suffix.lower() == ".pdf"
                ]
                if not possible:
                    raise RuntimeError("Ficheiro PDF original não encontrado")
                pdf_path = possible[0]

            docling_json = convert_pdf_to_docling_json(
                str(pdf_path),
                Path(folder) / "extracted" / f"{pdf_path.stem}.json",
            )
            docling_json_par = save_paragraphs(
                docling_json,
                Path(folder) / "paragraphs" / f"{pdf_path.stem}.json",
            )
            parsed = parse_paragraphs(docling_json_par, pdf_path.name)
            with processing_jobs_lock:
                processing_jobs[job_id]["progress"] = 70
            res = engine.ingest_csr(Store(), parsed, client=client)
            with processing_jobs_lock:
                processing_jobs[job_id].update({
                    "status": "completed",
                    "progress": 100,
                    "doc_id": res["doc_id"],
                    "result": res["status"],
                })
        except Exception as e:
            with processing_jobs_lock:
                processing_jobs[job_id].update({
                    "status": "failed",
                    "progress": 100,
                    "error": str(e),
                })

    threading.Thread(target=refresh, daemon=True).start()
    return jsonify({"status": "accepted", "job_id": job_id}), 202
    


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
            matrix_data = excel_to_dict(output)
            store = Store(config.DB_PATH)
            ensure_manual_overrides(store)
            overrides = store.q(
                "SELECT section, process, wsd, wptgu FROM manual_overrides WHERE doc_id=?",
                (doc_id,),
            )
            if overrides:
                override_map = {row["section"]: row for row in overrides}
                matrix_rows = matrix_data.get("Matrix", [])
                for row in matrix_rows:
                    if not isinstance(row, list) or len(row) < 10:
                        continue
                    section = str(row[1] or "")
                    override = override_map.get(section)
                    if override:
                        row[4] = override["process"] or row[4]
                        row[6] = override["wsd"] or row[6]
                        row[9] = override["wptgu"] or row[9]
            return jsonify({"client": client, "doc_id": doc_id, "matrix": matrix_data})
        
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