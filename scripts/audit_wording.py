"""Read-only wording audit of the stored display text (titles, headlines, summaries, assessments) in the staging DB.

    KSSL_STAGING_DSN=postgresql://... PYTHONIOENCODING=utf-8 python -m scripts.audit_wording > docs/ui_port/WORDING_AUDIT.md

Every text column of a staging table whose name reads as display text is scanned with the rules below. The report splits
prompt-written text (fixed in the prompts) from text copied verbatim from a source (publisher headlines, portal titles,
datasheet labels: the source's own words, not rewritten). Code columns are left out: the UI shows them as words.
Nothing is written to the database.
"""
import os
import re
import sys
from collections import defaultdict

import psycopg2

SHORT = re.compile(r"(title|headline|eyebrow|label|glance)", re.I)   # one-line fields: the ending rules apply
# lower-case only: "Item A", "Nammo AS", "Stridsvagn 123 A" are names, not a stranded article
FUNCTION_END = re.compile(r"\b(for|of|to|in|on|at|with|and|or|by|from|as|the|a|an|its|their|than|into|over|under|via)\s*$")
# a label printed in front of its value ("Delivered to: Poland"): its ending is not the end of the text
LABEL_OF_VALUE = {"competitive_signal_evidence.label"}
RULES = [
    # (id, what, one-line fields only?, test)
    ("ends-function-word", "ends on a preposition, conjunction or article", True, lambda t: FUNCTION_END.search(t)),
    ("ends-bare-count", "ends on 'for/of/to/with N' with no noun after the number", True,
     lambda t: re.search(r"\b(for|of|to|with)\s+(?!(?:19|20)\d\d\b)\d[\d,.]*\s*$", t, re.I)),   # a year is a noun
    ("ends-dangling-punct", "ends on a comma, colon, semicolon, dash or slash", False, lambda t: re.search(r"[,:;/–—-]\s*$", t)),
    ("cut-off", "ends in '…' / '...' or stops inside an open bracket or quote", False,
     lambda t: re.search(r"(\.\.\.|…)\s*$", t) or t.count("(") > t.count(")") or t.count("[") > t.count("]")
     or t.count('"') % 2 == 1),
    ("doubled-word", "the same word twice in a row", False, lambda t: re.search(r"\b(\w{2,})\s+\1\b", t, re.I)),
    ("raw-code", "a stored code instead of words (snake_case)", False, lambda t: re.search(r"\b[a-z]+_[a-z_]+\b", t)),
    ("markup", "HTML tags or entities", False, lambda t: re.search(r"</?[a-z][^>]*>|&(amp|lt|gt|quot|#\d+);", t, re.I)),
    ("placeholder", "a placeholder value (null, None, undefined, N/A, TBD, lorem)", False,
     lambda t: re.fullmatch(r"\s*(null|none|undefined|n/?a|tbd|tba|-|—)\s*", t, re.I) or re.search(r"\blorem ipsum\b", t, re.I)),
    ("spacing", "double space, leading/trailing space or a space before punctuation", False,
     lambda t: "  " in t or t != t.strip() or re.search(r"\s[,.;:!?](\s|$)", t)),
    ("lowercase-start", "a one-line field that starts lowercase", True, lambda t: re.match(r"[a-z]", t)),
]
SKIP_TABLES = {"source_document", "tender_raw", "news_candidate", "prompt_run", "spec_dictionary", "review_decision", "fact_source"}
COL = re.compile(r"(title|headline|summary|finding|why|what_|assessment|description|note|line|narrative|rationale|verdict|"
                 r"label|reason|recommend|impact|eyebrow|glance|statement|desc|text)", re.I)
NOT_COL = re.compile(r"((^|_)(url|code|key|kind|type|status|raw|json)(_|$)|_id$|body_text)", re.I)   # whole name parts: "drawer" is not "raw"
# columns that hold a stored CODE (the UI turns it into words), not prose
CODE_COLS = {"impact_dimension", "impact_dimension_2", "label_after", "label_before", "current_label", "fit_label",
             "pursue_label", "relationship_label", "option_label"}
# text copied verbatim from a source: reported apart, it is the source's wording
SOURCE = re.compile(r"^(market_tender\.|market_award\.|competitive_news_article\.headline$|.*\.source_text$|.*\.evidence_text$|"
                    r".*source_label$|.*publisher.*|.*\.source_article_title$|technology_source\.label$|.*\.spec_label$|"
                    r".*specification\.value_text$|competitive_product_news\.headline$|competitive_geo_product_news\.headline$)")


def section(title, hits, scanned, keep):
    print(f"\n# {title}\n")
    print("| Rule | Texts | Columns |\n|---|---:|---:|")
    picked = {rid: {k: v for k, v in hits[rid].items() if keep(k)} for rid, *_ in RULES}
    for rid, what, _, _ in RULES:
        print(f"| {what} (`{rid}`) | {sum(len(v) for v in picked[rid].values())} | {len(picked[rid])} |")
    for rid, what, _, _ in RULES:
        if not picked[rid]:
            continue
        print(f"\n## {what} (`{rid}`)\n")
        for col, texts in sorted(picked[rid].items(), key=lambda kv: -len(kv[1])):
            print(f"- **{col}**: {len(texts)} of {scanned[col]}")
            for x in texts[:3]:
                print(f"  - {x[:200].replace('|', '/')}{'…' if len(x) > 200 else ''}")


def main():
    dsn = os.environ.get("KSSL_STAGING_DSN") or sys.exit("KSSL_STAGING_DSN is not set")
    con = psycopg2.connect(dsn)
    cur = con.cursor()
    cur.execute("""SELECT c.table_name, c.column_name FROM information_schema.columns c
                   JOIN information_schema.tables t USING (table_schema, table_name)
                   WHERE c.table_schema = 'staging' AND t.table_type = 'BASE TABLE'
                     AND c.data_type IN ('text', 'character varying') ORDER BY 1, 2""")
    cols = [(t, c) for t, c in cur.fetchall()
            if t not in SKIP_TABLES and COL.search(c) and not NOT_COL.search(c) and c not in CODE_COLS]
    hits = defaultdict(lambda: defaultdict(list))        # rule -> "table.column" -> [text]
    scanned = defaultdict(int)
    for t, c in cols:
        cur.execute(f'SELECT "{c}" FROM staging."{t}" WHERE "{c}" IS NOT NULL AND "{c}" <> \'\'')
        short = bool(SHORT.search(c)) and f"{t}.{c}" not in LABEL_OF_VALUE
        for (v,) in cur.fetchall():
            v = str(v)
            scanned[f"{t}.{c}"] += 1
            for rid, _, one_line, test in RULES:
                if (not one_line or short) and test(v):
                    hits[rid][f"{t}.{c}"].append(v)
    con.close()
    print("# Wording audit (staging)\n")
    print(f"{len(scanned)} display-text columns, {sum(scanned.values())} stored texts scanned. Read-only "
          "(`scripts/audit_wording.py`). Code columns (impact_dimension, current_label, fit_label, ...) are left out: "
          "the UI shows them as words. One-line rules apply to title / headline / label / eyebrow / glance fields.")
    section("Prompt-written text (fix in the prompts)", hits, scanned, lambda col: not SOURCE.match(col))
    section("Source text copied verbatim (publisher / portal wording; not rewritten)", hits, scanned, lambda col: bool(SOURCE.match(col)))


if __name__ == "__main__":
    main()
