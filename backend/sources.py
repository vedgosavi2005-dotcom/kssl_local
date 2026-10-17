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
    # added after the 2026-10-16 news audit (vetted from drop counts; each carried relevant stories)
    # Korea business / defence / electronics press
    "mk.co.kr", "businesskorea.co.kr", "en.sedaily.com", "asiae.co.kr", "thelec.net",   # mk.co.kr covers pulse.mk.co.kr
    "mbiz.heraldcorp.com", "mt.co.kr", "ajupress.com", "donga.com", "fntimes.com",
    # defence trade press and wires
    "defence-industry.eu", "defencesecurityasia.com", "asiapacificdefencereporter.com",
    "canadiandefencereview.com", "nationalinterest.org", "joint-forces.com", "zona-militar.com",
    "aa.com.tr",
    # India business and trade press
    "swarajyamag.com", "manufacturingtodayindia.com", "zeebiz.com", "etnownews.com",
    "freepressjournal.in", "telanganatoday.com", "constructionworld.in",
    "oilandgasmiddleeast.com", "rareearthexchanges.com",
]
# Decisions:
#   idrw.org           -- BLOCKED ("blog"): largely rewrites other outlets' stories with
#                         speculative commentary, no named editorial standards.
#   ajaishukla.com     -- BLOCKED ("blog"): a personal blog (Broadsword), not an outlet.
#                         Owner decision: no source on a "blog" domain is ever loaded or cited; the
#                         loaders drop such sources (is_blocked) and db/purge_blog_sources.py cleaned the data.
#   defence-xpress.com -- listed: Ukrainian defence-analysis outlet with an editorial
#                         staff, widely cited by Western trade press.
#   PR wires           -- blocked: they rehost releases; the issuing company's own
#                         newsroom (a company domain) is the primary copy.
#   Audit additions    -- see the "added after the 2026-10-16 news audit" lines in INDEPENDENT.
#                         NOT added: defence-blog.com (mixed quality, and a "blog"), republicworld.com
#                         (borderline), the tip / exam-prep / partisan sites listed under BLOCKED.

# --- blocked: rejected with an explicit reason (unknown domains are rejected anyway) -------
BLOCKED = {
    "wiki": ["wikipedia.org", "wikimedia.org", "wikiwand.com", "wikia.com", "wikia.org", "wikidata.org", "wikitree.com",
             "fandom.com"],
    "blog": ["ajaishukla.com", "idrw.org"],
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
                                 "dailyhunt.in", "newsnow.co.uk"],
    "data / market site": ["dealroom.co", "crunchbase.com", "tracxn.com", "pitchbook.com",
                           "zoominfo.com", "owler.com", "cbinsights.com",
                           "marketscreener.com", "investing.com", "seekingalpha.com",
                           "simplywall.st", "marketbeat.com", "stocktitan.net",
                           "tipranks.com", "zawya.com"],
    "market tips / trading": ["finance.biggo.com", "biggo.com", "scanx.trade", "ad-hoc-news.de", "marketwatch.com",
                              "kalkine.co.in", "tradebrains.in", "upstox.com", "tradingview.com", "univest.in",
                              "cryptorank.io"],
    "exam prep / explainer": ["ssbcrack.com", "vajiramandravi.com", "gktoday.in", "indianmasterminds.com",
                              "envantermedya.com"],
    "partisan / sensational": ["pgurus.com", "opindia.com", "eurasiantimes.com", "republicworld.com",
                               "en.defence-ua.com"],
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


# mobile hosts -> the desktop host the site redirects to (the stored article url should be the desktop one)
MOBILE_HOSTS = {
    "m.economictimes.com": "economictimes.indiatimes.com",
    "m.timesofindia.com": "timesofindia.indiatimes.com",
    "m.timesofindia.indiatimes.com": "timesofindia.indiatimes.com",
    "m.economictimes.indiatimes.com": "economictimes.indiatimes.com",
}


def desktop_host(host: str) -> str:
    """Desktop host for a mobile one (m.economictimes.com -> economictimes.indiatimes.com). Other `m.` / `mobile.`
    hosts lose the prefix only when the rest is a listed outlet; every other host is returned unchanged."""
    h = (host or "").lower()
    if h in MOBILE_HOSTS:
        return MOBILE_HOSTS[h]
    for pre in ("m.", "mobile."):
        if h.startswith(pre):
            rest = h[len(pre):]
            if any(_matches(rest, d) or _matches("www." + rest, d) for d in INDEPENDENT):
                return rest
    return h


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

def is_blog(url: str) -> bool:
    """A source on one of the permanently blocked blog domains (BLOCKED["blog"], subdomains included)."""
    host = host_of(url or "")
    return bool(host) and any(_matches(host, d) for d in BLOCKED["blog"])


def is_blocked(url: str) -> bool:
    """A source the loaders must never store or cite: a wiki or a blocked blog. Prompts (prompts/spec.py), the Excel
    loaders (backend/excel_load.py) and the news job all use this one helper."""
    return is_wiki(url) or is_blog(url)


# --- the client's own domains: primary for the client subject ---------------------------------------
# KSSL (Kalyani Strategic Systems) and its group. Used when the subject IS the client (client=True), never for
# competitors, so a Kalyani page cited about a rival is not treated as official for that rival.
CLIENT_DOMAINS = ("kssl.in", "bharatforge.com", "kalyanigroup.com")


def client_domains() -> tuple[str, ...]:
    return CLIENT_DOMAINS


def classify_reason(url: str, company_domains=(), client: bool = False) -> tuple[str | None, str]:
    """(tier, reason). tier is "primary", "independent" or None (rejected).
    company_domains: the subject company's own domains (primary: "company domain");
    client=True: the subject is the client, so CLIENT_DOMAINS count as company domains too."""
    if client:
        company_domains = (*company_domains, *CLIENT_DOMAINS)
    if not url or not url.lower().startswith(("http://", "https://")):
        return None, "not an http(s) url"
    host = host_of(url)
    if not host:
        return None, "no host"
    if is_wiki(url):
        return None, "blocked: wiki"
    if is_blog(url):
        return None, "blocked: blog"
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


def classify(url: str, company_domains=(), client: bool = False) -> str | None:
    """'primary' | 'independent' | None (rejected). See module docstring."""
    return classify_reason(url, company_domains, client)[0]


# --- rank of a source as the MAIN article of a story (prompts/news_merge.py) ------------------------------
# official / company site -> wire agency -> national press -> everything else. Pages that a plain client cannot
# read (paywalled, or answering 401/403 to scripts) come last whatever their outlet, because the signal run
# fetches the main article's page.
WIRES = ["reuters.com", "apnews.com", "afp.com", "ptinews.com", "aninews.in", "ianslive.in", "yna.co.kr"]
NATIONAL_PRESS = [
    "thehindu.com", "thehindubusinessline.com", "indianexpress.com", "newindianexpress.com", "hindustantimes.com",
    "timesofindia.indiatimes.com", "economictimes.indiatimes.com", "economictimes.com", "business-standard.com",
    "livemint.com", "ndtv.com", "financialexpress.com", "indiatoday.in", "deccanherald.com", "tribuneindia.com",
    "bbc.com", "bbc.co.uk", "ft.com", "wsj.com", "nytimes.com", "washingtonpost.com", "theguardian.com",
    "economist.com", "aljazeera.com", "dw.com", "france24.com", "asia.nikkei.com", "koreaherald.com",
    "koreatimes.co.kr", "koreajoongangdaily.joins.com", "koreajoongangdaily.com", "chosun.com", "handelsblatt.com",
    "lesechos.fr", "scmp.com", "straitstimes.com", "bloomberg.com", "politico.com", "politico.eu",
]
# Measured 2026-10-16: reuters 401, upi 403, bloomberg 403 to a plain client; the others sit behind a paywall.
HARD_TO_FETCH = ["reuters.com", "upi.com", "bloomberg.com", "wsj.com", "ft.com", "nytimes.com", "economist.com",
                 "washingtonpost.com", "aviationweek.com", "janes.com"]


def hard_to_fetch(url: str) -> bool:
    host = host_of(url or "")
    return bool(host) and any(_matches(host, d) for d in HARD_TO_FETCH)


def outlet_rank(url: str, tier: str | None = None, company_domains=()) -> int:
    """0 official / company site (tier "primary"), 1 wire agency, 2 national press, 3 everything else."""
    if tier == "primary":
        return 0
    host = host_of(url or "")
    if host and any(_matches(host, d) for d in company_domains if d):
        return 0
    if host and any(_matches(host, d) for d in WIRES):
        return 1
    if host and any(_matches(host, d) for d in NATIONAL_PRESS):
        return 2
    return 3


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
        ("https://www.ajaishukla.com/2016/12/x.html", (), None),
        ("https://m.idrw.org/?p=1", ("idrw.org",), None),
        ("https://notidrw.org/x", (), None),
        ("https://www.sahi.com/news/x", (), None),
        ("https://news.google.com/rss/articles/CBMi", (), None),
        ("https://x.medium.com/post", (), None),
        ("https://notgov.com/x", (), None),
        ("https://reuters.com.evil.example/x", (), None),
        # audit allowlist additions (2026-10-16) and the kept blocks
        ("https://www.mk.co.kr/en/x", (), "independent"),
        ("https://pulse.mk.co.kr/news/english/1", (), "independent"),
        ("https://www.businesskorea.co.kr/news/articleView.html?idxno=1", (), "independent"),
        ("https://en.sedaily.com/NewsView/1", (), "independent"),
        ("https://www.asiae.co.kr/en/x", (), "independent"),
        ("https://www.thelec.net/news/articleView.html?idxno=1", (), "independent"),
        ("https://defence-industry.eu/x/", (), "independent"),
        ("https://defencesecurityasia.com/en/x/", (), "independent"),
        ("https://www.swarajyamag.com/defence/x", (), "independent"),
        ("https://www.zeebiz.com/india/news-x", (), "independent"),
        ("https://finance.biggo.com/news/x", (), None),
        ("https://www.ssbcrack.com/2026/x", (), None),
        ("https://www.opindia.com/2026/x", (), None),
        ("https://www.tradingview.com/news/x", (), None),
        ("https://defence-blog.com/x", (), None),                       # not added: a "blog", mixed quality
        ("https://www.kssl.in/news/x", (), None),                       # the client's site is primary only for the client
    ]
    bad = 0
    for url, doms, want in cases:
        got, why = classify_reason(url, doms)
        ok = got == want
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {str(got):12} {why:28} {url}")
    assert not bad, f"{bad} case(s) failed"
    # client domains: primary for the client subject only
    assert classify("https://www.kssl.in/news/x", client=True) == "primary"
    assert classify("https://www.bharatforge.com/media/x", client=True) == "primary"
    assert classify("https://www.kalyanigroup.com/x", client=True) == "primary"
    assert classify("https://www.bharatforge.com/media/x") is None and classify("https://www.kalyanigroup.com/x") is None
    assert classify_reason("https://kssl.in/x", client=True)[1] == "company domain"
    assert classify("https://www.kssl.in/x", ("hanwha.com",), client=True) == "primary"        # both lists add up
    assert classify("https://idrw.org/kssl", client=True) is None                                # a blog is never a source
    assert client_domains() == ("kssl.in", "bharatforge.com", "kalyanigroup.com")
    # mobile hosts -> desktop
    assert desktop_host("m.economictimes.com") == "economictimes.indiatimes.com"
    assert desktop_host("m.timesofindia.com") == "timesofindia.indiatimes.com"
    assert desktop_host("m.thehindu.com") == "thehindu.com" and desktop_host("m.unknown-site.com") == "m.unknown-site.com"
    assert desktop_host("www.reuters.com") == "www.reuters.com"
    # main-article rank: official > wire > national press > others; blocked-to-scripts outlets are flagged
    assert outlet_rank("https://www.army.mil/x", "primary") == 0
    assert outlet_rank("https://www.bharatforge.com/x", "independent", ("bharatforge.com",)) == 0
    assert outlet_rank("https://www.ptinews.com/x") == outlet_rank("https://en.yna.co.kr/x") == outlet_rank("https://www.aninews.in/x") == 1
    assert outlet_rank("https://www.thehindu.com/x") == outlet_rank("https://www.koreatimes.co.kr/x") == 2
    assert outlet_rank("https://www.breakingdefense.com/x") == outlet_rank("https://www.armyrecognition.com/x") == 3
    assert hard_to_fetch("https://www.reuters.com/x") and hard_to_fetch("https://www.bloomberg.com/x") and not hard_to_fetch("https://en.yna.co.kr/x")
    assert classify_reason("https://idrw.org/x/")[1] == "blocked: blog"
    assert classify_reason("https://www.ajaishukla.com/2016/12/x.html")[1] == "blocked: blog"
    assert classify_reason("https://sub.idrw.org/x", ("idrw.org",))[1] == "blocked: blog"          # blocked even as a "company" domain
    assert is_blog("http://IDRW.org/?p=397085") and is_blog("https://blog.ajaishukla.com/x") and not is_blog("https://notidrw.org/x")
    assert is_blocked("https://en.wikipedia.org/wiki/X") and is_blocked("https://idrw.org/x") and not is_blocked("https://www.janes.com/x")
    assert not is_blocked("") and not is_blocked(None) and not is_blog("not a url")
    print(f"all {len(cases)} cases pass")
