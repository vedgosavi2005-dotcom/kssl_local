"""Geo layer 2 by code: OVERLAP and WHITE-SPACE rows of staging.competitive_geo_analysis (no model).

    python -m prompts.geo_analysis --code [--dry-run]      rebuild every overlap / whitespace row from the stored layer-1 rows
    python -m prompts.geo_analysis --selftest              pure checks, fictional values

The inputs are stored rows only:
  * a rival's geo product (competitive_geo_product) in a country, and the KSSL products of the same class
    (competitive_geo_product_match, built by derive.geo_match_code from the like-for-like gate);
  * what KSSL has in that country: its own geo presence rows and the countries of its partners.
overlap     = the rival sells the class of product in a country where KSSL is present, offered or has a partner;
whitespace  = the rival sells it in a country where KSSL has nothing on record.
(The third kind, anomaly, needs a source that states the buyer's reason, so it is the prompt geo_analysis.)

Every row gets a fact_source row (tier `stored`) naming the rows it rests on. Rows of kind overlap / whitespace are replaced as a whole on
each run; the model never writes those kinds. Local kssl_staging only.
"""

from __future__ import annotations

import hashlib
import os
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("KSSL_STAGING_DSN") or os.environ.get("KSSL_DSN") or "host=127.0.0.1 port=55432 dbname=kssl_staging user=kssl password=kssl"


def hash63(*parts) -> int:
    return int.from_bytes(hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()[:8], "big") & 0x7FFFFFFFFFFFFFFF


def cut(s, n: int):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 3].rstrip() + "..."


def sentence(kind: str, rival: str, product: str, activity: str, country: str, kssl_product: str, kssl_here: str | None,
             customer: str | None = None, since=None, kssl_other: str | None = None, *, client: str) -> str:
    """The templated finding (<= 300 characters, facts only). overlap: KSSL has the same class of product there (kssl_here lists it);
    whitespace: it has not (kssl_other says what else KSSL does there, if anything)."""
    act = {"Export": "sells", "Sales and service": "sells and services", "Local production": "makes", "Licensed production": "makes under licence",
           "Sourcing": "buys from"}.get(activity, "is active with")
    who = f"{rival} {act} {product} in {country}"
    if customer:
        who += f" (customer: {customer})"
    if since:
        who += f", since {since.year if hasattr(since, 'year') else since}"
    if kind == "overlap":
        return cut(f"{who}. {client} has the same class of product there: {kssl_here}.", 300)
    tail = (f"{client} has a same-class product ({kssl_product}) but is there only with other products ({kssl_other})." if kssl_other
            else f"{client} has a same-class product ({kssl_product}) but no presence, offer or partner on record in {country}.")
    return cut(f"{who}. {tail}", 300)


def rows(cur) -> list:
    cur.execute("""
        SELECT l.location_id, l.country_name, c.competitor_id, c.display_name AS competitor, c.origin_country, g.geo_product_id, g.product_name, g.activity_type,
               g.customer_name, g.since_date, g.product_range, m.match_id, m.kssl_product_id, m.kssl_counter_label,
               (SELECT string_agg(DISTINCT kg.product_name || ' (' || coalesce(kg.activity_type, '?') || ', ' || coalesce(k.presence_status, '?') || ')', '; ')
                  FROM staging.competitive_geo_company_presence k JOIN staging.competitive_geo_product kg ON kg.presence_id = k.presence_id
                 WHERE k.company_role = 'client' AND k.location_id = l.location_id AND kg.product_range IS NOT DISTINCT FROM g.product_range) AS kssl_same_class,
               (SELECT string_agg(DISTINCT coalesce(k.activity_type, '?') || ' (' || coalesce(k.presence_status, '?') || ')', ', ')
                  FROM staging.competitive_geo_company_presence k WHERE k.company_role = 'client' AND k.location_id = l.location_id) AS kssl_presence,
               EXISTS (SELECT 1 FROM staging.client_partner kp WHERE lower(kp.country) = lower(l.country_name)) AS kssl_partner_here
        FROM staging.competitive_geo_product_match m
        JOIN staging.competitive_geo_product g ON g.geo_product_id = m.geo_product_id
        JOIN staging.competitive_geo_company_presence p ON p.presence_id = g.presence_id AND p.company_role = 'competitor'
        JOIN staging.competitive_geo_location l ON l.location_id = p.location_id
        JOIN staging.competitive_competitor c ON c.competitor_id = p.competitor_id
        WHERE g.activity_type IN ('Export', 'Sales and service', 'Local production', 'Licensed production')
        ORDER BY l.country_name, c.display_name, g.product_name, m.kssl_counter_label""")
    return [dict(r) for r in cur.fetchall()]


def build(cur, dry_run: bool = False) -> dict:
    """Replace every overlap / whitespace row; returns counts."""
    from prompts.derive import client_name
    client = client_name(cur)
    data = rows(cur)
    seen, out, n = set(), {"overlap": 0, "whitespace": 0}, 0
    if not dry_run:
        cur.execute("""DELETE FROM staging.fact_source WHERE table_name = 'competitive_geo_analysis'
                         AND row_id IN (SELECT analysis_id::text FROM staging.competitive_geo_analysis WHERE kind IN ('overlap', 'whitespace'))""")
        cur.execute("DELETE FROM staging.competitive_geo_analysis WHERE kind IN ('overlap', 'whitespace')")
    for r in data:
        # one row per rival product x KSSL product x country; the KSSL products of one class collapse to the first listed
        key = (r["location_id"], r["geo_product_id"])
        if key in seen:
            continue
        seen.add(key)
        same = r["kssl_same_class"]
        other = r["kssl_presence"] or (f"a {client} partner is based there" if r["kssl_partner_here"] else None)
        kind = "overlap" if same else "whitespace"
        # 2026-10-18: a rival making its product in its own home country is its home base, not an open market: no white-space row
        if kind == "whitespace" and r["activity_type"] == "Local production" and (r["origin_country"] or "").strip().lower() == (r["country_name"] or "").strip().lower():
            continue
        others = sorted({x["kssl_counter_label"] for x in data if (x["location_id"], x["geo_product_id"]) == key and x["kssl_counter_label"] != r["kssl_counter_label"]})
        kp = r["kssl_counter_label"] + (f" (and {len(others)} more of the same class)" if others else "")
        text = sentence(kind, r["competitor"], r["product_name"], r["activity_type"], r["country_name"], kp, same, r["customer_name"], r["since_date"], other,
                        client=client)
        here = same or other
        aid = hash63("geo_analysis", kind, r["location_id"], r["geo_product_id"], r["kssl_product_id"])
        out[kind] += 1
        n += 1
        if dry_run:
            continue
        cur.execute("""INSERT INTO staging.competitive_geo_analysis
                       (analysis_id, location_id, competitor_id, geo_product_id, kssl_product_id, kind, finding, reason_state, display_order)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,NULL,%s)""",
                    (aid, r["location_id"], r["competitor_id"], r["geo_product_id"], r["kssl_product_id"], kind, text, n))
        cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, quote)
                       VALUES ('competitive_geo_analysis', %s, 'finding', 'stored row', 'stored', %s)""",
                    (str(aid), cut(f"competitive_geo_product {r['geo_product_id']} ({r['product_name']}, {r['activity_type']}); "
                                   f"competitive_geo_product_match {r['match_id']} (like-for-like gate); {client} in {r['country_name']}: {here or 'nothing on record'}", 300)))
    return out


def _selftest() -> None:
    import datetime
    assert sentence("whitespace", "Nordvik Defence", "NV-155", "Export", "Veland", "MArG 155", None, "Veland Ministry of Defence", datetime.date(2026, 1, 1),
                    client="KSSL").startswith(
        "Nordvik Defence sells NV-155 in Veland (customer: Veland Ministry of Defence), since 2026. KSSL has a same-class product (MArG 155) but no presence")
    s = sentence("overlap", "Nordvik Defence", "NV-155", "Local production", "Veland", "MArG 155", "MArG 155 (Export, Active)", client="Acme")
    assert "Acme has the same class" in s
    assert "makes NV-155 in Veland" in s and s.endswith("(Export, Active).") and len(s) <= 300
    assert "only with other products (barrels (Export, Active))" in sentence("whitespace", "N", "NV", "Export", "Veland", "M", None, None, None, "barrels (Export, Active)", client="Acme")
    assert len(cut("x" * 400, 300)) == 300 and hash63("a", 1) == hash63("a", 1) != hash63("a", 2)
    print("geo_analysis self-check ok")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        _selftest()
        return 0
    if "--code" not in argv:
        print(__doc__)
        return 0
    conn = psycopg2.connect(DSN, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        with conn.cursor() as cur:
            res = build(cur, dry_run="--dry-run" in argv)
        if "--dry-run" in argv:
            conn.rollback()
        else:
            conn.commit()
        print("geo_analysis (code):", res, "(dry run)" if "--dry-run" in argv else "")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
