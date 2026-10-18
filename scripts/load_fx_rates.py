"""Load official reference rates into staging.fx_rate: rupees for one unit of each currency.

    KSSL_STAGING_DSN=postgresql://... python -m scripts.load_fx_rates            # dry run: prints the rates
    KSSL_STAGING_DSN=postgresql://... python -m scripts.load_fx_rates --write    # upserts staging.fx_rate

Sources (no rate is typed anywhere):
  - ECB euro foreign exchange reference rates (daily XML): every quoted currency X -> INR per X = (INR per EUR) / (X per EUR);
    EUR itself = INR per EUR.
  - National Bank of Ukraine official rates (JSON) for UAH, which the ECB does not quote: INR per UAH = 1 / (UAH per INR).
Approve the fx_rate setup table on the review site to take the rates live.
"""
import argparse
import json
import os
import re
import sys
from datetime import date
from urllib.request import Request, urlopen

import psycopg2

ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
NBU_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json"
UA = {"User-Agent": "Mozilla/5.0 (KSSL fx loader)"}


def get(url):
    with urlopen(Request(url, headers=UA), timeout=30) as r:
        return r.read().decode("utf-8")


def ecb_rates(xml):
    """{code: inr_per_unit}, as_of from the ECB daily file."""
    day = re.search(r"time=['\"](\d{4}-\d{2}-\d{2})['\"]", xml).group(1)
    per_eur = {c: float(v) for c, v in re.findall(r"currency=['\"]([A-Z]{3})['\"]\s+rate=['\"]([\d.]+)['\"]", xml)}
    inr = per_eur.pop("INR")
    rates = {c: inr / v for c, v in per_eur.items()}
    rates["EUR"] = inr
    return rates, date.fromisoformat(day)


def nbu_uah(js):
    """INR per UAH, as_of, from the NBU list (rate = UAH for one unit of the listed currency)."""
    row = next(r for r in json.loads(js) if r.get("cc") == "INR")
    d, m, y = row["exchangedate"].split(".")
    return 1 / float(row["rate"]), date(int(y), int(m), int(d))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    ecb, ecb_day = ecb_rates(get(ECB_URL))
    rows = [(c, r, ecb_day, "ECB euro reference rates (cross via INR)", ECB_URL) for c, r in ecb.items()]
    uah, nbu_day = nbu_uah(get(NBU_URL))
    rows.append(("UAH", uah, nbu_day, "National Bank of Ukraine official rate (UAH per INR, inverted)", NBU_URL))
    for c, r, d, *_ in sorted(rows):
        print(f"{c}  1 = INR {r:,.4f}   ({d})")
    if not args.write:
        return
    dsn = os.environ.get("KSSL_STAGING_DSN") or sys.exit("KSSL_STAGING_DSN is not set")
    con = psycopg2.connect(dsn)
    with con, con.cursor() as cur:
        cur.executemany("""INSERT INTO staging.fx_rate (currency_code, inr_per_unit, as_of_date, source_label, source_url)
                           VALUES (%s, %s, %s, %s, %s)
                           ON CONFLICT (currency_code) DO UPDATE SET inr_per_unit = EXCLUDED.inr_per_unit,
                             as_of_date = EXCLUDED.as_of_date, source_label = EXCLUDED.source_label, source_url = EXCLUDED.source_url""",
                        [(c, round(r, 6), d, lbl, url) for c, r, d, lbl, url in rows])
    print(f"written: {len(rows)} rates")


if __name__ == "__main__":
    main()
