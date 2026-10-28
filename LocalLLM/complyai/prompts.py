"""All prompts and JSON schemas sent to the local LLM, kept in one place for tuning."""
import os

# Language of everything the AI writes (statements, explanations, actions). English by default, like LEONI's
# correspondence matrices; e.g. COMPLYAI_OUTPUT_LANGUAGE="Portuguese (Portugal)" switches it.
OUT_LANG = os.getenv("COMPLYAI_OUTPUT_LANGUAGE", "English")

# Context lock: appended to EVERY system prompt by llm.chat_json. The code checks it as well (quotes, numbers and
# IT evidence must be found in the source text; README "Accuracy safeguards").
GROUNDING = """CONTEXT RULE: work only from the text given in this message (passages, requirements, IT excerpts,
rules and lists). Do not add facts from general knowledge, other documents, standards or typical industry
practice. If the given text does not state something, leave the field empty or choose the "not related" / "not
stated" answer: never guess. Quotes and evidence are copied word for word from the given text, in its original
language."""

CATEGORIES = [
    "quality_system", "apqp_ppap", "product_process_spec", "testing_inspection",
    "labeling_packaging", "traceability_records", "change_management",
    "nonconformity_corrective_action", "supplier_subcontractor", "training_competence",
    "measurement_calibration", "environment_safety_legal", "logistics_delivery", "other",
]

# --- document metadata ----------------------------------------------------------
META_SYSTEM = """You read the first pages of a document received by LEONI Portugal (a wire-harness
manufacturer) and return its metadata. Use null when a field is not present. Never invent values.
"client" is the company that ISSUED / OWNS the document (e.g. Cummins, Caterpillar, John Deere / Deere &
Company, AGCO, JCB). LEONI is the supplier receiving it: never answer LEONI unless the document is a LEONI
internal document. Use the short company name (e.g. "John Deere", not "Deere & Company, Moline")."""

META_SCHEMA = {
    "type": "object",
    "properties": {
        "client": {"type": ["string", "null"], "description": "Issuing company"},
        "code": {"type": ["string", "null"], "description": "Document number/identifier"},
        "title": {"type": ["string", "null"]},
        "version": {"type": ["string", "null"], "description": "Revision / version / change number"},
        "date": {"type": ["string", "null"], "description": "Publication or revision date as written"},
        "language": {"type": ["string", "null"], "description": "ISO 639-1 code of the main language"},
    },
    "required": ["client", "code", "title", "version", "date", "language"],
}

# LEONI's own Portuguese terms, so translated statements match the wording of the ITs
GLOSSARY = (" using LEONI terminology: harness/Kabelbaum = cablagem, sleeve = manga, tape wrap = bandagem, "
            "wire = fio, connector = conector, label = etiqueta, assembly board = tábua de montagem"
            if OUT_LANG.lower().startswith("portug") else
            " with standard English wire-harness terms only (if the source is Portuguese or German, translate: "
            "cablagem/Kabelbaum -> harness, manga -> sleeve, bandagem -> tape wrap, fio -> wire, etiqueta -> label, "
            "tábua de montagem -> assembly board; never keep the Portuguese/German word)"
            if OUT_LANG.lower().startswith("english") else "")

# --- requirement extraction ---------------------------------------------------------
EXTRACT_SYSTEM = f"""You are a quality/compliance engineer at LEONI Portugal, a supplier of wire harnesses.
You receive a passage of a customer document (Customer Specific Requirements or a technical standard).
Extract every requirement the passage imposes on the SUPPLIER (LEONI), i.e. something the supplier
shall / must / is expected to do, provide, guarantee, keep, measure, or not do.

Rules:
- One atomic requirement per item. Split sentences that contain several obligations.
- Ignore definitions, marketing text, background, scope/purpose/applicability statements ("this document
  describes...", "applies to..."), the customer's own internal duties and pure references to other
  documents (unless the passage obliges the supplier to comply with them).
- Do not invent the subject: if the text says "X shall be open in delivery condition", the requirement is
  exactly that, not "the supplier shall describe...". When the actor is the supplier, make "the supplier" the
  subject ("The supplier shall ...") — never make the harness the actor of an organisational duty.
- "kind": classify each item honestly; only "supplier_requirement" items are used downstream:
  "supplier_requirement" = an obligation on the supplier; "definition" = explains a term/process/acronym;
  "informative" = background, consequences, statistics, what the customer will do/count/consider
  (e.g. "parts will be treated as non-conforming", "X will not count as a defect");
  "customer_duty" = what the customer or its staff does or MAY do ("o SQE da Cummins pode verificar...",
  "a Cummins irá cobrar...", rules about the customer's own documents/translations), even if the sentence
  mentions the supplier; "scope" = what the document/process applies to.
- "statement": a concise, self-contained rewrite in {OUT_LANG} that is understandable WITHOUT the passage:
  name the object/context it applies to when the passage gives one (e.g. the component, document or
  process concerned); never add a context that is not in the passage. Keep every number, tolerance,
  unit, frequency, deadline, retention period and referenced standard exactly.
- "quote": the shortest verbatim excerpt (original language) that supports the requirement, max 300 chars.
- "obligation": "mandatory" (shall/must/deve/muss) or "recommended" (should/expected/recommended/soll).
- "parameters": measurable values in the requirement (empty list if none).
- If the passage contains no supplier requirement return an empty list."""

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {  # quote first: copy the source, then translate it
                    "quote": {"type": "string"},
                    "kind": {"type": "string", "enum": ["supplier_requirement", "definition", "informative",
                                                       "customer_duty", "scope"]},
                    "statement": {"type": "string"},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "obligation": {"type": "string", "enum": ["mandatory", "recommended"]},
                    "parameters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"name": {"type": "string"}, "value": {"type": "string"},
                                           "unit": {"type": "string"}},
                            "required": ["name", "value", "unit"],
                        },
                    },
                },
                "required": ["quote", "kind", "statement", "category", "obligation", "parameters"],
            },
        }
    },
    "required": ["requirements"],
}


def extract_user(client: str, doc_title: str, section: str, page: int, text: str) -> str:
    return (f"Customer: {client}\nDocument: {doc_title}\nSection: {section or '-'} (page {page})\n\n"
            f"PASSAGE:\n\"\"\"\n{text}\n\"\"\"\n\n"
            f"Write every \"statement\" in {OUT_LANG}{GLOSSARY}. Keep \"quote\" in the original language.")


# --- requirement vs requirement (version change) -----------------------------------------
CHANGE_SYSTEM = f"""You compare a NEW customer requirement against OLDER requirements from the same customer
(possibly an earlier version of the same document, possibly in another language).
Decide whether one of the older requirements is the same obligation as the new one.
- "same": same obligation and same values (wording/language/translation differences don't matter).
- "modified": same subject/obligation but something changed (value, tolerance, frequency, deadline,
  scope, method, responsibility, referenced standard, mandatory vs recommended...).
- "unrelated": none of the older requirements is about the same obligation (match_index = -1).
"difference": in {OUT_LANG}, state precisely what changed (old -> new). Empty if same/unrelated.
"impact": how much the change could affect LEONI's processes/ITs (high/medium/low)."""

CHANGE_SCHEMA = {
    "type": "object",
    "properties": {
        "match_index": {"type": "integer"},
        "relation": {"type": "string", "enum": ["same", "modified", "unrelated"]},
        "difference": {"type": "string"},
        "impact": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["match_index", "relation", "difference", "impact"],
}


def change_user(new_stmt: str, new_quote: str, olds: list[dict]) -> str:
    lines = [f"NEW requirement:\n{new_stmt}\nOriginal text: \"{new_quote}\"\n", "OLDER requirements:"]
    for i, o in enumerate(olds):
        lines.append(f"[{i}] ({o['doc']}, p.{o['page']}) {o['statement']}\n    Original text: \"{o['quote']}\"")
    return "\n".join(lines)


# --- requirement vs ITs (conflict / compliance) ------------------------------------------
ASSESS_SYSTEM = f"""You are a compliance auditor at LEONI Portugal (wire-harness manufacturer).
You get ONE customer requirement, LEONI internal Work Instructions (ITs) found by an automatic search
(what each IT governs, its closest rules and an excerpt), and a list of further IT titles from LEONI's
IT index. Use "Governs/Applies to/Trigger" to decide same_subject: an IT only covers the activity,
situation and trigger it is written for. Mind the DIRECTION: customer requirements are about LEONI acting
as SUPPLIER towards the customer. An IT on how LEONI manages ITS OWN suppliers (complaints to suppliers,
supplier evaluation, purchased material) or internal supplier/customer units governs a different activity,
unless the requirement is explicitly about LEONI's sub-suppliers.

IMPORTANT: the search returns the closest ITs even when none is relevant, so most ITs shown are usually
NOT related. Sharing generic words (cliente, desenho, documento, alteração, etiqueta, qualidade) is not
enough.

Step 0: "requirement_subject": in a few words, which activity/process/object the requirement is about.
Step 1, for EACH IT shown (one assessment per IT code):
- "it_subject": in a few words, which activity/process the IT governs.
- "same_subject": true ONLY if that IT governs the same activity/process the requirement is about
  (e.g. requirement on 8D reports <-> IT on 8D analysis; requirement on harness labels <-> IT on labels).
Step 2, verdict:
- "not_related": same_subject is false.
- "conflict": same subject AND the IT prescribes something that contradicts the requirement (different
  value, limit, tolerance, frequency, deadline, retention period, method, approval/responsibility), so
  working according to the IT would violate the requirement. Needs a verbatim contradicting IT sentence.
  A different value for the same parameter IS a conflict (e.g. IT "10 a 15 mm" vs requirement
  "20 to 25 mm"; IT accepts 95% vs requirement demands at least 98%). An IT STRICTER than the requirement
  (shorter deadline, tighter tolerance, more frequent check, "imediatamente" vs "within 15 days") is NOT a
  conflict: it satisfies the requirement.
- "partial": same subject but the IT lacks what the requirement demands (missing step, record, customer
  notification/approval, weaker criterion). The IT must be revised.
- "compliant": same subject and the IT explicitly satisfies the requirement. The SPECIFIC element demanded
  (value, deadline, named standard, approver, record) must be in the IT: a generic wording ("um sistema de
  gestão reconhecido", "prazo adequado", "conforme necessário") does not cover a specific one ("ISO 9001 ou
  IATF 16949", "48 horas", "aprovação do SQE") -> that is "partial".
Terminology / translation differences are NOT gaps (tape wrap = bandagem = fita, sleeve = manga,
harness = cablagem, 8D report = relatório 8D): judge the substance.
Only use what is written in the excerpts; never assume content that is not shown.
"evidence": verbatim sentence copied from the IT excerpt (empty for not_related).
"explanation" and "action" in {OUT_LANG}; "action" = what must change in the IT (empty if
compliant/not_related).

Be brief (this runs on hundreds of requirements):
- requirement_subject and it_subject: max 8 words.
- not_related ITs: explanation max 12 words, evidence "", action "".
- other verdicts: evidence = ONE sentence copied from the IT, explanation max 50 words, action max 30 words.

Step 3: "related_index_its": codes from the IT INDEX list whose title indicates that the IT governs the
activity of the requirement, i.e. the ITs a quality engineer would list in the compliance matrix.
Usually 0-2 codes; empty list if none clearly fits."""


def assess_schema(it_codes: list[str], index_codes: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "requirement_subject": {"type": "string"},
            "assessments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "it_code": {"type": "string", "enum": it_codes or ["-"]},
                        "it_subject": {"type": "string"},
                        "same_subject": {"type": "boolean"},
                        "evidence": {"type": "string"},
                        "explanation": {"type": "string"},
                        "verdict": {"type": "string", "enum": ["conflict", "partial", "compliant", "not_related"]},
                        "action": {"type": "string"},
                    },
                    "required": ["it_code", "it_subject", "same_subject", "evidence", "explanation",
                                 "verdict", "action"],
                },
            },
            "related_index_its": {"type": "array", "items": {"type": "string", "enum": index_codes or ["-"]}},
        },
        "required": ["requirement_subject", "assessments", "related_index_its"],
    }


def assess_user(client: str, req: dict, its: dict[str, dict], index: list[dict]) -> str:
    parent = req.get("parent_section") if hasattr(req, "get") else ""
    where = " > ".join(dict.fromkeys(s for s in (parent, req["section"]) if s)) or "-"
    parts = [f"CUSTOMER REQUIREMENT ({client}, {req['doc']}, section {where}, p.{req['page']}):",
             req["statement"], f"Original text: \"{req['quote']}\"", "", "LEONI IT EXCERPTS:"]
    if not its:
        parts.append("(none)")
    for code, it in its.items():
        parts.append(f"\n=== {code} — {it['title']} ===")
        prof = it.get("profile") or {}
        if prof.get("purpose"):
            parts.append(f"Governs: {prof['purpose']} | Applies to: {prof.get('applies_to', '')}"
                         + (f" | Trigger: {prof['trigger']}" if prof.get("trigger") else ""))
        if it.get("rules"):
            parts.append("Closest IT rules:\n" + "\n".join(f"- {r}" for r in it["rules"]))
        for ex in it["excerpts"]:
            parts.append(f"Excerpt [p.{ex['page']} | {ex['section'] or '-'}]:\n{ex['text']}")
    parts.append("\nIT INDEX (titles only):")
    parts.extend(f"- {e['code']}: {e['title']}" for e in index)
    parts.append(f"\nWrite it_subject, requirement_subject, explanation and action in {OUT_LANG}.")
    return "\n".join(parts)


# --- narrow numeric cross-check -------------------------------------------------------------
VALUE_SYSTEM = """You compare a customer requirement with one sentence of an internal work instruction.
Answer whether both specify the SAME parameter (same physical quantity / deadline / limit for the same
thing) and whether the values conflict.
"values_conflict" is true only if some value ALLOWED by the instruction would VIOLATE the requirement
(e.g. instruction 10-15 mm vs requirement 20-25 mm; instruction accepts 95-100 % vs requirement >= 98 %).
It is false when every value allowed by the instruction satisfies the requirement (e.g. instruction
95-100 % vs requirement >= 95 %; instruction 24 h vs requirement within 48 h)."""

VALUE_SCHEMA = {
    "type": "object",
    "properties": {  # explanation first: the model reasons before committing to the booleans
        "explanation": {"type": "string"},
        "same_parameter": {"type": "boolean"},
        "values_conflict": {"type": "boolean"},
    },
    "required": ["explanation", "same_parameter", "values_conflict"],
}


def value_user(statement: str, quote: str, evidence: str) -> str:
    return (f"REQUIREMENT: {statement}\nOriginal: \"{quote}\"\n\nINSTRUCTION SENTENCE: {evidence}\n\n"
            f"Write the explanation in {OUT_LANG}.")


# --- grounding repair -------------------------------------------------------------------
FIX_NUMBERS_SYSTEM = f"""A requirement statement was translated from a source quote but its numbers do not
match the source. Rewrite the statement in {OUT_LANG} so that every number, unit, tolerance and deadline is
exactly the one in the source quote (e.g. "48 horas", not "4,8 horas"). Change nothing else."""

FIX_NUMBERS_SCHEMA = {"type": "object", "properties": {"statement": {"type": "string"}}, "required": ["statement"]}


def fix_numbers_user(statement: str, quote: str) -> str:
    return f"SOURCE QUOTE: {quote}\nSTATEMENT: {statement}"


# --- IT knowledge, extracted once per IT at ingestion ---------------------------------------
IT_PROFILE_SYSTEM = f"""You read a LEONI Portugal Work Instruction (IT) and describe precisely what it governs.
Answer in {OUT_LANG}. Be concrete and short; never describe things the IT does not contain.
- "purpose": the activity/process the IT governs (max 25 words).
- "applies_to": products, customers, departments, situations it applies to (max 25 words).
- "trigger": what starts the process described (e.g. "pedido de alteração do cliente"), "" if none.
- "actors": who executes it.
- "out_of_scope": closely related things the IT clearly does NOT cover (max 25 words, "" if unclear).
- "direction": whom the IT's activity is directed at:
  "customer_or_production" = LEONI's own production, quality system, or what LEONI does for/towards its
  customers; "own_suppliers" = how LEONI deals with ITS OWN suppliers (purchasing, incoming material,
  supplier evaluation, complaints or returns TO suppliers); "internal_units" = relations between internal
  LEONI units/plants (internal customer-supplier evaluation)."""

IT_PROFILE_SCHEMA = {
    "type": "object",
    "properties": {**{k: {"type": "string"} for k in ("purpose", "applies_to", "trigger", "actors", "out_of_scope")},
                   "direction": {"type": "string",
                                 "enum": ["customer_or_production", "own_suppliers", "internal_units"]}},
    "required": ["purpose", "applies_to", "trigger", "actors", "out_of_scope", "direction"],
}


def it_profile_user(code: str, title: str, text: str) -> str:
    return f"IT {code} — {title}\n\n{text}"


IT_RULES_SYSTEM = f"""Extract the concrete rules a LEONI Work Instruction (IT) passage prescribes: what must be done,
by whom, when, with which values/limits/deadlines/records. One rule per item, in {OUT_LANG}, self-contained
(mention the object/process), keeping numbers exactly. Skip document headers, revision history,
distribution notices, definitions and the template rules on how to edit this document (grey highlighting,
"-> <-" for deleted text, "content completely changed"). Return an empty list if the passage has no rule."""

IT_RULES_SCHEMA = {
    "type": "object",
    "properties": {"rules": {"type": "array", "items": {"type": "string"}}},
    "required": ["rules"],
}


def it_rules_user(code: str, title: str, section: str, text: str) -> str:
    return f"IT {code} — {title}\nSection: {section or '-'}\n\nPASSAGE:\n{text}"


# --- verification of flagged findings (thinking mode) ----------------------------------------------
VERIFY_SYSTEM = f"""You are a senior quality auditor at LEONI Portugal double-checking an automatic finding that a
customer requirement is not met by a LEONI Work Instruction (IT). Most automatic findings are FALSE ALARMS,
so be strict. Answer these in order:
1. "same_activity": does the IT govern exactly the activity, situation, actor and trigger the requirement is
   about? (e.g. an IT for changes requested by the customer does NOT govern changes initiated by the
   supplier; an IT on label layouts does NOT govern material-data submissions; an IT on how LEONI handles
   complaints to ITS OWN suppliers or internal supplier units does NOT govern LEONI's duties as the
   customer's supplier, unless the requirement is about sub-suppliers). If no -> not_related.
2. "already_covered": read ALL the IT information. Is the requirement satisfied in substance? Wording,
   language or level of detail differences do not matter (an 8D procedure with containment, root cause
   and preventive actions covers generic "take preventive/containment actions" requirements). But a
   SPECIFIC element the requirement names (value, deadline, standard, approver) must be present: a generic
   IT wording does not cover it. An IT stricter than the requirement (shorter deadline, tighter limit)
   covers it.
3. "contradicting_rule": an IT rule that, if followed, would violate the requirement (copy it), or "".
Verdict:
- "conflict": same_activity and a contradicting rule exists (different value/limit/deadline/method/approval).
- "partial": same_activity, nothing contradicts, but a SPECIFIC element of the requirement is missing and
  LEONI would need to add it to THIS IT (name it in "missing").
- "compliant": same_activity and already covered.
- "not_related": not the same activity.
Write reasoning, missing and action in {OUT_LANG}."""

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "same_activity": {"type": "boolean"},
        "already_covered": {"type": "boolean"},
        "contradicting_rule": {"type": "string"},
        "missing": {"type": "string"},
        "verdict": {"type": "string", "enum": ["conflict", "partial", "compliant", "not_related"]},
        "action": {"type": "string"},
    },
    "required": ["reasoning", "same_activity", "already_covered", "contradicting_rule", "missing", "verdict",
                 "action"],
}


def verify_user(client: str, req, it: dict, first_verdict: str, first_explanation: str) -> str:
    rules = "\n".join(f"- {r}" for r in it.get("rules", [])) or "(none extracted)"
    prof = it.get("profile") or {}
    return (f"CUSTOMER REQUIREMENT ({client}, {req['doc']} p.{req['page']}, section {req['section'] or '-'}):\n"
            f"{req['statement']}\nOriginal: \"{req['quote']}\"\n\n"
            f"IT {it['code']} — {it['title']}\n"
            f"Purpose: {prof.get('purpose', '')}\nApplies to: {prof.get('applies_to', '')}\n"
            f"Trigger: {prof.get('trigger', '')}\nActors: {prof.get('actors', '')}\n"
            f"Out of scope: {prof.get('out_of_scope', '')}\n\nRELEVANT IT RULES:\n{rules}\n\n"
            f"IT EXCERPT:\n{it['excerpt']}\n\n"
            f"AUTOMATIC FINDING TO CHECK: {first_verdict} — {first_explanation}\n\n"
            f"Write reasoning, missing and action in {OUT_LANG}.")


# --- section-level IT mapping (what LEONI's correspondence matrix lists per section) ----------------
SECTION_SYSTEM = f"""You build LEONI Portugal's customer-requirements correspondence matrix (IT 3535-11 A5).
For ONE section of a customer document you get its heading (often with the ISO/IATF clause), a summary of
its requirements and candidate LEONI Work Instructions (ITs) from the IT index. Select the ITs a LEONI
quality engineer would list for this section: the ITs that GOVERN the activities the section requires
(e.g. "Competence (7.2)" -> the training IT; "Preservation (8.5.4)" -> storage/shelf-life/packaging ITs;
"Control of changes (8.5.6)" -> the engineering-change IT). Usually 1-3 ITs; none if no candidate clearly
governs the section. Sections that are introduction, scope, purpose, definitions/acronyms/glossary,
references or forms lists ALWAYS get an empty list, even if their text mentions processes.
"reason": one short sentence per IT in {OUT_LANG}."""


def section_schema(codes: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "selected": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"reason": {"type": "string"},
                                   "it_code": {"type": "string", "enum": codes or ["-"]}},
                    "required": ["reason", "it_code"],
                },
            }
        },
        "required": ["selected"],
    }


def section_user(client: str, doc: str, heading: str, statements: list[str], candidates: list[dict]) -> str:
    reqs = "\n".join(f"- {s}" for s in statements) or "(no requirements)"
    cands = "\n".join(f"- {c['code']}: {c['title']}" + (f" (ISO {c['iso']})" if c.get("iso") else "")
                      for c in candidates)
    return (f"CUSTOMER: {client} — {doc}\nSECTION: {heading}\n\nREQUIREMENTS OF THIS SECTION:\n{reqs}\n\n"
            f"CANDIDATE ITs (LEONI IT index):\n{cands}\n\nWrite each reason in {OUT_LANG}.")


# --- double-check of "compliant" verdicts --------------------------------------------------------
VERIFY_COMPLIANT_SYSTEM = f"""You double-check an automatic claim that a LEONI Work Instruction (IT) ALREADY SATISFIES a
customer requirement. Be strict about specifics:
1. "key_element": the specific thing the requirement demands (value, deadline, named standard or document,
   approver, recipient, record), in a few words.
2. "it_quote": copy the IT sentence that contains that key element (same value, or stricter), or "" if none.
   Generic wording does NOT count ("normas aplicáveis", "canal estabelecido", "prazo adequado",
   "conforme necessário" do not cover "ISO-3834", "um interlocutor designado", "48 horas").
3. "contradicting_rule": copy an IT rule that allows what the requirement forbids or sets a less strict
   value/deadline (e.g. IT "até 20 dias" vs requirement "15 dias"), or "".
Verdict: "conflict" if contradicting_rule; "compliant" if it_quote contains the key element; else "partial".
"missing" and "action" in {OUT_LANG} (empty if compliant)."""

VERIFY_COMPLIANT_SCHEMA = {
    "type": "object",
    "properties": {
        "key_element": {"type": "string"},
        "it_quote": {"type": "string"},
        "contradicting_rule": {"type": "string"},
        "verdict": {"type": "string", "enum": ["conflict", "partial", "compliant"]},
        "missing": {"type": "string"},
        "action": {"type": "string"},
    },
    "required": ["key_element", "it_quote", "contradicting_rule", "verdict", "missing", "action"],
}


# --- requirement vs requirements of OTHER documents of the same customer -----------------------
CROSS_SYSTEM = f"""You compare a customer requirement with requirements from OTHER documents of the same customer
(e.g. a quality manual and its PPAP annex, a handbook and a technical standard). Documents of one customer
often repeat or elaborate the same obligation; that is normal and NOT a problem. Decide:
- "same": the same obligation (wording, language or translation differ).
- "complements": same topic, but one adds detail, scope or a related obligation; LEONI can satisfy both at once.
- "contradicts": LEONI CANNOT satisfy both: different value, limit, deadline, frequency, retention period,
  approver or method for the same thing (e.g. "retain records 10 years" vs "retain records 15 years" is
  satisfiable by 15 -> "complements"; "submit within 24 h" vs "submit within 48 h" for the same report ->
  satisfiable by 24 h -> "complements"; "approval by SQE required" vs "no approval required" -> "contradicts").
  Only real incompatibility counts.
- "unrelated": no older requirement is about the same obligation (match_index = -1).
"difference": for "contradicts" only, in {OUT_LANG}, state both versions precisely; otherwise "".
"impact": high/medium/low for LEONI's processes."""

CROSS_SCHEMA = {
    "type": "object",
    "properties": {
        "match_index": {"type": "integer"},
        "relation": {"type": "string", "enum": ["same", "complements", "contradicts", "unrelated"]},
        "difference": {"type": "string"},
        "impact": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["match_index", "relation", "difference", "impact"],
}


# --- section headings in the output language (matrix column "Conteudo") ---------------------------
HEADINGS_SYSTEM = f"""Translate section headings of a customer quality document into {OUT_LANG}.
Keep the numbering/lettering and any ISO/IATF clause in brackets exactly ("K. Competência (7.2)" ->
"K. Competence (7.2)"). Use standard quality-management terms (IATF 16949 / ISO 9001 English wording when the
heading names an ISO clause). Headings already in {OUT_LANG} are returned unchanged. Return exactly one
translation per input heading, in the same order."""

HEADINGS_SCHEMA = {
    "type": "object",
    "properties": {"translations": {"type": "array", "items": {"type": "string"}}},
    "required": ["translations"],
}


def headings_user(headings: list[str]) -> str:
    # "[n]" tags (not "1.", which would mix with the headings' own numbering); the tags are not translated
    return (f"{len(headings)} HEADINGS:\n" + "\n".join(f"[{i + 1}] {h}" for i, h in enumerate(headings))
            + "\n\nReturn the translations without the [n] tags.")


# --- translating already stored output (switching the output language without reprocessing) -----------
TRANSLATE_SYSTEM = f"""Translate each text into {OUT_LANG}. These are compliance analyses about customer requirements
and LEONI Work Instructions (wire-harness plant). Keep exactly: numbers, units, codes (WI 3164-11, IC 3157-11,
PPAP, APQP, 8D, SQE, SCR, CES), document names and anything inside quotation marks. Use standard
quality-management terms (harness, sleeve, tape wrap, control plan, nonconformity). Texts already in
{OUT_LANG} are returned unchanged. Return exactly one translation per input text, in the same order."""

TRANSLATE_SCHEMA = {
    "type": "object",
    "properties": {"translations": {"type": "array", "items": {"type": "string"}}},
    "required": ["translations"],
}


def translate_user(texts: list[str]) -> str:
    return (f"{len(texts)} TEXTS:\n" + "\n".join(f"[{i + 1}] {t}" for i, t in enumerate(texts))
            + "\n\nReturn the translations without the [n] tags.")
