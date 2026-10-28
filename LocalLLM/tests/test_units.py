"""Fast deterministic tests of the rule-based helpers (no LLM, < 1 s). The parser on the real PDFs is tested by
tests/test_parser.py.

    python tests/test_units.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from complyai import engine as e  # noqa: E402
from complyai import parser as p  # noqa: E402
from complyai import rerank as r  # noqa: E402


def _toc(*lines):
    return [(t.key, t.level) for t in p._toc_entries([p.Line(2, x, 100 + 15 * i, 500, 112 + 15 * i, s, 11, False)
                                                      for i, (x, s) in enumerate(lines)])]


def _magnet(weight: float):
    """Candidates of requirement 0 (engine._candidates): a generic IT window close to every requirement vs a specific
    one close to requirement 0 only; plus a short generic rule, a short rule with a number and a long rule."""
    import numpy as np
    from complyai.store import to_blob
    unit = lambda v: np.array(v, dtype=np.float32) / np.linalg.norm(v)  # noqa: E731
    R = np.eye(3, 4, dtype=np.float32)                       # three requirements on three different topics
    generic, specific = unit([0.8, 0.42, 0.42, 0]), unit([0.78, 0, 0, 0.6258])
    chunks = [{"it_code": "WI A", "id": 1, "text": "generic window", "emb": to_blob(generic)},
              {"it_code": "WI B", "id": 2, "text": "specific window", "emb": to_blob(specific)}]
    rules = [{"it_code": "WI A", "chunk_id": 1, "rule": "The supplier's description must be provided.", "emb": to_blob(generic)},
             {"it_code": "WI B", "chunk_id": 2, "rule": "Fill rate 95 % minimum.", "emb": to_blob(specific)},
             {"it_code": "WI B", "chunk_id": 2, "rule": "The sleeve must be wrapped so that every wire stays inside.",
              "emb": to_blob(specific)}]
    hub = lambda M: np.sort(R @ M.T, axis=0)[-3:].mean(axis=0)  # noqa: E731  (as engine._hubs, K = 3)
    hubs = (hub(np.vstack([generic, specific])), hub(np.vstack([generic, specific, specific])))
    saved, e.config.IT_HUB_WEIGHT = e.config.IT_HUB_WEIGHT, weight
    try:
        cands, rel, _ = e._candidates([{}] * 3, R, chunks, rules, {"WI A": {}, "WI B": {}}, hubs)
    finally:
        e.config.IT_HUB_WEIGHT = saved
    return [t for _, t in sorted(zip(rel[0], (c[3] for c in cands[0])), reverse=True)]


def _picked(per_family: bool, statement="The supplier shall submit the PPAP."):
    """ITs shown to the judge for candidate passages of a PPAP requirement (engine._pick_its)."""
    direction = {"WI 3476-11 A4": "internal_units"}
    knowledge = {c: {"profile": {"direction": direction.get(c, "customer_or_production")}} for c in
                 ("WI 3326-11", "WI 3326-11 A3", "WI 3326-11 A1", "WI 3069-11", "WI 3476-11", "WI 3476-11 A4")}
    cands = [("WI 3326-11 A3", 1, 0.70, ""), ("WI 3326-11 A1", 2, 0.69, ""), ("WI 3326-11", 3, 0.68, ""),
             ("WI 3476-11 A4", 4, 0.65, ""), ("WI 3069-11", 5, 0.60, ""), ("WI 3476-11", 6, 0.55, ""),
             ("WI 3326-11 A3", 7, 0.50, "")]
    saved, e.config.IT_PER_FAMILY = e.config.IT_PER_FAMILY, per_family
    try:
        return [c for c, _, _ in e._pick_its({"statement": statement, "quote": ""}, cands, [c[2] for c in cands],
                                             knowledge)]
    finally:
        e.config.IT_PER_FAMILY = saved

CASES = [
    # document code: file-name identifier wins over a wrong number from the title block
    ("doc code 18227", e._doc_code("212020-011", "18227_013.pdf", "Standard Number 18227 ... 212020-011"), "18227"),
    ("doc code kept", e._doc_code("1E2358", "1E2358_32.pdf", "1E2358"), "1E2358"),
    ("doc code ignores month-year", e._doc_code("JDS-G223", "JDS-G223 Supplier Quality Manual_Nov2021.pdf", "x"),
     "JDS-G223"),
    ("doc code no candidates", e._doc_code(None, "Supplier Handbook-Portuguese-January 2026_0.pdf", "2026"),
     "Supplier Handbook-Portuguese-January 2026_0"),
    # revision suffix stripped so versions of one document match
    ("base code rev", e._base_code("DLW20803_revB"), "DLW20803"),
    ("base code version", e._base_code("SupplierQualityManual2022 version3.0"), "SupplierQualityManual2022"),
    # number grounding: statement numbers must exist in the source
    ("grounding catches 4,8 vs 48", e._numbers_ok("dentro de 4,8 horas", "em até 48 horas"), False),
    ("grounding decimal comma", e._numbers_ok("Ppk 1,67", "maior ou igual a 1,67"), True),
    ("grounding 1.50 == 1,5", e._numbers_ok("1.50", "1,5"), True),
    # same-unit value comparison
    ("values differ mm ranges", e._values_differ("extending 20 to 25 mm", "estendendo 10 a 15mm"), True),
    ("values equal mm ranges", e._values_differ("extending 10 to 15 mm", "estendendo a bandagem 10 a 15mm"), False),
    ("values differ % (no word boundary after %)", e._values_differ("at least 98 %", "de 95%- 100%."), True),
    ("values hours vs horas", e._values_differ("within 24 hours", "no prazo de 24 horas"), False),
    ("values different units ignored", e._values_differ("8D within 10 days", "6 semanas"), False),
    # ISO clause matching (section heading clause vs IT index clauses)
    ("clause 7.2 ~ 7.2.2", e._clause_match("7.2", "7.2.2"), True),
    ("clause in list", e._clause_match("8.2.3", "5.1.2, 8.2.2, 8.2.3"), True),
    ("clause deeper section", e._clause_match("8.5.1.2", "8.5.1"), True),
    ("clause no match", e._clause_match("8.2", "8.5.1"), False),
    # "magnet" IT texts: a text close to every requirement ranks below a specific one; short generic rules are out
    ("magnet: hub correction ranks the specific window first", _magnet(0.3)[0], "specific window"),
    ("magnet: without it the generic window wins", _magnet(0.0)[0], "generic window"),
    ("magnet: short generic rule not a candidate", "The supplier's description must be provided." in _magnet(0.3), False),
    ("magnet: short rule with a number kept", "Fill rate 95 % minimum." in _magnet(0.3), True),
    # IT selection: a base IT and its annexes take one slot; internal-unit ITs skipped before the slots are filled
    ("IT family: one slot per IT + annexes", _picked(True), ["WI 3326-11 A3", "WI 3069-11", "WI 3476-11"]),
    ("IT family off: every annex its own IT", _picked(False), ["WI 3326-11 A3", "WI 3326-11 A1", "WI 3326-11"]),
    ("IT family: internal IT allowed for sub-suppliers",
     _picked(True, "The supplier shall make its sub-suppliers submit the PPAP."),
     ["WI 3326-11 A3", "WI 3476-11 A4", "WI 3069-11"]),
    # direction filter: requirements mentioning sub-suppliers may use own-supplier ITs
    ("sub-supplier mentioned", bool(e.SUBSUPPLIER_RE.search("análise de subfornecedor em 15 dias")), True),
    ("sub-supplier: seus fornecedores", bool(e.SUBSUPPLIER_RE.search("garantir que seus fornecedores cumpram")), True),
    ("no sub-supplier", bool(e.SUBSUPPLIER_RE.search("analisar peças devolvidas pela Cummins")), False),
    # parser heading heuristics
    ("IT code from file name", e._it_code_from({"source_file": "WI-3234-11-A1.pdf", "first_pages_text": ""}),
     "WI 3234-11 A1"),
    ("IT code ignores template 'P4000 Anexo 3'",
     e._it_code_from({"source_file": "WI-3164-11.pdf", "first_pages_text": "WI 3164-11\nP4000 Anexo 3, Revisão"}),
     "WI 3164-11"),
    ("central procedure code (VA, no plant suffix)",
     e._it_code_from({"source_file": "VA-3160-A2_associado a WI-3550-11.pdf", "first_pages_text": ""}), "VA 3160 A2"),
    ("annex code with 'IT 3 069-11 Anexo 3' on the page",
     e._it_code_from({"source_file": "scan.pdf", "first_pages_text": "IT 3 069-11  Anexo 3  (Ed. 09.18)"}),
     "WI 3069-11 A3"),
    # context lock: quotes must come from the passage
    ("quote found in passage", e._overlap("keep records for 10 years", "The supplier shall keep records for 10 years."),
     1.0),
    ("invented quote not found", e._overlap("notify within 24 hours", "The supplier shall keep records for 10 years."),
     0.0),
    ("short quote compared as text", e._overlap("8D", "open an 8D report"), 1.0),
    # parser: heading numbers and their depth
    ("heading number 5.4.3", p._HEAD_NUM.match("5.4.3 Terminal Crimp Criteria")["num"], "5.4.3"),
    ("heading letter AA.", p._HEAD_NUM.match("AA. Auditoria Interna (9.2)")["num"], "AA."),
    ("lower-case list item is no heading", p._HEAD_NUM.match("a. ANSI J-Std-004"), None),
    ("depth 1.0 -> 1", p._number_depth("1.0"), 1),
    ("depth 5.10 -> 2", p._number_depth("5.10"), 2),
    ("depth 6.1.3. -> 3", p._number_depth("6.1.3."), 3),
    ("numbered requirement is no heading", bool(p._MODAL.search("Devices used for heating shall be controlled")),
     True),
    ("continued heading", bool(p._CONTINUED.search("PACKAGING (CONTINUED)")), True),
    ("revision log is history", bool(p._HISTORY.search("LOG DE REVISÃO FF")), True),
    ("page number footer", bool(p._PAGE_NO.match("Página 3 de 44")), True),
    ("running footer key ignores digits", p._key("Page 3 of 9") == p._key("Page 4 of 9"), True),
    # parser: tables of contents (number label printed left of the text = same level as the text)
    ("TOC levels by indentation", _toc((83, "A. Promessa da marca ........ 4"), (144, "1. Verificação ........ 9"),
                                       (162, "Conformidade de Produtos ........ 13"), (83, "B. Escopo ........ 5")),
     [("promessa da marca", 1), ("verificação", 2), ("conformidade de produtos", 2), ("escopo", 1)]),
    ("TOC multi-column nav bar is flat", _toc((86, "Introduction ....... 2"), (224, "Process Adherence ....... 8"),
                                              (361, "Tooling ....... 14"), (498, "Warranty ....... 21")),
     [("introduction", 1), ("process adherence", 1), ("tooling", 1), ("warranty", 1)]),
    # parser: table rows become self-contained lines; stacked cell values are split into rows
    ("table rows", p._table_lines(p.Table(1, (0, 0, 1, 1), [["Abbreviation", "Definition"], ["BOM", "Bill of Materials"]])),
     ["Abbreviation: BOM; Definition: Bill of Materials"]),
    ("hyphen kept when joining lines", p._join_lines([p.Line(1, 0, 0, 1, 1, "adequando-", 10, False),
                                                      p.Line(1, 0, 12, 1, 13, "se ao tipo", 10, False)]),
     "adequando-se ao tipo"),
    # reranker input: values masked on both sides (topic, not agreement), identifiers kept
    ("rerank masks values", r.mask_values("fill rate of 95%- 100%, 10 a 15mm, within 24 hours, Ppk 1,67"),
     "fill rate of N%- N%, N a Nmm, within N hours, Ppk N"),
    ("rerank keeps identifiers", r.mask_values("ISO 9001, IATF 16949, WI 3600-11, 8D report, step D3, Anexo A5"),
     "ISO 9001, IATF 16949, WI 3600-N, 8D report, step D3, Anexo A5"),
    # reranker input: a passage is scored sentence by sentence; short fragments join the next one
    ("rerank sentences", r.sentences("4.1.2 – Torcer a manga sobre os fios até ficar justo. Deve ser alcançada uma "
                                     "taxa de preenchimento da manga de 95%- 100%. Nota: ver tábua."),
     ["4.1.2 – Torcer a manga sobre os fios até ficar justo.",
      "Deve ser alcançada uma taxa de preenchimento da manga de 95%- 100%. Nota: ver tábua."]),
    ("rerank table cells", r.sentences("Containment Actions | Responsible | DueDate | Indicar as ações de contenção "
                                       "imediatas para cada ação"),
     ["Containment Actions Responsible DueDate Indicar as ações de contenção imediatas para cada ação"]),
]

failed = 0
for name, got, want in CASES:
    ok = got == want
    failed += not ok
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  (got {got!r}, expected {want!r})"))
print(f"{len(CASES) - failed}/{len(CASES)} passed")
sys.exit(1 if failed else 0)
