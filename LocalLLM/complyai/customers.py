"""Which customers a text is about (deterministic, no LLM).

LEONI's ITs often hold information for several customers in one document: a table column per customer (WI 3069-11 A2,
traceability), a section per customer label (WI 3404-11 A5), a sentence "AGCO: ..." / "(only for PERKINS)", or a whole
IT written for one customer (WI 3600-11, John Deere braid sleeve). IT text for another customer is no evidence for a
requirement of this customer (README "Accuracy safeguards"). Names come from config.CUSTOMER_ALIASES.
"""
import re

from . import config

# customers named only as examples do not limit a rule: "(ex. CAT e VOLVO CE)", "(e.g., Cummins)", "por exemplo ..."
_EXAMPLE = re.compile(r"\((?:ex\.|e\.\s?g\.|eg\.|por exemplo|for example|z\.\s?b\.|such as|como)[^)]*\)"
                      r"|\b(?:por exemplo|for example|e\.\s?g\.|such as)\b[^.;\n]*", re.I)


def _compile(name: str, pats: list[str]):
    # upper-case aliases ("\bCAT\b", "\bJD\b") are matched as written: "cat" / "jd" in running text are not customers
    exact = [p for p in pats if re.sub(r"\\[a-z]", "", p) != re.sub(r"\\[a-z]", "", p).lower()]
    loose = [p for p in pats if p not in exact]
    out = []
    if loose:
        out.append(re.compile("|".join(f"(?:{p})" for p in loose), re.I))
    if exact:
        out.append(re.compile("|".join(f"(?:{p})" for p in exact)))
    return name, out


_PATTERNS = [_compile(n, p) for n, p in config.CUSTOMER_ALIASES.items()]


def named(text: str, examples: bool = False) -> set[str]:
    """Canonical names of the customers a text names ('CAT -PERKINS' -> {'Caterpillar'}). Names given only as examples
    are ignored unless examples=True."""
    text = text or ""
    if not examples:
        text = _EXAMPLE.sub(" ", text)
    return {name for name, pats in _PATTERNS if any(p.search(text) for p in pats)}


def canonical(client: str) -> str:
    """'Deere & Company' -> 'John Deere', 'Caterpillar Inc.' -> 'Caterpillar'; unknown names stay as they are."""
    found = named(client or "", examples=True)
    return next(iter(found)) if len(found) == 1 else (client or "").strip()


def applies(scope: set[str], client: str) -> bool:
    """True if IT text with this customer scope (empty = every customer) may be used for a requirement of `client`."""
    return not scope or canonical(client) in scope
