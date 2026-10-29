"""Build a LABELLED test set for the requirement-vs-IT judge (tests/fixtures/judge_set.json).

LEONI's real labels are not available, so: take real customer requirements (from the ingested Cummins
handbook) and let the LLM write, for each one, three short IT passages with a KNOWN relation:
  compliant  - same activity, satisfies the requirement (same values, wording may differ)
  conflict   - same activity, a rule that violates it (other value / deadline / approval / method)
  partial    - same activity, consistent, but the specific element of the requirement is missing
Deterministic checks reject variants that do not respect their label; tests/eval_judge.py adds a 4th,
unrelated IT (another item's passage) and scores the engine against these labels.

    python tests/make_judge_set.py --n 24
"""
import argparse
import json
import random
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from complyai import llm  # noqa: E402
from complyai.engine import _norm_numbers, _pimap  # noqa: E402
from complyai.store import Store  # noqa: E402

SYSTEM = """You write test data for a compliance-checking system at LEONI Portugal (wire-harness plant).
Given ONE customer requirement, first name its "key_element": ONLY the specific thing it demands, in at most 6
words, without the activity around it (e.g. "48 horas", "aprovação do SQE via SCR", "ISO 9001 ou IATF 16949",
"registos durante 15 anos", "apenas em situações de exceção"). Then write three excerpts of an internal LEONI Work
Instruction (IT) that governs exactly the activity of the requirement, 3-5 sentences each, European Portuguese.

Each excerpt must read like the IT itself: neutral imperative rules ("O QM deve...", "A VCM regista..."), with
departments (QM/VCM/PR/IE/PP/RH) and concrete values. NEVER comment on the requirement, the customer document,
compliance, violations or what is missing (no "viola", "não menciona", "não há definição", "requisito do
cliente", "exigência", "política da Cummins").
- "compliant": includes the key_element with the SAME value/deadline/approval (wording may differ).
- "conflict": same activity, states as a normal rule something INCOMPATIBLE with the key_element: another
  value, a longer deadline, a different approver, or allows what the requirement forbids.
- "partial": same activity and level of detail, consistent with the requirement, but the key_element is
  simply absent (a reader would not find it anywhere in the excerpt).
"it_title": a plausible LEONI IT title for this activity (Portuguese)."""

SCHEMA = {
    "type": "object",
    "properties": {k: {"type": "string"} for k in ("it_title", "key_element", "compliant", "conflict", "partial")},
    "required": ["it_title", "key_element", "compliant", "conflict", "partial"],
}
# commentary that would leak the label to the judge
LEAKS = re.compile(r"\bviola|contraria|não (há|existe|se encontra)\b.{0,25}(menç|defini|refer)|não menciona|"
                   r"não especifica|requisito do cliente|exigência|exigid[oa] pel[oa]|política (atual|da)|"
                   r"sistema IT|não está alinhad|em conformidade com o requisito", re.I)
STOP = {"para", "pelo", "pela", "como", "deve", "devem", "qualquer", "todos", "todas", "entre", "após", "sobre",
         "cummins", "fornecedor", "fornecedores", "processo", "sempre", "caso", "quando", "desde", "parte"}
KEYWORDS = re.compile(r"\d|aprova|notific|prazo|regist|dias|horas|anos|mensal|anual|semanal|imediat", re.I)


def _words(text: str) -> set[str]:
    """Lower-case words of 4+ letters without accents, plural 's' dropped ('alterações' == 'alteracao')."""
    plain = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return {re.sub(r"(oe|e)?s$", "", w) for w in re.findall(r"[a-z]{4,}", plain)}


def checks(req: dict, v: dict) -> list[str]:
    """Reasons to reject a generated item (label not respected)."""
    problems = []
    nums = _norm_numbers(req["statement"] + " " + req["quote"])
    if nums:
        if not nums & _norm_numbers(v["compliant"]):
            problems.append("compliant variant lacks the requirement's numbers")
        if nums & _norm_numbers(v["partial"]):
            problems.append("partial variant repeats the requirement's numbers")
    if len({v["compliant"], v["conflict"], v["partial"]}) < 3:
        problems.append("variants not distinct")
    # the partial variant must really lack the key element: reject if it contains most of its words
    key_words = _words(v.get("key_element", "")) - _words(" ".join(STOP))
    if key_words:
        if len(key_words & _words(v["partial"])) / len(key_words) >= 0.5:
            problems.append("partial variant contains the key element")
    for label in ("compliant", "conflict", "partial"):
        if m := LEAKS.search(v[label]):
            problems.append(f"{label} variant comments on itself ({m.group(0)!r})")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=24)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--out", default=str(ROOT / "tests" / "fixtures" / "judge_set.json"))
    args = ap.parse_args()

    store = Store()
    rows = [dict(r) for r in store.q("""SELECT r.id, r.statement, r.quote, r.category, d.client, d.code doc
                                        FROM requirements r JOIN documents d ON d.id=r.doc_id
                                        WHERE d.kind='CSR' AND r.status='active' AND r.obligation='mandatory'""")]
    rows = [r for r in rows if 60 <= len(r["statement"]) <= 260 and KEYWORDS.search(r["statement"])]
    if not rows:
        sys.exit("no ingested customer requirements found (ingest a CSR first)")
    # round-robin over categories for diversity; ask for extra items to replace rejected ones
    random.Random(args.seed).shuffle(rows)
    by_cat: dict[str, list] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    picked = []
    while len(picked) < args.n * 3 and any(by_cat.values()):
        for cat in list(by_cat):
            if by_cat[cat]:
                picked.append(by_cat[cat].pop())

    def gen(r):
        user = f"CUSTOMER REQUIREMENT ({r['client']}):\n{r['statement']}\nOriginal: \"{r['quote']}\""
        try:
            return r, llm.chat_json(SYSTEM, user, SCHEMA, max_tokens=1200)
        except llm.LLMError as e:
            return r, {"error": str(e)}

    items = []
    for r, v in _pimap(gen, picked, "generation"):
        if "error" in v:
            continue
        problems = checks(r, v)
        if problems:
            print(f"rejected req {r['id']}: {'; '.join(problems)}")
            continue
        items.append({"req_id": r["id"], "client": r["client"], "doc": r["doc"], "category": r["category"],
                      "statement": r["statement"], "quote": r["quote"], "it_title": v["it_title"],
                      "key_element": v["key_element"],
                      "variants": {"compliant": v["compliant"], "conflict": v["conflict"], "partial": v["partial"]}})
        if len(items) >= args.n:
            break
    Path(args.out).write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(items)} labelled items written to {args.out}")


if __name__ == "__main__":
    main()
