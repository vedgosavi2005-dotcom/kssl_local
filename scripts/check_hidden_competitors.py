"""Leak check for the qualification filter (user decision 2026-10-18): build the dataset the API serves and search it for every
competitor that does not qualify. Ids must never appear; a name may appear only inside free text of another card (reported).

    KSSL_VIEW=review KSSL_STAGING_DSN=... python -m scripts.check_hidden_competitors     # exit 1 when a hidden id leaks
"""
import json
import os
import re
import sys
from collections import Counter

os.environ.setdefault("KSSL_VIEW", "review")
from backend import app  # noqa: E402
from prompts.derive_comp import norm_org  # noqa: E402


def main() -> int:
    database = app.load_all_tables()
    comps = database["serving"]["competitive_competitor"]
    hidden = {str(r["competitor_id"]): r for r in comps if r.get("qualifies") is not True}
    d = app.build_dataset(database)
    shown = [c for c in d["competitors"].values() if c.get("dir") != "client"]
    print(f"competitors: {len(comps)} stored, {len(comps) - len(hidden)} qualify, {len(shown)} shipped (+ the client)")
    blob = json.dumps(d, default=str)
    leaks = [cid for cid in hidden if cid in blob]
    print(f"hidden competitor ids found in the dataset: {len(leaks)}")
    # names: where do they still appear (paths), to tell structure leaks from mentions inside free text
    from backend.news import subject_for
    names = set()
    for cid, r in hidden.items():             # every name the news job knows for it (aliases, acronyms such as HII)
        sub = subject_for(cid, r.get("display_name") or "", r.get("legal_name") or "", r.get("short_name") or "")
        names |= {n for n in (*sub.names, *(a for a, _ in sub.cond)) if n and len(n) >= 3}
    # an alias that is also part of a shown company's name ("KNDS" in "Nexter (KNDS France)") is ambiguous: not a leak signal
    shown_names = " | ".join(str(r.get(k) or "") for r in comps if str(r["competitor_id"]) not in hidden for k in ("display_name", "short_name", "legal_name"))
    names = {n for n in names if not re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", shown_names)}
    paths: Counter = Counter()

    def walk(o, path):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, f"{path}.{k}")
        elif isinstance(o, list):
            for v in o:
                walk(v, f"{path}[]")
        elif isinstance(o, str):
            for n in names:
                if re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", o):
                    paths[re.sub(r"\.details\.[^.]+", ".details.<id>", path)] += 1
    walk(d, "")
    print("hidden names inside text (path: count):")
    for p, n in paths.most_common(25):
        print(f"  {p}: {n}")
    exact = [p for p in paths if re.search(r"\.(company|name|competitor|competitorName|rival|rivalToBeat|assignee|owner)$", p)]
    print(f"name-valued fields still holding a hidden competitor: {exact or 'none'}")
    return 1 if leaks else 0


if __name__ == "__main__":
    sys.exit(main())
