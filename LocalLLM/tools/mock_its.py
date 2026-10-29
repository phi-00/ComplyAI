"""Generate SYNTHETIC LEONI Work Instructions for index entries that have no real PDF.

Only 7 of ~300 ITs are available as PDFs; the rest of LEONI's IT base is private. This tool asks the
local LLM to write a plausible IT for each index entry (title, process, ISO clause, department) in
LEONI's IT format, saved as a ParsedDocument JSON (the parser contract) with "synthetic": true.

The content is INVENTED. Everything the engine derives from these ITs is labelled "[simulated IT]" /
"*" and they are meant for a separate demo database only (tools/build_demo.py), never for real results.

    python tools/mock_its.py --top 80          # the 80 index ITs most relevant to the ingested documents
    python tools/mock_its.py --all             # every index entry without a real PDF
    python tools/mock_its.py --codes "WI 3157-11" "WI 3476-11"

Resumable: ITs already generated in --out are skipped (re-run after an interruption).
"""
import argparse
import json
import logging
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from complyai import config, llm  # noqa: E402
from complyai.engine import _pimap  # noqa: E402
from complyai.store import Store  # noqa: E402

log = logging.getLogger("mock_its")

SYSTEM = """You write internal Work Instructions ("Instruções de Trabalho", IT) for LEONI Portugal, a wire-harness
plant certified to IATF 16949 / ISO 9001. This is SYNTHETIC test data for a software prototype: write a realistic,
specific IT for the given index entry, in Portuguese (Portugal), in LEONI's IT structure.

Requirements for the content:
- Consistent with the title, process and ISO/IATF clause given. Stay on that topic only.
- Concrete and checkable: numbered steps with who does what, when, with which values — frequencies, deadlines,
  quantities, sample sizes, tolerances, approval levels, record retention periods — typical of an automotive
  wire-harness plant. Plausible values, not extreme ones.
- Departments by acronym: QM (qualidade), VCM (cadeia de valor/logística), PR (engenharia de produção),
  IE (engenharia industrial), PP (preparação produção), RH, ST (manutenção), HSEE, Compras.
- Internal systems ONLY for their purpose (otherwise say "registo em papel" or "pasta partilhada"):
  LPMCS = controlo da produção na linha/etiquetas; LPERP = ERP (encomendas, stocks, ordens de produção);
  Omnitracker = reclamações e relatórios 8D; LEOPARTS = alterações técnicas de produto.
- European Portuguese (Portugal), LEONI vocabulary: cablagem (never "harness"/"chicote"), planeamento,
  registo/registado, equipa, ficheiro, utilizador, fornecedor, colaborador, posto de trabalho.
- No person names. Do not cite customer requirement documents; mention a customer only if the title does.
- "realizacao": 4 to 8 steps, each 2-5 sentences."""

SCHEMA = {
    "type": "object",
    "properties": {
        "objetivo": {"type": "string"},
        "area_aplicacao": {"type": "string"},
        "definicoes": {"type": "array", "items": {"type": "string"}},
        "responsabilidades": {"type": "string"},
        "realizacao": {
            "type": "array",
            "items": {"type": "object",
                      "properties": {"titulo": {"type": "string"}, "texto": {"type": "string"}},
                      "required": ["titulo", "texto"]},
        },
        "registos": {"type": "string"},
        "documentos_relacionados": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["objetivo", "area_aplicacao", "definicoes", "responsabilidades", "realizacao", "registos",
                 "documentos_relacionados"],
}


def _department(owner: str) -> str:
    """Index 'Dono do Processo' is 'DEPT / Person Name' -> keep only the department."""
    return (owner or "").split("/")[0].strip()


def generate(entry) -> dict | None:
    user = (f"IT: {entry['code']} — {entry['title']}\n"
            f"Processo LEONI: {entry['process'] or '-'}\nCláusula ISO 9001/IATF 16949: {entry['iso_clause'] or '-'}\n"
            f"Departamento responsável: {_department(entry['owner']) or '-'}")
    try:
        out = llm.chat_json(SYSTEM, user, SCHEMA, max_tokens=2200)
    except llm.LLMError as e:
        log.warning("%s failed: %s", entry["code"], e)
        return None
    if len(out.get("realizacao", [])) < 2:
        log.warning("%s: too little content, skipped", entry["code"])
        return None
    version = (entry["revision"] or "1").split("/")[0].strip() or "1"
    chunks = [{"page": 1, "section": "1. Objetivo", "text": f"1. Objetivo {out['objetivo']}"},
              {"page": 1, "section": "2. Área de aplicação", "text": f"2. Área de aplicação {out['area_aplicacao']}"}]
    if out["definicoes"]:
        chunks.append({"page": 1, "section": "3. Termos e definições",
                       "text": "3. Termos e definições " + " ".join(out["definicoes"])})
    chunks.append({"page": 1, "section": "4. Responsabilidades",
                   "text": f"4. Responsabilidades {out['responsabilidades']}"})
    for k, step in enumerate(out["realizacao"], start=1):
        sec = f"5.{k} {re.sub(r'^\s*\d+(\.\d+)*\.?\s*', '', step['titulo']).strip()}"  # model numbers steps too
        chunks.append({"page": 2, "section": sec, "text": f"{sec} {step['texto'].strip()}"})
    chunks.append({"page": 3, "section": "6. Registos e documentação",
                   "text": "6. Registos e documentação " + out["registos"]
                           + (" Documentos relacionados: " + "; ".join(out["documentos_relacionados"])
                              if out["documentos_relacionados"] else "")})
    return {
        "source_file": f"{entry['code'].replace(' ', '-')}_SIMULADA.json",
        "synthetic": True,
        "pages": 3,
        "first_pages_text": (f"{entry['code']}\nInstrução de Trabalho\n{entry['title']}\n"
                             f"Instrução de Trabalho nº: {entry['code']}\nVersão: {version}\n"
                             f"DOCUMENTO SIMULADO — gerado para testes, não é uma IT real da LEONI"),
        "chunks": chunks,
        "generator": {"model": config.CHAT_MODEL, "index_entry": entry["code"]},
    }


def priority(store: Store, real: set[str]) -> list[str]:
    """Index ITs ordered by how much the ingested customer documents point to them."""
    votes = Counter()
    for r in store.q("SELECT it_code FROM section_its"):
        votes[r["it_code"]] += 5
    for r in store.q("SELECT it_code FROM req_it_links WHERE source='catalog'"):
        votes[" ".join(r["it_code"].split()[:2])] += 1
    return [c for c, _ in votes.most_common() if c not in real]


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--top", type=int, help="the N index ITs most relevant to the ingested documents")
    g.add_argument("--all", action="store_true")
    g.add_argument("--codes", nargs="+")
    ap.add_argument("--out", default=str(ROOT / "mock_data" / "its"))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    sys.stdout.reconfigure(encoding="utf-8")

    store = Store()
    catalog = {r["code"]: r for r in store.q("SELECT * FROM it_catalog")}
    if not catalog:
        sys.exit("IT index not loaded: run `python -m complyai load-index ...` first")
    # ITs we have as real PDFs are never simulated
    real = {" ".join(d["code"].split()[:2]) for d in store.q("SELECT code, meta_json FROM documents WHERE kind='IT'")
            if not json.loads(d["meta_json"] or "{}").get("synthetic")}
    if args.codes:
        codes = args.codes
    elif args.all:
        codes = [c for c in catalog if c not in real]
    else:
        codes = priority(store, real)[:args.top]

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = [catalog[c] for c in codes if c in catalog
            and not (out_dir / f"{c.replace(' ', '-')}_SIMULADA.json").exists()]
    log.info("%d ITs requested, %d already generated, %d to generate", len(codes), len(codes) - len(todo), len(todo))
    done = 0
    for doc in _pimap(generate, todo, "generation"):
        if doc:
            path = out_dir / doc["source_file"]
            path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
            done += 1
    log.info("%d mock ITs written to %s", done, out_dir)


if __name__ == "__main__":
    main()
