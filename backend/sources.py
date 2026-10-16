"""Source policy for news: which sites may feed the dashboard, and at what tier.

Allowlist model -- a URL is accepted only if it is
  * "primary":     the company's own site, a government / military / procurement portal,
                   a stock-exchange or regulator filing, or a patent office; or
  * "independent": an established editorial outlet or defence trade publication listed
                   in INDEPENDENT below.
Everything else (unknown domains, and the BLOCKED list which exists only to give a clear
rejection reason) is rejected.

The lists are plain data: edit them to change the policy. A domain entry matches the
domain itself and every subdomain ("economictimes.indiatimes.com" matches
"m.economictimes.indiatimes.com").

Reused by the pulse job (backend/news.py) and meant for the data loader too:

    from backend.sources import classify
    tier = classify(url, company_domains=("bharatforge.com",))   # "primary" | "independent" | None

Self-check: python -m backend.sources
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

# --- primary: official sources ------------------------------------------------------------
# Government / military hosts by suffix: x.gov, x.gov.in, x.nic.in, x.mil, x.gov.uk,
# x.gouv.fr, x.gob.es, x.go.kr, x.mil.kr, x.govt.nz, x.gc.ca, x.europa.eu, ...
PRIMARY_HOST_PATTERN = re.compile(
    r"(^|\.)((gov|mil|gob|gouv|go|govt)(\.[a-z]{2})?|nic\.in|gc\.ca|europa\.eu|nato\.int)$"
)
PRIMARY = [
    # defence ministries / procurement agencies not on a gov suffix
    "bmvg.de", "bundeswehr.de", "baainbw.de", "defense.gouv.fr", "dapa.go.kr",
    # stock exchanges and regulators (filings)
    "bseindia.com", "nseindia.com", "sec.gov", "sebi.gov.in", "londonstockexchange.com",
    "dart.fss.or.kr", "kind.krx.co.kr", "hkexnews.hk", "asx.com.au",
    # patent offices
    "uspto.gov", "ipindia.gov.in", "epo.org", "wipo.int", "dpma.de", "kipo.go.kr",
]

# --- independent: editorial outlets and defence trade press -------------------------------
INDEPENDENT = [
    # wires
    "reuters.com", "apnews.com", "afp.com", "ptinews.com", "aninews.in", "ianslive.in",
    "yna.co.kr",
    # Indian national / business press
    "thehindu.com", "thehindubusinessline.com", "indianexpress.com", "newindianexpress.com",
    "hindustantimes.com", "timesofindia.indiatimes.com", "economictimes.indiatimes.com",
    "economictimes.com", "business-standard.com", "livemint.com", "moneycontrol.com",
    "ndtv.com", "ndtvprofit.com", "firstpost.com", "theprint.in", "financialexpress.com",
    "indiatoday.in", "businesstoday.in", "cnbctv18.com", "deccanherald.com",
    "tribuneindia.com", "theweek.in", "fortuneindia.com",
    # Indian defence trade press
    "spslandforces.com", "spsnavalforces.com", "spsairbuz.com", "sps-aviation.com",
    "forceindia.net", "bharatshakti.in",
    # international general / business press
    "bbc.com", "bbc.co.uk", "bloomberg.com", "ft.com", "wsj.com", "nytimes.com",
    "washingtonpost.com", "theguardian.com", "economist.com", "cnbc.com", "aljazeera.com",
    "dw.com", "france24.com", "asia.nikkei.com", "koreaherald.com", "koreatimes.co.kr",
    "koreajoongangdaily.joins.com", "koreajoongangdaily.com", "chosun.com", "kedglobal.com",
    "upi.com", "handelsblatt.com", "lesechos.fr", "politico.eu",
    "politico.com", "scmp.com", "straitstimes.com",
    # international defence / aerospace trade press
    "janes.com", "defensenews.com", "breakingdefense.com", "defenseone.com",
    "c4isrnet.com", "army-technology.com", "naval-technology.com",
    "airforce-technology.com", "shephardmedia.com", "flightglobal.com",
    "aviationweek.com", "thedefensepost.com", "armyrecognition.com", "navalnews.com",
    "euro-sd.com", "defence-xpress.com", "militarytimes.com", "defense-aerospace.com",
    "asianmilitaryreview.com", "defenceweb.co.za",
]
# Decisions:
#   idrw.org           -- NOT listed: largely rewrites other outlets' stories with
#                         speculative commentary, no named editorial standards.
#   defence-xpress.com -- listed: Ukrainian defence-analysis outlet with an editorial
#                         staff, widely cited by Western trade press.
#   PR wires           -- blocked: they rehost releases; the issuing company's own
#                         newsroom (a company domain) is the primary copy.

# --- blocked: rejected with an explicit reason (unknown domains are rejected anyway) -------
BLOCKED = {
    "wiki": ["wikipedia.org", "wikimedia.org", "wikiwand.com", "wikia.com", "wikia.org", "wikidata.org", "wikitree.com",
             "fandom.com"],
    "forum / q&a": ["reddit.com", "quora.com", "defence.in", "defenceforumindia.com",
                    "pakdefense.com", "militaryforum.com", "stackexchange.com"],
    "social media": ["twitter.com", "x.com", "facebook.com", "instagram.com",
                     "linkedin.com", "youtube.com", "tiktok.com", "t.me", "threads.net"],
    "blog platform": ["medium.com", "substack.com", "blogspot.com", "wordpress.com",
                      "tumblr.com", "blogger.com"],
    "syndication / aggregator": ["pressreader.com", "magzter.com", "bignewsnetwork.com",
                                 "irishsun.com", "sydneysun.com", "newsbreak.com",
                                 "msn.com", "yahoo.com", "flipboard.com", "ground.news",
                                 "inkl.com", "devdiscourse.com", "latestly.com",
                                 "dailyhunt.in", "newsnow.co.uk", "idrw.org"],
    "data / market site": ["dealroom.co", "crunchbase.com", "tracxn.com", "pitchbook.com",
                           "zoominfo.com", "owler.com", "cbinsights.com",
                           "marketscreener.com", "investing.com", "seekingalpha.com",
                           "simplywall.st", "marketbeat.com", "stocktitan.net",
                           "tipranks.com", "zawya.com"],
    "press-release wire": ["prnewswire.com", "businesswire.com", "globenewswire.com",
                           "accesswire.com", "einpresswire.com", "newswire.com",
                           "openpr.com", "prlog.org"],
}
# URL paths that mark forum threads / user content on otherwise unknown hosts
BLOCKED_PATH = re.compile(r"/(threads?|forums?|showthread|community|discussion)(/|\.|$)", re.I)
BLOCKED_HOST_PREFIX = ("forum.", "forums.", "community.", "blog.", "blogs.")


def host_of(url: str) -> str:
    try:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _matches(host: str, domain: str) -> bool:
    domain = domain.lower().lstrip(".")
    if domain.startswith("www."):
        domain = domain[4:]
    return host == domain or host.endswith("." + domain)


def is_wiki(url: str) -> bool:
    """A wiki or wiki mirror (Wikipedia, Wikiwand, Fandom, wikia, any host label starting with 'wiki' or ending in 'pedia',
    any /wiki/ path). Prompts must never cite one; the prompt runner rejects such urls."""
    host = host_of(url or "")
    if not host:
        return False
    if any(_matches(host, d) for d in BLOCKED["wiki"]):
        return True
    if any(l.startswith("wiki") or l.endswith("pedia") for l in host.split(".")[:-1]):
        return True
    return "/wiki/" in (urlsplit(url).path or "").lower() + "/"



def classify_reason(url: str, company_domains=()) -> tuple[str | None, str]:
    """(tier, reason). tier is "primary", "independent" or None (rejected)."""
    if not url or not url.lower().startswith(("http://", "https://")):
        return None, "not an http(s) url"
    host = host_of(url)
    if not host:
        return None, "no host"
    if is_wiki(url):
        return None, "blocked: wiki"
    if host.endswith("news.google.com") or host == "google.com":
        return None, "google wrapper"
    if any(_matches(host, d) for d in company_domains if d):
        return "primary", "company domain"
    for reason, domains in BLOCKED.items():
        if any(_matches(host, d) for d in domains):
            return None, "blocked: " + reason
    if host.startswith(BLOCKED_HOST_PREFIX) or BLOCKED_PATH.search(urlsplit(url).path or ""):
        return None, "blocked: forum / blog path"
    if PRIMARY_HOST_PATTERN.search(host) or any(_matches(host, d) for d in PRIMARY):
        return "primary", "official"
    if any(_matches(host, d) for d in INDEPENDENT):
        return "independent", "allowlisted outlet"
    return None, "unknown domain"


def classify(url: str, company_domains=()) -> str | None:
    """'primary' | 'independent' | None (rejected). See module docstring."""
    return classify_reason(url, company_domains)[0]


if __name__ == "__main__":
    cases = [
        ("https://www.bharatforge.com/media/press-release-x", ("bharatforge.com",), "primary"),
        ("https://pib.gov.in/PressReleasePage.aspx?PRID=1", (), "primary"),
        ("https://mod.gov.in/en/press-release", (), "primary"),
        ("https://gem.gov.in/tender/123", (), "primary"),
        ("https://www.defense.gov/News/Releases/", (), "primary"),
        ("https://www.army.mil/article/1", (), "primary"),
        ("https://www.bseindia.com/xml-data/corpfiling/AttachLive/x.pdf", (), "primary"),
        ("https://www.sec.gov/Archives/edgar/data/1/x.htm", (), "primary"),
        ("https://dapa.go.kr/dapa_en/main.do", (), "primary"),
        ("https://www.reuters.com/business/aerospace-defense/x-2026-10-01/", (), "independent"),
        ("https://economictimes.indiatimes.com/news/defence/x/articleshow/1.cms", (), "independent"),
        ("https://m.economictimes.com/news/defence/x/articleshow/1.cms", (), "independent"),
        ("https://www.janes.com/osint-insights/defence-news/x", (), "independent"),
        ("https://www.livemint.com/companies/news/x.html", (), "independent"),
        ("https://www.defence-xpress.com/news/x", (), "independent"),
        ("https://defence.in/threads/bharat-forge.1234/", (), None),
        ("https://some-unknown-site.com/forum/x", (), None),
        ("https://www.pressreader.com/india/x/2026", (), None),
        ("https://www.magzter.com/stories/x", (), None),
        ("https://www.irishsun.com/news/x", (), None),
        ("https://finance.yahoo.com/news/x.html", (), None),
        ("https://app.dealroom.co/companies/x", (), None),
        ("https://en.wikipedia.org/wiki/Bharat_Forge", (), None),
        ("https://www.prnewswire.com/news-releases/x.html", (), None),
        ("https://idrw.org/x/", (), None),
        ("https://www.sahi.com/news/x", (), None),
        ("https://news.google.com/rss/articles/CBMi", (), None),
        ("https://x.medium.com/post", (), None),
        ("https://notgov.com/x", (), None),
        ("https://reuters.com.evil.example/x", (), None),
    ]
    bad = 0
    for url, doms, want in cases:
        got, why = classify_reason(url, doms)
        ok = got == want
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {str(got):12} {why:28} {url}")
    assert not bad, f"{bad} case(s) failed"
    print(f"all {len(cases)} cases pass")
