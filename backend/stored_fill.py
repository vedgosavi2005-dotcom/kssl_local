"""Fill two display fields from rows already stored: no model call, no fetch. A routine code step (backend/routine.py), idempotent.

    python -m backend.stored_fill [--dry-run]         both fills on the local staging DB
    python -m backend.stored_fill --selftest          pure checks, fictional values

programs  competitive_product_program from the geo prompt's sales rows (competitive_geo_product) that name a CUSTOMER and a catalogue
          product of the same competitor (exact name). A named buyer of a named product is a programme (prompts/product_program.yml rule).
          program_id = uuid5 of the geo_product_id, so a re-run rebuilds the same rows; every derived row carries fact_source rows tagged
          document_id 'geo_product:<id>' (copied from the sales row's own sources), which is how a re-run finds and replaces them.
          One row per product and buyer (latest date), only when the sales row has a source for the customer. Skipped when the product already has a prompt-written programme with the same authority. Status is left empty (the sales row
          says export / production, not the programme's stage).
moment    competitive_competitor_moment.image_url, when empty: its signal's thumbnail, else the news image stored for the same url.
"""

from __future__ import annotations

import argparse
import sys
import uuid

NS = uuid.UUID("6f1d3c52-6a9e-4c1b-9a51-1c0b6a7d2e11")
TAG = "geo_product:"
WORD = {"export": "purchase", "licensed production": "licence production", "local production": "production"}
COPY = {"program_title": ("customer_name", "product_name"), "authority": ("customer_name",), "program_date": ("since_date",),
        "description": ("record_note", "quantity", "reported_value")}


def program_row(g: dict) -> dict:
    """One sales row (geo_product + product_id + country) -> the programme columns."""
    family = (g["product_name"] or "").split(" (")[0].strip()
    act = (g.get("activity_type") or "").strip()
    title = f"{g['customer_name'].strip()} {family} {WORD.get(act.lower(), 'purchase')}"
    where = "to" if act.lower() in ("", "export") else "in"
    bits = [f"{act or 'Supply'} {where} {g['country_name']}." if g.get("country_name") else ""]
    bits += [f"Quantity: {g['quantity']}." if g.get("quantity") else "", f"Value: {g['reported_value']}." if g.get("reported_value") else ""]
    return {"program_id": str(uuid.uuid5(NS, str(g["geo_product_id"]))), "product_id": str(g["product_id"]), "program_title": title[:250],
            "authority": g["customer_name"].strip()[:200], "program_date": g.get("since_date"),
            "description": " ".join(b for b in bits if b) or None}


def fill_programs(cur) -> int:
    cur.execute("SELECT DISTINCT row_id FROM staging.fact_source WHERE table_name = 'competitive_product_program' AND document_id LIKE %s",
                (TAG + "%",))
    old = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT geo_product_id FROM staging.competitive_geo_product")
    old += [str(uuid.uuid5(NS, str(r[0]))) for r in cur.fetchall()]     # also rows whose tagged sources were lost
    cur.execute("DELETE FROM staging.fact_source WHERE table_name = 'competitive_product_program' AND row_id = ANY(%s)", (old,))
    cur.execute("DELETE FROM staging.competitive_product_program WHERE program_id = ANY(%s::uuid[])", (old,))
    cur.execute("""SELECT DISTINCT ON (p.product_id, lower(trim(gp.customer_name))) gp.geo_product_id, gp.product_name, gp.customer_name, gp.activity_type, gp.quantity, gp.reported_value,
                          gp.since_date, g.country_name, p.product_id
                   FROM staging.competitive_geo_product gp
                   JOIN staging.competitive_geo_company_presence pr ON pr.presence_id = gp.presence_id
                   JOIN staging.competitive_geo_location g ON g.location_id = pr.location_id
                   JOIN staging.competitive_product p ON p.competitor_id = pr.competitor_id AND lower(p.product_name) = lower(gp.product_name)
                   WHERE coalesce(trim(gp.customer_name), '') <> ''
                     AND NOT EXISTS (SELECT 1 FROM staging.competitive_product_program x
                                     WHERE x.product_id = p.product_id AND lower(x.authority) = lower(trim(gp.customer_name)))
                     AND EXISTS (SELECT 1 FROM staging.fact_source f WHERE f.table_name = 'competitive_geo_product'
                                 AND f.row_id = gp.geo_product_id::text AND f.column_name = 'customer_name')    -- a sourced buyer only
                   ORDER BY p.product_id, lower(trim(gp.customer_name)), gp.since_date DESC NULLS LAST, gp.geo_product_id""")
    cols = [d[0] for d in cur.description]
    n = 0
    for g in (dict(zip(cols, r)) for r in cur.fetchall()):
        row = program_row(g)
        cur.execute("""INSERT INTO staging.competitive_product_program (program_id, product_id, program_title, authority, program_date, description)
                       VALUES (%(program_id)s, %(product_id)s, %(program_title)s, %(authority)s, %(program_date)s, %(description)s)""", row)   # old derived rows were deleted above
        n += cur.rowcount
        for col, src_cols in COPY.items():          # the sales row's own sources, re-pointed at the programme column they back
            cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, document_id)
                           SELECT DISTINCT ON (source_url) 'competitive_product_program', %s, %s, source_url, source_tier, publisher, quote, %s
                           FROM staging.fact_source WHERE table_name = 'competitive_geo_product' AND row_id = %s AND column_name = ANY(%s)
                           ORDER BY source_url""", (row["program_id"], col, TAG + str(g["geo_product_id"]), str(g["geo_product_id"]), list(src_cols)))
    return n


def fill_moment_images(cur) -> int:
    cur.execute("""UPDATE staging.competitive_competitor_moment m SET image_url = coalesce(
                     (SELECT s.thumbnail_url FROM staging.competitive_signal s WHERE s.signal_id = m.signal_id AND s.thumbnail_url IS NOT NULL),
                     (SELECT n.image_url FROM staging.competitive_news_article n WHERE n.article_url = m.source_url AND n.image_url IS NOT NULL LIMIT 1))
                   WHERE m.image_url IS NULL""")
    cur.execute("SELECT count(*) FROM staging.competitive_competitor_moment WHERE image_url IS NOT NULL")
    return cur.fetchone()[0]


def _selftest() -> None:
    g = {"geo_product_id": 7, "product_name": "Raven B (small UAS)", "customer_name": " Netherlands MoD ", "activity_type": "Export",
         "quantity": "72 systems", "reported_value": None, "since_date": None, "country_name": "Netherlands", "product_id": "p1"}
    r = program_row(g)
    assert r["program_title"] == "Netherlands MoD Raven B purchase" and r["authority"] == "Netherlands MoD"
    assert r["description"] == "Export to Netherlands. Quantity: 72 systems." and r["program_id"] == program_row(g)["program_id"]
    assert program_row({**g, "activity_type": "Local production"})["description"].startswith("Local production in Netherlands.")
    print("stored_fill self-check ok")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        _selftest()
        return 0
    import psycopg2
    from backend.routine import env
    conn = psycopg2.connect(env()["KSSL_STAGING_DSN"])
    with conn.cursor() as cur:
        print(f"programs from sales rows: {fill_programs(cur)} written")
        print(f"movement images: {fill_moment_images(cur)} movements now have one")
    conn.rollback() if a.dry_run else conn.commit()
    print("dry run: rolled back" if a.dry_run else "committed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
