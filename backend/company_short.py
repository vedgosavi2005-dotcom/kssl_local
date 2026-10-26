"""Short company details (Competitor Profile) from the workbook sentences, with the local LLM; checked by code.

    python -m backend.company_short --selftest
    python -m backend.company_short [--dry-run] [--model gemma4-26b-gpu]
    python -m backend.company_short --labels [--dry-run]     only the two labels below, no model

For each competitor the local model (Ollama, this PC) reads starting_year_text / employee_count_text / revenue_text / financial_year /
industry_sector and answers JSON: a year, a headcount, the revenue figure as written (number, scale word, currency), a sector of at
most 5 words. Code then:
  - keeps a value only if its digits are in the sentence it came from (no figure is invented); else NULL, the sentence still shows;
  - converts the revenue to USD with staging.fx_rate (INR per unit, official) and sets revenue_tier;
  - writes starting_year_short / employee_count_short / revenue_short / industry_short / revenue_usd / revenue_tier.
No cloud model, no cost. Re-runnable (overwrites the short columns only).
Owner 2026-10-25: the size names its unit ("7,659 employees", not "7,659"), and the sector is what the company MAKES -- its largest
product categories in competitive_product -- not the workbook's wording ("Global defence technology"); a company with no products
keeps the model's sector.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request

OLLAMA = "http://127.0.0.1:11434/api/chat"
SCALE = {"": 1, "thousand": 1e3, "k": 1e3, "million": 1e6, "mn": 1e6, "m": 1e6, "billion": 1e9, "bn": 1e9, "b": 1e9,
         "trillion": 1e12, "tn": 1e12, "crore": 1e7, "cr": 1e7, "lakh": 1e5}
CUR = {"$": "USD", "us$": "USD", "usd": "USD", "€": "EUR", "eur": "EUR", "£": "GBP", "gbp": "GBP", "₹": "INR", "inr": "INR", "rs": "INR",
       "krw": "KRW", "₩": "KRW", "nok": "NOK", "sek": "SEK", "try": "TRY", "pln": "PLN", "ils": "ILS", "nis": "ILS", "shekel": "ILS", "tl": "TRY", "jpy": "JPY", "cny": "CNY",
       "zar": "ZAR", "aud": "AUD", "cad": "CAD", "chf": "CHF", "rub": "RUB", "aed": "AED", "sgd": "SGD", "czk": "CZK"}
TIERS = [(1e9, "Under $1B"), (10e9, "$1-10B"), (50e9, "$10-50B"), (float("inf"), "Over $50B")]
SYMBOL = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹"}

SYSTEM = """You turn company-profile sentences into short values. Use ONLY what the text says; never estimate or convert.
Return JSON with these keys:
 "year": the founding or starting year as 4 digits (the earliest year the company itself started; null if none),
 "employees": the headcount as written, shortest form, e.g. "~5,383" or "33,217" (null if none is stated),
 "revenue_number": the revenue figure exactly as written, digits only with its decimal point, e.g. "9.935" (null if not disclosed),
 "revenue_scale": the scale word written with it: thousand | million | billion | trillion | crore | lakh | "" ,
 "revenue_currency": the currency as written (EUR, USD, INR, KRW, ...), or null,
 "revenue_year": the financial year as written, e.g. "FY2025" (null if none),
 "sector": the main business in at most 5 words, e.g. "Small arms, missiles, UAVs"."""


def ask(model: str, text: str) -> dict:
    body = {"model": model, "stream": False, "format": "json", "think": False, "options": {"temperature": 0, "num_predict": 300},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}]}
    req = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(json.load(r)["message"]["content"])


def digits(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def checked(value, source) -> str | None:
    """value if every digit run in it occurs in the source text (thousand separators ignored), else None."""
    if not value:
        return None
    src = re.sub(r"(?<=\d)[,\s](?=\d{3}\b)", "", str(source or ""))
    runs = re.findall(r"\d+(?:\.\d+)?", re.sub(r"(?<=\d),(?=\d{3}\b)", "", str(value)))
    return str(value).strip() if all(r in src for r in runs) else None


def revenue_usd(number, scale, currency, inr_per: dict) -> float | None:
    try:
        n = float(str(number).replace(",", ""))
    except (TypeError, ValueError):
        return None
    cur = CUR.get(str(currency or "").strip().lower(), str(currency or "").strip().upper())
    sc = SCALE.get(str(scale or "").strip().lower())
    if sc is None or cur not in inr_per or "USD" not in inr_per:
        return None
    return n * sc * inr_per[cur] / inr_per["USD"]


def tier(usd) -> str | None:
    return None if usd is None else next(t for lim, t in TIERS if usd < lim)


def short_money(number, scale, currency, year) -> str:
    cur = CUR.get(str(currency or "").strip().lower(), str(currency or "").strip().upper())
    sc = {"billion": "B", "bn": "B", "million": "M", "mn": "M", "trillion": "T", "crore": " Cr", "lakh": " L", "thousand": "K"}.get(str(scale or "").lower(), "")
    if sc in ("B", "M", "T"):                     # display only: "1.976845" -> "1.98"; the exact figure stays in revenue_text
        try:
            number = f"{float(str(number).replace(',', '')):,.2f}".rstrip("0").rstrip(".")
        except ValueError:
            pass
    sym = SYMBOL.get(cur)
    out = f"{sym}{number}{sc}" if sym else f"{number}{sc} {cur}"
    return f"{out} ({year})" if year else out


def employees(emp) -> str | None:
    """"7,659" -> "7,659 employees"; a value that already names its unit is kept."""
    e = str(emp or "").strip()
    return None if not e else e if re.search(r"employ|staff|people|workers|personnel", e, re.I) else f"{e} employees"


def portfolio_sector(counts: list[tuple[str, int]], width: int = 80) -> str | None:
    """the largest product categories (count order, 'Other' left out), as many as fit in `width`: "Artillery; Ammunition"."""
    out = []
    for cat, _ in sorted(counts, key=lambda c: -c[1]):
        if not cat or cat.strip().lower() == "other" or len(out) == 3 or len("; ".join(out + [cat])) > width:
            continue
        out.append(cat)
    return "; ".join(out) or None


def labels(cur, dry: bool = False) -> None:
    """employee_count_short with its unit, industry_short from the product portfolio (no model)."""
    cur.execute("""SELECT c.competitor_id, c.display_name, c.employee_count_short, c.industry_short,
                          (SELECT json_agg(json_build_array(category, n)) FROM (SELECT category, count(*) AS n FROM staging.competitive_product p
                            WHERE p.competitor_id = c.competitor_id GROUP BY category) x) AS cats
                   FROM staging.competitive_competitor c ORDER BY c.display_name""")
    for r in cur.fetchall():
        emp, sec = employees(r["employee_count_short"]), portfolio_sector([tuple(x) for x in r["cats"] or []]) or r["industry_short"]
        print(f"  {r['display_name'][:30]:30} {emp} | {sec}")
        if not dry:
            cur.execute("UPDATE staging.competitive_competitor SET employee_count_short = %s, industry_short = %s WHERE competitor_id = %s",
                        (emp, sec, r["competitor_id"]))


def _selftest() -> None:
    assert employees("~5,383") == "~5,383 employees" and employees("Over 21,000 staff") == "Over 21,000 staff" and employees("More than 4,000") == "More than 4,000 employees" and employees("") is None
    assert portfolio_sector([("Other", 9), ("Artillery", 3), ("Ammunition", 5)]) == "Ammunition; Artillery"
    assert portfolio_sector([("A" * 50, 3), ("B" * 40, 2), ("C", 1)]) == "A" * 50 + "; C"
    assert portfolio_sector([]) is None
    assert checked("~5,383", "~5,383 employees as of 2026") == "~5,383" and checked("5,400", "~5,383 employees") is None
    assert checked("9.935", "€9.935 billion consolidated sales") == "9.935" and checked("2015", "2015-2017 build-out") == "2015"
    rates = {"USD": 95.0, "EUR": 110.0, "INR": 1.0}
    assert abs(revenue_usd("9.935", "billion", "€", rates) - 9.935e9 * 110 / 95) < 1 and tier(11.5e9) == "$10-50B" and tier(5e8) == "Under $1B"
    assert revenue_usd("50,512", "million", "INR", rates) and revenue_usd("x", "billion", "EUR", rates) is None
    assert short_money("9.935", "billion", "EUR", "FY2025") == "€9.94B (FY2025)" and short_money("5,050", "billion", "KRW", None) == "5,050B KRW"
    print("company_short self-check ok")


def run(model: str, dry: bool) -> None:
    from prompts.run import connect
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT currency_code, inr_per_unit FROM staging.fx_rate")
    inr_per = {r["currency_code"]: float(r["inr_per_unit"]) for r in cur.fetchall()}
    inr_per["INR"] = 1.0
    cur.execute("""SELECT competitor_id, display_name, starting_year_text, starting_year, employee_count_text, revenue_text, financial_year,
                          industry_sector, annual_revenue, revenue_currency FROM staging.competitive_competitor ORDER BY display_name""")
    rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        text = "\n".join(f"{k}: {r[k]}" for k in ("starting_year_text", "employee_count_text", "revenue_text", "financial_year", "industry_sector") if r.get(k))
        if not text:
            continue
        try:
            a = ask(model, text)
        except Exception as e:  # noqa: BLE001
            print(f"  {r['display_name']}: model error {e}")
            continue
        year = checked(a.get("year"), r.get("starting_year_text") or r.get("starting_year"))
        emp = checked(a.get("employees"), r.get("employee_count_text"))
        rev_n = checked(a.get("revenue_number"), r.get("revenue_text"))
        usd = revenue_usd(rev_n, a.get("revenue_scale"), a.get("revenue_currency"), inr_per) if rev_n else None
        if usd is None and r.get("annual_revenue") and r.get("revenue_currency") in inr_per:      # the loader's own clean figure
            usd = float(r["annual_revenue"]) * inr_per[r["revenue_currency"]] / inr_per["USD"]
        rev_s = short_money(rev_n, a.get("revenue_scale"), a.get("revenue_currency"), a.get("revenue_year")) if rev_n else (
            "Not disclosed" if re.search(r"not (publicly |separately )?disclosed|not available", str(r.get("revenue_text") or ""), re.I) else None)
        sector = (str(a.get("sector") or "").strip() or None)
        sector = sector if sector and len(sector.split()) <= 6 else None
        print(f"  {r['display_name'][:30]:30} year={year} emp={emp} rev={rev_s} usd={round(usd / 1e9, 2) if usd else None}B tier={tier(usd)} | {sector}")
        if not dry:
            cur.execute("""UPDATE staging.competitive_competitor SET starting_year_short = %s, employee_count_short = %s, revenue_short = %s,
                                  industry_short = %s, revenue_usd = %s, revenue_tier = %s WHERE competitor_id = %s""",
                        (year, emp, (rev_s or "")[:60] or None, (sector or "")[:80] or None, usd, tier(usd), r["competitor_id"]))
            conn.commit()
    labels(cur, dry)
    conn.commit()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--model", default="gemma4-26b-gpu")
    ap.add_argument("--labels", action="store_true", help="only the size unit and the portfolio sector, no model")
    a = ap.parse_args(argv)
    if a.selftest:
        _selftest()
        return 0
    if a.labels:
        from prompts.run import connect
        conn = connect()
        labels(conn.cursor(), a.dry_run)
        conn.commit() if not a.dry_run else conn.rollback()
        return 0
    run(a.model, a.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
