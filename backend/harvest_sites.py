"""Site harvester: company newsrooms, government pages and trade press -> staging.source_document (raw layer).

For every site of the list in SITES it finds article URLs the cheap way first and then reads each article once:
  1. RSS / Atom feed (declared in the page head, a common path, or the site's own `feeds`; WordPress feeds
     are paged with ?paged=N to go back in time),
  2. sitemaps (robots.txt `Sitemap:`, /sitemap.xml, `sitemaps`), filtered by lastmod / news dates,
  3. a paginated listing page (anchors + the dates printed next to them).
The methods are tried in that order and stop as soon as the date window is covered; each candidate remembers
the method that found it (triage.method).

Rules kept here: only staging.source_document is written (INSERT .. ON CONFLICT (url) DO NOTHING, so a re-run
resumes); robots.txt Disallow is honoured for every fetched path (own parser, wildcards supported); at most 2
requests in flight per host with a gap between them (backend.news._HostGate); a browser UA; bot walls
(Cloudflare / Imperva / DataDome challenges) and logins are NOT bypassed -- such sites are recorded as skipped.
Only items dated inside the window are kept (published_at from feed / article:published_time / JSON-LD /
<time> / URL; NULL only when the listing page itself shows the item between two in-window items).

    python -m backend.harvest_sites [--site DOMAIN] [--kind newsroom|gov|trade_press] [--prio P1|P2|P3|gov|trade]
                                    [--from 2026-01-17 --to 2026-10-17] [--max-per-site N] [--dry-run]
                                    [--probe] [--workers N]
    python -m backend.harvest_sites --selftest

Connection: env KSSL_STAGING_DSN (fallback KSSL_DSN, then the repo .env). Stdlib + psycopg2 only; body text
comes from prompts.render's text parser (which needs PyYAML, already a dependency of the prompt runner).
"""

from __future__ import annotations

import argparse
import collections
import gzip
import html as htmllib
import json
import os
import re
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit
from xml.etree import ElementTree

from backend import news
from backend.news import clean_url, is_homepage, page_blocked, parse_page, _MetaParser, _ld_objects
from backend.sources import classify, host_of

HARVESTER = "harvest_sites v1"
WINDOW = (date.today() - timedelta(days=274), date.today())      # rolling 9 months (a routine run passes a short --from)
BODY_CAP = 30_000
TRADE_CAP = 3000
DEFAULT_CAP = 6000
ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "db" / "excel_reports" / "harvest_sites_report.txt"


# ----------------------------------------------------------------------------- site list

@dataclass
class Site:
    domain: str                    # registrable-ish domain; tier "primary" for newsroom/gov uses it as company domain
    url: str                       # start URL (newsroom / news listing)
    kind: str                      # newsroom | gov | trade_press
    prio: str                      # P1 | P2 | P3 | gov | trade
    name: str = ""                 # publisher / company name
    walled: str = ""               # non-empty: skip with this reason (separate crawler farm)
    skip: str = ""                 # non-empty: skip with this reason (no newsroom etc.)
    non_competitor: bool = False   # company that is not one of the 50 competitors: harvest only
    feeds: tuple = ()              # explicit feed URLs
    multi_feed: bool = False       # read every explicit feed (category feeds), not only the first that works
    feed_pages: str = ""           # full-URL template with {off}/{n} for offset-style feed paging (Arc, Blogger)
    feed_page_size: int = 100
    sitemap_reverse: bool = False  # sitemap lists oldest first and has no dates: take its tail (newest) first
    early_stop: bool = False       # candidates are newest-first: stop after 60 consecutive out-of-window pages
    feed_paged: str = ""           # page-N suffix for feeds, e.g. "?paged={n}"  ("" = auto for WordPress)
    sitemaps: tuple = ()           # explicit sitemap URLs
    listing: tuple = ()            # listing URL templates, "{n}" = page number
    list_start: int = 1
    list_step: int = 1             # page-number increment ({n} = offset for offset-style paging)
    list_max: int = 60
    link_re: str = ""              # regex an article URL must match (listing / sitemap)
    exclude_re: str = ""
    methods: tuple = ("feed", "sitemap", "listing")
    external: bool = False         # listing links point to other sites (a press-coverage page)
    trust_lastmod: bool = False    # sitemap lastmod counts as the publication date when the page has none
    list_dates: bool = True        # False: the date printed next to listing links is not trusted; use the date in the URL
    date_pos: str = "auto"         # listing: where the date sits relative to the link: in | after | before | auto
    cap: int = 0                   # max stored; 0 = default (3000 trade press / 6000 others)
    api: str = ""                  # name of a site-specific puller in API_PULLERS
    cdomains: tuple = ()           # the company's real domains when they differ from `domain` (tier primary)
    url_fix: tuple = ()            # (regex, replacement) applied to every candidate URL
    notes: str = ""

    def __post_init__(self):
        if not self.name:
            self.name = self.domain


def S(domain, url, kind, prio, name="", **kw):
    return Site(domain, url, kind, prio, name or domain, **kw)


NC = dict(non_competitor=True)
WALL = "walled (bot challenge) - farm target"

SITES: list[Site] = [
    # ---- company newsrooms P1
    S("adanidefence.com", "https://www.adanidefence.com/", "newsroom", "P1", "Adani Defence & Aerospace", external=True,
      listing=("https://www.adanidefence.com/",), list_max=1, methods=("listing",),
      notes="newsroom = press-coverage tiles linking to third-party articles"),
    S("hanwhaaerospace.com", "https://www.hanwhaaerospace.com/eng/media/newsroom/list.do", "newsroom", "P1", "Hanwha Aerospace"),
    S("knds.com", "https://knds.com/en/newsroom", "newsroom", "P1", "KNDS"),
    S("larsentoubro.com", "https://www.larsentoubro.com/corporate/news-and-resources/", "newsroom", "P1", "Larsen & Toubro"),
    S("munitionsindia.in", "https://munitionsindia.in/", "newsroom", "P1", "Munitions India Limited"),
    S("nibe.in", "https://www.nibe.in/", "newsroom", "P1", "NIBE Limited", **NC),
    S("rheinmetall.com", "https://www.rheinmetall.com/en/media/news-watch", "newsroom", "P1", "Rheinmetall"),
    S("smpp.co.in", "https://www.smpp.co.in/", "newsroom", "P1", "SMPP", **NC),
    S("solargroup.com", "https://www.solargroup.com/media-center.php", "newsroom", "P1", "Solar Industries"),
    S("tataadvancedsystems.com", "https://www.tataadvancedsystems.com/media-centre/", "newsroom", "P1", "Tata Advanced Systems"),
    # ---- company newsrooms P2
    S("amgeneral.com", "https://www.amgeneral.com/news/", "newsroom", "P2", "AM General", **NC),
    S("aweil.gov.in", "https://aweil.gov.in/", "newsroom", "P2", "Advanced Weapons and Equipment India Ltd"),
    S("avinc.com", "https://www.avinc.com/resources/press-releases", "newsroom", "P2", "AeroVironment"),
    S("anduril.com", "https://www.anduril.com/newsroom/", "newsroom", "P2", "Anduril", walled=WALL),
    S("baesystems.com", "https://www.baesystems.com/en/our-company/newsroom", "newsroom", "P2", "BAE Systems",
      walled="walled (Imperva) - farm target"),
    S("bdl-india.in", "https://bdl-india.in/", "newsroom", "P2", "Bharat Dynamics"),
    S("bel-india.in", "https://www.bel-india.in/", "newsroom", "P2", "Bharat Electronics", **NC),
    S("elbitsystems.com", "https://elbitsystems.com/pr-new/", "newsroom", "P2", "Elbit Systems", walled=WALL),
    S("ga.com", "https://www.ga.com/news", "newsroom", "P2", "General Atomics", **NC),
    S("mahindradefence.com", "https://www.mahindradefence.com/news", "newsroom", "P2", "Mahindra Defence"),
    S("norincogroup.com.cn", "http://www.norincogroup.com.cn/", "newsroom", "P2", "NORINCO"),
    S("oshkoshdefense.com", "https://oshkoshdefense.com/news/", "newsroom", "P2", "Oshkosh Defense"),
    S("premierexplosives.com", "https://www.premierexplosives.com/", "newsroom", "P2", "Premier Explosives"),
    S("sncorp.com", "https://www.sncorp.com/press-releases/", "newsroom", "P2", "Sierra Nevada Corporation", **NC),
    S("yantraindia.co.in", "https://yantraindia.co.in/", "newsroom", "P2", "Yantra India", **NC),
    # ---- company newsrooms P3
    S("avnl.co.in", "https://avnl.co.in/", "newsroom", "P3", "Armoured Vehicles Nigam Limited", **NC),
    S("ashokleyland.com", "https://www.ashokleyland.com/in/en/media", "newsroom", "P3", "Ashok Leyland Defence", **NC),
    S("bemlindia.in", "https://www.bemlindia.in/", "newsroom", "P3", "BEML", **NC),
    S("gd.com", "https://www.gd.com/news", "newsroom", "P3", "General Dynamics"),
    S("hal-india.co.in", "https://hal-india.co.in/", "newsroom", "P3", "Hindustan Aeronautics", **NC),
    S("irrpl.in", "", "newsroom", "P3", "IRRPL", skip="no newsroom (per user list)", **NC),
    S("jcblgroup.com", "https://www.jcblgroup.com/", "newsroom", "P3", "JCBL", **NC),
    S("leonardo.com", "https://www.leonardo.com/en/press-release-list", "newsroom", "P3", "Leonardo"),
    S("news.lockheedmartin.com", "https://news.lockheedmartin.com/", "newsroom", "P3", "Lockheed Martin"),
    S("mku.com", "https://mku.com/media/", "newsroom", "P3", "MKU", **NC),
    S("rafael.co.il", "https://www.rafael.co.il/press/", "newsroom", "P3", "Rafael", walled=WALL),
    S("raphe.com", "https://www.raphe.com/", "newsroom", "P3", "Raphe mPhibr", **NC),
    S("walchand.com", "https://www.walchand.com/", "newsroom", "P3", "Walchandnagar Industries", **NC),
    S("zentechnologies.com", "https://www.zentechnologies.com/media.php", "newsroom", "P3", "Zen Technologies", **NC),
    # ---- government (tier 1)
    S("pib.gov.in", "https://www.pib.gov.in/allRel.aspx", "gov", "gov", "PIB - Ministry of Defence", api="pib"),
    S("mod.gov.in", "https://mod.gov.in/", "gov", "gov", "Ministry of Defence, India"),
    S("drdo.gov.in", "https://www.drdo.gov.in/", "gov", "gov", "DRDO"),
    S("ddpmod.gov.in", "https://ddpmod.gov.in/", "gov", "gov", "Department of Defence Production"),
    S("defense.gov", "https://www.defense.gov/News/Releases/", "gov", "gov", "US Department of Defense"),
    # ---- trade press
    S("janes.com", "https://www.janes.com/", "trade_press", "trade", "Janes"),
    S("defensenews.com", "https://www.defensenews.com/", "trade_press", "trade", "Defense News"),
    S("breakingdefense.com", "https://breakingdefense.com/", "trade_press", "trade", "Breaking Defense"),
    S("shephardmedia.com", "https://www.shephardmedia.com/", "trade_press", "trade", "Shephard Media"),
    # defenseworld.net removed 2026-10-18: commentary / aggregator (backend/sources.py BLOCKED); never a source
    S("twz.com", "https://www.twz.com/", "trade_press", "trade", "The War Zone"),
    # 19fortyfive.com removed 2026-10-18: commentary / aggregator (backend/sources.py BLOCKED); never a source
    S("insidedefense.com", "https://insidedefense.com/", "trade_press", "trade", "Inside Defense"),
    S("flightglobal.com", "https://www.flightglobal.com/", "trade_press", "trade", "Flight Global"),
    S("rusi.org", "https://www.rusi.org/", "trade_press", "trade", "RUSI"),
    S("israeldefense.co.il", "https://www.israeldefense.co.il/en", "trade_press", "trade", "Israel Defense"),
    S("thedefensepost.com", "https://thedefensepost.com/", "trade_press", "trade", "The Defense Post"),
    S("armyrecognition.com", "https://www.armyrecognition.com/", "trade_press", "trade", "Army Recognition"),
    S("asianmilitaryreview.com", "https://asianmilitaryreview.com/", "trade_press", "trade", "Asian Military Review"),
    S("oryxspioenkop.com", "https://www.oryxspioenkop.com/", "trade_press", "trade", "Oryx"),
    S("dvidshub.net", "https://www.dvidshub.net/", "trade_press", "trade", "DVIDS"),
    S("air-cosmos.latribune.fr", "https://air-cosmos.latribune.fr/", "trade_press", "trade", "Air & Cosmos"),
    # vpk.name removed 2026-10-18: commentary / aggregator (backend/sources.py BLOCKED); never a source
    S("raksha-anirveda.com", "https://raksha-anirveda.com/", "trade_press", "trade", "Raksha Anirveda"),
    # indiandefensenews.in removed 2026-10-18: a Blogger blog (backend/sources.py BLOCKED["blog"]); blogs are never sources
]


HTTP_ONLY = ("norincogroup.com.cn",)      # clean_url upgrades http->https; these hosts only answer on http (https = connection error)


def clean(url: str) -> str:
    """backend.news.clean_url, except that http-only hosts keep their http scheme."""
    new = clean_url(url)
    if url.lower().startswith("http://") and new.startswith("https://") and host_of(new).endswith(HTTP_ONLY):
        new = "http://" + new[len("https://"):]
    return new


def apply_overrides(sites):
    """Per-site recipes found by reconnaissance (see RECIPES at the bottom of the file)."""
    by = {s.domain: s for s in sites}
    for dom, kw in RECIPES.items():
        s = by.get(dom)
        if s is not None:
            for k, v in kw.items():
                setattr(s, k, v)
    return sites


_NW = ("&appid=1&webid=1&path=/&columnid={col}&unitid={unit}&webname=%25E4%25B8%25AD%25E5%259B%25BD%25E5%2585%25B5%25E5%2599%25A8"
       "%25E5%25B7%25A5%25E4%25B8%259A%25E9%259B%2586%25E5%259B%25A2%25E6%259C%2589%25E9%2599%2590%25E5%2585%25AC%25E5%258F%25B8&permissiontype=0")
NORINCO_LISTING = tuple("http://www.norincogroup.com.cn/module/web/jpage/dataproxy.jsp?page={n}" + _NW.format(col=c, unit=u).replace("{", "{{")
                        for c, u in ((84, 2104), (85, 2104)))

RECIPES: dict[str, dict] = {
    "rheinmetall.com": dict(methods=("sitemap",), sitemaps=("https://www.rheinmetall.com/sitemap.site_1.xml",),
                            link_re=r"/en/media/news-watch/(news|press)[^/]*/20\d\d/"),
    "hanwhaaerospace.com": dict(listing=("https://www.hanwhaaerospace.com/eng/media/newsroom/list.do?pageNum={n}",),
                                link_re=r"newsroom/view\.do\?seq=", methods=("listing",), date_pos="after"),
    "solargroup.com": dict(methods=("api",), api="solar", external=True),
    # knds.com: article pages carry no date; the press-release listing's embedded data does (first 9 cards; "Load more" is JS-only)
    "knds.com": dict(listing=("https://knds.com/en/press-releases",),
                     link_re=r"knds\.com/(en/(press-releases|news)|de/pressemitteilungen)/[a-z0-9-]{8,}"),
    "munitionsindia.in": dict(skip="news page holds 2 undated PDF clippings (older than the window); WP feed is empty"),
    "rheinmetall.com": dict(link_re=r"/en/media/news-watch/news/20\d\d/", exclude_re=r"\.pdf", methods=("sitemap",)),
    "larsentoubro.com": dict(link_re=r"/pressreleases/2026/|/news-stories/[^/]+"),
    "pib.gov.in": dict(methods=("api",)),
    "ddpmod.gov.in": dict(methods=("api",), api="ddp"),
    "defense.gov": dict(feeds=("https://www.war.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=9&Site=945&max=500",),
                        methods=("feed",), notes="defense.gov redirects to war.gov"),
    "drdo.gov.in": dict(methods=("listing",), list_max=1, date_pos="after",
                        listing=("https://drdo.gov.in/drdo/en/what-is-news", "https://drdo.gov.in/drdo/en/whats-news-archive",
                                 "https://drdo.gov.in/drdo/en/"),
                        link_re=r"drdo\.gov\.in/(drdo/)?en/(announcement|documents/(drdo-in-news|publications/drdo-newsletter))/",
                        url_fix=(r"^https?://drdo\.gov\.in/en/", "https://drdo.gov.in/drdo/en/")),
    "mod.gov.in": dict(skip="Next.js SPA: press-release page is client-rendered, WordPress REST content types return nothing, "
                            "sitemap = 6 undated pages; MoD releases are covered through pib.gov.in"),
    "aweil.gov.in": dict(skip="listed domain aweil.gov.in does not resolve; aweil.in has only recruitment/RTI/events pages (no newsroom items)"),
    "mahindradefence.com": dict(skip="domain does not resolve (DNS SERVFAIL on 8.8.8.8 and system resolver)"),
    "premierexplosives.com": dict(skip="listed domain does not resolve; the company site pelgel.com has no news/media section"),
    "yantraindia.co.in": dict(methods=("listing",), listing=("https://yantraindia.co.in/en/media-view",), list_max=1,
                              link_re=r"/upload/media/[^/]*release\.(jpg|jpeg|png|pdf)$", date_pos="in",
                              notes="media releases are images with a dated caption"),
    "sncorp.com": dict(methods=("sitemap",), link_re=r"/news-archive/[^/]+$"),
    "bel-india.in": dict(methods=("listing",), listing=("https://bel-india.in/news/",), list_max=1, link_re=r"/news-bel/",
                         date_pos="after", notes="news page shows the latest 12 items; older ones sit behind a JS pager (partial coverage)"),
    "ga.com": dict(methods=("listing",), listing=("https://www.ga.com/press-releases-by-year.php?year=2026",), list_max=1,
                   link_re=r"^https://www\.ga\.com/[a-z0-9]+(-[a-z0-9]+){4,}/?$", date_pos="after"),
    "norincogroup.com.cn": dict(methods=("listing",), list_dates=False, link_re=r"/art/20\d\d/", list_start=1, list_max=6,
                                listing=NORINCO_LISTING),
    "bdl-india.in": dict(methods=("listing",), listing=("https://bdl-india.in/media-releases",), list_max=1,
                         link_re=r"^https://bdl-india\.in/[a-z0-9]+(-[a-z0-9]+){2,}$"),
    "avnl.co.in": dict(methods=("listing",), listing=("https://avnl.co.in/news", "https://avnl.co.in/events"), list_max=40,
                       link_re=r"^https://avnl\.co\.in/(news|events)/[a-z0-9-]{12,}$"),
    "mku.com": dict(methods=("listing",), list_max=40,
                    listing=("https://www.mku.com/en-gb/news-and-announcements", "https://www.mku.com/en-gb/news-event"),
                    link_re=r"/en-gb/news-event/[^/]+$"),
    "ashokleyland.com": dict(methods=("listing",), listing=("https://www.ashokleyland.com/in/newsroom",), list_max=40,
                             link_re=r"/in/(pressrelease|newsroom)/[^/]+"),
    "walchand.com": dict(skip="media page = a WILPOWER newsletter PDF page and investor announcements; no dated news items"),
    "news.lockheedmartin.com": dict(methods=("listing",), list_dates=False, list_start=0, list_step=100, list_max=20,
                                    listing=("https://news.lockheedmartin.com/news-releases?l=100&o={n}",),
                                    link_re=r"^https://news\.lockheedmartin\.com/20\d\d-\d\d-\d\d-"),
    "hal-india.co.in": dict(skip="site is JavaScript-only ('Please enable JavaScript'); no server-rendered content or feed"),
    "janes.com": dict(skip="robots.txt: 'User-agent: * / Disallow: /' (only Googlebot etc. may crawl) - respected, not fetched"),
    "insidedefense.com": dict(skip="robots.txt: 'User-agent: * / Disallow: /' with Crawl-delay 10 - respected, not fetched"),
    "defensenews.com": dict(methods=("feed",), feeds=("%s" % "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml&size=100&from=0",),
                            feed_pages="https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml&size=100&from={off}"),
    "breakingdefense.com": dict(walled="403 Forbidden (nginx WAF) on every page; the feed answers only intermittently with the 15 latest - farm target"),
    "shephardmedia.com": dict(methods=("sitemap",), early_stop=False,
                              sitemaps=tuple("https://www.shephardmedia.com/sitemap-news.xml" + ("" if n == 1 else f"?p={n}") for n in range(1, 6))),
    "rusi.org": dict(methods=("feed",), multi_feed=True,
                     feeds=("https://www.rusi.org/rss/latest-commentary.xml", "https://www.rusi.org/rss/latest-publications.xml",
                            "https://www.rusi.org/rss/whats-new.xml"),
                     notes="only the RSS feeds are used (20-60 latest items each); the sitemap is undated and its pages carry "
                           "no machine-readable date (a 3,500-page trial yielded 18 dated items)"),
    "dvidshub.net": dict(skip="robots.txt answers 502 Bad Gateway on every attempt; treated as disallow-all (RFC 9309) - retry later / farm "
                              "(RSS /rss/news and sitemap-news*.xml are otherwise public)"),
    "oryxspioenkop.com": dict(methods=("sitemap",), sitemaps=("https://www.oryxspioenkop.com/sitemap.xml",), link_re=r"/20\d\d/\d\d/"),
    "israeldefense.co.il": dict(methods=("listing",), listing=("https://www.israeldefense.co.il/en/latest-articles?page={n}",),
                                list_start=0, list_max=200, link_re=r"/en/node/\d+$", early_stop=True),
    "armyrecognition.com": dict(methods=("sitemap",), link_re=r"armyrecognition\.com/news/[a-z-]+/20\d\d/", sitemaps=("https://www.armyrecognition.com/sitemap.xml",)),
    "twz.com": dict(methods=("feed", "sitemap"), feeds=("https://www.twz.com/feed",),
                    link_re=r"^https://www\.twz\.com/[a-z0-9-]+/[a-z0-9-]{12,}$", early_stop=False),
    "thedefensepost.com": dict(methods=("sitemap",), link_re=r"^https://thedefensepost\.com/20\d\d/\d\d/\d\d/[a-z0-9-]+/?$"),
    "asianmilitaryreview.com": dict(methods=("feed",), feeds=("https://www.asianmilitaryreview.com/feed/",), feed_paged="?paged={n}"),
    "raksha-anirveda.com": dict(methods=("sitemap",), exclude_re=r"/(category|tag|author|product|shop|page)/"),
    "nibe.in": dict(walled="Cloudflare challenge ('Just a moment...') on every URL - farm target"),
    "smpp.co.in": dict(skip="TLS certificate does not verify (self-signed chain); not bypassed - farm/manual target"),
    "tataadvancedsystems.com": dict(skip="media-centre redirects to /public/media-centre which is 404; no news pages in sitemap/home"),
}


# ----------------------------------------------------------------------------- dates

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_ISO = re.compile(r"(?<!\d)(20\d{2})[-/.][ ]?(\d{1,2})[-/.][ ]?(\d{1,2})(?!\d)")
_DMY_TXT = re.compile(r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)?[\s\-,./]*" + _MON + r"[\s\-,./]*(20\d{2})(?!\d)", re.I)
_MDY_TXT = re.compile(r"(?<![a-z])" + _MON + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(20\d{2})(?!\d)", re.I)
_DMY_NUM = re.compile(r"(?<![\d.])(\d{1,2})[/.\-](\d{1,2})[/.\-](20\d{2})(?!\d)")


def _mk(y, m, d):
    try:
        v = date(int(y), int(m), int(d))
    except ValueError:
        return None
    return v if 2000 <= v.year <= 2035 else None


def find_date(text: str):
    """The first calendar date found in free text (earliest position wins), or None. Numeric d/m/y is day-first."""
    if not text:
        return None
    best = None
    for rx, conv in (
        (_ISO, lambda m: _mk(m[1], m[2], m[3])),
        (_DMY_TXT, lambda m: _mk(m[3], MONTHS[m[2][:3].lower()], m[1])),
        (_MDY_TXT, lambda m: _mk(m[3], MONTHS[m[1][:3].lower()], m[2])),
        (_DMY_NUM, lambda m: _mk(m[3], m[2], m[1]) or _mk(m[3], m[1], m[2])),
    ):
        for m in rx.finditer(text):
            v = conv(m)
            if v and (best is None or m.start() < best[0]):
                best = (m.start(), v)
                break
    return best[1] if best else None


def parse_date(s: str):
    """A machine date string (ISO, RFC 822, or a printed date) -> date, or None."""
    s = (s or "").strip()
    if not s:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return _mk(s[:4], s[5:7], s[8:10])
    try:
        return parsedate_to_datetime(s).date()
    except (TypeError, ValueError, IndexError):
        pass
    return find_date(s)


_URL_DATES = (
    re.compile(r"/(20\d{2})/(\d{1,2})/(\d{1,2})(?:/|$|-)"),
    re.compile(r"/(20\d{2})-(\d{2})-(\d{2})(?:/|$|-)"),
    re.compile(r"[-_/](20\d{2})(\d{2})(\d{2})(?:[-_/.]|$)"),
)
_URL_YMONTXT = re.compile(r"/(20\d{2})/" + _MON + r"/(\d{1,2})(?:/|$)", re.I)


def url_date(url: str):
    path = urlsplit(url).path
    m = _URL_YMONTXT.search(path)
    if m:
        return _mk(m[1], MONTHS[m[2][:3].lower()], m[3])
    for rx in _URL_DATES:
        m = rx.search(path)
        if m:
            v = _mk(m[1], m[2], m[3])
            if v:
                return v
    return None


def in_window(d, win) -> bool:
    return d is not None and win[0] <= d <= win[1]


# ----------------------------------------------------------------------------- feeds / sitemaps / robots

def _ln(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def parse_feed(body: bytes) -> list[dict]:
    """RSS 2.0 / RSS 1.0 / Atom -> [{title, link, date, summary}] (feed order)."""
    body = body.lstrip(b"\xef\xbb\xbf \r\n\t")
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return []
    out = []
    for it in root.iter():
        if _ln(it.tag) not in ("item", "entry"):
            continue
        d = {"title": "", "link": "", "date": None, "summary": "", "content": ""}
        dates = {}
        for c in it:
            n = _ln(c.tag)
            txt = (c.text or "").strip()
            if n == "title":
                d["title"] = htmllib.unescape(txt)
            elif n == "link":
                href = c.get("href")
                if href:
                    if c.get("rel", "alternate") == "alternate" or not d["link"]:
                        d["link"] = href.strip()
                elif txt and not d["link"]:
                    d["link"] = txt
            elif n == "guid" and not d["link"] and txt.startswith("http") and c.get("ispermalink", "true") != "false":
                d["link"] = txt
            elif n in ("pubdate", "published", "date", "issued", "created"):
                dates.setdefault("pub", txt)
            elif n in ("updated", "modified"):
                dates.setdefault("upd", txt)
            elif n in ("description", "summary"):
                d["summary"] = txt
            elif n in ("encoded", "content"):
                d["content"] = txt
        d["date"] = parse_date(dates.get("pub") or dates.get("upd") or "")
        if d["link"]:
            out.append(d)
    return out


def feed_looks_wordpress(body: bytes) -> bool:
    return b"wordpress.org" in body[:3000].lower() or b"/wp-content/" in body[:20000]


def parse_sitemap(body: bytes):
    """-> ("index"|"urlset", [{loc, lastmod(date|None), pubdate(date|None), title}])"""
    if body[:2] == b"\x1f\x8b":
        try:
            body = gzip.decompress(body)
        except OSError:
            return "", []
    body = body.lstrip(b"\xef\xbb\xbf \r\n\t")
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return "", []
    kind = "index" if _ln(root.tag) == "sitemapindex" else "urlset"
    out = []
    for e in root:
        if _ln(e.tag) not in ("url", "sitemap"):
            continue
        row = {"loc": "", "lastmod": None, "pubdate": None, "title": ""}
        for c in e.iter():
            n = _ln(c.tag)
            txt = (c.text or "").strip()
            if n == "loc" and not row["loc"]:
                row["loc"] = txt
            elif n == "lastmod":
                row["lastmod"] = parse_date(txt)
            elif n == "publication_date":
                row["pubdate"] = parse_date(txt)
            elif n == "title" and txt:
                row["title"] = txt
        if row["loc"]:
            out.append(row)
    return kind, out


class Robots:
    """robots.txt rules for the `*` group (longest match wins, Allow wins ties, * and $ supported).
    Status policy (RFC 9309): 4xx -> everything allowed; 5xx / network error -> everything disallowed."""

    def __init__(self, text: str = "", allow_all=True):
        self.allow_all = allow_all
        self.rules: list[tuple[bool, re.Pattern, int]] = []
        self.sitemaps: list[str] = []
        self.crawl_delay = 0.0
        if text:
            self._parse(text)

    def _parse(self, text):
        groups, agents, rules, in_rules = [], [], [], False
        delay = {}
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            k, v = (x.strip() for x in line.split(":", 1))
            k = k.lower()
            if k == "user-agent":
                if in_rules:
                    groups.append((agents, rules, delay))
                    agents, rules, delay, in_rules = [], [], {}, False
                agents.append(v.lower())
            elif k in ("allow", "disallow"):
                in_rules = True
                if v:
                    rules.append((k == "allow", v))
            elif k == "crawl-delay":
                in_rules = True
                try:
                    delay["d"] = float(v)
                except ValueError:
                    pass
            elif k == "sitemap" and v.startswith("http"):
                self.sitemaps.append(v)
        groups.append((agents, rules, delay))
        star = [g for g in groups if "*" in g[0]]
        pick = star[0] if star else None
        if pick:
            for allow, pat in pick[1]:
                rx = re.escape(pat).replace(r"\*", ".*")
                if rx.endswith(r"\$"):
                    rx = rx[:-2] + "$"
                try:
                    self.rules.append((allow, re.compile(rx), len(pat)))
                except re.error:
                    pass
            self.crawl_delay = pick[2].get("d", 0.0)

    def allowed(self, url: str) -> bool:
        if not self.allow_all:
            return False
        p = urlsplit(url)
        path = (p.path or "/") + (("?" + p.query) if p.query else "")
        best = None
        for allow, rx, ln in self.rules:
            if rx.match(path) and (best is None or ln > best[1] or (ln == best[1] and allow)):
                best = (allow, ln)
        return True if best is None else best[0]


# ----------------------------------------------------------------------------- listing pages

_A_RE = re.compile(r"""<a\s[^>]*?href\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>"']+))[^>]*>(.*?)</a\s*>""", re.S | re.I)
_TAG_RE = re.compile(r"<(script|style)\b.*?</\1\s*>|<[^>]+>", re.S | re.I)


def _plain(fragment: str) -> str:
    return " ".join(htmllib.unescape(_TAG_RE.sub(" ", fragment)).split())


NOT_ARTICLE = re.compile(
    r"(/(tag|tags|category|categories|author|authors|page|feed|search|login|wp-content|wp-json|cdn-cgi|contact|about|"
    r"careers?|privacy|terms|cookie|sitemap|subscribe|newsletter|events?-calendar)(/|$)|"
    r"\.(jpe?g|png|gif|svg|webp|css|js|ico|zip|mp4|mp3|xml)(\?|$)|^(mailto|tel|javascript):)", re.I)


def extract_listing(page_html: str, base: str, link_re: str = "", exclude_re: str = "", same_host=True,
                    date_pos="auto") -> list[dict]:
    """Article-looking anchors of a listing page, in page order -> [{url, title, date, pos}].
    The date is the first date printed in the anchor text, else (date_pos) in the text right after / before it."""
    host = host_of(base)
    lre = re.compile(link_re, re.I) if link_re else None
    xre = re.compile(exclude_re, re.I) if exclude_re else None
    raw = []
    for m in _A_RE.finditer(page_html):
        href = htmllib.unescape(m.group(1) or m.group(2) or m.group(3) or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")) or (not lre and NOT_ARTICLE.search(href)):
            continue
        url = urljoin(base, href)
        if urlsplit(url).scheme not in ("http", "https"):
            continue
        if same_host and host_of(url) != host:
            continue
        if lre and not lre.search(url):
            continue
        if xre and xre.search(url):
            continue
        if not lre and not _looks_like_article(url, base):
            continue
        raw.append((url, _plain(m.group(4)), m.start(), m.end()))
    by_url: dict[str, dict] = {}
    for i, (url, text, s, e) in enumerate(raw):
        nxt = raw[i + 1][2] if i + 1 < len(raw) else min(len(page_html), e + 600)
        prv = raw[i - 1][3] if i else max(0, s - 600)
        after = _plain(page_html[e:min(nxt, e + 600)])
        before = _plain(page_html[max(prv, s - 600):s])
        d = find_date(text)
        if d is None:
            order = {"after": (after, before), "before": (before, after), "in": (), "auto": (after, before)}[date_pos]
            for frag in order:
                d = find_date(frag)
                if d:
                    break
        key = clean(url)
        cur = by_url.get(key)
        if cur is None:
            by_url[key] = {"url": key, "title": text, "date": d, "pos": len(by_url)}
        else:
            if len(text) > len(cur["title"]):
                cur["title"] = text
            cur["date"] = cur["date"] or d
    return list(by_url.values())


def _looks_like_article(url: str, base: str) -> bool:
    p = urlsplit(url)
    segs = [x for x in p.path.split("/") if x]
    if not segs or url_eq(url, base) or is_homepage(url):
        return False
    last = segs[-1]
    if re.search(r"[?&](p|id|newsid|nid|prid|article|post|seq|no|idx|num|uid|key|nttid|bbsid)=\d+", p.query, re.I):
        return True
    if len(segs) >= 2 and ("-" in last or last.count(".") == 1 and last.endswith((".html", ".htm", ".php", ".aspx"))) and len(last) >= 14:
        return True
    return len(last) >= 28 and "-" in last


def url_eq(a: str, b: str) -> bool:
    return urlsplit(a)._replace(query="", fragment="").geturl().rstrip("/") == urlsplit(b)._replace(query="", fragment="").geturl().rstrip("/")


# ----------------------------------------------------------------------------- article pages

class _Body:
    _cls = None

    @classmethod
    def parser(cls):
        if cls._cls is None:
            from prompts.render import _TextParser

            class P(_TextParser):          # <main> counts like <article>; <form> is not skipped (ASP.NET wraps the page in one)
                def handle_starttag(self, tag, attrs):
                    if tag != "form":
                        super().handle_starttag("article" if tag == "main" else tag, attrs)

                def handle_endtag(self, tag):
                    if tag != "form":
                        super().handle_endtag("article" if tag == "main" else tag)
            cls._cls = P
        return cls._cls


BOILER = re.compile(r"^(skip to (main )?content|accept (all )?cookies|we use cookies|this (web)?site uses cookies|"
                    r"share (this|on)|follow us|subscribe to|sign up for|related (articles|posts|news)|read more\b|"
                    r"copyright|all rights reserved|privacy policy)", re.I)


def extract_body(page_html: str) -> str:
    from prompts.render import _good_blocks
    p = _Body.parser()()
    try:
        p.feed(page_html)
        p.close()
    except Exception:
        pass
    art, allb = _good_blocks(p.art), _good_blocks(p.all)
    blocks = art if sum(map(len, art)) >= 400 else allb
    blocks = [b for b in blocks if not BOILER.match(b)]
    text = "\n".join(blocks)
    if len(text) < 400:                 # script-rendered pages sometimes carry the text in JSON-LD
        m = _MetaParser()
        try:
            m.feed(page_html)
        except Exception:
            pass
        for o in _ld_objects(m.ld):
            b = o.get("articleBody")
            if isinstance(b, str) and len(b) > len(text):
                text = htmllib.unescape(b)
    return text[:BODY_CAP]


_TIME_RE = re.compile(r"""<time\b[^>]*?datetime\s*=\s*["']([^"']+)["']""", re.I)
_DATE_CLASS_RE = re.compile(r"""<(\w+)\b[^>]*\b(?:class|itemprop)\s*=\s*["']([^"']*)["'][^>]*>\s*([^<]{4,60}?)\s*</\1>""", re.I)
_DATE_LABEL_RE = re.compile(r">\s*(?:date|published(?:\s+on)?|posted(?:\s+on)?|release\s+date)\s*:\s*(?:</\w+>)?\s*([^<]{4,40}?)\s*<", re.I)
_DATE_CLASS_NAME = re.compile(r"\b(date|publish\w*|posted|pubdate|datepublished)\b", re.I)
_DATE_META = {"article:published_time", "og:published_time", "datepublished", "pubdate", "publishdate", "publish-date",
              "date", "dc.date", "dc.date.issued", "dcterms.date", "dcterms.created", "sailthru.date", "parsely-pub-date",
              "cxenseparse:recs:publishtime", "article.published", "release_date", "datecreated"}
_LANG_RE = re.compile(r"<html[^>]*?\blang\s*=\s*[\"']?([A-Za-z]{2})", re.I)


@dataclass
class Page:
    canonical: str
    title: str
    date: date | None
    date_src: str
    body: str
    lang: str | None
    site_name: str


def read_page(page_html: str, final_url: str) -> Page:
    info = parse_page(page_html, final_url)
    m = _MetaParser()
    try:
        m.feed(page_html)
    except Exception:
        pass
    d, src = None, ""
    cands = [("meta", v) for k, v in m.meta if k in _DATE_META]
    cands.append(("ld/meta", info.published))
    for o in _ld_objects(m.ld):
        for key in ("datePublished", "dateCreated", "uploadDate"):
            if isinstance(o.get(key), str):
                cands.append(("ld", o[key]))
    cands += [("time", v) for v in _TIME_RE.findall(page_html[:400_000])[:3]]
    # an element whose class / itemprop names a date (hanwha.com: <span class="date">August 19, 2026</span>), never a
    # modified / updated one. A CMS page-data "publishedAt" is NOT read: on knds.com it is the site settings' date.
    cands += [("class", t) for _, n, t in _DATE_CLASS_RE.findall(page_html[:400_000])
              if _DATE_CLASS_NAME.search(n) and not re.search(r"modif|updat", n, re.I)][:3]
    # a labelled date (brahmos.com: <b>Date:</b> 27 Apr, 2022)
    cands += [("label", v) for v in _DATE_LABEL_RE.findall(page_html[:400_000])[:2]]
    for s, v in cands:
        d = parse_date(v)
        if d and s in ("time", "class", "label") and d >= date.today() - timedelta(days=1):
            d = None                          # today in a bare <time> / date-classed element / "Date:" label is a header clock, not the publication date
        if d:
            src = s
            break
    if d is None:
        d = url_date(final_url)
        src = "url" if d else ""
    body = extract_body(page_html)
    if d is None:
        d = find_date(body[:700])
        src = "text" if d else ""
    if d is None and info.title:                 # a printed byline date right after the headline ("Author 16 October 2026")
        plain_all = _plain(page_html[:600_000])
        k = plain_all.find(info.title.split("|")[0].strip()[:40])
        if k >= 0:
            d = find_date(plain_all[k:k + 350])
            src = "text" if d else ""
    lm = _LANG_RE.search(page_html[:3000])
    return Page(info.canonical, info.title or "", d, src, body, lm.group(1).lower() if lm else None, info.site_name or "")


# ----------------------------------------------------------------------------- context: HTTP, robots, DB

class Ctx:
    def __init__(self, win, dry_run, log=print, conn_factory=None, workers=2):
        self.win, self.dry, self.log = win, dry_run, log
        self.robots: dict[str, Robots] = {}
        self.lock = threading.Lock()
        self.conn_factory = conn_factory
        self.db_lock = threading.Lock()
        self.conn = None
        self.known: set[str] = set()
        self.delay_locks: dict[str, list] = {}
        self.net_fail: dict[str, list] = {}           # host -> [network failures, answered requests]
        self.workers = workers

    # --- http
    def get(self, url, *, check_robots=True, max_bytes=news.MAX_PAGE_BYTES, headers=None, timeout=25):
        """-> (Resp|None, reason). reason non-empty = not fetched / not usable."""
        host = host_of(url)
        with self.lock:
            bad = self.net_fail.get(host, [0, 0])
        if bad[0] >= 6 and bad[1] == 0:
            return None, "host unreachable (timeouts / connection errors; circuit open)"
        rb = self.robots_for(url)
        if check_robots and not rb.allowed(url):
            return None, "robots.txt disallows"
        if rb.crawl_delay > 0.5:                      # honour Crawl-delay (capped at 12 s)
            with self.lock:
                lk = self.delay_locks.setdefault(host, [threading.Lock(), 0.0])
            with lk[0]:
                wait = lk[1] + min(rb.crawl_delay, 12.0) - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                lk[1] = time.monotonic()
        r = news.http(url, timeout=timeout, max_bytes=max_bytes, headers=headers)
        with self.lock:
            f = self.net_fail.setdefault(host, [0, 0])
            f[0 if r.status == 0 else 1] += 1
        if r.status == 0 or r.status >= 500:
            time.sleep(1.5)
            r = news.http(url, timeout=timeout, max_bytes=max_bytes, headers=headers)
        if r.status == 429:
            time.sleep(8)
            r = news.http(url, timeout=timeout, max_bytes=max_bytes, headers=headers)
        why = page_blocked(r) if r.status != 200 else ""
        if r.status == 200:
            why = page_blocked(r)
            ct = r.headers.get("content-type", "").lower()
            if not why and r.body[:2000].lstrip()[:1] == b"<" and (b"cf-chl" in r.body[:30000] or b"_Incapsula_" in r.body[:30000]):
                why = "bot wall"
            _ = ct
        elif r.status:
            why = f"http {r.status}"
        else:
            why = "network error: " + r.body[:80].decode("utf-8", "replace")
        return (r if r.status == 200 and not why else None), why

    def robots_for(self, url) -> Robots:
        p = urlsplit(url)
        key = f"{p.scheme}://{p.netloc}"
        with self.lock:
            rb = self.robots.get(key)
        if rb is not None:
            return rb
        r = news.http(key + "/robots.txt", timeout=15, max_bytes=500_000)
        for _ in range(3):
            if r.status < 500 and r.status != 0:
                break
            time.sleep(3)
            r = news.http(key + "/robots.txt", timeout=15, max_bytes=500_000)
        if r.status == 200 and b"<html" not in r.body[:500].lower():
            rb = Robots(r.text())
        elif 400 <= r.status < 500:
            rb = Robots()
        else:
            rb = Robots(allow_all=False) if r.status >= 500 else Robots()
            if r.status == 0:
                rb = Robots()          # unreachable robots.txt on an otherwise reachable host: the page fetch decides
        with self.lock:
            self.robots[key] = rb
        return rb

    # --- db
    def connect(self):
        if self.dry:
            return
        import psycopg2
        dsn = (os.getenv("KSSL_STAGING_DSN") or os.getenv("KSSL_DSN") or "").strip()
        if not dsn:
            for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
                m = re.match(r"\s*KSSL_STAGING_DSN\s*=\s*(.*)", line)
                if m:
                    dsn = m.group(1).strip().strip("\"'")
        if not dsn:
            raise RuntimeError("KSSL_STAGING_DSN (or KSSL_DSN) is not set")
        self.conn = psycopg2.connect(dsn, connect_timeout=8)
        self.conn.autocommit = True
        with self.conn.cursor() as cur:
            cur.execute("SELECT url, triage->>'listed_as' FROM staging.source_document")
            for u, la in cur.fetchall():
                self.known.add(u)
                if la:
                    self.known.add(la)

    def store(self, row: dict) -> bool:
        """INSERT .. ON CONFLICT DO NOTHING -> True when a new row was written."""
        if self.dry:
            return True
        with self.db_lock:
            with self.conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO staging.source_document (doc_id, url, source_kind, source_name, source_tier, feed_url, "
                    "title, published_at, language, body_text, triage, status) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'new') ON CONFLICT DO NOTHING",
                    (row["doc_id"], row["url"], row["source_kind"], row["source_name"], row["source_tier"], row["feed_url"],
                     row["title"], row["published_at"], row["language"], row["body_text"], json.dumps(row["triage"])))
                ok = cur.rowcount > 0
            if ok:
                self.known.add(row["url"])
            return ok

    def close(self):
        if self.conn:
            self.conn.close()


# ----------------------------------------------------------------------------- discovery

@dataclass
class Cand:
    url: str
    title: str = ""
    date: date | None = None
    reliable: bool = False           # date is a publication date (feed / listing), not a sitemap lastmod
    method: str = ""
    feed_url: str = ""
    inferred: bool = False
    extra: dict = field(default_factory=dict)


@dataclass
class Stats:
    site: Site
    methods: list = field(default_factory=list)
    found: int = 0
    in_window: int = 0
    stored: int = 0
    already: int = 0
    skipped: collections.Counter = field(default_factory=collections.Counter)
    dates: list = field(default_factory=list)
    status: str = ""                 # ok | skipped | failed
    note: str = ""
    larger_than_cap: int = 0
    consec_out: int = 0
    secs: float = 0.0

    def skip(self, why, n=1):
        self.skipped[why] += n


NEWSY = re.compile(r"news|press|media|release|article|stor(y|ies)|blog|update|announce|insight|statement|/20\d\d", re.I)
SM_BAD = re.compile(r"(tag|categor|author|page|image|video|attachment|product|taxonom|user|event|dossier|company|shows?)s?[-_.]", re.I)
SM_GOOD = re.compile(r"^(posts?-sitemap|news|articles?|sitemap-news|sitemap_news|sitemap-index-articles|story|stories)", re.I)


def host_base(url):
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}"


def discover(site: Site, ctx: Ctx, st: Stats) -> list[Cand]:
    """Run the methods in order; stop when the window start is covered by dated candidates."""
    win = ctx.win
    cands: dict[str, Cand] = {}
    covered = False

    def add(c: Cand):
        c.url = clean(quote(c.url.strip(), safe="/%:@?&=+,;~#[]!$'()*-._"))
        if site.url_fix:
            c.url = re.sub(site.url_fix[0], site.url_fix[1], c.url)
        if not c.url.startswith("http") or (is_homepage(c.url) and not urlsplit(c.url).query):
            return
        old = cands.get(c.url)
        if old is None or (c.reliable and not old.reliable):
            cands[c.url] = c

    def oldest():
        ds = [c.date for c in cands.values() if c.date and c.reliable]
        return min(ds) if ds else None

    for method in site.methods:
        if covered:
            break
        n0 = len(cands)
        try:
            if method == "api":
                for c in API_PULLERS[site.api](site, ctx, st):
                    add(c)
            elif method == "feed":
                feeds_run(site, ctx, st, add)
            elif method == "sitemap":
                sitemaps_run(site, ctx, st, add)
            elif method == "listing":
                listing_run(site, ctx, st, add)
        except Exception as e:  # noqa: BLE001
            st.note += f" [{method} error {type(e).__name__}: {str(e)[:80]}]"
        if len(cands) > n0:
            st.methods.append(method)
        o = oldest()
        if o is not None and o <= win[0]:
            covered = True
    return list(cands.values())


def feeds_run(site: Site, ctx: Ctx, st: Stats, add):
    base = host_base(site.url)
    urls = list(site.feeds)
    if not urls:
        r, why = ctx.get(site.url, max_bytes=800_000)
        if r is not None:
            m = _MetaParser()
            try:
                m.feed(r.text())
            except Exception:
                pass
            for rel, h in m.links:
                hl = h.lower()
                if "alternate" in rel and any(x in hl for x in ("rss", "feed", "atom", ".xml")) and "oembed" not in hl \
                        and "comments" not in hl:
                    urls.append(urljoin(r.url, h))
        for pth in ("/feed", "/feed/", "/rss", "/rss.xml", "/feed.xml", "/atom.xml", "/news/rss", "/news/feed",
                    "/?feed=rss2", "/news/rss.xml", "/en/rss.xml"):
            urls.append(base + pth)
    seen_feed = set()
    for fu in dict.fromkeys(urls):
        r, why = ctx.get(fu, max_bytes=5_000_000, headers={"Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml,*/*;q=0.5"})
        if r is None:
            continue
        items = parse_feed(r.body)
        if not items:
            continue
        sig = tuple(i["link"] for i in items[:3])
        if sig in seen_feed:
            continue
        seen_feed.add(sig)
        got = len(items)
        seen_links = set()
        budget = site.cap or (TRADE_CAP if site.kind == "trade_press" else DEFAULT_CAP)

        def take(its):
            n_new = 0
            for i in its:
                if i["link"] not in seen_links:
                    seen_links.add(i["link"])
                    n_new += 1
                    add(Cand(i["link"], i["title"], i["date"], True, "rss", fu, extra={"summary": i["summary"][:300]}))
            return n_new

        take(items)
        # history: offset-style paging (feed_pages: full URL template with {off}) or WordPress-style ?paged=N
        if site.feed_pages:
            pages = ((site.feed_pages.format(off=k * site.feed_page_size, off1=k * site.feed_page_size + 1, n=k + 1), k) for k in range(0, 400))
        else:
            tmpl = site.feed_paged or ("?paged={n}" if feed_looks_wordpress(r.body) else "")
            sep = "&" if "?" in fu and tmpl.startswith("?") else ""
            pages = ((fu + ("&" + tmpl.format(n=n)[1:] if sep else tmpl.format(n=n)), n) for n in range(2, 400))                 if tmpl and got >= 5 else iter(())
        for purl, k in pages:
            if site.feed_pages and k == 0:
                continue                   # page 0 of an offset template is the feed already read
            if len(seen_links) >= budget * 1.3:
                break
            pr, why = ctx.get(purl, max_bytes=8_000_000)
            if pr is None:
                break
            pitems = parse_feed(pr.body)
            if not pitems or take(pitems) == 0:
                break
            ds = [i["date"] for i in pitems if i["date"]]
            if ds and max(ds) < ctx.win[0]:
                break
        if got and not site.multi_feed:
            break                       # the first working feed is enough (others are usually the same stream)


def sitemaps_run(site: Site, ctx: Ctx, st: Stats, add):
    base = host_base(site.url)
    roots = list(site.sitemaps)
    if not roots:
        roots = list(ctx.robots_for(base + "/").sitemaps)
        roots += [base + "/sitemap.xml", base + "/news-sitemap.xml", base + "/sitemap_index.xml"]
    win = ctx.win
    inc = re.compile(site.link_re, re.I) if site.link_re else None
    exc = re.compile(site.exclude_re, re.I) if site.exclude_re else None
    seen, budget = set(), [90]

    def walk(u, depth):
        if u in seen or budget[0] <= 0 or depth > 3:
            return
        seen.add(u)
        budget[0] -= 1
        r, why = ctx.get(u, max_bytes=40_000_000, timeout=60)
        if r is None:
            return
        kind, rows = parse_sitemap(r.body)
        if kind == "index":
            kids = []
            for row in rows:
                loc = row["loc"]
                fname = urlsplit(loc).path.rsplit("/", 1)[-1]
                if SM_BAD.search(fname) and not SM_GOOD.match(fname):
                    continue
                if row["lastmod"] and row["lastmod"] < win[0] - timedelta(days=45):
                    continue
                years = re.findall(r"(?<!\d)(20\d{2})(?!\d)", urlsplit(loc).path)
                if years and max(map(int, years)) < win[0].year:
                    continue
                kids.append(row)
            kids.sort(key=lambda r_: r_["lastmod"] or date.max, reverse=True)
            for row in kids:
                walk(row["loc"], depth + 1)
        elif kind == "urlset":
            for row in (rows[::-1] if site.sitemap_reverse else rows):
                loc = row["loc"]
                path = urlsplit(loc).path
                if inc is not None:
                    if not inc.search(loc):
                        continue
                elif not NEWSY.search(path):
                    continue
                if exc and exc.search(loc):
                    continue
                if NOT_ARTICLE.search(path):
                    continue
                d = row["pubdate"] or url_date(loc) or row["lastmod"]
                reliable = bool(row["pubdate"] or url_date(loc))
                if d is not None and d < win[0] - timedelta(days=(0 if reliable else 0)):
                    continue
                if d is not None and d > win[1] + timedelta(days=2):
                    continue
                add(Cand(loc, row["title"], d, reliable, "sitemap", u, extra={"lastmod_only": not reliable}))

    for sm in dict.fromkeys(roots):
        walk(sm, 0)


_EMB_DATE = re.compile(r'"slug"\s*:\s*"([^"]+)"(?:(?!"slug")[^{}]){0,600}?"(?:publicationDate|datePublished|publishDate|publication_date)"'
                       r'\s*:\s*"([^"]+)"')


def embedded_dates(page_html: str) -> dict:
    """{slug: date} from a listing's embedded CMS data (Next.js / Strapi flight data: "slug" ... "publicationDate").
    knds.com article pages carry no date; the listing's data does. Never "publishedAt" (knds: the site settings' date)."""
    out = {}
    for slug, v in _EMB_DATE.findall(page_html.replace('\\"', '"')):
        d = parse_date(v)
        if d:
            out.setdefault(slug, d)
    return out


def listing_run(site: Site, ctx: Ctx, st: Stats, add):
    tmpls = list(site.listing) or [site.url]
    win = ctx.win
    for tmpl in tmpls:
        paged = "{n}" in tmpl
        if not paged:
            auto = None
        seen_urls: set = set()
        n = site.list_start
        pages = 0
        empty = 0
        tried_auto = False
        while pages < site.list_max:
            url = tmpl.format(n=n) if paged else tmpl
            r, why = ctx.get(url, max_bytes=3_000_000)
            if r is None:
                if pages == 0:
                    st.note += f" [listing {url}: {why}]"
                break
            items = extract_listing(r.text(), r.url, site.link_re, site.exclude_re, same_host=not site.external,
                                    date_pos=site.date_pos)
            fresh = [i for i in items if i["url"] not in seen_urls]
            if not fresh:
                empty += 1
                if empty >= 1:
                    break
            for i in fresh:
                seen_urls.add(i["url"])
            if not site.list_dates:
                for i in fresh:
                    i["date"] = url_date(i["url"])
            emb = embedded_dates(r.text())            # the listing's own data per card beats a printed date matched by position
            for i in fresh:
                d = emb.get(urlsplit(i["url"]).path.rstrip("/").rsplit("/", 1)[-1])
                if d:
                    i["date"], i["inferred"] = d, False
            infer_neighbors(fresh, win)
            for i in fresh:
                if not site.link_re and not i["date"] and not NEWSY.search(urlsplit(i["url"]).path):
                    continue                  # undated link outside any news-looking path: site chrome, not an article
                add(Cand(i["url"], i["title"], i["date"], True, "listing", url, inferred=i.get("inferred", False)))
            pages += 1
            if not paged:
                # no template: try the usual pagination styles once, using page 2 as the probe
                if tried_auto:
                    break
                tried_auto = True
                found = False
                for t in ("{u}?page={n}", "{u}/page/{n}/", "{u}?paged={n}", "{u}?pg={n}", "{u}?p={n}"):
                    u2 = t.format(u=url.rstrip("/"), n=2)
                    r2, _ = ctx.get(u2, max_bytes=3_000_000)
                    if r2 is None:
                        continue
                    it2 = extract_listing(r2.text(), r2.url, site.link_re, site.exclude_re, same_host=not site.external,
                                          date_pos=site.date_pos)
                    if any(i["url"] not in seen_urls for i in it2):
                        tmpl, paged, n = t.replace("{u}", url.rstrip("/")), True, 2
                        found = True
                        break
                if not found:
                    break
                continue
            ds = [i["date"] for i in fresh if i["date"]]
            if ds and max(ds) < win[0]:
                break
            n += site.list_step


def infer_neighbors(items: list[dict], win):
    """An undated item lying between two in-window dated items of the same listing page counts as in-window."""
    for k, it in enumerate(items):
        if it["date"] is not None:
            continue
        prev = next((x["date"] for x in reversed(items[:k]) if x["date"]), None)
        nxt = next((x["date"] for x in items[k + 1:] if x["date"]), None)
        if prev and nxt and in_window(prev, win) and in_window(nxt, win):
            it["date"], it["inferred"] = prev, True


def pull_solar(site, ctx, st):
    """solargroup.com: the news page renders /admin-panel/news (JSON) client-side; headline/date/link per item."""
    r, why = ctx.get("https://www.solargroup.com/admin-panel/news")
    if r is None:
        st.note += f" [api: {why}]"
        return []
    out = []
    for it in json.loads(r.text()).get("news", []):
        if it.get("link"):
            out.append(Cand(it["link"], it.get("headline", ""), parse_date(it.get("date", "")), True, "api",
                            "https://www.solargroup.com/admin-panel/news", extra={"summary": it.get("shortNews", "")}))
    return out


def pull_pib(site, ctx, st):
    """pib.gov.in: allRel.aspx is an ASP.NET postback form (ministry + day/month/year). Ministry of Defence = 33.
    One POST per day of the window (English edition, region 3); the day is the release date."""
    from urllib.parse import urlencode
    url = "https://www.pib.gov.in/allRel.aspx?reg=3&lang=1"
    r, why = ctx.get(url)
    if r is None:
        st.note += f" [api: {why}]"
        return []
    t = r.text()

    def hid(n):
        m = re.search(r'id="%s" value="([^"]*)"' % n, t)
        return htmllib.unescape(m.group(1)) if m else ""
    base = {"__EVENTTARGET": "ctl00$ContentPlaceHolder1$ddlYear", "__EVENTARGUMENT": "", "__VIEWSTATE": hid("__VIEWSTATE"),
            "__VIEWSTATEGENERATOR": hid("__VIEWSTATEGENERATOR"), "__EVENTVALIDATION": hid("__EVENTVALIDATION"),
            "ctl00$ContentPlaceHolder1$ddlMinistry": "33", "ctl00$ContentPlaceHolder1$hydregionid": "3",
            "ctl00$ContentPlaceHolder1$hydLangid": "1"}
    out, d, fails = [], ctx.win[1], 0
    while d >= ctx.win[0]:
        form = dict(base, **{"ctl00$ContentPlaceHolder1$ddlday": str(d.day), "ctl00$ContentPlaceHolder1$ddlMonth": str(d.month),
                             "ctl00$ContentPlaceHolder1$ddlYear": str(d.year)})
        x = news.http(url, data=urlencode(form).encode(), timeout=40,
                      headers={"Content-Type": "application/x-www-form-urlencoded", "Referer": url})
        if x.status != 200:
            fails += 1
            if fails > 8:
                st.note += f" [api: http {x.status} at {d}]"
                break
        else:
            seen = set()
            for m in re.finditer(r"""<a[^>]*href=['"]([^'"]*PRID=(\d+)[^'"]*)['"][^>]*>(.*?)</a>""", x.text(), re.S):
                if m.group(2) in seen:
                    continue
                seen.add(m.group(2))
                out.append(Cand(f"https://www.pib.gov.in/PressReleasePage.aspx?PRID={m.group(2)}", _plain(m.group(3)), d, True,
                                "api", url, extra={"fetch": f"https://www.pib.gov.in/PressReleaseIframePage.aspx?PRID={m.group(2)}",
                                                   "fixed": True}))
        d -= timedelta(days=1)
    return out


def pull_ddp(site, ctx, st):
    """ddpmod.gov.in: "What's New" is a table (title | PDF | language | publish date - end date); one notice per row."""
    url = "https://www.ddpmod.gov.in/en/ministry/whats-new?items_per_page=50&page=0"
    r, why = ctx.get(url)
    if r is None:
        st.note += f" [api: {why}]"
        return []
    out = []
    for row in re.findall(r"<tr>(.*?)</tr>", r.text(), re.S):
        title = re.search(r'views-field-title">(.*?)</td>', row, re.S)
        link = re.search(r'href="(/sites/default/files/[^"]+)"', row)
        pub = re.search(r'views-field-field-news-date-1">\s*(\d{1,2}/\d{1,2}/\d{4})', row)
        if title and link and pub:
            out.append(Cand(urljoin(url, htmllib.unescape(link.group(1))), _plain(title.group(1)), parse_date(pub.group(1)), True,
                            "listing", url))
    return out


API_PULLERS: dict = {"solar": pull_solar, "pib": pull_pib, "ddp": pull_ddp}


# ----------------------------------------------------------------------------- per-article processing

BLOG_RE = re.compile(r"(idrw\.org|ajaishukla\.com)", re.I)      # blogs: never a source (user decision)


def tier_for(site: Site, url: str) -> str:
    cd = (site.cdomains or (site.domain,)) if site.kind in ("newsroom", "gov") else ()
    return classify(url, cd) or "listed"


_CATEGORY = re.compile(r"^(news|press release|press|blog|story|event|media|article|video|feature|update|announcement)\s*[:|-]?\s+", re.I)
_DATE_ANY = re.compile(_ISO.pattern + "|" + _DMY_TXT.pattern + "|" + _MDY_TXT.pattern + "|" + _DMY_NUM.pattern, re.I)


def clean_listing_title(t: str) -> str:
    t = _DATE_ANY.sub(" ", t or "")
    t = _CATEGORY.sub("", " ".join(t.split()))
    return " ".join(t.split())


GENERIC_WORDS = {"newsroom", "news", "media", "press", "home", "releases", "release", "centre", "center", "latest", "updates"}


def choose_title(page_title: str, cand_title: str, method: str) -> str:
    """The page's own title, unless it is a site-wide generic one ("Newsroom | Site") that shares almost no
    words with the title the feed / listing gave -- then the cleaned listing title wins. Feed titles always win."""
    page_title, cand = (page_title or "").strip(), clean_listing_title(cand_title) if method != "rss" else (cand_title or "").strip()
    if method == "rss" and cand:
        return cand
    if not cand or len(cand) < 12:
        return page_title or cand
    if not page_title:
        return cand
    w = lambda x: set(re.findall(r"\w{3,}", x.lower()))     # noqa: E731
    a, b = w(page_title), w(cand)
    generic = bool(a & GENERIC_WORDS) and not (a - b - GENERIC_WORDS)       # "Newsroom | Site" ⊂ the real headline
    return cand if generic or len(a & b) / max(1, min(len(a), len(b))) < 0.3 else page_title


def process_cand(site: Site, c: Cand, ctx: Ctx, st: Stats, lock: threading.Lock):
    def skip(why):
        with lock:
            st.skip(why)
            st.consec_out = st.consec_out + 1 if why == "outside date window" else 0

    url = c.url
    if BLOG_RE.search(url):
        return skip("blog domain (not a source)")
    if url in ctx.known:
        with lock:
            st.already += 1
        return
    if urlsplit(url).path.lower().endswith((".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx")):
        return store_listing_only(site, c, ctx, st, lock, skip)
    r, why = ctx.get(c.extra.get("fetch") or url)
    if r is None:
        if site.external and c.title and c.date:       # press-coverage tile whose page cannot be read: keep the tile
            return store_listing_only(site, c, ctx, st, lock, skip, note=f"page not fetched ({why}); listing title/date only")
        return skip(why)
    ct = r.headers.get("content-type", "").lower()
    if ct and not any(x in ct for x in ("html", "xml", "text")):
        return skip(f"non-html ({ct.split(';')[0]})")
    pg = read_page(r.text(), r.url)
    canon = clean(pg.canonical) if pg.canonical else ""
    final = clean(r.url)
    if c.extra.get("fixed"):
        use = url
    elif canon and not (is_homepage(canon) and not urlsplit(canon).query) and (host_of(canon) == host_of(final) or site.external is False and any(host_of(canon).endswith(d) for d in (site.cdomains or (site.domain,)))):
        use = canon
    else:
        use = final
    if is_homepage(use) and not urlsplit(use).query:
        return skip("resolved to a homepage")
    if use in ctx.known and use != url:
        with lock:
            st.already += 1
        return
    # date: feed/listing date is a publication date; a page date is preferred for listing/sitemap candidates
    d, dsrc = None, ""
    if c.method == "rss" and c.date:
        d, dsrc = c.date, "feed"
    elif pg.date and pg.date_src in ("meta", "ld", "ld/meta"):
        d, dsrc = pg.date, pg.date_src
    elif c.date and c.reliable:
        d, dsrc = c.date, ("listing-inferred" if c.inferred else ("api" if c.method == "api" else "listing"))
    elif c.date and site.trust_lastmod:
        d, dsrc = c.date, "sitemap-lastmod"
    elif pg.date:                          # <time>, URL or text date: weaker than a declared listing / feed date
        d, dsrc = pg.date, pg.date_src
    if d is None:
        return skip("no publication date")
    if not in_window(d, ctx.win):
        return skip("outside date window")
    body = pg.body
    title = choose_title(pg.title, c.title, c.method)
    title = htmllib.unescape(re.sub(r"\s+", " ", title))[:500]
    if not title and not body:
        return skip("empty page")
    notes = []
    if dsrc in ("listing-inferred", "sitemap-lastmod", "text"):
        notes.append(f"date from {dsrc}")
    if len(body) < 150:
        notes.append("short body")
    triage = {"harvester": HARVESTER, "site": site.domain, "method": c.method, "notes": "; ".join(notes) or None,
              "date_source": dsrc}
    if site.non_competitor:
        triage.update({"non_competitor": True, "company": site.name})
    if use != url:
        triage["listed_as"] = url
    tier = tier_for(site, use)
    row = {"doc_id": str(uuid.uuid5(uuid.NAMESPACE_URL, use)), "url": use, "source_kind": site.kind,
           "source_name": site.name if not site.external else (pg.site_name or host_of(use)),
           "source_tier": tier, "feed_url": c.feed_url or site.url, "title": title, "published_at": d,
           "language": pg.lang, "body_text": body, "triage": triage}
    if site.external:
        triage["via"] = site.name
    ok = ctx.store(row)
    with lock:
        st.consec_out = 0
        if ok:
            st.stored += 1
            st.dates.append(d)
        else:
            st.already += 1


def store_listing_only(site, c, ctx, st, lock, skip, note="pdf: body not extracted"):
    """A PDF / unfetchable external item: keep the listing's title and date, no body (nothing is fetched here)."""
    if c.date is None and c.title:
        c.date = find_date(c.title)
        c.reliable = c.date is not None
    if not (c.date and c.reliable and c.title):
        return skip("pdf/image without listing date/title")
    if not in_window(c.date, ctx.win):
        return skip("outside date window")
    triage = {"harvester": HARVESTER, "site": site.domain, "method": c.method, "notes": note, "date_source": "listing"}
    if site.non_competitor:
        triage.update({"non_competitor": True, "company": site.name})
    row = {"doc_id": str(uuid.uuid5(uuid.NAMESPACE_URL, c.url)), "url": c.url, "source_kind": site.kind,
           "source_name": site.name, "source_tier": tier_for(site, c.url), "feed_url": c.feed_url or site.url,
           "title": c.title[:500], "published_at": c.date, "language": None, "body_text": None, "triage": triage}
    ok = ctx.store(row)
    with lock:
        st.consec_out = 0
        if ok:
            st.stored += 1
            st.dates.append(c.date)
        else:
            st.already += 1


def harvest_site(site: Site, ctx: Ctx, max_per_site=0, probe=False) -> Stats:
    st = Stats(site)
    t0 = time.monotonic()
    try:
        if site.walled:
            st.status, st.note = "skipped", site.walled
            return st
        if site.skip:
            st.status, st.note = "skipped", site.skip
            return st
        cands = discover(site, ctx, st)
        st.found = len(cands)
        win = ctx.win
        inw = [c for c in cands if c.date is None or in_window(c.date, win) or not c.reliable]
        # candidates with a reliable date outside the window are dropped without a fetch
        dropped = [c for c in cands if c.reliable and c.date and not in_window(c.date, win)]
        st.skip("listed outside window (not fetched)", len(dropped))
        st.in_window = len(inw)
        inw.sort(key=lambda c: (c.date or date.min), reverse=True)
        cap = max_per_site or site.cap or (TRADE_CAP if site.kind == "trade_press" else DEFAULT_CAP)
        if len(inw) > cap:
            st.larger_than_cap = len(inw)
        todo = [c for c in inw if c.url not in ctx.known]
        st.already = len(inw) - len(todo)
        if probe:
            ds = [c.date for c in cands if c.date]
            st.status = "ok" if cands else "failed"
            if not cands:
                st.note = (st.note + " no candidates found").strip()
            st.dates = [d for d in ds if in_window(d, win)]
            return st
        lock = threading.Lock()
        budget = max(0, cap - st.already)
        to_do = todo[:budget + budget // 2] if st.larger_than_cap else todo      # headroom: some fetches skip
        done = lambda: st.stored + st.already >= cap                              # noqa: E731
        with ThreadPoolExecutor(max_workers=ctx.workers) as ex:
            for f in as_completed([ex.submit(_guarded, site, c, ctx, st, lock, done) for c in to_do]):
                f.result()
        st.status = "ok" if (st.stored or st.already) else "failed"
        if st.status == "failed" and not st.note:
            st.note = ("no candidates found" if not cands else "nothing stored: " + ", ".join(
                f"{k} x{v}" for k, v in st.skipped.most_common(3)))
    except Exception as e:  # noqa: BLE001
        st.status, st.note = "failed", f"{type(e).__name__}: {str(e)[:150]}"
    finally:
        st.secs = time.monotonic() - t0
    return st


def _guarded(site, c, ctx, st, lock, done):
    if done():
        return
    if site.early_stop and st.consec_out >= 60:
        with lock:
            st.skip("not fetched (60 consecutive pages older than the window)")
        return
    try:
        process_cand(site, c, ctx, st, lock)
    except Exception as e:  # noqa: BLE001
        with lock:
            st.skip(f"error {type(e).__name__}: {str(e)[:50]}")


# ----------------------------------------------------------------------------- report

def fmt_report(all_stats: list[Stats], win, db_totals=None) -> str:
    db_totals = db_totals or {}
    lines = [f"harvest_sites report  window {win[0]} .. {win[1]}  generated {datetime.now():%Y-%m-%d %H:%M}",
             "",
             f"{'site':26} {'kind':11} {'pri':5} {'status':8} {'method':18} {'found':>6} {'inwin':>6} {'new':>5} {'inDB':>5} "
             f"{'oldest':10} {'newest':10}  skipped / note   (new = stored this run; inDB/oldest/newest = all rows of the site in the table)"]
    for s in all_stats:
        d = s.dates
        n_db, o_db, n_db_new = db_totals.get(s.site.domain, (0, None, None))
        sk = "; ".join(f"{k} x{v}" for k, v in s.skipped.most_common(4))
        note = (s.note + (" | " if s.note and sk else "") + sk).strip()
        if s.larger_than_cap:
            note += f" | LARGER THAN CAP: {s.larger_than_cap} candidates in window"
        if s.site.notes:
            note += f" | NOTE: {s.site.notes}"
        lines.append(f"{s.site.domain[:26]:26} {s.site.kind:11} {s.site.prio:5} {s.status:8} {'+'.join(s.methods)[:18]:18} "
                     f"{s.found:6} {s.in_window:6} {s.stored:5} {n_db:5} "
                     f"{(o_db.isoformat() if o_db else (min(d).isoformat() if d else '-')):10} "
                     f"{(n_db_new.isoformat() if n_db_new else (max(d).isoformat() if d else '-')):10}  {note}")
    lines.append("")
    tot = collections.defaultdict(lambda: [0, 0, 0, 0])
    for s in all_stats:
        t = tot[s.site.kind]
        t[0] += 1
        t[1] += db_totals.get(s.site.domain, (0, None, None))[0]
        t[2] += s.status == "ok"
        t[3] += s.status in ("skipped", "failed")
    lines.append("totals by kind (sites, rows stored by this harvester in staging.source_document, sites ok, sites skipped/failed):")
    for k, (n, rows_, ok_, bad_) in tot.items():
        lines.append(f"  {k:12} sites {n:3}  rows {rows_:6}  ok {ok_:3}  skipped/failed {bad_:3}")
    bad = [s for s in all_stats if s.status in ("skipped", "failed")]
    if bad:
        lines += ["", "walled / skipped / failed:"]
        for s in bad:
            lines.append(f"  {s.site.domain:26} {s.status:8} {s.note[:200]}")
    return "\n".join(lines)


# ----------------------------------------------------------------------------- CLI

STATE = ROOT / "db" / "excel_reports" / "harvest_sites_state.json"


def merge_state(results, db_totals):
    """The report covers every site ever harvested: this run's per-site stats replace the saved ones."""
    try:
        old = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    for st in results:
        old[st.site.domain] = {
            "status": st.status, "note": st.note, "methods": st.methods, "found": st.found, "in_window": st.in_window,
            "stored": st.stored, "already": st.already, "skipped": dict(st.skipped), "larger": st.larger_than_cap,
            "db": [db_totals.get(st.site.domain, (0, None, None))[0],
                   str(db_totals.get(st.site.domain, (0, None, None))[1] or ""),
                   str(db_totals.get(st.site.domain, (0, None, None))[2] or "")]}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(old, indent=1), encoding="utf-8")
    by = {s.domain: s for s in SITES}
    merged, tot = [], {}
    for dom, d in old.items():
        if dom not in by:
            continue
        st = Stats(by[dom], methods=d["methods"], found=d["found"], in_window=d["in_window"], stored=d["stored"],
                   already=d["already"], skipped=collections.Counter(d["skipped"]), status=d["status"], note=d["note"],
                   larger_than_cap=d["larger"])
        merged.append(st)
        n, lo, hi = d["db"]
        tot[dom] = (n, date.fromisoformat(lo) if lo else None, date.fromisoformat(hi) if hi else None)
    return merged, tot


def db_summary(ctx, sites) -> dict:
    """{domain: (rows, oldest, newest)} of the rows this harvester stored for each site (all runs)."""
    out = {}
    with ctx.conn.cursor() as cur:
        for s in sites:
            cur.execute("SELECT count(*), min(published_at), max(published_at) FROM staging.source_document "
                        "WHERE source_kind = %s AND triage->>'harvester' LIKE 'harvest_sites%%' AND "
                        "(triage->>'site' = %s OR (triage->>'site' IS NULL AND (source_name = %s OR triage->>'via' = %s)))",
                        (s.kind, s.domain, s.name, s.name))
            n, lo, hi = cur.fetchone()
            out[s.domain] = (n, lo, hi)
    return out


def normalize_urls(ctx, kinds=("newsroom", "gov", "trade_press"), dry=False) -> tuple[int, int]:
    """Re-apply backend.news.clean_url (http->https, mobile->desktop host, tracking params) to stored rows of the given
    source kinds: url and doc_id (= uuid5(url)) are recomputed; when the clean url already exists the two rows are merged
    (the existing row is kept, the other one is deleted, its triage is folded in as triage.merged_from).
    -> (rows re-keyed, rows merged away)."""
    changed = merged = 0
    with ctx.conn.cursor() as cur:
        cur.execute("SELECT doc_id::text, url FROM staging.source_document WHERE source_kind = ANY(%s)", (list(kinds),))
        rows = cur.fetchall()
        for doc_id, url in rows:
            new = clean(url)
            if new == url:
                continue
            cur.execute("SELECT doc_id::text, body_text IS NULL OR length(body_text) < 150 FROM staging.source_document WHERE url = %s",
                        (new,))
            hit = cur.fetchone()
            if hit and hit[0] != doc_id:
                merged += 1
                if not dry:
                    cur.execute("UPDATE staging.source_document t SET "
                                "body_text = CASE WHEN %s THEN o.body_text ELSE t.body_text END, "
                                "published_at = COALESCE(t.published_at, o.published_at), "
                                "title = COALESCE(t.title, o.title), "
                                "triage = COALESCE(t.triage, '{}'::jsonb) || jsonb_build_object('merged_from', "
                                "COALESCE(t.triage->'merged_from', '[]'::jsonb) || to_jsonb(%s::text)) "
                                "FROM staging.source_document o WHERE t.doc_id = %s::uuid AND o.doc_id = %s::uuid",
                                (hit[1], url, hit[0], doc_id))
                    cur.execute("DELETE FROM staging.source_document WHERE doc_id = %s::uuid", (doc_id,))
            else:
                changed += 1
                if not dry:
                    cur.execute("UPDATE staging.source_document SET url = %s, doc_id = %s::uuid WHERE doc_id = %s::uuid",
                                (new, str(uuid.uuid5(uuid.NAMESPACE_URL, new)), doc_id))
    return changed, merged


def select_sites(a) -> list[Site]:
    sites = apply_overrides(SITES)
    if a.site:
        want = {x.lower().removeprefix("www.") for x in a.site}
        sites = [s for s in sites if s.domain in want]
        if not sites:
            raise SystemExit(f"unknown site(s) {a.site}")
    if a.kind:
        sites = [s for s in sites if s.kind == a.kind]
    if a.prio:
        sites = [s for s in sites if s.prio.lower() == a.prio.lower()]
    return sites


def run(a) -> int:
    if a.normalize_urls:
        ctx = Ctx(WINDOW, False)
        ctx.connect()
        ch, mg = normalize_urls(ctx, dry=a.dry_run)
        print(f"{'would re-key' if a.dry_run else 're-keyed'} {ch} rows, merged away {mg} duplicates")
        ctx.close()
        return 0
    win = (date.fromisoformat(a.frm), date.fromisoformat(a.to))
    sites = select_sites(a)
    ctx = Ctx(win, a.dry_run or a.probe, workers=2)
    news.GATE = news._HostGate(per_host=2, gap=0.4)
    ctx.connect()
    print(f"window {win[0]} .. {win[1]}; {len(sites)} site(s); {'DRY RUN' if ctx.dry else 'writing staging.source_document'}",
          flush=True)
    results: list[Stats] = []
    lock = threading.Lock()

    def one(s):
        st = harvest_site(s, ctx, a.max_per_site, probe=a.probe)
        with lock:
            results.append(st)
            d = st.dates
            print(f"[{len(results)}/{len(sites)}] {s.domain}: {st.status} {'+'.join(st.methods)} found={st.found} "
                  f"inwin={st.in_window} stored={st.stored} had={st.already} "
                  f"{(min(d).isoformat() + '..' + max(d).isoformat()) if d else ''} {st.note[:120]} "
                  f"{dict(st.skipped.most_common(3))} ({st.secs:.0f}s)", flush=True)
        return st

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        list(ex.map(one, sites))
    db_totals = {}
    if not (ctx.dry or a.probe):
        db_totals = db_summary(ctx, sites)
    ctx.close()
    if not (ctx.dry or a.probe):
        results, db_totals = merge_state(results, db_totals)
    order = {s.domain: i for i, s in enumerate(SITES)}
    results.sort(key=lambda s: order[s.site.domain])
    rep = fmt_report(results, win, db_totals)
    print("\n" + rep)
    if not (ctx.dry or a.probe):
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(rep + "\n", encoding="utf-8")
    return 0


def _selftest():
    # --- dates
    assert parse_date("2026-03-12T10:20:30+05:30") == date(2026, 3, 12)
    assert parse_date("Tue, 15 Sep 2026 23:30:00 GMT") == date(2026, 9, 15)
    assert parse_date("17 January 2026") == date(2026, 1, 17)
    assert parse_date("Jan 5th, 2026") == date(2026, 1, 5)
    assert parse_date("Sept. 3, 2026") == date(2026, 9, 3)
    assert parse_date("03/09/2026") == date(2026, 9, 3)             # day-first
    assert parse_date("25/12/2026") == date(2026, 12, 25)
    assert parse_date("12/25/2026") == date(2026, 12, 25)           # impossible as d/m -> m/d
    assert parse_date("garbage") is None and parse_date("") is None and parse_date("2026-13-45") is None
    assert find_date("Posted on 4 Mar 2026 by admin, updated 9 Mar 2026") == date(2026, 3, 4)
    assert find_date("Mar 4, 2026 | 5 Jan 2026") == date(2026, 3, 4)
    assert find_date("Posted on: October 13,2026") == date(2026, 10, 13)
    assert find_date("no date here 1234") is None
    assert url_date("https://x.test/2026/03/12/some-story/") == date(2026, 3, 12)
    assert url_date("https://x.test/news/2026-02-03-big-order") == date(2026, 2, 3)
    assert url_date("https://x.test/a/20260117-story.html") == date(2026, 1, 17)
    assert url_date("https://x.test/2026/Mar/12/story") == date(2026, 3, 12)
    assert url_date("https://x.test/2026/03/") is None and url_date("https://x.test/story") is None
    assert in_window(date(2026, 1, 17), WINDOW) and in_window(date(2026, 10, 17), WINDOW)
    assert not in_window(date(2026, 1, 16), WINDOW) and not in_window(None, WINDOW)
    # --- RSS / Atom
    rss = (b'<?xml version="1.0"?><rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/" '
           b'xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>'
           b'<generator>https://wordpress.org/?v=6.5</generator>'
           b'<item><title>Zed Corp wins &amp; delivers</title><link>https://zed.test/2026/02/01/wins/</link>'
           b'<pubDate>Sun, 01 Feb 2026 08:00:00 +0000</pubDate><description>Short</description>'
           b'<content:encoded><![CDATA[<p>Full</p>]]></content:encoded></item>'
           b'<item><title>Dc dated</title><link>https://zed.test/b</link><dc:date>2026-03-02T00:00:00Z</dc:date></item>'
           b'<item><title>No link</title></item></channel></rss>')
    it = parse_feed(rss)
    assert len(it) == 2 and it[0]["title"] == "Zed Corp wins & delivers" and it[0]["date"] == date(2026, 2, 1)
    assert it[1]["date"] == date(2026, 3, 2) and it[0]["content"] == "<p>Full</p>"
    assert feed_looks_wordpress(rss)
    atom = (b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>A</title>'
            b'<link rel="self" href="https://a.test/self"/><link rel="alternate" href="https://a.test/a1"/>'
            b'<published>2026-04-05T10:00:00Z</published><updated>2026-05-01T00:00:00Z</updated></entry>'
            b'<entry><title>B</title><link href="https://a.test/b1"/><updated>2026-06-07T00:00:00Z</updated></entry></feed>')
    at = parse_feed(atom)
    assert [x["link"] for x in at] == ["https://a.test/a1", "https://a.test/b1"]
    assert at[0]["date"] == date(2026, 4, 5) and at[1]["date"] == date(2026, 6, 7)
    assert parse_feed(b"<html>not a feed</html>") == [] and parse_feed(b"") == []
    # --- sitemaps
    sm = (b'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
          b'xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">'
          b'<url><loc>https://q.test/n/one</loc><lastmod>2026-05-05T00:00:00+00:00</lastmod></url>'
          b'<url><loc>https://q.test/n/two</loc><news:news><news:publication_date>2026-06-06T01:02:03Z</news:publication_date>'
          b'<news:title>Two</news:title></news:news></url></urlset>')
    kind, rows = parse_sitemap(sm)
    assert kind == "urlset" and rows[0]["lastmod"] == date(2026, 5, 5) and rows[1]["pubdate"] == date(2026, 6, 6)
    assert rows[1]["title"] == "Two"
    smi = (b'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://q.test/s1.xml</loc>'
           b'<lastmod>2026-01-01</lastmod></sitemap></sitemapindex>')
    assert parse_sitemap(smi) == ("index", [{"loc": "https://q.test/s1.xml", "lastmod": date(2026, 1, 1), "pubdate": None, "title": ""}])
    assert parse_sitemap(gzip.compress(sm))[0] == "urlset" and parse_sitemap(b"junk") == ("", [])
    # --- robots
    rb = Robots("User-agent: Googlebot\nDisallow: /\n\nUser-agent: *\nDisallow: /private\nDisallow: /*.pdf$\n"
                "Allow: /private/open\nCrawl-delay: 2\nSitemap: https://r.test/sm.xml\n")
    assert rb.allowed("https://r.test/news/a") and not rb.allowed("https://r.test/private/x")
    assert rb.allowed("https://r.test/private/open/x") and not rb.allowed("https://r.test/a/b.pdf")
    assert rb.allowed("https://r.test/a/b.pdf?x=1") and rb.crawl_delay == 2 and rb.sitemaps == ["https://r.test/sm.xml"]
    assert Robots("User-agent: *\nDisallow:\n").allowed("https://r.test/x") and not Robots(allow_all=False).allowed("https://r.test/")
    # --- listing extraction
    page = ('<nav><a href="/about">About</a><a href="/news/">News</a></nav>'
            '<div class="card"><span>12 Mar 2026</span><a href="/news/big-contract-awarded-to-zed">Big contract</a></div>'
            '<div class="card"><a href=/news/second-story-about-radar-systems>Radar <b>story</b></a><p>5 February 2026</p></div>'
            '<div class="card"><a href="/news/third-story-without-a-date-here">Third</a></div>'
            '<a href="https://other.test/news/external-article-slug-long">ext</a>'
            '<a href="/news/page/2/">next</a><a href="/img/logo.png">x</a>')
    ex = extract_listing(page, "https://z.test/news/", date_pos="after")
    assert [x["url"] for x in ex] == ["https://z.test/news/big-contract-awarded-to-zed",
                                      "https://z.test/news/second-story-about-radar-systems",
                                      "https://z.test/news/third-story-without-a-date-here"], ex
    assert ex[1]["date"] == date(2026, 2, 5) and ex[1]["title"] == "Radar story"
    exb = extract_listing(page, "https://z.test/news/", date_pos="before")
    assert exb[0]["date"] == date(2026, 3, 12)
    ext = extract_listing(page, "https://z.test/news/", same_host=False, date_pos="after")
    assert any(x["url"].startswith("https://other.test/") for x in ext)
    items = [{"date": date(2026, 3, 1)}, {"date": None}, {"date": date(2026, 2, 1)}, {"date": None}]
    infer_neighbors(items, WINDOW)
    assert items[1]["date"] == date(2026, 3, 1) and items[1]["inferred"] and items[3]["date"] is None
    items = [{"date": date(2025, 3, 1)}, {"date": None}, {"date": date(2026, 2, 1)}]
    infer_neighbors(items, WINDOW)
    assert items[1]["date"] is None
    # --- article page: date sources, canonical, body
    art = ('<html lang="en-GB"><head><title>T</title><link rel="canonical" href="https://z.test/a/1">'
           '<meta property="article:published_time" content="2026-04-04T09:00:00Z"></head><body><nav>menu</nav>'
           '<article><h1>Headline of the story</h1><p>' + "Real sentence about a defence order. " * 20 + '</p></article>'
           '<footer>copyright</footer></body></html>')
    pgx = read_page(art, "https://z.test/a/1?utm_source=x")
    assert pgx.date == date(2026, 4, 4) and pgx.date_src == "meta" and pgx.canonical == "https://z.test/a/1"
    assert pgx.lang == "en" and "Real sentence" in pgx.body and "menu" not in pgx.body and len(pgx.body) <= BODY_CAP
    p2 = read_page('<html><body><main><time datetime="2026-05-06">x</time><p>' + "Words go here and there. " * 30 + '</p></main></body></html>',
                   "https://z.test/b")
    assert p2.date == date(2026, 5, 6) and p2.date_src == "time"
    p3 = read_page('<html><body><p>' + "Words " * 100 + '</p></body></html>', "https://z.test/2026/07/08/story")
    assert p3.date == date(2026, 7, 8) and p3.date_src == "url"
    p4 = read_page('<html><body><h1>Release</h1><p>Posted on 9 June 2026 by the press office</p><p>' + "Words " * 100 + '</p></body></html>',
                   "https://z.test/story")
    assert p4.date == date(2026, 6, 9) and p4.date_src == "text"
    ld = ('<html><head><script type="application/ld+json">{"@type":"NewsArticle","datePublished":"2026-08-09T00:00:00Z"}'
          '</script></head><body><p>x</p></body></html>')
    assert read_page(ld, "https://z.test/c").date == date(2026, 8, 9)
    p5 = read_page('<html><head><title>Fentanyl in Italy | RUSI</title></head><body><header>menu</header><h1>Fentanyl in Italy</h1>'
                   '<p>Federico Varese 16 October 2026 8 Minute Read</p><article><p>' + "Words go here. " * 40 + '</p></article></body></html>',
                   "https://z.test/commentary/fentanyl")
    assert p5.date == date(2026, 10, 16), p5
    # hanwha.com: the date is only in a date-classed span; a "modified" span and the URL lose to it
    p6 = read_page('<html><body><span class="updated-date">September 1, 2026</span><div class="news"><span class="date">August 19, 2026</span>'
                   '<p>' + "Words " * 100 + '</p></div></body></html>', "https://z.test/2026/09/30/story")
    assert p6.date == date(2026, 8, 19) and p6.date_src == "class", p6
    p7 = read_page('<html><body><h2>Anti-ship BRAHMOS test-fired</h2><div> <b>Date:</b>  27 Apr, 2022    </div><div><b>Source:</b> PTI</div>'
                   '<p>' + "Words " * 100 + '</p></body></html>', "https://z.test/brahmos-in-media/102")
    assert p7.date == date(2022, 4, 27) and p7.date_src == "label", p7
    # a header clock (bharatshakti, globaldefensecorp) shows today's date in a date-classed span: not the article date
    clock = date.today().strftime("%B %d, %Y")
    p8 = read_page(f'<html><body><span class="header-date">{clock}</span><p>' + "Words " * 100 + '</p></body></html>', "https://z.test/story")
    assert p8.date is None or p8.date_src not in ("class", "label"), p8
    # knds.com listing: Next.js flight data, escaped quotes; publishedAt (site settings) is never read
    emb = embedded_dates('self.__next_f.push([1,"{\\"publishedAt\\":\\"2025-09-11T13:14:04Z\\",\\"posts\\":{\\"data\\":[{\\"id\\":1,'
                         '\\"slug\\":\\"knds-a\\",\\"title\\":\\"A\\",\\"publicationDate\\":\\"2026-10-14\\"},'
                         '{\\"id\\":2,\\"slug\\":\\"knds-b\\",\\"title\\":\\"B\\",\\"publishedAt\\":\\"2025-09-11\\"}]}}"])')
    assert emb == {"knds-a": date(2026, 10, 14)}, emb
    # --- titles
    assert clean_listing_title("NEWS Hanwha to Showcase Air Defense 2026. 09. 08") == "Hanwha to Showcase Air Defense"
    assert clean_listing_title("NATO summit news") == "NATO summit news"
    assert choose_title("Newsroom | Hanwha Aerospace", "NEWS Hanwha Aerospace Hosts US Army 2026. 09. 02", "listing") ==         "Hanwha Aerospace Hosts US Army"
    assert choose_title("KNDS signs contract extension | KNDS", "Read more", "sitemap") == "KNDS signs contract extension | KNDS"
    assert choose_title("Real page title about radar", "Real page title about radar systems order", "listing") == "Real page title about radar"
    assert choose_title("Page", "Feed title wins", "rss") == "Feed title wins"
    # --- site list sanity
    doms = [s.domain for s in SITES]
    assert len(doms) == len(set(doms)) and all(s.kind in ("newsroom", "gov", "trade_press") for s in SITES)
    assert all(s.walled for s in SITES if s.domain in ("anduril.com", "baesystems.com", "elbitsystems.com", "rafael.co.il"))
    assert tier_for(SITES[0], "https://www.adanidefence.com/x") == "primary"
    print("selftest ok")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m backend.harvest_sites", description=__doc__.split("\n")[0])
    ap.add_argument("--site", action="append", help="domain from the site list (repeatable)")
    ap.add_argument("--kind", choices=["newsroom", "gov", "trade_press"])
    ap.add_argument("--prio", help="P1 | P2 | P3 | gov | trade")
    ap.add_argument("--from", dest="frm", default=WINDOW[0].isoformat())
    ap.add_argument("--to", default=WINDOW[1].isoformat())
    ap.add_argument("--max-per-site", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true", help="fetch and parse, write nothing")
    ap.add_argument("--probe", action="store_true", help="discovery only (no article fetch, no DB)")
    ap.add_argument("--workers", type=int, default=6, help="sites in parallel (each site: <=2 requests at a time per host)")
    ap.add_argument("--normalize-urls", action="store_true",
                    help="re-apply backend.news.clean_url to the stored rows (re-key url/doc_id, merge duplicates)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.selftest:
        _selftest()
        return 0
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
