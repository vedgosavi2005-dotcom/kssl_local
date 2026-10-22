"""Navigation payloads for THIS product version (KSSL_Deploy v2; every id is text): each payload key a page reads on mount
(adapter/product.json "pages"[].payload), resolved to the exact value the page matches on.

resolve() gets only keys the page takes, plus `fetch(sql, params)` (read-only lookups over
the analytics views) and the manifest. Raise ValueError with the valid choices when a
value matches nothing; the service hands that message back to the model."""


def _one(fetch, rows, what, value, options_sql=None):
    if rows:
        return rows[0]
    hint = ""
    if options_sql:
        opts = [next(iter(r.values())) for r in fetch(options_sql)]
        hint = f" Valid values: {', '.join(map(str, opts[:40]))}."
    raise ValueError(f"No {what} matches {value!r}.{hint}")


def resolve(pillar: str, view: str, payload: dict, fetch, manifest: dict) -> dict:
    out = {}
    sections = set(manifest["routes"].get("report_sections") or [])
    lanes = {p["view"]: p["feed_lane"] for p in manifest["pages"] if p.get("feed_lane")}

    if "cid" in payload:
        v = str(payload["cid"]).strip()
        row = _one(fetch, fetch(
            "SELECT comp_id FROM company WHERE comp_id = %s "
            "UNION SELECT comp_id FROM company_alias WHERE alias_lower = lower(%s) LIMIT 1", (v, v)),
            "company", v, "SELECT comp_id FROM company ORDER BY sort_order")
        out["cid"] = row["comp_id"]

    if "productName" in payload:
        v = str(payload["productName"]).strip()
        rows = fetch("SELECT model FROM product WHERE (%s IS NULL OR comp_id = %s) AND model ILIKE %s "
                     "ORDER BY length(model) LIMIT 1", (out.get("cid"), out.get("cid"), f"%{v}%"))
        if rows:
            out["productName"] = rows[0]["model"]

    if "tenderTitle" in payload:
        v = str(payload["tenderTitle"]).strip()
        rows = fetch("SELECT title FROM tender WHERE tender_id = %s", (v,)) if v.isdigit() else []   # ids are text here
        rows = rows or fetch("SELECT title FROM tender WHERE title = %s", (v,)) or fetch(
            "SELECT title FROM tender WHERE title ILIKE %s ORDER BY length(title) LIMIT 1", (f"%{v}%",))
        out["tenderTitle"] = _one(fetch, rows, "tender", v)["title"]

    if "cat" in payload:   # Tenders page filter (this version): a tender segment
        v = str(payload["cat"]).strip()
        rows = fetch("SELECT segment FROM tender WHERE segment ILIKE %s GROUP BY 1 ORDER BY count(*) DESC LIMIT 1", (f"%{v}%",))
        out["cat"] = _one(fetch, rows, "tender segment", v, "SELECT DISTINCT segment FROM tender ORDER BY 1")["segment"]

    if "country" in payload:
        v = str(payload["country"]).strip()
        v = {"ksa": "Saudi Arabia", "uae": "United Arab Emirates", "saudi": "Saudi Arabia", "emirates": "United Arab Emirates"}.get(v.lower(), v)
        rows = fetch("SELECT country FROM tender WHERE country ILIKE %s GROUP BY 1 LIMIT 1", (f"%{v}%",))
        out["country"] = _one(fetch, rows, "tender country", v, "SELECT DISTINCT country FROM tender ORDER BY 1")["country"]

    if "matchupId" in payload:
        v = str(payload["matchupId"]).strip()
        rows = fetch("SELECT matchup_id FROM matchup WHERE matchup_id = %s", (v,))   # ids are text here
        out["matchupId"] = str(_one(fetch, rows, "matchup", v)["matchup_id"])

    if "cardId" in payload:
        v = str(payload["cardId"]).strip()
        lane = lanes.get(view)
        rows = fetch("SELECT signal_id FROM signal WHERE signal_id = %s AND lane = %s", (v, lane))
        out["cardId"] = _one(fetch, rows, f"{lane} signal", v)["signal_id"]

    if "section" in payload:
        v = str(payload["section"]).strip().lower()
        if v not in sections:
            raise ValueError(f"section must be one of {', '.join(sorted(sections))}.")
        out["section"] = v

    if "catId" in payload:
        v = str(payload["catId"]).strip()
        rows = fetch("SELECT area_id FROM tech_area WHERE area_id = %s OR area ILIKE %s LIMIT 1", (v, f"%{v}%"))
        out["catId"] = _one(fetch, rows, "technology area", v, "SELECT area_id FROM tech_area")["area_id"]
        t = str(payload.get("title") or "").strip()
        rows = fetch("SELECT title FROM innovation WHERE area_id = %s AND title ILIKE %s LIMIT 1",
                     (out["catId"], f"%{t}%")) if t else []
        # the Innovations page switches area only when it is also given an item to open
        rows = rows or fetch("SELECT title FROM innovation WHERE area_id = %s ORDER BY title LIMIT 1", (out["catId"],))
        if rows:
            out["title"] = rows[0]["title"]
    return out
