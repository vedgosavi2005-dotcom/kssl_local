"""Each competitor's threat read, from its own signals (owner 2026-10-24: "from its signals, by code").

    python -m backend.threat_level [--dry-run]      (code only, no model; a routine step after the signal steps)
    python -m backend.threat_level --selftest

competitive_competitor.threat_level (the 'Threat read' on Profile / Products / Partnerships) had no writer: empty for all 50.
Rule: a threat signal dated in the last WINDOW_DAYS -> 'threat'; only watch signals -> 'watch'; none -> NULL (no badge, the
competitor did nothing that counts lately). The signal's date is the card's (published, else event). Each change is noted with
its counts. Staging only; it reaches the live site through Approve like every other row.
"""
from __future__ import annotations

import argparse

from backend import ops_log

WINDOW_DAYS = 90


def level(threats: int, watches: int) -> str | None:
    return "threat" if threats else "watch" if watches else None


SQL = f"""SELECT c.competitor_id::text AS cid, c.display_name, c.threat_level AS old,
                 count(*) FILTER (WHERE s.classification = 'threat') AS threats,
                 count(*) FILTER (WHERE s.classification = 'watch') AS watches
          FROM staging.competitive_competitor c
          LEFT JOIN staging.competitive_signal s ON s.company_id = c.competitor_id
               AND coalesce(s.published_date, s.event_date) >= current_date - {WINDOW_DAYS}
          GROUP BY 1, 2, 3"""


def run(dry_run: bool = False) -> dict:
    from prompts.run import connect
    conn = connect()
    cur = conn.cursor()
    cur.execute(SQL)
    rows = cur.fetchall()
    changes = [(r, level(r["threats"], r["watches"])) for r in rows]
    changes = [(r, new) for r, new in changes if new != r["old"]]
    for r, new in changes:
        print(f"{r['display_name'][:40]:40} {str(r['old']):8} -> {str(new):8} ({r['threats']} threats, {r['watches']} watches in {WINDOW_DAYS} days)")
    if not dry_run and changes:
        cur.executemany("UPDATE staging.competitive_competitor SET threat_level = %s WHERE competitor_id = %s::uuid",
                        [(new, r["cid"]) for r, new in changes])
        conn.commit()
        for r, new in changes:
            ops_log.note("threat_level", str(new or "none"), f"Threat read {r['old'] or 'empty'} -> {new or 'empty'}: {r['threats']} threat and "
                         f"{r['watches']} watch signals in the last {WINDOW_DAYS} days.", subject=r["display_name"],
                         tbl="staging.competitive_competitor", rec_id=r["cid"], detail={"threats": r["threats"], "watches": r["watches"]})
    conn.close()
    out = {"competitors": len(rows), "changed": len(changes),
           "threat": sum(level(r["threats"], r["watches"]) == "threat" for r in rows),
           "watch": sum(level(r["threats"], r["watches"]) == "watch" for r in rows)}
    print(out)
    return out


def _selftest() -> None:
    assert level(1, 9) == "threat" and level(0, 2) == "watch" and level(0, 0) is None
    print("threat_level self-check ok")


@ops_log.logged("backend.threat_level")
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest()
    else:
        run(a.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
