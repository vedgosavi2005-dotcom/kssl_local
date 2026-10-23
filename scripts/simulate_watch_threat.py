"""SIMULATION: a watch signal that later turns into a threat (owner 2026-10-24: "First it goes to watch. Then, when some new article
comes about it, its score can be higher... it goes to threat. I should be able to see that or simulate it.")

Runs the REAL pipeline on dummy articles, in a SANDBOX copy of the local databases (kssl_test_sim_staging / kssl_test_sim_serving;
the real kssl_staging / kssl_serving are only read, once, by `setup`). No model call: each article comes with the reply a model
would give (the same JSON envelope the signal prompt returns), and that reply goes through prompts/run.run_one(reply=...) --
the same validation, loader, derive rules (signal_label, risk score, label basis) and story linking as a real run.

    python -m scripts.simulate_watch_threat setup        build the sandbox (copies of local staging + serving, no raw layer / pictures)
    python -m scripts.simulate_watch_threat article 1    "shortlisted for trials"  -> probability 3: WATCH
    python -m scripts.simulate_watch_threat article 2    "contract signed"         -> probability 5, impact 5: THREAT, same story
    python -m scripts.simulate_watch_threat show         the two signals and the story timeline (label changes included)
    python -m scripts.simulate_watch_threat changes      dummy facts from an article -> "Changes from news" proposals (non-changes dropped)
    python -m scripts.simulate_watch_threat serve        how to open it in the review site (sandbox API :8611, UI :5181)
    python -m scripts.simulate_watch_threat drop         delete the sandbox
Reading the review site on the sandbox: the story is ONE card (its latest signal): Watch after article 1, Threat after article 2,
and its timeline says "Label changed to Threat".
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid

import psycopg2
import psycopg2.extras

SB = {"staging": "kssl_test_sim_staging", "serving": "kssl_test_sim_serving"}
HANWHA = "eb5fad0b-c2fb-5197-849a-e71b9e515a5c"
PRODUCT = "K9 / K9A1 Thunder"
NS = uuid.UUID("5a1a0000-0000-4000-8000-000000000001")      # dummy ids are uuid5 of this, so a re-run replaces, never duplicates

ARTICLES = {
    1: dict(date="2026-09-10", category="Product launch & testing", move="Trial", probability=3, impact=4, tte="1_3y",
            headline="[SIMULATION] Indian Army shortlists Hanwha K9 Thunder for tracked howitzer trials",
            body=("[SIMULATION ARTICLE - NOT REAL NEWS] The Indian Army has shortlisted Hanwha Aerospace's K9 Thunder 155 mm tracked "
                  "self-propelled howitzer for field trials under a new requirement for tracked guns. Trials in the Thar desert are "
                  "planned for early 2027. No contract has been signed and the Army has not said how many guns it may buy. "
                  "Hanwha Aerospace said it would offer local production with an Indian partner if selected. Officials said a "
                  "decision would follow the trials and a cost negotiation, which usually take one to two years. ") * 3,
            what="The Indian Army shortlisted Hanwha Aerospace's K9 Thunder for tracked howitzer trials planned for early 2027. No contract is signed.",
            why="A shortlisting in India for a 155 mm tracked gun, the same line as KSSL's tracked artillery. It is not an order yet."),
    2: dict(date="2026-10-20", category="Contract & order", move="Contract", probability=5, impact=5, tte="lt_1y",
            headline="[SIMULATION] India signs contract with Hanwha for 100 K9 Thunder howitzers",
            body=("[SIMULATION ARTICLE - NOT REAL NEWS] India's Ministry of Defence signed a contract with Hanwha Aerospace for 100 "
                  "K9 Thunder 155 mm tracked self-propelled howitzers after the Army's trials. Deliveries start in 2027 and the guns "
                  "will be built in India with a local partner. The contract follows the Army's shortlisting of the K9 Thunder for "
                  "tracked howitzer trials. The ministry said the guns fill the Army's tracked artillery requirement. ") * 3,
            what="India's Ministry of Defence signed a contract with Hanwha Aerospace for 100 K9 Thunder tracked howitzers; deliveries start in 2027.",
            why="A signed contract in India for 100 tracked 155 mm guns: the Army requirement KSSL's tracked artillery also targets is now filled."),
}


def dsn(db: str) -> str:
    base = (os.getenv("KSSL_STAGING_DSN") or "").strip()
    if not base:
        sys.exit("set KSSL_STAGING_DSN (set -a; . ./.env; set +a)")
    return re.sub(r"dbname=\S+", f"dbname={db}", base)


def guard(conn_dsn: str) -> None:
    db = re.search(r"dbname=(\S+)", conn_dsn).group(1)
    if not db.startswith("kssl_test_sim_"):
        sys.exit(f"refusing: {db} is not a simulation sandbox")


def docker(*cmd, stdin=None) -> None:
    subprocess.run(["docker", "exec", "-i", "kssl-pg", *cmd], check=True, stdin=stdin)


def setup() -> None:
    """copy local kssl_staging / kssl_serving into the sandbox; the raw layer, prompt log, row log and pictures are left empty"""
    skip = ["staging.source_document", "staging.tender_raw", "staging.news_candidate", "staging.prompt_run", "ops.record_event", "media.*"]
    for src, dst in (("kssl_staging", SB["staging"]), ("kssl_serving", SB["serving"])):
        docker("psql", "-q", "-U", "kssl", "-d", "postgres", "-c", f"DROP DATABASE IF EXISTS {dst}", "-c", f"CREATE DATABASE {dst}")
        ex = " ".join(f"--exclude-table-data='{t}'" for t in skip) if src == "kssl_staging" else "--exclude-table-data='activity.*'"
        docker("bash", "-c", f"pg_dump -U kssl -d {src} -Fc --lock-wait-timeout=20s {ex} | pg_restore -U kssl -d {dst} --no-owner")
        print(f"sandbox {dst} ready (copy of {src})")


def article(n: int) -> None:
    from prompts import loader, render, run as runner
    from prompts.claude_call import ModelResult
    a = ARTICLES[n]
    url = f"https://simulation.kssl.invalid/article-{n}"
    art_id = str(uuid.uuid5(NS, url))
    conn = psycopg2.connect(dsn(SB["staging"]), cursor_factory=psycopg2.extras.RealDictCursor)
    guard(conn.dsn)
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO staging.source_document (doc_id, url, source_kind, source_name, title, published_at, language, body_text,
                                                           triage, competitor_ids, status, processed_by, fetched_at)
                       VALUES (%s, %s, 'simulation', 'SIMULATION', %s, %s, 'en', %s, '{"route": ["signal"]}', ARRAY[%s]::uuid[], 'new', '{}', now())
                       ON CONFLICT (url) DO UPDATE SET body_text = EXCLUDED.body_text, title = EXCLUDED.title""",
                    (str(uuid.uuid5(NS, "doc" + url)), url, a["headline"], a["date"], a["body"], HANWHA))
        cur.execute("""INSERT INTO staging.competitive_news_article (article_id, article_url, category, competitor_id, headline, published_date, publisher, description)
                       SELECT %s, %s, %s, %s, %s, %s, 'SIMULATION', %s
                       WHERE NOT EXISTS (SELECT 1 FROM staging.competitive_news_article WHERE article_id = %s)""",   # no primary key on this table
                    (art_id, url, a["category"], HANWHA, a["headline"], a["date"], a["what"], art_id))
    conn.commit()
    spec = render.load_prompt("signal")
    with conn.cursor() as cur:
        subs = [s for s in render.subjects(cur, spec) if s["_key"] == art_id]
        client = render.client_row(cur)
        blocks = render.context_blocks(cur, client)
    conn.rollback()
    if not subs:
        sys.exit("the dummy article is not a signal subject (check the subject query)")
    sents = [x.strip() + "." for x in a["body"].split("] ", 1)[1].split(". ") if x.strip()][:5]   # the article's own sentences
    quote = sents[0]
    reply = {"prompt_id": "signal", "subject": a["headline"], "skip_reason": None, "records": [{
        "table": "competitive_signal",
        "values": {"ref_competitor": "Hanwha Aerospace", "title": a["headline"].replace("[SIMULATION] ", "Simulation: "), "summary": a["what"],
                   "event_date": a["date"], "ref_category": "Artillery", "direction": "adverse", "probability": a["probability"],
                   "time_to_effect": a["tte"], "impact_orders_revenue": a["impact"], "impact_market_standing": 3, "impact_supply_chain": 1,
                   "impact_technology_gap": 2, "impact_partnerships": 1, "impact_policy_export": 1, "impact_funding": 1,
                   "subtype_match": "same", "in_client_market": "yes", "story_ref": "new", "story_kind": "programme",
                   "story_country": "India", "story_product": PRODUCT,
                   "_reason": {"summary": "Simulation article.", "direction": "adverse: a rival gains in KSSL's market.",
                               "probability": f"{a['probability']}: {sents[0]}", "time_to_effect": f"{a['tte']}: {sents[1]}",
                               "impact_orders_revenue": f"{a['impact']}: a 155 mm tracked howitzer order in India.",
                               "subtype_match": "same: 155 mm tracked self-propelled howitzer.", "in_client_market": "yes: India."},
                   "_sources": {"title": [{"url": url, "quote": quote}]}},
        "children": {
            "competitive_signal_detail": [{"drawer_title": a["headline"].replace("[SIMULATION] ", "Simulation: "), "glance_who": "Hanwha Aerospace",
                                           "glance_move": a["move"], "glance_where": "India", "glance_third_party": "Indian Army",
                                           "glance_when": a["date"], "impact_eyebrow": "Orders and revenue · high", "what_article_says": a["what"],
                                           "why_it_matters": a["why"], "_sources": {"what_article_says": [{"url": url, "quote": quote}]}}],
            "competitive_signal_evidence": [{"evidence_group": "key_point", "label": f"Point {i + 1}", "value": x, "quote": x}
                                            for i, x in enumerate(sents[:4])],
        }}]}
    o = runner.run_one(conn, spec, subs[0], client, blocks, dry_run=False,
                       reply=ModelResult(text=json.dumps(reply), cost_usd=0.0), prompt=("simulation", a["body"]))
    runner.log_run(conn, spec, art_id, o)
    conn.commit()
    print(f"article {n}: {o.status} {o.error or ''} | {o.note or ''}")
    if o.details.get("labels"):
        print("  labels:", o.details["labels"])
    for w in (o.details.get("warnings") or [])[:5]:
        print("  warning:", w)
    show(conn)


def show(conn=None) -> None:
    conn = conn or psycopg2.connect(dsn(SB["staging"]), cursor_factory=psycopg2.extras.RealDictCursor)
    guard(conn.dsn)
    with conn.cursor() as cur:
        cur.execute("""SELECT s.published_date, s.classification, s.risk_score, s.probability, s.impact, s.title, s.story_id
                       FROM staging.competitive_signal s WHERE s.title LIKE 'Simulation:%%' ORDER BY s.published_date""")
        sigs = cur.fetchall()
        print("\nSIGNALS")
        for s in sigs:
            print(f"  {s['published_date']}  {str(s['classification']).upper():7} risk {s['risk_score']}/100  p{s['probability']} i{s['impact']}  {s['title']}")
        sid = next((s["story_id"] for s in reversed(sigs) if s["story_id"]), None)
        if sid:
            cur.execute("SELECT title, current_label, escalated_at FROM staging.story WHERE story_id = %s", (sid,))
            st = cur.fetchone()
            print(f"\nSTORY {sid}: {st['title']} | now: {str(st['current_label']).upper()} | escalated at: {st['escalated_at']}")
            cur.execute("""SELECT step_date, step_type, label_after, changed, one_line FROM staging.story_step WHERE story_id = %s
                           ORDER BY step_no""", (sid,))
            for r in cur.fetchall():
                print(f"  {r['step_date']}  {r['step_type']:13} -> {str(r['label_after'] or ''):7} {r['changed'] or ''}  {r['one_line']}")
            same = len({s["story_id"] for s in sigs if s["story_id"]}) == 1
            print("\nboth articles on ONE story:", same)
    conn.rollback()


def changes() -> None:
    """dummy facts an article might state, through backend/change_proposals.add (what the signal / news prompts' hook calls):
    real changes become proposals on the review site's "Changes from news"; non-changes are dropped"""
    from backend import change_proposals
    url, quote = "https://simulation.kssl.invalid/article-3", "[SIMULATION] Hanwha Aerospace unveiled the KAAV-II amphibious assault vehicle."
    items = [
        {"kind": "new_product", "subject": "KAAV-II amphibious assault vehicle (simulation)", "field": "Armoured Vehicles",
         "value": "Amphibious assault vehicle prototype unveiled for the Korean Marine Corps.", "quote": quote},
        {"kind": "spec", "subject": "KAAV-II amphibious assault vehicle (simulation)", "field": "Water speed", "value": "12", "unit": "km/h", "quote": quote},
        {"kind": "spec", "subject": "K9 / K9A1 Thunder", "field": "Range", "value": "over 54 km with extended-range rounds", "quote": quote},
        {"kind": "spec", "subject": "K9 / K9A1 Thunder", "field": "Burst", "value": "3 rounds in 15 s", "quote": quote},          # same as ours: dropped
        {"kind": "leadership", "subject": "Jane Simulation", "field": "Chairperson of the Board", "value": "appointed",
         "effective_date": "2026-11-01", "quote": quote},
        {"kind": "location", "subject": "Hanwha K9 plant, Rajasthan (simulation)", "field": "facility", "value": "India", "quote": quote},
        {"kind": "company_fact", "field": "employee_count_text", "subject": "Hanwha Aerospace", "value": "8,100 employees at 30 Sep 2026", "quote": quote},
        {"kind": "new_product", "subject": "K9 / K9A1 Thunder", "field": "Artillery", "value": "already ours", "quote": quote},  # held: dropped
    ]
    conn = psycopg2.connect(dsn(SB["staging"]), cursor_factory=psycopg2.extras.RealDictCursor)
    guard(conn.dsn)
    with conn.cursor() as cur:
        r = change_proposals.add(cur, items, competitor_id=HANWHA, article_url=url, article_date="2026-10-22", source_prompt="simulation")
    conn.commit()
    print(f"proposals added: {r['added']}")
    for d in r["dropped"]:
        print("  dropped (not a change):", d)


def serve() -> None:
    st, sv = dsn(SB["staging"]), dsn(SB["serving"])
    print("Sandbox review site (two terminals, Git Bash, in kssl_local):")
    print(f'  set -a; . ./.env; set +a; KSSL_VIEW=review KSSL_STAGING_DSN="{st}" KSSL_SERVING_DSN="{sv}" python -m uvicorn backend.app:app --port 8611')
    print("  KSSL_API_TARGET=http://127.0.0.1:8611 npx vite --mode review --port 5181")
    print("then open http://localhost:5181 -> Competitive overview: the 'Simulation:' K9 Thunder card (Watch after article 1, Threat after 2).")


def drop() -> None:
    for db in SB.values():
        docker("psql", "-q", "-U", "kssl", "-d", "postgres", "-c", f"DROP DATABASE IF EXISTS {db}")
    print("sandbox dropped")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "setup":
        setup()
    elif cmd == "article" and len(sys.argv) > 2:
        article(int(sys.argv[2]))
    elif cmd == "show":
        show()
    elif cmd == "changes":
        changes()
    elif cmd == "serve":
        serve()
    elif cmd == "drop":
        drop()
    else:
        print(__doc__)
