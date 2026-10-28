"""Parser regression test on the real documents (no LLM, ~1 min): expected headings and levels (checked against
each document's own table of contents and LEONI's Cummins matrix), no table-of-contents / header / footer
leftovers, sane chunk sizes and pages, forms printed twice on one sheet read once.

    python tests/test_parser.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from complyai import config  # noqa: E402
from complyai.parser import parse_pdf  # noqa: E402

C, L = ROOT / "Cliente", ROOT / "Leoni" / "Leoni"
N = L / "RE__Pedido_de_Documentação_Exemplo"  # second batch of LEONI ITs (2026-10-22)
# file -> (minimum number of headings, [(level, heading prefix)] that must be in the outline in this order)
EXPECT = {
    C / "Cliente" / "Supplier Handbook-Portuguese-January 2026_0.pdf": (55, [
        (1, "A. Promessa da marca"), (1, "E. Requisitos do Sistema de Qualidade"), (2, "1. Verificação de Registro"),
        (1, "G. Sistema de Gestão de Qualidade"), (2, "Conformidade de Produtos e Processos"), (2, "Requisitos do VDA"),
        (1, "J. Recursos (7.1)"), (2, "Laboratório Externo"), (1, "K. Competência (7.2)"),
        (1, "Q. Controle de Processos, Produtos e Serviços Externamente Fornecidos (8.4)"),
        (1, "AA. Auditoria Interna (9.2)"), (1, "EE. Apêndice")]),
    C / "SupplierQualityManual2022 version3.0" / "SupplierQualityManual2022 version3.0.pdf": (30, [
        (1, "INTRODUCTION"), (1, "PROCESS ADHERENCE"), (1, "PRODUCTION PART APPROVAL PROCESS (PPAP)"),
        (1, "PROCESS CHANGE NOTIFICATION"), (1, "CORRECTIVE ACTION"), (1, "GLOSSARY OF TERMS")]),
    C / "Cliente" / "JDS-G223 Supplier Quality Manual_Nov2021.pdf": (100, [
        (1, "1 Scope"), (1, "4 Context of the Organization"), (2, "4.1 Understanding the Organization"),
        (1, "8 Operation"), (2, "8.2 Requirements for Products and Services"), (3, "8.2.1 Communication to John Deere")]),
    C / "Cliente" / "JDS-G223X3 - Production Part Approval (PPAP) Requirements_Nov2021.pdf": (40, [
        (1, "1 Scope"), (1, "5 Document Requirements"), (2, "5.9 Control Plans"), (3, "5.12.1 Material"),
        (1, "10 PPAP Submission Responses"), (2, "10.2 Conditional Approval")]),
    C / "Cliente" / "DLW 25046_A_Sep2023.pdf": (30, [
        (1, "1. Scope and Application"), (1, "5. Requirements"), (2, "5.1 General requirements"),
        (3, "5.9.1 Barcode label as a flag"), (2, "5.27 Connectors used for Automotive Ethernet")]),
    C / "Cliente" / "1E2358_32.pdf": (60, [
        (1, "1.0 SCOPE"), (1, "5.0 GENERAL REQUIREMENTS"), (2, "5.4 Terminal Attachment"),
        (3, "5.4.3 Terminal Crimp Criteria"), (1, "9.0 CONTAMINATION CONTROL"), (1, "12.0 REFERENCES")]),
    C / "Cliente" / "18227_013.pdf": (60, [
        (1, "1. Scope"), (1, "4. Tools and Equipment"), (2, "4.1. Tool Selection"), (1, "7. Crimping"),
        (2, "7.2. Crimp Height"), (1, "18. Reference Readings")]),
    L / "WI-3404-11.pdf": (15, [
        (1, "1 OBJETIVO"), (1, "5 CONTEÚDO"), (2, "5.1 Planeamento de produção"), (3, "5.3.6 Teste elétrico"),
        (1, "7 DOCUMENTAÇÃO")]),
    L / "WI-3164-11.pdf": (8, [(1, "1 OBJETIVO"), (1, "6 DECURSO / REALIZAÇÃO")]),
    L / "WI-3600-11.pdf": (5, [(1, "1. Finalidade"), (1, "5. Documentação válida")]),
    L / "WI-3234-11.pdf": (5, [(1, "1.0 Objetivo"), (1, "5.0 Documentação")]),
    L / "WI-3234-11-A1.pdf": (0, []),
    L / "WI-3234-11-A2.pdf": (0, []),
    L / "WI-3404-11-A5.pdf": (5, []),
    # "Anexo 9 Corte:" list labels in section 6 are not headings (they made "1 OBJECTIVO" level 2)
    N / "WI-3157-11.pdf": (7, [(1, "1 OBJECTIVO"), (1, "5 CONTEÚDO"), (1, "6 ANEXOS E DOCUMENTOS DE SUPORTE"),
                               (1, "7 DOCUMENTAÇÃO")]),
    # 5.9 wraps in the TOC and in the text (hanging indent)
    N / "WI-3196-11.pdf": (19, [(1, "1 OBJETIVO"), (1, "5 CONTEÚDO"), (2, "5.1. ÂMBITO DO LABORATÓRIO"),
                                (2, "5.9. PROCEDIMENTO A SEGUIR EM CASO DE EQUIPAMENTO DE MEDIÇÃO DESAPARECIDO"),
                                (2, "5.12. TESTES DE LABORATÓRIO"), (1, "7 DOCUMENTAÇÃO")]),
    N / "WI-3236-11.pdf": (20, [(1, "5 CONTEÚDO"), (2, "5.1 CIP Equipas"), (3, "5.1.1 Criação da Ideia"),
                                (3, "5.2.5 Fecho do CIP"), (2, "5.3 Transferência de informações"),
                                (1, "7 DOCUMENTAÇÃO")]),
}
# file -> phrases that must be in the passages exactly once (forms printed twice side by side on one sheet:
# one copy read; a form whose labels look like headings: its text is not dropped as a cover block)
ONCE = {
    N / "WI-3326-11-A1.pdf": ["Verificação de: Secção, Cor e tipo de fio", "Relatório Dimensional 2"],
    N / "WI-3326-11-A2.pdf": ["Verificação terminais BUZZBAR"],
}
# never a heading: requirements written as numbered sentences, continuation titles, histories, cover lines
BAD_HEADING = re.compile(r"\bshall\b|\(continued\)|revis(ion|ão) (history|log)|log de revis|^Cummins Inc\.$", re.I)

ok = True


def check(name, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {detail}"))


for pdf, (min_heads, expected) in EXPECT.items():
    p = parse_pdf(pdf)
    name = pdf.name[:40]
    outline, chunks = p["outline"], p["chunks"]
    check(f"{name}: >= {min_heads} headings", len(outline) >= min_heads, f"got {len(outline)}")
    pos = 0
    for level, prefix in expected:
        found = next((i for i in range(pos, len(outline)) if outline[i]["heading"].startswith(prefix)), None)
        check(f"{name}: [{level}] {prefix}", found is not None and outline[found]["level"] == level,
              "missing / out of order" if found is None else f"level {outline[found]['level']}")
        pos = found + 1 if found is not None else pos
    bad = [o["heading"] for o in outline if BAD_HEADING.search(o["heading"])]
    check(f"{name}: no false headings", not bad, bad[:3])
    text = "\n".join(c["text"] for c in chunks)
    check(f"{name}: no table-of-contents leftovers", not re.search(r"\.{6,}\s*\d+\s*$", text, re.M),
          re.findall(r".{40}\.{6,}\s*\d+", text)[:2])
    check(f"{name}: no page-number lines", not re.search(r"^(page|página)\s+\d+\s+(of|de)\s+\d+$", text, re.I | re.M))
    check(f"{name}: chunk sizes", all(0 < len(c["text"]) <= config.CHUNK_MAX_CHARS + 200 for c in chunks),
          max(len(c["text"]) for c in chunks) if chunks else "no chunks")
    check(f"{name}: pages in range", all(1 <= c["page"] <= c["page_end"] <= p["pages"] for c in chunks))
    if outline:
        check(f"{name}: every chunk has a section path", all(c["path"] and c["section"] for c in chunks))

for pdf, phrases in ONCE.items():
    text = "\n".join(c["text"] for c in parse_pdf(pdf)["chunks"])
    for phrase in phrases:
        check(f"{pdf.name[:40]}: once '{phrase}'", text.count(phrase) == 1, f"{text.count(phrase)} times")

print("ALL PASSED" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
