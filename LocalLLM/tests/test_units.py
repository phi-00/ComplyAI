"""Fast deterministic tests of the rule-based helpers (no LLM, < 1 s). The parser on the real PDFs is tested by
tests/test_parser.py.

    python tests/test_units.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from complyai import customers as cu  # noqa: E402
from complyai import engine as e  # noqa: E402
from complyai import parser as p  # noqa: E402
from complyai import rerank as r  # noqa: E402


def _perm(statement: str) -> bool:
    return e._permissive({"statement": statement})


def _window(customer="", path=None, it_code="WI X"):
    import json
    return {"customer": customer, "path": json.dumps(path or []), "it_code": it_code}


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
        cands, rel, _, _ = e._candidates([{}] * 3, R, chunks, rules, {"WI A": {}, "WI B": {}}, hubs)
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

_IT_TEXT = "Os PPAPs John Deere devem ser carregados no portal cliente antes do envio das cablagens."


def _verified(verifier: dict | None, violates=False, value_conflict=False, judge_evidence="judge evidence"):
    """engine._verify on a judge conflict with stubbed LLM answers: verifier = the verification answer (None = the
    call fails), violates = the narrow conflict check's answer. Returns (fields to overwrite, conflict checks made)."""
    calls = []

    def chat_json(system, user, schema, **kw):
        if system == e.prompts.CONFLICT_CHECK_SYSTEM:
            calls.append(user)
            return {"requirement_demands": "", "rule_demands": "", "same_thing": True, "only_missing": False,
                    "violates": violates}
        if verifier is None:
            raise e.llm.LLMError("output truncated at 2400 tokens")
        return {"reasoning": "r", "same_activity": True, "already_covered": False, "context_removes": False,
                "it_stricter": False, "missing": "approval", "action": "Add the approval.", **verifier}

    it = {"code": "WI X", "title": "PPAP", "excerpts": [{"text": _IT_TEXT}], "rules": []}
    r = {"id": 1, "client": "John Deere", "doc": "D", "page": 1, "section": "", "quote": "q",
         "statement": "The supplier shall not ship parts before PPAP approval."}
    saved, e.llm.chat_json = e.llm.chat_json, chat_json
    try:
        out = e._verify(r, it, {"verdict": "conflict", "explanation": "x", "evidence": judge_evidence,
                                "value_conflict": value_conflict})
    finally:
        e.llm.chat_json = saved
    return {k: out.get(k) for k in ("verdict", "evidence", "verified") if k in out}, len(calls)


def _preset(**env):
    """config values with the given COMPLYAI_* variables set (config is re-read, then restored)."""
    import importlib
    import os
    keys = ("COMPLYAI_PRESET", "COMPLYAI_CHAT_MODEL", "COMPLYAI_THINK_MODEL", "COMPLYAI_NUM_CTX", "COMPLYAI_LLM_WORKERS",
            "COMPLYAI_VERIFY_MAX_TOKENS")
    saved = {k: os.environ.pop(k, None) for k in keys}
    os.environ.update({f"COMPLYAI_{k.upper()}": str(v) for k, v in env.items()})
    try:
        c = importlib.reload(e.config)
        return c.CHAT_MODEL, c.THINK_MODEL, c.NUM_CTX, c.LLM_WORKERS, c.VERIFY_MAX_TOKENS
    except ValueError as err:
        return str(err)[:30]
    finally:
        for k in keys:
            os.environ.pop(k, None)
            if saved[k] is not None:
                os.environ[k] = saved[k]
        importlib.reload(e.config)


CASES = [
    # server presets: the default is the measured setup, single variables override a preset (2026-11-12)
    ("preset default = measured setup", _preset(), ("qwen3:8b", "qwen3:8b", 4096, 4, 2400)),
    ("preset gpu12 = default", _preset(preset="gpu12"), _preset()),
    ("preset gpu8: same model, 2 parallel", _preset(preset="gpu8"), ("qwen3:8b", "qwen3:8b", 4096, 2, 2400)),
    ("preset gpu6: smaller model", _preset(preset="GPU6"), ("qwen3:4b", "qwen3:4b", 4096, 2, 2400)),
    ("preset gpu48: longer context, larger verify budget", _preset(preset="gpu48"),
     ("qwen3:32b", "qwen3:32b", 8192, 8, 4096)),
    ("preset + single overrides", _preset(preset="gpu24", chat_model="Qwen/Qwen3-30B-A3B", think_model="gpt-oss:20b",
                                          llm_workers=6), ("Qwen/Qwen3-30B-A3B", "gpt-oss:20b", 4096, 6, 2400)),
    ("unknown preset refused", _preset(preset="gpu10"), "COMPLYAI_PRESET='gpu10' is not"),
    # conflicts: a narrow check must confirm them, the contradicting rule must be real IT text (2026-11-12)
    ("conflict confirmed by the narrow check", _verified({"verdict": "conflict", "contradicting_rule": _IT_TEXT}, True),
     ({"verdict": "conflict", "evidence": _IT_TEXT, "verified": 1}, 1)),
    ("conflict not confirmed -> gap, judge evidence kept",
     _verified({"verdict": "conflict", "contradicting_rule": _IT_TEXT}, False), ({"verdict": "partial", "verified": 1}, 1)),
    ("contradicting rule not in the IT, judge evidence neither -> gap, no check",
     _verified({"verdict": "conflict", "contradicting_rule": "Shipping is allowed before any customer approval."}, True),
     ({"verdict": "partial", "verified": 1}, 0)),
    ("translated contradicting rule -> the judge's real IT evidence is checked",
     _verified({"verdict": "conflict", "contradicting_rule": "John Deere PPAPs must be uploaded before shipping."}, True,
               judge_evidence=_IT_TEXT), ({"verdict": "conflict", "evidence": _IT_TEXT, "verified": 1}, 1)),
    ("verification failed on a conflict -> gap", _verified(None), ({"verdict": "partial", "verified": 0}, 0)),
    ("verification failed on a numeric conflict -> kept", _verified(None, value_conflict=True), ({"verified": 0}, 0)),
    ("numeric conflict: no narrow check", _verified({"verdict": "conflict", "contradicting_rule": _IT_TEXT},
                                                    value_conflict=True),
     ({"verdict": "conflict", "evidence": _IT_TEXT, "verified": 1}, 0)),
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
    # customers named in IT text (review feedback 2026-11: IT text for another customer is no evidence)
    ("customer column 'CAT -PERKINS'", cu.named("CAT -PERKINS"), {"Caterpillar"}),
    ("customer misspelt 'John-Deer'", cu.named("Para os clientes Fendt, John-Deer e Agco"), {"AGCO", "John Deere"}),
    ("customers given as examples do not count", cu.named("aprovação pelo cliente no seu portal (ex. CAT e VOLVO CE)"),
     set()),
    ("lower-case 'cat' is no customer", cu.named("the cat label"), set()),
    ("client name canonical", cu.canonical("Deere & Company"), "John Deere"),
    ("scope: other customer's column excluded", cu.applies(e._scope(_window("JOHN DEERE"), {}), "Cummins"), False),
    ("scope: own column kept", cu.applies(e._scope(_window("CUMMINS"), {}), "Cummins"), True),
    ("scope: section heading names the customer",
     e._scope(_window(path=["Etiquetas", "ETIQUETA CLIENTE CATERPILLAR [Código de barras]"]), {}), {"Caterpillar"}),
    ("scope: IT written for one customer", e._scope(_window(it_code="WI 3600-11"), {"WI 3600-11": {"scope": {"John Deere"}}}),
     {"John Deere"}),
    ("scope: general text for every customer", e._scope(_window(path=["4 Realização"]), {}), set()),
    ("rule naming a customer keeps it", e._rule_scope("AGCO: por norma as saídas olhal não levam etiqueta", set()),
     {"AGCO"}),
    ("masking: other customers' sentences removed",
     e._mask_other_customers("Each packaging must be labelled. AGCO: no label on eyelets. Cummins: tag every harness.",
                             "Cummins"), "Each packaging must be labelled. Cummins: tag every harness."),
    # permissions / exemptions: an IT that does more can never violate them (conflict -> "IT stricter")
    ("permission: exemption unless requested",
     _perm("The supplier is not required to report reference and basic dimensions unless specifically requested."), True),
    ("permission: supplier may use", _perm("The supplier may use internal supplier markings, such as barcodes."), True),
    ("permission with approval is left to the verifier",
     _perm("The supplier may use a Special Level 4 PPAP upon agreement with Cummins SQE."), False),
    ("obligation is no permission", _perm("The supplier shall report all toleranced dimensions."), False),
    ("'may be required' is no permission", _perm("The supplier may be required to submit additional samples."), False),
    ("'may not' is a prohibition", _perm("The supplier may not change the process without approval."), False),
    # action plans start with an imperative verb
    ("action: passive -> verb first", e.action_text("The IT must be updated to include the DL numbers."),
     "Update the IT to include the DL numbers."),
    ("action: 'LEONI must add'", e.action_text("LEONI must explicitly add a rule to this IT."), "Add a rule to this IT."),
    ("action: 'needs to state'", e.action_text("The IT needs to explicitly state that black is preferred."),
     "Update the IT to explicitly state that black is preferred."),
    ("action: lower-case verb", e.action_text("update IT to state 'two wraps'"), "Update IT to state 'two wraps'"),
    ("action: verb kept", e.action_text("Clarify the retention period."), "Clarify the retention period."),
    ("action: description kept after 'Review the IT'", e.action_text("The IT requires annual checks only.")[:15],
     "Review the IT: "),
    ("action: none", e.action_text("No action needed."), ""),
    # parser: a customer column read line by line (words of tiny text in one merged cell)
    ("column words -> paragraphs", p._word_paragraphs([(0, 0, 10, 3.4, "20.2", 0, 0, 0), (11, 0, 30, 3.4, "Apply", 0, 0, 1),
                                                       (0, 4.6, 20, 8, "the", 0, 1, 0), (0, 9.2, 5, 12.6, "•", 0, 2, 0),
                                                       (6, 9.2, 30, 12.6, "John", 0, 2, 1)]),
     ["20.2 Apply the", "• John"]),
    ("customer column split keeps its heading", p._split_column("JOHN DEERE\n" + "a" * 50 + "\n" + "b" * 50, 70),
     ["JOHN DEERE\n" + "a" * 50, "JOHN DEERE\n" + "b" * 50]),
]

failed = 0
for name, got, want in CASES:
    ok = got == want
    failed += not ok
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  (got {got!r}, expected {want!r})"))
print(f"{len(CASES) - failed}/{len(CASES)} passed")
sys.exit(1 if failed else 0)
