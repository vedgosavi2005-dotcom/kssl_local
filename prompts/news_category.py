"""News category by code (functional test G5, 2026-10-25): no model.

    python -m prompts.news_category --selftest
    python -m prompts.news_category [--apply]       dry run (rolled back) without --apply; kssl_staging / kssl_test_* only

The company news list shows one of the news categories of prompts/news.yml. Two kinds of row carried something else:
  * competitive_competitor_moment rows: moment.yml stores a PRODUCT category ("Marine / Naval", "Artillery"), which the company
    news list printed as a news label;
  * competitive_news_article rows with no category ("-").
`news_category` gives the news category when the rule is clear: from the move of the signal the moment points at
(competitive_signal_detail.glance_move), else from the headline when exactly one family of words matches. A sale to a customer
outside the company's home country is Export (news.yml: "Export wins over Contract & order"). Anything unclear is left as it is
and counted: those need the news prompt (owner approval, with a cost).

Investments (owner 2026-10-26): money the company puts in or takes in (news.yml). investment_rule() decides from the headline:
"yes" (IPO / QIP / stake / funding round / raise, or invest + an amount with the company as the subject), "maybe" (investment
words but who invests in what is unclear: backend/news_category_check.py asks the local model) or "no" (stock-market noise such
as fund holdings and "stocks for investment" is always "no"). with_investments() adds Investments to a row's category as an
ADDITIONAL category, joined with SEP (" · ") the way the news list already joins two categories of one article (cats_of splits).
"""

from __future__ import annotations

import re
import sys

NEWS_CATEGORIES = ("Contract & order", "Partnership / JV", "Product launch & testing", "Delivery & induction", "Export",
                   "Financial results", "Stock & market", "Facility & capacity", "Investments", "Leadership & corporate",
                   "Non-defence business", "Other")
INVESTMENTS = "Investments"
# A row can carry several categories in its one category column, joined by SEP: the way src/lib/news.js (dedupeArticles)
# already joins the categories of two rows of one article, and splits them again on "·" (newsGroup, hiddenNews).
SEP = " · "


def cats_of(value) -> list[str]:
    """The categories a stored value carries ("Facility & capacity · Investments" -> two), in order, no repeats."""
    out: list[str] = []
    for c in str(value or "").split("·"):
        c = c.strip()
        if c and c not in out:
            out.append(c)
    return out


def join_cats(cats) -> str:
    return SEP.join(cats_of(SEP.join(c for c in cats if c)))


def is_news_category(value) -> bool:
    """Every category the value carries is one of NEWS_CATEGORIES (an empty value is not)."""
    cs = cats_of(value)
    return bool(cs) and all(c in NEWS_CATEGORIES for c in cs)


# ---- Investments (owner 2026-10-26) -------------------------------------------------------------------------------------
# Money the company puts in or takes in: a stated investment / capex, an equity stake, a funding round or raise, an IPO / QIP /
# bond or share issue, a government or partner investing in the company. investment_rule() answers "yes" (the code is sure),
# "maybe" (investment words, but who invests in what is not clear from the words: the local model decides,
# backend/news_category_check.py) or "no".
_AMOUNT = r"(?:[$€£₹]|\brs\.?\s?|\binr\b|\busd\b|\beur\b|\bgbp\b|\bkrw\b)\s?\d|\d[\d,.]*\s?(?:crore|cr\b|lakh|billion|bn\b|million|mn\b|tln\b|trillion|won\b)"
# stock-market noise: stays Stock & market, never Investments
_INVEST_NOISE = (r"mutual fund|flexi ?cap|\bfund (?:holdings?|house)\b|\bfunds? invests? rs|\bstocks? (?:to buy|for (?:long-term )?investment|picks?)\b|"
                 r"\binvest(?:ment)? in (?:this|these|the) (?:stock|share)s?\b|should investors|\binvestor wealth\b|\btop picks?\b|\bportfolio\b|"
                 r"\bbuy,? sell,? or hold\b|\btarget price\b|\bupside\b|investment climate|\binvestor (?:day|presentation|meet|call)|"
                 r"\bstocks? in focus\b|\bfor (?:long-term |short-term )?investment\b|\bexperts? picks?\b|\bmarket (?:is )?falling\b|\binvestment destination\b|\binvestment opportunit")
# investment words that are not investments
_NOT_INVEST = r"\binvestigat\w*|\bstakeholders?\b|high-stakes|\braising (?:the )?stakes\b|\bstakes? (?:against|are high)\b|\braises? (?:fire rate|question|concern|guidance|target|weight)"
_INVEST_STRONG = (
    r"\bipo\b|\bqip\b|\binitial public offering\b|\bpre-ipo\b|\bfunding round\b|\bseries [a-d] (?:round|funding)\b|\bfund ?rais(?:e|es|ing)\b|"
    r"\b(?:bond|share|rights) (?:sale|issue|offering)\b|\bpreferential (?:issue|allotment)\b|"
    r"\b(?:acquir\w*|acquisitions?|bids? for|buy\w*|bought|tak(?:es?|ing)|raises?|rais(?:ed|ing)|boost\w*|increas\w*|lifts?|ups|purchas\w*)\b[^.;:]{0,45}\bstakes?\b|"
    r"\b\d+(?:\.\d+)?\s?(?:%|per ?cent|percent)\s+(?:\w+\s+){0,2}stakes?\b|\b(?:strategic|minority|majority|equity) stakes?\b|"
    r"\braises? " + r"(?:" + _AMOUNT + r")"
)
_INVEST_WEAK = r"\binvest\w*|\bcapex\b|\bfunding\b|\bfunds?\b|\bfunded\b|\braises?\b|\bequity\b|\bstakes?\b|\bbonds?\b|\bbacked by\b"
_INVEST_VERB = r"\b(?:to )?invest(?:s|ed|ing|ment|ments)?\b"
_EXPANSION = r"\b(?:expansion|expand\w*|plant|facility|factory|project|campus|complex|hub|ecosystem|park)\b"
_SALE_WORDS = (r"\b(?:contracts?|orders?|awards?|awarded|wins?|won|deal|tender|procure\w*|buys?|bags?|bid\w*|lowest|in fray|"
               r"picks?|selects?|selected|penalt\w*|fined?|slaps?)\b")
_GENERIC_NAME = {"the", "and", "defence", "defense", "systems", "system", "group", "industries", "limited", "ltd", "aerospace",
                 "technologies", "company", "corporation", "corp", "inc", "plc", "holdings", "international", "dynamics", "advanced"}


# a government / ministry / armed service as the subject: it funds its own programme or buys equipment, not an investment
_GOV_SUBJECT = (r"^\W*(?:the\s+)?(?:u\.?s\.?|united states|uk|u\.k\.|britain|british|germany|german|france|french|india|indian|"
                r"australia|canada|japan|(?:south )?korea|department of \w+|ministry|pentagon|government|army|navy|air force|usaf|"
                r"dod|dow|mod|nato|congress|european commission|eu)\b")


def _name_tokens(company) -> set[str]:
    """The distinctive words of a company name, plus its "&" short form ("Larsen & Toubro" -> "l&t")."""
    name = str(company or "").lower()
    toks = {w for w in re.findall(r"[a-z0-9&]+", name) if len(w) >= 3 and w not in _GENERIC_NAME}
    amp = re.match(r"\s*([a-z])\w*\s*&\s*([a-z])", name)
    return toks | ({f"{amp.group(1)}&{amp.group(2)}"} if amp else set())


def names_company(headline, company) -> bool:
    return bool(_name_tokens(company) & set(re.findall(r"[a-z0-9&]+", str(headline or "").lower())))


def investment_rule(headline, summary="", company=None) -> tuple[str, str]:
    """("yes" | "maybe" | "no", the words that decided it). Decided on the headline; the summary only adds "maybe".
    "yes": an IPO / QIP / stake / funding-round / raise pattern, or invest(s/ment) + an amount with the company itself as the
    subject (one of its distinctive name words before the verb). Stock-market noise is always "no"."""
    h = str(headline or "")
    text = f"{h} {summary or ''}"
    if re.search(_INVEST_NOISE, text, re.I):
        return "no", "stock-market words"
    clean = re.sub(_NOT_INVEST, " ", h, flags=re.I)
    m = re.search(_INVEST_STRONG, clean, re.I)
    if m:
        return "yes", m.group(0).strip()
    if re.search(_GOV_SUBJECT, clean, re.I) and not re.search(r"\bstakes?\b", clean, re.I):
        return "no", "a government funds its own programme or buys"
    # an expansion / plant WITH a stated amount ("₹2,000-Crore Expansion", "Rs 2,500 Cr ... Manufacturing Plant"): the company's
    # investment, unless it is a sale (a contract to upgrade someone's facility)
    e = re.search(r"(?:" + _AMOUNT + r")[^.;:|]{0,40}?" + _EXPANSION, clean, re.I)
    if e and not re.search(_SALE_WORDS, clean, re.I):
        return "yes", e.group(0).strip()
    v = re.search(_INVEST_VERB, clean, re.I)
    if v and re.search(_AMOUNT, clean, re.I):
        before = set(re.findall(r"[a-z0-9&]+", clean[:v.start()].lower()))
        if _name_tokens(company) & before:
            return "yes", f"{clean[:v.end()].strip()} + an amount"
    w = re.search(_INVEST_WEAK, re.sub(_NOT_INVEST, " ", text, flags=re.I), re.I)
    return ("maybe", w.group(0).strip()) if w else ("no", "")


def with_investments(category, headline, summary="", company=None) -> str:
    """The stored category with Investments added when the code rule is sure ("yes"). A civil (Non-defence business) story
    stays as it is; "Other" alone becomes Investments (Other is only for when nothing fits)."""
    cs = cats_of(category)
    if INVESTMENTS in cs or "Non-defence business" in cs or investment_rule(headline, summary, company)[0] != "yes":
        return SEP.join(cs) if cs else (category or "")
    cs = [c for c in cs if c != "Other"]
    return join_cats(cs + [INVESTMENTS])

# the signal's move (signal.yml glance_move) -> news category; None = no clear news category
MOVE_NEWS = {"Order": "Contract & order", "Contract": "Contract & order", "Selection": "Contract & order", "Supply deal": "Contract & order",
             "Delivery": "Delivery & induction", "Induction": "Delivery & induction", "Trial": "Product launch & testing",
             "Launch": "Product launch & testing", "JV": "Partnership / JV", "MoU": "Partnership / JV", "Acquisition": "Leadership & corporate",
             "Capacity": "Facility & capacity", "Export approval": "Export", "Policy": None, "Cancellation": None}
SALE = ("Contract & order",)        # becomes Export when the buyer is abroad

HEADLINE_RULES = (   # (category, words); a headline is clear when exactly one category matches
    ("Delivery & induction", r"\bdeliver(?:s|ed|y|ies)\b|\bhand(?:s|ed)? over\b|\binduct(?:s|ed|ion)?\b|\breceives? (?:the )?first\b|\bcommission(?:s|ed)\b"),
    ("Contract & order", r"\bcontracts?\b|\borders?\b|\bordered\b|\bawards?\b|\bawarded\b|\bwins?\b|\bselect(?:s|ed)\b|\bprocure(?:s|ment)?\b|"
                         r"\bbuys?\b|\bpurchases?\b|\bdeal\b"),
    ("Partnership / JV", r"\bmou\b|\bpartner(?:s|ship)?\b|\bteaming\b|\bjoint venture\b|\bjv\b|\bties? up\b|\blicen[cs]e\b|\bcollaborat|\bletter of intent\b"),
    ("Product launch & testing", r"\bunveil(?:s|ed)?\b|\blaunch(?:es|ed)?\b|\btest(?:s|ed|ing)?\b|\btrials?\b|\bdemonstrat|\bfir(?:es|ed|ing)\b|"
                                 r"\bshowcas|\bdebuts?\b|\bcertif|\bqualif|\bprototype\b|\breveals?\b"),
    ("Facility & capacity", r"\bplant\b|\bfacility\b|\bfactory\b|\bproduction line\b|\bfoundation stone\b|\bcapacity\b|\bexpan(?:d|ds|sion)\b"),
    ("Investments", _INVEST_STRONG + r"|" + _INVEST_VERB),
    ("Financial results", r"\bresults\b|\bprofit\b|\brevenue\b|\bearnings\b|\bq[1-4]\b"),
    ("Leadership & corporate", r"\bceo\b|\bappoint|\bnames? new\b|\bacquir|\bacquisition\b|\bmerger\b|\bsteps down\b"),
    ("Stock & market", r"\bshares?\b|\bshare price\b|\bstocks?\b|\bsensex\b|\bnifty\b|\btarget price\b"),
)


def headline_category(headline) -> str | None:
    h = str(headline or "")
    if re.search(_INVEST_NOISE, h, re.I):
        h = re.sub(_INVEST_VERB, " ", h, flags=re.I)              # "stocks for investment": not an investment
    h_inv = re.sub(_NOT_INVEST, " ", h, flags=re.I)
    hits = {cat for cat, pat in HEADLINE_RULES if re.search(pat, h_inv if cat == INVESTMENTS else h, re.I)}
    if INVESTMENTS in hits and len(hits) == 2:                    # "invests $135M to expand a plant": the plant is the category,
        hits.discard(INVESTMENTS)                                 # with_investments() adds Investments on top
    return hits.pop() if len(hits) == 1 else None


def news_category(headline, move=None, abroad: bool | None = None) -> str | None:
    """The news category, or None when no rule is clear. `move`: the signal's glance_move; `abroad`: the buyer is outside the
    company's home country (None = not known)."""
    cat = MOVE_NEWS.get(move) if move else None
    if cat is None and not (move and move in MOVE_NEWS):
        cat = headline_category(headline)
    if cat in SALE and abroad:
        return "Export"
    return cat


def _iso(cur, name) -> str:
    if not name:
        return ""
    cur.execute("""SELECT iso2 FROM staging.country_reference WHERE lower(iso2) = lower(%(v)s) OR lower(country_name) = lower(%(v)s)
                   OR lower(%(v)s) = ANY(SELECT lower(a) FROM unnest(coalesce(aliases, '{}')) a) LIMIT 1""", {"v": str(name).strip()})
    r = cur.fetchone()
    return (r["iso2"] or "").upper() if r else ""


def _cite(cur, table: str, row_id, category: str, basis: str) -> None:
    """The category's source: one judgement fact_source row naming the code rule (replaces earlier category rows of the row)."""
    cur.execute("DELETE FROM staging.fact_source WHERE table_name = %s AND row_id = %s AND column_name = 'category'", (table, str(row_id)))
    cur.execute("""INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, quote, retrieved_at)
                   VALUES (%s, %s, 'category', 'judgement', 'judgement', %s, now())""",
                (table, str(row_id), f"{category}: {basis} (code rule, prompts/news_category.py, G5 2026-10-25)."))


def moment_rows(cur, only_ids=None) -> list[dict]:
    cats = list(NEWS_CATEGORIES)
    cur.execute("""SELECT m.moment_id, m.title, m.category, m.country_name, d.glance_move, c.origin_country
                   FROM staging.competitive_competitor_moment m
                   LEFT JOIN staging.competitive_signal_detail d ON d.signal_id = m.signal_id
                   LEFT JOIN staging.competitive_competitor c ON c.competitor_id = m.competitor_id
                   WHERE (m.category IS NULL OR NOT (string_to_array(m.category, ' · ') <@ %s::text[]))""" + (" AND m.moment_id::text = ANY(%s)" if only_ids is not None else ""),
                (cats, [str(i) for i in only_ids]) if only_ids is not None else (cats,))
    return [dict(r) for r in cur.fetchall()]


def recategorise_moments(cur, only_ids=None) -> tuple[list, list]:
    """Moment rows whose category is not a news category -> news_category; returns (changed, left)."""
    changed, left = [], []
    for r in moment_rows(cur, only_ids):
        a, b = _iso(cur, r["country_name"]), _iso(cur, r["origin_country"])
        new = news_category(r["title"], r["glance_move"], (a != b) if a and b else None)
        if new:
            cur.execute("UPDATE staging.competitive_competitor_moment SET category = %s WHERE moment_id = %s", (new, r["moment_id"]))
            basis = (f"the move of its signal is {r['glance_move']}" if r["glance_move"] in MOVE_NEWS and MOVE_NEWS[r["glance_move"]]
                     else "the headline names one kind of move") + (" and the buyer is outside the company's home country" if new == "Export" else "")
            _cite(cur, "competitive_competitor_moment", r["moment_id"], new, basis)
            changed.append((r["moment_id"], r["category"], new, r["title"]))
        else:
            left.append((r["moment_id"], r["category"], r["title"]))
    return changed, left


def recategorise_news(cur) -> tuple[list, list]:
    """competitive_news_article rows with no category -> the headline rule; returns (changed, left)."""
    changed, left = [], []
    cur.execute("SELECT article_id, headline FROM staging.competitive_news_article WHERE coalesce(trim(category), '') = ''")
    for r in cur.fetchall():
        new = headline_category(r["headline"])
        if new:
            new = with_investments(new, r["headline"])
            cur.execute("UPDATE staging.competitive_news_article SET category = %s WHERE article_id = %s AND coalesce(trim(category), '') = ''",
                        (new, r["article_id"]))
            _cite(cur, "competitive_news_article", r["article_id"], new, "the headline names one kind of news")
            changed.append((r["article_id"], None, new, r["headline"]))
        else:
            left.append((r["article_id"], None, r["headline"]))
    return changed, left


def main(apply: bool) -> None:
    from prompts.run import connect
    conn = connect()
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS d")
        db = cur.fetchone()["d"]
        if db != "kssl_staging" and not db.startswith("kssl_test"):
            raise SystemExit(f"refused: database {db} (kssl_staging or kssl_test_* only)")
        mc, ml = recategorise_moments(cur)
        nc, nl = recategorise_news(cur)
        for title, ch, lf in (("moments", mc, ml), ("news", nc, nl)):
            print(f"{title}: {len(ch)} set, {len(lf)} left for the news prompt")
            for i, old, new, h in ch:
                print(f"  set  {i}: {old or '-'} -> {new}   | {str(h)[:90]}")
            for i, old, h in lf:
                print(f"  LEFT {i}: {old or '-'}   | {str(h)[:90]}")
        print("applied" if apply else "dry run, rolled back (--apply to write)")
        conn.commit() if apply else conn.rollback()
    conn.close()


def _selftest() -> None:
    assert news_category("Nordvik wins Veland order", "Contract", abroad=True) == "Export"
    assert news_category("Nordvik wins Veland order", "Contract", abroad=False) == "Contract & order"
    assert news_category("x", "Delivery", abroad=True) == "Delivery & induction"           # a delivery abroad stays a delivery
    assert news_category("Nordvik unveils the NV-155", None) == "Product launch & testing"
    assert news_category("Nordvik signs MoU with Veland Arms", None) == "Partnership / JV"
    assert news_category("Nordvik lays foundation stone for a shell plant", None) == "Facility & capacity"
    assert news_category("Nordvik unveils and tests a new gun after winning an order", None) is None   # two families: unclear
    assert news_category("Nordvik in the news", None) is None and news_category(None, None) is None
    assert news_category("Veland Shipyard shares jump 7% on signing MoU with Nordvik", None) is None      # share move + MoU: unclear
    assert news_category("Policy note", "Policy") is None and news_category("x", "Cancellation") is None
    assert news_category("Nordvik takes over Veland", "Acquisition") == "Leadership & corporate"
    assert set(v for v in MOVE_NEWS.values() if v) <= set(NEWS_CATEGORIES)
    assert {c for c, _p in HEADLINE_RULES} <= set(NEWS_CATEGORIES)
    # Investments (owner 2026-10-26)
    ir = investment_rule
    assert ir("Adani Defence & Aerospace to Invest ₹2,500 Crore in a Missile Ecosystem", company="Adani Defence & Aerospace")[0] == "yes"
    assert ir("BAE Systems Invests $135M to Expand US Defense Manufacturing Facilities", company="BAE Systems")[0] == "yes"
    assert ir("U.S. Invests $16.2B in Columbia-Class SSBN Submarine", company="General Dynamics")[0] == "no"        # a government buys
    assert ir("UK Announces $11.2 Billion Investment in Nuclear Submarines")[0] == "no"
    assert ir("Germany pursues stake purchase in tank maker KNDS")[0] == "maybe"           # a government investing in the company
    assert ir("L&T plans Rs 4,500 crore investment in Bengal", company="Larsen & Toubro")[0] == "yes"            # "L&T" names it
    assert ir("Pratt & Whitney Invests $25M in Polish Engine Parts Plant", company="RTX (Raytheon)")[0] == "yes"     # amount + plant
    assert names_company("L&T Partners Exail for a mine countermeasure suite", "Larsen & Toubro") and not names_company("Navy orders", "Saab")
    assert ir("Rheinmetall acquires majority stake in DOK-ING")[0] == "yes" and ir("Hanwha Aerospace raises stake in KAI above 5%")[0] == "yes"
    assert ir("KNDS IPO still possible this year, chief tells Handelsblatt")[0] == "yes"
    assert ir("FTC approves Hanwha's acquisition of additional KAI stakes")[0] == "yes" and ir("CSG bids for stake in KNDS")[0] == "yes"
    assert ir("Skapion Raises $36M to Counter the Drone Swarm Threat")[0] == "yes"
    assert ir("Abakkus Flexi Cap Fund invests Rs 2,426 crore in equities in January")[0] == "no"                     # fund holdings
    assert ir("Defence Stocks: BEL, HAL, Bharat Dynamics for long-term investment - Expert picks")[0] == "no"
    assert ir("Hanwha Aerospace vows full investigation into deadly explosion")[0] == "no"
    assert ir("India Signs Javelin ATGM Deal, Raising Stakes Against China-Pakistan Armour")[0] == "no"
    assert ir("KAI's top stakeholder says no sale planned")[0] == "no"
    assert ir("K9MH Howitzer Raises Fire Rate to 9 RPM")[0] == "no"
    assert ir("Nordvik wins Veland order")[0] == "no"
    assert ir("Uttar Pradesh: Adani Defence Plans ₹2,000-Crore Expansion In Kanpur To Boost Ammunition Manufacturing")[0] == "yes"
    assert ir("MP: Union Minister Scindia To Lay Foundation Stone Of Rs 2,500 Cr Adani Defence Manufacturing Plant")[0] == "yes"
    assert ir("Babcock wins £100m contract to upgrade the Devonport facility")[0] == "no"                       # a sale, not capex
    assert ir("Tata emerges lowest bidder for Rs 20,000-crore Project Zorawar light tank")[0] != "yes"
    assert ir("Sewerage board slaps Rs 18-cr penalty on L&T for canal water project delay")[0] != "yes"
    assert with_investments("Facility & capacity", "Nordvik to invest $100 million in a new shell plant", company="Nordvik") \
        == "Facility & capacity · Investments"
    assert with_investments("Facility & capacity · Investments", "Nordvik to invest $100 million", company="Nordvik") == "Facility & capacity · Investments"
    assert with_investments("Other", "Nordvik takes 20% stake in Veland Arms") == "Investments"
    assert with_investments("Non-defence business", "Nordvik to invest Rs 25,000 cr in a data centre", company="Nordvik") == "Non-defence business"
    assert with_investments("Export", "Nordvik wins Veland order") == "Export"
    assert news_category("Saab deepens AI push with strategic stake in Comand AI", None) == "Investments"
    assert news_category("Nordvik invests $135M to expand its shell plant", None) == "Facility & capacity"   # + Investments by with_investments
    assert cats_of("Partnership / JV · Contract & order") == ["Partnership / JV", "Contract & order"] and cats_of(None) == []
    assert is_news_category("Facility & capacity · Investments") and not is_news_category("Artillery") and not is_news_category("")
    assert join_cats(["Export", "Investments", "Export"]) == "Export · Investments"
    print("news_category self-check ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        main(apply="--apply" in sys.argv)
