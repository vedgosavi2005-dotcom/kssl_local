"""Model output -> validated records -> kssl_staging (one transaction per run). See prompts/FORMAT.md.

    envelope text --spec.parse_envelope--> dict --spec.validate--> Validated (Rec trees + rejected/warnings)
    Validated --Loader.load(...)--> Row trees: refs resolved, loader values evaluated (prompts/vocab.py),
        previous rows deleted, rows inserted / updated, fact_source written, derive hooks run

Self-check (no DB, no model):  python -m prompts.loader --selftest
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import psycopg2.extras

from backend import review
from backend.sources import classify, host_of
from prompts import vocab
from prompts.spec import (EnvelopeError, GRAPH, NotJson, Rec, RowRejected, TableRules, Validated,  # noqa: F401  (re-exported)
                          _date, _number, enum_sources, parse_envelope, parse_output, validate)
from prompts.vocab import ID_COLUMNS, REFS, UNSET, NoValue

BOOKKEEPING = ("created_at", "updated_at")
JUDGEMENT_SOURCE = "judgement"
STORED_ROW_SOURCE = "stored row"          # a _sources entry that cites an input row (no url)
TEXT_TYPES = ("text", "character varying", "character")
UNLISTED_TIER = "unlisted"          # a cited url that backend/sources.py does not allow (still shown in Trace, with a warning)


def compact_name(name: str) -> str:
    """"Larsen & Toubro Limited" -> "larsentoubro": for matching a company's name to its web host."""
    from backend.news import name_key
    return re.sub(r"[^a-z0-9]", "", name_key(name.replace("&", " ")))
PORTFOLIO_LENSES = ("rival", "field")


# =====================================================================================================
# ids, names
# =====================================================================================================

def make_id(data_type: str, seed: str):
    """Deterministic id from a seed: uuid -> uuid5, bigint/integer -> 63/31-bit hash."""
    if data_type == "uuid":
        return str(uuid.uuid5(uuid.NAMESPACE_URL, "kssl-prompt|" + seed))
    h = int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8], "big")
    if data_type == "bigint":
        return h & 0x7FFFFFFFFFFFFFFF
    if data_type == "integer":
        return h & 0x7FFFFFFF
    if data_type in ("text", "character varying"):
        return str(uuid.uuid5(uuid.NAMESPACE_URL, "kssl-prompt|" + seed))
    raise ValueError(f"cannot generate an id for a {data_type} column")


def id_seed(prompt_id: str, subject: str, table: str, n: int, extra: tuple = ()) -> str:
    return "|".join([prompt_id, subject, *extra, table, str(n)])


def norm_name(s: str) -> str:
    s = (s or "").lower().replace("&", " and ")
    return " ".join(re.sub(r"[^\w]+", " ", s).split())


def match_name(rows: list, name_cols: list, name: str) -> list:
    """Rows whose name column equals `name` (case/punctuation-insensitive); a trailing '(...)' is
    ignored as a second try, since context lists show 'product (category)'."""
    for candidate in (name, re.sub(r"\s*\([^)]*\)\s*$", "", name)):
        key = norm_name(candidate)
        if not key:
            continue
        hit = [r for r in rows if any(norm_name(str(r.get(c) or "")) == key for c in name_cols)]
        if hit:
            return hit
    return []


# =====================================================================================================
# DB column typing
# =====================================================================================================

class Meta:
    def __init__(self, cur):
        self.cur, self.t = cur, {}

    def table(self, name: str) -> dict:
        if name not in self.t:
            self.cur.execute("""SELECT column_name, data_type, is_nullable, column_default, character_maximum_length
                                FROM information_schema.columns WHERE table_schema='staging' AND table_name=%s""", (name,))
            self.t[name] = {r["column_name"]: dict(r) for r in self.cur.fetchall()}
            if not self.t[name]:
                raise ValueError(f"staging.{name} does not exist")
        return self.t[name]


def coerce(col: str, v: Any, m: dict):
    """Python value for a DB column; ValueError when it does not fit."""
    t = m["data_type"]
    if v is None:
        return None
    try:
        if t == "date":
            return v if isinstance(v, date) else _date(v)
        if t.startswith("timestamp"):
            return v if isinstance(v, datetime) else datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        if t in ("integer", "bigint", "smallint"):
            d = _number(v)
            if d != d.to_integral_value():
                raise ValueError("not a whole number")
            return int(d)
        if t in ("numeric", "real", "double precision"):
            return v if isinstance(v, Decimal) else _number(v)
        if t == "boolean":
            if isinstance(v, bool):
                return v
            if str(v).lower() in ("true", "false"):
                return str(v).lower() == "true"
            raise ValueError("not true/false")
        if t == "uuid":
            return str(uuid.UUID(str(v)))
        if t in ("json", "jsonb"):
            return psycopg2.extras.Json(v)
        s = v if isinstance(v, str) else (json.dumps(v) if isinstance(v, (dict, list)) else str(v))
        if m.get("character_maximum_length") and len(s) > m["character_maximum_length"]:
            raise ValueError(f"{len(s)} characters, column holds {m['character_maximum_length']}")
        return s
    except (ValueError, InvalidOperation, TypeError) as e:
        raise ValueError(f"{col}: {e}") from None


# =====================================================================================================
# rows
# =====================================================================================================

class Row:
    """One row to be written: input values (cols), loader items evaluated lazily on `get`."""

    def __init__(self, L, table: str, rules, parent=None, rec: Rec | None = None, ctx: dict | None = None, pos: int = 0,
                 items: dict | None = None, key_col: str | None = None, literal_ok: bool = False):
        self.L, self.table, self.rules, self.parent, self.rec = L, table, rules, parent, rec
        self.cols: dict = {}
        self.items = dict(items or {})
        self.transient = dict(rec.transient) if rec else {}
        self.sources = dict(rec.sources) if rec else {}
        self.reasons = dict(rec.reasons) if rec else {}
        self.children: list = []
        self.ctx = ctx or {}
        self.pos = pos
        self.resolved: dict = {}
        self.key_col = key_col or (GRAPH[table][0] if table in GRAPH else None)
        self.mode = "insert"                  # insert | update | extend | update_only
        self.existing: dict | None = None
        self.literal_ok = literal_ok
        self.unset: set = set()
        self.keep: set = set()
        self.key_extra: tuple = ()
        self._busy: set = set()

    @property
    def path(self) -> str:
        return self.rec.path if self.rec else self.table

    def has(self, col: str) -> bool:
        """The row has / will have this column (a column the model may fill counts even when it left it null)."""
        return col in self.cols or col in self.items or col in self.transient or (
            self.rules is not None and col in self.rules.columns and not self.rules.columns[col].get("from_ref"))

    def get(self, col: str):
        if col in self.cols:
            return self.cols[col]
        if col in self.items and col not in self._busy and col not in self.unset and col not in self.keep:
            self._busy.add(col)
            try:
                v = vocab.evaluate(self.items[col], self, self.L, col)
            except NoValue as e:
                raise RowRejected(f"{col}: {e}") from None
            finally:
                self._busy.discard(col)
            if v is UNSET:
                (self.keep if str(self.items[col]).startswith("keep") else self.unset).add(col)
                return None
            self.cols[col] = self.L.coerce(self, col, v)
            return self.cols[col]
        return self.transient.get(col)

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


@dataclass
class LoadResult:
    cards: list = field(default_factory=list)          # [(table, id)] top-level rows written (not update_only)
    written: list = field(default_factory=list)        # [(table, id, is_card)] every row written (for the next re-run)
    rows: int = 0
    deleted: int = 0
    unresolved: list = field(default_factory=list)     # [{ref, name, table}]
    dropped: list = field(default_factory=list)        # [str]
    warnings: list = field(default_factory=list)
    created: list = field(default_factory=list)
    labels: list = field(default_factory=list)         # patent_classification: [{filing_id, category_label}]
    notes: list = field(default_factory=list)          # derive logs


class Loader:
    def __init__(self, cur, prompt_id: str, subject: str, output: dict, subject_row: dict | None = None,
                 client: dict | None = None):
        self.cur, self.prompt_id, self.subject_key, self.output = cur, prompt_id, subject, output
        self.subject = {k: v for k, v in (subject_row or {}).items() if not k.startswith("_")}
        self.subject_row = self.subject
        self.client = client or {}
        self.meta = Meta(cur)
        self.now = datetime.now(timezone.utc)
        self.today = self.now.date()
        self.out = LoadResult()
        self.n: dict = {}
        self.cards: list = []
        self.post: list = []
        self.labels: list = []
        self._tables: dict = {}
        self._countries: list | None = None
        self._names: set | None = None
        self.owned = self._owned_tables()
        self.allowed = self._all_tables()
        self.keep_previous: dict = {}        # table -> SQL condition (prompt file `keep_previous`): such a previous row survives a re-run

    # ---------------------------------------------------------------- spec helpers
    def _all_tables(self) -> set:
        found: set = set()

        def walk(t: TableRules):
            found.add(t.name)
            for c in [*t.children.values(), *t.loader_children.values()]:
                walk(c)

        for t in self.output.values():
            walk(t)
        return found

    def _owned_tables(self) -> set:
        """Tables whose key comes from the subject (subject.<col>): rows are updated in place, never bulk-deleted."""
        owned: set = set()

        def walk(t: TableRules):
            kc = GRAPH[t.name][0] if t.name in GRAPH else None
            tok = t.loader.get(kc)
            if isinstance(tok, str) and tok.startswith("subject."):
                owned.add(t.name)
            for c in [*t.children.values(), *t.loader_children.values()]:
                walk(c)

        for t in self.output.values():
            walk(t)
        return owned

    def uses_previous(self) -> bool:
        """A prompt keyed beyond (prompt_id, subject) leaves the subject's other cards alone on a re-run."""
        if getattr(self, "force_replace", False):
            return True
        return all(p in ("prompt_id", "subject") for t in self.output.values() if t.card for p in t.key)

    # ---------------------------------------------------------------- services used by the vocabulary
    def warn(self, msg: str):
        self.out.warnings.append(msg)

    def fill_text(self, s: str) -> str:
        from prompts import render
        return render.fill(s, self.client, self.subject, {}, "")

    def coerce(self, row: Row, col: str, v):
        meta = self.meta.table(row.table)
        if col not in meta:
            raise RowRejected(f"{row.table} has no column {col}")
        try:
            return coerce(col, v, meta[col])
        except ValueError as e:
            raise RowRejected(str(e)) from None

    def new_id(self, row: Row, col: str):
        dt = self.meta.table(row.table)[col]["data_type"]
        extra = row.key_extra if col == row.key_col else ()
        k = (row.table, extra)
        self.n[k] = self.n.get(k, -1) + 1
        return make_id(dt, id_seed(self.prompt_id, self.subject_key, row.table, self.n[k], extra))

    def stable_id(self, table: str, col: str, seed: str):
        return make_id(self.meta.table(table)[col]["data_type"], f"created|{table}|{seed}")

    def casefold_uuid(self, col: str, value):
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"kssl-{col}|{' '.join(str(value or '').casefold().split())}"))

    def alpha_rank(self, row: Row) -> int:
        def name(r: Row):
            return next((n for _, n in (r.rec.refs.values() if r.rec else [])), "").casefold()
        names = sorted(name(r) for r in self.cards if r.table == row.table)
        return names.index(name(row)) + 1

    def _rows_of(self, table: str) -> list:
        if table not in self._tables:
            self.cur.execute(f"SELECT * FROM staging.{table}")
            self._tables[table] = [dict(r) for r in self.cur.fetchall()]
        return self._tables[table]

    def name_of(self, idcol: str, value):
        if value is None or idcol not in ID_COLUMNS:
            return None
        table, ncol = ID_COLUMNS[idcol]
        return self.name_of_col(table, idcol, value, ncol)

    def name_of_col(self, table: str, idcol: str, value, col: str):
        if value is None:
            return None
        self.cur.execute(f"SELECT {col} AS v FROM staging.{table} WHERE {idcol}::text = %s", (str(value),))
        r = self.cur.fetchone()
        return r["v"] if r else None

    def ui_value(self, table: str, col: str):
        self.cur.execute(f"SELECT {col} AS v FROM staging_ui.{table} LIMIT 1")
        r = self.cur.fetchone()
        return r["v"] if r else None

    def country(self, name_or_code):
        if not name_or_code:
            return None
        if self._countries is None:
            self.cur.execute("SELECT country_name, iso2, region_name, latitude, longitude, aliases FROM staging.country_reference")
            self._countries = [dict(r) for r in self.cur.fetchall()]
        key = norm_name(str(name_or_code))
        for c in self._countries:
            if key in {norm_name(c["country_name"]), norm_name(c["iso2"]), *map(norm_name, c["aliases"] or [])}:
                return c
        return None

    def pillar(self, want_name: bool):
        self.cur.execute("SELECT pillar_id, pillar_name FROM staging.technology_pillar ORDER BY pillar_id")
        rows = self.cur.fetchall()
        if len(rows) != 1:
            raise NoValue(f"staging.technology_pillar has {len(rows)} rows; exactly one is needed to pick the pillar")
        return rows[0]["pillar_name"] if want_name else rows[0]["pillar_id"]

    fetch_images = True                    # False (or env KSSL_NO_IMAGE_FETCH=1): never fetch the article page for its og:image

    def article_image(self):
        """Thumbnail of the subject article: subject.image_url; else the image stored for the same url on competitive_news_article;
        else (when fetching is allowed) the og:image of the page, by backend/news.py parse_page. None when nothing is found."""
        if hasattr(self, "_image"):
            return self._image
        img = self.subject.get("image_url") or None
        url = next((self.subject.get(k) for k in ("article_url", "url", "source_url") if self.subject.get(k)), None)
        if not img and url:
            self.cur.execute("SELECT image_url FROM staging.competitive_news_article WHERE article_url = %s AND image_url IS NOT NULL LIMIT 1", (str(url),))
            r = self.cur.fetchone()
            img = r["image_url"] if r else None
        if not img and url and self.fetch_images and not os.environ.get("KSSL_NO_IMAGE_FETCH"):
            try:
                from backend import news
                resp = news.http(str(url), timeout=8)
                if resp.status == 200 and not news.page_blocked(resp):
                    img = news.parse_page(resp.text(), resp.url).image or None
            except Exception as e:  # noqa: BLE001  a missing thumbnail must never fail a load
                self.warn(f"thumbnail: could not read {str(url)[:80]} ({type(e).__name__})")
        self._image = img
        return img

    def article_published(self):
        """Publication date of the subject article: the harvested record (source_document.published_at) for its url, else the
        subject's own published_date (the news job's date). A date in the future is dropped. None = "date not known"."""
        url = next((self.subject.get(k) for k in ("article_url", "url", "source_url") if self.subject.get(k)), None)
        d = None
        if url:
            self.cur.execute("""SELECT published_at FROM staging.source_document WHERE url = %s AND published_at IS NOT NULL
                                ORDER BY published_at LIMIT 1""", (str(url),))
            r = self.cur.fetchone()
            d = r["published_at"] if r else None
        d = d or self.subject.get("published_date")
        if isinstance(d, datetime):
            d = d.date()
        return d if isinstance(d, date) and d <= date.today() else None

    def competitor_products_in_category(self, competitor_id):
        cat = self.subject.get("category_text") or self.subject.get("category_name")
        if competitor_id is None or not cat:
            return None
        self.cur.execute("""SELECT product_name FROM staging.competitive_product WHERE competitor_id = %s
                            AND lower(trim(category)) = lower(trim(%s)) ORDER BY product_name""", (competitor_id, cat))
        return ", ".join(r["product_name"] for r in self.cur.fetchall()) or None

    def find_or_create(self, row: Row, table: str, by: str):
        """id of the technology_source / technology_company row for this row's url / name; created if missing."""
        spec = row.rules.creates.get(table) if row.rules else None
        if spec is None:
            raise NoValue(f"{row.table} has no `creates: {table}` block")
        keycol = next((c for c, t in spec.items() if t in ("new_id_if_missing", "new_id")), None)
        matchcol = next((c for c, t in spec.items() if isinstance(t, str) and (t == by or t.endswith("." + by) or t.endswith("_" + by))), None)
        if keycol is None or matchcol is None:
            raise NoValue(f"`creates: {table}` needs a new_id_if_missing column and a column filled from '{by}'")
        tmp = Row(self, table, None, None, None, ctx={"src": row}, items=spec, key_col=keycol, literal_ok=True)
        value = tmp.get(matchcol)
        if not value:
            return None
        self.cur.execute(f"SELECT {keycol} AS id FROM staging.{table} WHERE lower(trim({matchcol}::text)) = lower(trim(%s)) LIMIT 1", (str(value),))
        r = self.cur.fetchone()
        if r:
            return r["id"]
        tmp.cols[keycol] = self.stable_id(table, keycol, str(value).strip().casefold())
        return self._insert_created(tmp, table, f"{table}: {value}")

    def _insert_created(self, tmp: Row, table: str, label: str):
        for c in list(tmp.items):
            tmp.get(c)
        self._fill_not_null(tmp, tmp.cols)
        names = [c for c in tmp.cols if c not in tmp.unset]
        self.cur.execute(f"INSERT INTO staging.{table} ({', '.join(names)}) VALUES ({', '.join(['%s'] * len(names))})",
                         [tmp.cols[c] for c in names])
        self.out.created.append(label)
        return tmp.cols[tmp.key_col]

    def create_location(self, name: str):
        """A ref_location that is not in competitive_geo_location yet: built with the loader block of that table."""
        rules = self.output.get("competitive_geo_location")
        items = dict(rules.loader) if rules else {"location_id": "new_id_if_missing", "country_name": "from_ref_location"}
        tmp = Row(self, "competitive_geo_location", None, None, None, ctx={"ref_name": name}, items=items, key_col="location_id",
                  literal_ok=True)
        tmp.cols["location_id"] = self.stable_id("competitive_geo_location", "location_id", norm_name(name))
        lid = self._insert_created(tmp, "competitive_geo_location", f"competitive_geo_location: {name}")
        self._tables.pop("competitive_geo_location", None)
        return {"id": lid, "row": {"location_id": lid, "country_name": tmp.cols.get("country_name")}, "table": "competitive_geo_location"}

    # ---------------------------------------------------------------- references
    def scope_for(self, ref: str, row: Row):
        chain = []
        r = row
        while r is not None:
            chain.append(r)
            r = r.parent
        if ref == "ref_product":
            return next((x.resolved["ref_competitor"]["id"] for x in chain if "ref_competitor" in x.resolved), self.subject.get("competitor_id"))
        if ref in ("ref_signal", "ref_partnership"):
            return self.subject.get("competitor_id")
        if ref == "ref_client_spec":
            return next((x.resolved["ref_client_product"]["id"] for x in chain if "ref_client_product" in x.resolved),
                        self.subject.get("client_product_id"))
        if ref == "ref_competitor_spec":
            if self.subject.get("product_id") is not None:
                return self.subject["product_id"]
            pname = next((x.cols.get("product_name") for x in chain if x.cols.get("product_name")), None)
            comp = self.subject.get("subject_id") if self.subject.get("company_role") == "competitor" else self.subject.get("competitor_id")
            if pname and comp:
                hit = match_name([r for r in self._rows_of("competitive_product") if str(r["competitor_id"]) == str(comp)],
                                 ["product_name"], pname)
                if len({h["product_id"] for h in hit}) == 1:
                    return hit[0]["product_id"]
        return None

    def resolve_filing(self, handle: str):
        """ref_filing: batch handle F001... -> filing_id (handles count the portfolio's filings by filing_id)."""
        m = re.fullmatch(r"[Ff](\d+)", str(handle).strip())
        pid = self.subject.get("portfolio_id")
        if not m or pid is None:
            return None
        rn = int(m.group(1))
        batch = self.subject.get("batch_no")
        if batch is not None and (rn - 1) // 60 != int(batch):
            return None
        self.cur.execute("SELECT filing_id FROM staging.competitive_patent_filing WHERE portfolio_id = %s ORDER BY filing_id OFFSET %s LIMIT 1",
                         (pid, rn - 1))
        r = self.cur.fetchone()
        return {"id": r["filing_id"], "row": {"filing_id": r["filing_id"]}, "table": "competitive_patent_filing"} if r else None

    def resolve(self, row: Row, ref: str, name: str):
        if ref == "ref_filing":
            return self.resolve_filing(name)
        table, idc, ncols, scope = REFS[ref]
        decl = row.rules.refs_decl.get(ref, "") if row.rules else ""
        if "." in decl and decl.split(".")[0] == table:
            ncols = [decl.split(".")[1]]
        rows = self._rows_of(table)
        scope_id = self.scope_for(ref, row) if scope else None
        if scope and scope_id is not None:
            rows = [r for r in rows if str(r.get(scope)) == str(scope_id)]
        hit = match_name(rows, ncols, name)
        ids = {h[idc] for h in hit}
        if len(ids) > 1:
            return None                                   # ambiguous: never guess
        if ids:
            return {"id": hit[0][idc], "row": hit[0], "table": table}
        if ref == "ref_location" and name.strip():
            return self.create_location(name.strip())
        return None

    # ---------------------------------------------------------------- building rows
    def _key_part(self, part: str, rec: Rec, pos: int) -> str:
        if part in rec.values:
            return str(rec.values[part])
        if part in rec.refs:
            return str(rec.refs[part][1])
        for _, name in rec.refs.values():
            if part in ("country", "partner", "title", "name"):
                return name
        if part in ("rank", "sequence", "position"):
            return str(pos)
        return next((n for _, n in rec.refs.values()), part)

    def _prime(self, row: Row):
        """Parent fk and key column default to parent_id / new_id unless the prompt says otherwise."""
        if row.key_col is None:
            return
        links = [fk for fk, p in GRAPH[row.table][2] if row.parent is not None and p == row.parent.table]
        for fk in links:
            if fk not in row.items and fk not in row.cols:
                row.items[fk] = "parent_id"
        if row.key_col not in row.items and row.key_col not in row.cols and row.key_col not in links:
            row.items[row.key_col] = "new_id"

    def build(self, rec: Rec, parent: Row | None, pos: int) -> Row:
        rules = rec.rules
        row = Row(self, rec.table, rules, parent, rec, pos=pos, items=rules.loader)
        meta = self.meta.table(rec.table)
        if rules.update_only:
            row.mode = "update_only"
        for target, (ref, name) in sorted(rec.refs.items(), key=lambda kv: (kv[1][0] != "ref_competitor", kv[1][0])):
            got = self.resolve(row, ref, name)
            if got is None:
                self.out.unresolved.append({"ref": ref, "name": name, "table": rec.table})
                raise RowRejected(f"{ref} '{name}' not found in the database")
            row.resolved[ref] = got
            if target in meta:
                text = meta[target]["data_type"] in TEXT_TYPES
                row.cols[target] = got["row"].get(REFS[ref][2][0]) if text and ref in REFS else got["id"]
                row.cols[target] = coerce(target, row.cols[target], meta[target])
            elif target in rules.transient:
                row.transient[target] = got["row"].get(REFS[ref][2][0]) if ref in REFS else got["id"]
        for col, v in rec.values.items():
            if col not in meta:
                raise RowRejected(f"{rec.table} has no column {col}")
            try:
                row.cols[col] = coerce(col, v, meta[col])
            except ValueError as e:
                raise RowRejected(str(e)) from None
        if row.mode == "update_only":
            ref = next((t for t, (r, _) in rec.refs.items() if t == r), None)       # the declared-only ref names the row
            if ref is None:
                raise RowRejected("update_only record names no row to update (needs its ref_*)")
            row.key_col = REFS[ref][1] if ref in REFS else "filing_id"          # the row is addressed by its id column
            row.cols[row.key_col] = row.resolved[ref]["id"]
            return row
        if parent is None and rules.card:
            row.key_extra = tuple(self._key_part(p, rec, pos) for p in rules.key if p not in ("prompt_id", "subject"))
        self._prime(row)
        counts: dict = {}
        for child in rec.children:
            p = counts.get(child.table, 0)
            try:
                row.children.append(self.build(child, row, p))
                counts[child.table] = p + 1
            except RowRejected as e:
                self.out.dropped.append(f"{child.path}: {e}")
        for tname, trules in rules.loader_children.items():
            self.expand(row, trules)
        return row

    # loader_only children: one row per ... (see FORMAT.md)
    def expand(self, row: Row, trules: TableRules):
        tokens = [t for t in trules.loader.values() if isinstance(t, str)]
        ctxs: list = []
        if trules.rows is not None:
            ctxs = [{"_rowspec": item} for item in trules.rows]
        else:
            ui = next((m for m in (re.match(r"from_ui\.(\w+)\.\w+$", t) for t in tokens) if m), None)
            prefix = next((m.group(1) for m in (re.match(r"copy_of_(\w+?)_\w+$", t) for t in tokens)
                           if m and any(vocab.tail_match(n, m.group(1)) for n in row.rules.children)), None)
            if ui:
                table = ui.group(1)
                order = "stage_order" if "stage_order" in self.meta_ui(table) else ("display_order" if "display_order" in self.meta_ui(table) else None)
                self.cur.execute(f"SELECT * FROM staging_ui.{table}" + (f" ORDER BY {order}" if order else ""))
                ctxs = [{"ui": {**dict(r), "_table": table}} for r in self.cur.fetchall()]
            elif prefix:
                ctxs = [{prefix: c} for c in row.children if vocab.tail_match(c.table, prefix)]
            elif trules.name == "competitive_matchup_source":
                urls: dict = {}
                for r in row.walk():
                    for entries in r.sources.values():
                        for e in entries:
                            if e["url"]:
                                urls.setdefault(e["url"], None)
                ctxs = [{"url": u} for u in urls]
            else:
                ctxs = [{}]
        made = 0
        for ctx in ctxs:
            items = dict(trules.loader)
            spec = ctx.pop("_rowspec", None)
            if spec:
                items.update(spec)
            child = Row(self, trules.name, trules, row, None, ctx=ctx, pos=made, items=items, literal_ok=spec is not None)
            self._prime(child)
            if spec:                                           # fixed rows: skip one whose copied narrative is empty
                copies = [c for c, t in spec.items() if isinstance(t, str) and t.startswith("copy_of_")]
                try:
                    if any(child.get(c) in (None, "") for c in copies):
                        continue
                except RowRejected:
                    continue
            row.children.append(child)
            made += 1

    def meta_ui(self, table: str) -> set:
        self.cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='staging_ui' AND table_name=%s", (table,))
        return {r["column_name"] for r in self.cur.fetchall()}

    # ---------------------------------------------------------------- evaluate / plan
    def finalize(self, row: Row):
        kept = []
        for ch in row.children:
            try:
                self.finalize(ch)
                kept.append(ch)
            except RowRejected as e:
                self.out.dropped.append(f"{ch.path}: {e}")
        row.children = kept
        if row.mode == "update_only":
            return
        for col in list(row.items):
            row.get(col)
        meta = self.meta.table(row.table)
        for col in row.cols:
            if col not in meta:
                raise RowRejected(f"{row.table} has no column {col}")

    def _fill_not_null(self, row: Row, cols: dict):
        for col, m in self.meta.table(row.table).items():
            if cols.get(col) is not None or col in row.unset or m["is_nullable"] == "YES" or m["column_default"] is not None:
                continue
            tok = row.items.get(col)
            if col in BOOKKEEPING:
                cols[col] = self.now
            elif isinstance(tok, str) and tok.startswith("from_ui.") and m["data_type"] in TEXT_TYPES:
                cols[col] = ""
            else:
                raise RowRejected(f"required column {col} has no value")

    def plan(self, row: Row):
        """Mode (insert / update / extend), NOT NULL bookkeeping; drops rows that cannot be written."""
        kept = []
        for ch in row.children:
            try:
                self.plan(ch)
                kept.append(ch)
            except RowRejected as e:
                self.out.dropped.append(f"{ch.path}: {e}")
        row.children = kept
        if row.mode == "update_only":
            return
        kc = row.key_col
        tok = row.items.get(kc)
        if row.mode != "extend" and row.parent is None and isinstance(tok, str) and tok.startswith("subject."):
            self.cur.execute(f"SELECT * FROM staging.{row.table} WHERE {kc}::text = %s", (str(row.cols.get(kc)),))
            ex = self.cur.fetchone()
            if ex:
                row.mode, row.existing = "update", dict(ex)
        if row.mode not in ("update", "extend"):
            self._fill_not_null(row, row.cols)

    # ---------------------------------------------------------------- deleting
    def delete_children(self, table: str, key) -> int:
        """Rows of the tables this prompt writes, below a card, per review.GRAPH (never subject-owned tables)."""
        n = 0
        for child, fk in review._children(table):
            if child not in self.allowed or child in self.owned:
                continue
            self.cur.execute(f"SELECT DISTINCT {GRAPH[child][0]}::text AS k FROM staging.{child} WHERE {fk}::text = %s", (str(key),))
            for r in self.cur.fetchall():
                n += self.delete_bundle(child, r["k"])
        return n

    def delete_bundle(self, table: str, key) -> int:
        n = self.delete_children(table, key)
        self._delete_row(table, key)
        return n + self.cur.rowcount

    def _delete_row(self, table: str, key):
        self.cur.execute("DELETE FROM staging.fact_source WHERE table_name = %s AND row_id = %s", (table, str(key)))
        self.cur.execute(f"DELETE FROM staging.{table} WHERE {GRAPH[table][0]}::text = %s", (str(key),))

    def _kept(self, table: str, key) -> bool:
        """A previous row that matches its table's keep_previous condition, or a child of such a row, is not deleted by a re-run
        (innovation_discovery: an innovation that innovation_detail has finished is no longer the discovery run's to replace)."""
        cond = self.keep_previous.get(table)
        if cond:
            self.cur.execute(f"SELECT 1 FROM staging.{table} WHERE {GRAPH[table][0]}::text = %s AND ({cond})", (str(key),))
            if self.cur.fetchone():
                return True
        for fk, parent in GRAPH[table][2]:
            pcond = self.keep_previous.get(parent)
            if pcond:
                self.cur.execute(f"SELECT 1 FROM staging.{parent} WHERE {GRAPH[parent][0]}::text = "
                                 f"(SELECT {fk}::text FROM staging.{table} WHERE {GRAPH[table][0]}::text = %s) AND ({pcond})", (str(key),))
                if self.cur.fetchone():
                    return True
        return False

    def delete_previous(self, previous: list) -> int:
        """The rows the last run of this subject wrote (prompt_run.loaded), except subject-owned ones."""
        n = 0
        for p in previous or []:
            t, i = p["table"], p["id"]
            if t in self.owned or t not in GRAPH or self._kept(t, i):
                continue
            if p.get("card", True):
                n += self.delete_bundle(t, i)
            else:
                self._delete_row(t, i)
                n += self.cur.rowcount
        return n

    # ---------------------------------------------------------------- writing
    def write(self, row: Row):
        out, kc = self.out, row.key_col
        meta = self.meta.table(row.table)
        cols = {c: v for c, v in row.cols.items() if c not in row.unset and c in meta}
        if row.mode == "insert":                  # a NOT NULL text column left to a derive step (classification) gets a placeholder; the hook sets it
            for c in row.unset:
                m = meta.get(c)
                if m and m["is_nullable"] == "NO" and m["column_default"] is None and m["data_type"] in TEXT_TYPES and str(row.items.get(c, "")).startswith("derive."):
                    cols[c] = ""
        key = row.cols.get(kc)
        if row.mode == "update_only":
            sets = {c: v for c, v in cols.items() if c != kc}
            if sets:
                self.cur.execute(f"UPDATE staging.{row.table} SET {', '.join(c + ' = %s' for c in sets)} WHERE {kc}::text = %s",
                                 [*sets.values(), str(key)])
            out.rows += 1
            self._facts(row)
            lab = row.transient.get("category_label") or row.cols.get("category_label")     # the filing now has the column: the ref lands in cols
            self.labels.append({"filing_id": str(key), "category_label": lab})
            return
        if row.mode == "extend":
            sets = {c: row.cols[c] for c in (row.rec.values if row.rec else {}) if c in meta and c != kc}
            if sets:
                self.cur.execute(f"UPDATE staging.{row.table} SET {', '.join(c + ' = %s' for c in sets)} WHERE {kc}::text = %s",
                                 [*sets.values(), str(key)])
            out.cards.append((row.table, str(key)))
            self._facts(row)
        elif row.mode == "update":
            if row.parent is None:
                self.delete_children(row.table, key)
            sets = {c: v for c, v in cols.items() if c != kc}
            self.cur.execute(f"UPDATE staging.{row.table} SET {', '.join(c + ' = %s' for c in sets)} WHERE {kc}::text = %s",
                             [*sets.values(), str(key)])
            out.rows += 1
            out.cards.append((row.table, str(key)))
            self._facts(row, replace=True)
        else:
            if row.parent is None:
                self.delete_bundle(row.table, key)
            else:
                self._delete_row(row.table, key)
            names = list(cols)
            self.cur.execute(f"INSERT INTO staging.{row.table} ({', '.join(names)}) VALUES ({', '.join(['%s'] * len(names))})",
                             [cols[c] for c in names])
            out.rows += 1
            if row.parent is None:
                out.cards.append((row.table, str(key)))
            self._facts(row)
        if row.table not in self.owned:
            out.written.append((row.table, str(key), row.parent is None))
        for ch in row.children:
            self.write(ch)

    def _facts(self, row: Row, replace: bool = False):
        ins = ("INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, retrieved_at) "
               "VALUES (%s, %s, %s, %s, %s, %s, %s, now())")
        rid = str(row.cols[row.key_col])
        if replace:
            self.cur.execute("DELETE FROM staging.fact_source WHERE table_name = %s AND row_id = %s", (row.table, rid))
        for col, entries in row.sources.items():
            for e in entries:
                if e["url"] is None:
                    self.cur.execute(ins, (row.table, rid, col, STORED_ROW_SOURCE, "stored", None, e["quote"]))
                    continue
                tier = classify(e["url"], self.company_domains(e["url"]))
                if tier is None:
                    tier = UNLISTED_TIER
                    self.out.warnings.append(f"{row.table}.{col}: source not on the allowlist: {e['url'][:100]}")
                publisher = self.subject.get("publisher") if e["url"] in map(str, self.subject.values()) else host_of(e["url"])
                self.cur.execute(ins, (row.table, rid, col, e["url"], tier, publisher, e["quote"]))
        for col, reason in row.reasons.items():
            self.cur.execute(ins, (row.table, rid, col, JUDGEMENT_SOURCE, JUDGEMENT_SOURCE, None, reason))

    def company_domains(self, url: str) -> tuple:
        """The url's host when it looks like a tracked company's own site (its name, without legal suffixes, is the
        host's main label); backend/sources.classify then calls it primary. There is no website column to ask."""
        if self._names is None:
            names = [self.client.get(k) for k in ("name", "legal_name", "brand_name")] + [self.subject.get("display_name")]
            for r in self._rows_of("competitive_competitor"):
                names += [r.get("display_name"), r.get("short_name"), r.get("legal_name")]
            self._names = {n for n in (compact_name(x) for x in names if x) if len(n) >= 5}
        host = host_of(url)
        parts = host.split(".")
        label = parts[-3] if len(parts) >= 3 and parts[-2] in ("co", "com", "gov", "org", "ac", "net") else (parts[-2] if len(parts) >= 2 else host)
        label = re.sub(r"[^a-z0-9]", "", label)
        if len(label) >= 5 and any(n == label or n.startswith(label) or label.startswith(n) for n in self._names):
            return (host,)
        return ()

    # ---------------------------------------------------------------- post steps
    def run_post(self):
        for kind, row in self.post:
            if kind == "partner_count" and row.cols.get("competitor_id") is not None:
                self.cur.execute("""UPDATE staging.competitive_partnership SET mapped_partner_count =
                        (SELECT count(*) FROM staging.competitive_partnership WHERE competitor_id = %s) WHERE competitor_id = %s""",
                                 (row.cols["competitor_id"], row.cols["competitor_id"]))

    def rebuild_patent_classification(self):
        """competitive_patent_classification of the subject's portfolio: counts of the labels of every batch
        (this run's, plus the latest loaded run of each other batch), each label written as 'rival' and 'field'."""
        rules = self.output.get("competitive_patent_classification")
        pid = self.subject.get("portfolio_id")
        if rules is None or pid is None or not self.labels:
            return
        batch = str(self.subject.get("batch_no"))
        counts: dict = {}
        for lab in self.labels:
            if lab["category_label"]:
                counts[lab["category_label"]] = counts.get(lab["category_label"], 0) + 1
        self.cur.execute("""SELECT DISTINCT ON (split_part(subject_key, '|', 2)) split_part(subject_key, '|', 2) AS batch, details -> 'labels' AS labels
                            FROM staging.prompt_run WHERE prompt_id = %s AND status = 'loaded' AND split_part(subject_key, '|', 1) = %s
                            ORDER BY split_part(subject_key, '|', 2), started_at DESC""", (self.prompt_id, str(pid)))
        for r in self.cur.fetchall():
            if r["batch"] != batch:
                for lab in r["labels"] or []:
                    if lab.get("category_label"):
                        counts[lab["category_label"]] = counts.get(lab["category_label"], 0) + 1
        self.cur.execute("DELETE FROM staging.competitive_patent_classification WHERE portfolio_id = %s", (pid,))
        for label, n in sorted(counts.items()):
            for lens in PORTFOLIO_LENSES:
                cid = make_id("uuid", f"{self.prompt_id}|{pid}|classification|{lens}|{label}")
                self.cur.execute("""INSERT INTO staging.competitive_patent_classification
                                    (classification_id, portfolio_id, category_label, filing_count, lens) VALUES (%s, %s, %s, %s, %s)""",
                                 (cid, pid, label, n, lens))
                self.out.rows += 1
        self.out.notes.append(f"competitive_patent_classification rebuilt: {sum(counts.values())} labelled filings in {len(counts)} categories")

    # ---------------------------------------------------------------- the run
    def load(self, valid: Validated, previous: list | None = None, derive_names: list | None = None) -> LoadResult:
        out = self.out
        tops, pos = [], {}
        for rec in valid.recs:
            p = pos.get(rec.table, 0)
            try:
                row = self.build(rec, None, p)
                pos[rec.table] = p + 1
                tops.append(row)
                self.cards.append(row)
            except RowRejected as e:
                out.dropped.append(f"{rec.path}: {e}")
        ready = []
        for row in tops:
            try:
                self.finalize(row)
                self.plan(row)
                ready.append(row)
            except RowRejected as e:
                out.dropped.append(f"{row.path}: {e}")
        if not ready:
            return out
        for t in self.output.values():
            if t.replace == "all_rows":
                self.cur.execute("DELETE FROM staging.fact_source WHERE table_name = %s", (t.name,))
                self.cur.execute(f"DELETE FROM staging.{t.name}")
                out.deleted += self.cur.rowcount
        if self.uses_previous():
            out.deleted += self.delete_previous(previous)
        for row in ready:
            self.cur.execute("SAVEPOINT card")
            before = (len(out.cards), len(out.written), out.rows, len(self.labels), len(self.post))
            try:
                self.write(row)
                self.cur.execute("RELEASE SAVEPOINT card")
            except Exception as e:  # noqa: BLE001  one card failing must not sink the run
                self.cur.execute("ROLLBACK TO SAVEPOINT card")
                out.dropped.append(f"{row.path}: write failed: {type(e).__name__}: {str(e).splitlines()[0]}")
                del out.cards[before[0]:], out.written[before[1]:], self.labels[before[3]:], self.post[before[4]:]
                out.rows = before[2]
        self.run_post()
        self.rebuild_patent_classification()
        out.labels = self.labels
        if (out.cards or out.rows) and derive_names:
            from prompts import derive
            derive.run(derive_names, self.cur, {
                "prompt_id": self.prompt_id, "subject": self.subject_key, "subject_row": self.subject, "cards": out.cards,
                "rows": out.written, "warnings": out.warnings, "notes": out.notes, "today": self.today,
                "transient": {(r.table, str(r.cols.get(r.key_col))): r.transient for t in ready for r in t.walk() if r.transient}})
        return out


# =====================================================================================================
# self-check
# =====================================================================================================

class _FakeCur:
    """Just enough cursor for Row/Loader pieces that touch no table."""
    def execute(self, *a, **k): raise AssertionError("no DB in the self-check")


def _selftest() -> None:
    import yaml
    from pathlib import Path
    from prompts import derive, render, vocab as V

    # -- ids: same seed same id, different n/subject differ; right type per column
    a = make_id("uuid", id_seed("signal", "A1", "competitive_signal", 0))
    assert a == make_id("uuid", id_seed("signal", "A1", "competitive_signal", 0))
    assert a != make_id("uuid", id_seed("signal", "A1", "competitive_signal", 1))
    assert a != make_id("uuid", id_seed("signal", "A2", "competitive_signal", 0))
    assert a != make_id("uuid", id_seed("moment", "A1", "competitive_signal", 0, ("https://x/a",)))
    assert str(uuid.UUID(a)) == a
    b = make_id("bigint", "x|y|t|0")
    assert isinstance(b, int) and 0 <= b < 2 ** 63 and b == make_id("bigint", "x|y|t|0")
    assert 0 <= make_id("integer", "x") < 2 ** 31
    try:
        make_id("date", "x")
        raise AssertionError("date id accepted")
    except ValueError:
        pass

    assert compact_name("Larsen & Toubro Limited") == "larsentoubro" and compact_name("Hanwha Aerospace") == "hanwhaaerospace"
    # -- reference matching
    rows = [{"competitor_id": 1, "display_name": "Larsen & Toubro", "short_name": "L&T", "legal_name": "Larsen & Toubro Limited"},
            {"competitor_id": 2, "display_name": "Hanwha Aerospace", "short_name": None, "legal_name": None},
            {"competitor_id": 3, "display_name": "Hanwha Defense", "short_name": None, "legal_name": None}]
    nc = ["display_name", "short_name", "legal_name"]
    assert match_name(rows, nc, "larsen & toubro")[0]["competitor_id"] == 1
    assert match_name(rows, nc, "L&T")[0]["competitor_id"] == 1
    assert match_name(rows, nc, "Larsen & Toubro Limited")[0]["competitor_id"] == 1
    assert match_name(rows, nc, "Hanwha Aerospace (South Korea)")[0]["competitor_id"] == 2   # context-list suffix
    assert match_name(rows, nc, "Hanwha") == [] and match_name(rows, nc, "") == []
    assert norm_name("  Adani Defence & Aerospace ") == "adani defence and aerospace"

    # -- every prompt file parses (spec extensions) and every loader token is known
    parsed = {}
    for pid in render.prompt_ids():
        spec = render.load_prompt(pid)
        render.required_context(spec)
        if not spec.get("handler"):                    # a handler prompt (news) is applied by its own module
            parsed[pid] = parse_output(spec["output"])
    assert len(parsed) >= 15, sorted(parsed)
    sig = parsed["signal"]["competitive_signal"]
    assert sig.card and sig.refs == {"ref_category": "category", "ref_competitor": "company_id"}
    assert sig.loader == {"sequence_no": "rank_by_event_date_desc", "classification": "derive.signal_label", "thumbnail_url": "article_image_url",
                          "published_date": "article_published_date"}
    ev = sig.children["competitive_signal_evidence"]
    assert ev.loader == {"evidence_id": "new_id", "display_order": "index", "source_url": "subject.article_url"} and ev.columns["evidence_group"]["required"]
    assert ev.count["min"] == 3 and ev.dedupe["against"] == ["title", "summary"] and set(sig.transient) == {"story_ref", "story_kind", "story_country", "story_product"}
    assert sig.columns["in_client_market"]["unknown_when_empty"] == "client_markets" and "competitive_product_news" in parsed["signal"]
    for bad in ({"competitive_signal": {"loader": {"x": "Not A Token!"}}},):
        try:
            parse_output(bad)
            raise AssertionError("bad loader value accepted")
        except ValueError:
            pass
    pm = parsed["moment"]["competitive_competitor_moment"]
    assert pm.columns["grade"]["enum"] == ["high", "watch"]          # moment v4: threat / watch only (rule s2)
    part = parsed["partnership"]["competitive_partnership"]
    assert "competitive_partnership_relationship_detail" in part.loader_children and part.children["competitive_partnership_evidence"]
    assert parsed["partnership"]["competitive_partnership_relationship_detail"].loader_only
    geo = parsed["geo"]["competitive_geo_company_presence"]
    gp = geo.children["competitive_geo_product"]
    assert set(gp.children) == {"competitive_geo_source", "competitive_geo_product_news"}      # geo v3: layer 1 only; the match rows are built by derive.geo_match_code
    assert gp.columns["product_range"]["from_ref"] == "ref_category" and "customer_name" in gp.columns and "local_partner" in gp.columns
    assert parsed["tender_assessment"]["market_tender_fit_assessment"].children["market_tender_product_match"].children[
        "market_tender_product_match_line"].transient["check"]["enum"] == ["met", "not_met", "unknown"]
    assert parsed["patent_classification"]["competitive_patent_filing"].update_only
    assert parsed["patent_classification"]["competitive_patent_filing"].transient["category_label"]["from_ref"] == "ref_category"
    assert parsed["top_opportunity"]["market_top_opportunity_tender"].replace == "all_rows"
    assert parsed["innovation_discovery"]["technology_innovation"].children["technology_innovation_source"].creates["technology_source"]["url"] == "transient.source_url"
    assert parsed["innovation_detail"]["technology_innovation"].loader_children["technology_innovation_analysis"].loader_only
    assert parsed["innovation_detail"]["technology_innovation"].loader_children["technology_innovation_analysis"].rows[0]["section_code"] == "background"
    assert parsed["opportunity"]["market_opportunity"].transient["country"]["max"] == 100
    assert parsed["opportunity"]["market_opportunity"].refs_decl == {"ref_opportunity": "market_opportunity.title"}

    # -- envelope: fences, prose around JSON, errors
    sig_enums = {"code_label.competitive_signal.direction": ["adverse", "favourable"],
                 "code_label.competitive_signal.time_to_effect": ["lt_1y", "1_3y", "gt_3y", "unknown"],
                 "code_label.competitive_signal.subtype_match": ["same", "adjacent", "none", "unknown"],
                 "code_label.competitive_signal.in_client_market": ["yes", "no", "unknown"],
                 "code_label.competitive_product_news.news_type": ["programme_order", "delivery_induction"], "empty.client_markets": False}
    sig_scores = {"direction": "Adverse", "time_to_effect": "1_3y", "subtype_match": "same", "in_client_market": "yes",
                  **{f"impact_{d}": 1 for d in ("orders_revenue", "market_standing", "supply_chain", "technology_gap", "partnerships", "policy_export", "funding")}}
    good = {"prompt_id": "signal", "subject": "s", "skip_reason": None, "records": [{
        "table": "competitive_signal",
        "values": {"title": "L&T wins order", "summary": "S.", **sig_scores, "probability": 5, "event_date": "2026-09-30",
                   "ref_competitor": "Larsen & Toubro", "ref_category": "Artillery",
                   "_sources": {"title": [{"url": "https://www.thehindu.com/x", "quote": "Q"}]},
                   "_reason": {"direction": "r"}},
        "children": {"competitive_signal_detail": [{"drawer_title": "D", "glance_who": "L&T", "glance_move": "Order", "glance_where": "India",
                                                    "what_article_says": "W.", "why_it_matters": "w"}],
                     "competitive_signal_evidence": [{"evidence_group": "fact", "label": "Customer", "value": "MoD", "quote": "q1"},
                                                     {"evidence_group": "key_point", "label": "Value", "value": "INR 900 crore for 50 launchers", "quote": "q2"},
                                                     {"evidence_group": "key_point", "label": "Option", "value": "An option for 20 more until 2029", "quote": "q3"},
                                                     {"evidence_group": "key_point", "label": "Delivery", "value": "Deliveries start in March 2028", "quote": "q4"},
                                                     {"evidence_group": "bogus", "label": "x"}]}}]}
    out = parsed["signal"]
    txt = json.dumps(good)
    assert parse_envelope("```json\n" + txt + "\n```") == good
    assert parse_envelope("Here you go:\n" + txt + "\nthanks") == good
    for bad in ("nope", "[1]", ""):
        try:
            parse_envelope(bad)
            raise AssertionError(f"accepted {bad!r}")
        except NotJson:
            pass
    v = validate(good, "signal", out, sig_enums)
    assert len(v.recs) == 1 and v.recs[0].values["direction"] == "adverse" and "classification" not in v.recs[0].values   # enum normalised; the label is the code's
    assert v.recs[0].refs == {"company_id": ("ref_competitor", "Larsen & Toubro"), "category": ("ref_category", "Artillery")}
    assert [c.table for c in v.recs[0].children] == ["competitive_signal_detail"] + ["competitive_signal_evidence"] * 4, [c.table for c in v.recs[0].children]
    assert any("bogus" in r for r in v.rejected)                                          # bad child row rejected, logged
    assert any(".probability" in w for w in v.warnings)                                  # judgement without a _reason
    assert v.recs[0].reasons == {"direction": "r"} and "title" in v.recs[0].sources
    try:
        validate(dict(good, prompt_id="other"), "signal", out)
        raise AssertionError("wrong prompt_id accepted")
    except EnvelopeError:
        pass
    sk = validate({"prompt_id": "signal", "skip_reason": "Not an event.", "records": []}, "signal", out)
    assert sk.skip_reason == "Not an event." and sk.recs == []

    def rejects(values, why, pid="signal", table="competitive_signal", enums=None):
        env = {"prompt_id": pid, "records": [{"table": table, "values": values}]}
        r = validate(env, pid, parsed[pid], enums if enums is not None else (sig_enums if pid == "signal" else None))
        assert not r.recs and any(why in x for x in r.rejected), (values, r.rejected)

    base = {**sig_scores, "ref_competitor": "Larsen & Toubro"}
    rejects({**base, "direction": "adverse"}, "title is required")
    rejects({**base, "title": "x" * 121}, "max 120")
    rejects({**base, "title": "t", "direction": "maybe"}, "not one of")
    rejects({**base, "title": "t", "probability": 6}, "not one of")
    rejects({**base, "title": "t", "event_date": "30/09/2026"}, "YYYY-MM-DD")
    rejects({**base, "title": "t", "colour": "red"}, "not allowed")
    rejects({**base, "title": "t", "classification": "threat"}, "not allowed")           # the model never writes the label
    rejects({**base, "title": "t", "company_id": "11111111-1111-1111-1111-111111111111"}, "not allowed")
    rejects({**base, "title": "t", "ref_tender": "x"}, "not a reference")
    rejects({**base, "title": "t", "impact_supply_chain": None}, "impact_supply_chain is required")
    assert "not allowed" in validate({"prompt_id": "signal", "records": [{"table": "market_tender", "values": {}}]}, "signal", out).rejected[0]
    assert "not allowed" in validate({"prompt_id": "partnership", "records": [{"table": "competitive_partnership_relationship_detail", "values": {}}]},
                                     "partnership", parsed["partnership"]).rejected[0]            # loader_only: never from the model

    # -- enum_from: context block codes (left of " = ") and ui columns (moment v4 has a fixed enum now, so a fixture keeps the old shape)
    import copy
    mo_out = copy.deepcopy(render.load_prompt("moment")["output"])
    mo_out["competitive_competitor_moment"]["columns"]["grade"] = {"judgement": True, "enum_from": "context.moment_levels"}
    parsed["moment"] = parse_output(mo_out)
    mom = lambda g: {"title": "T", "what_happened": "W", "movement_date": "2026-09-01", "source_url": "https://x/a", "grade": g}
    en = {"context.moment_levels": ["high", "watch", "opportunity"]}
    ok = validate({"prompt_id": "moment", "records": [{"table": "competitive_competitor_moment", "values": mom("HIGH")}]}, "moment", parsed["moment"], en)
    assert ok.recs[0].values["grade"] == "high"
    rejects(mom("critical"), "not one of", "moment", "competitive_competitor_moment", en)
    rejects(mom("high"), "not available", "moment", "competitive_competitor_moment", {})
    e = enum_sources(_FakeCur(), {"moment": parsed["moment"]["competitive_competitor_moment"]},
                     {"moment_levels": "high = High impact\nwatch = Watch\nopportunity = Opening for the client"})
    assert e == {"context.moment_levels": ["high", "watch", "opportunity"]}, e
    e = enum_sources(_FakeCur(), {"m": parsed["moment"]["competitive_competitor_moment"]}, {"moment_levels": "none on record"})
    assert e == {"context.moment_levels": []}

    # -- transient fields: accepted and checked, never stored; unknown ones refused
    lines = parsed["tender_assessment"]["market_tender_fit_assessment"].children["market_tender_product_match"].children["market_tender_product_match_line"]
    rec = validate_line = None
    tr_env = {"prompt_id": "tender_assessment", "records": [{"table": "market_tender_fit_assessment", "values": {"fit_grade": "strong"}, "children": {
        "market_tender_product_match": [{"fit_grade": "strong", "ref_client_product": "ATAGS", "children": {
            "market_tender_product_match_line": [{"line_label": "Calibre", "line_value": "x", "check": "met"},
                                                 {"line_label": "Range", "line_value": "y", "check": "maybe"}]}}]}}]}
    tv = validate(tr_env, "tender_assessment", parsed["tender_assessment"])
    pm_rec = tv.recs[0].children[0]
    assert [c.transient for c in pm_rec.children] == [{"check": "met"}] and any("maybe" in r for r in tv.rejected)
    assert "check" not in pm_rec.children[0].values

    # -- sources: an input row (no url) is kept with its quote
    sv = validate({"prompt_id": "moment", "records": [{"table": "competitive_competitor_moment", "values": {
        **mom("watch"), "_sources": {"title": [{"url": None, "quote": "SIGNAL: Range 41 km"}]}}}]}, "moment", parsed["moment"], en)
    assert sv.recs[0].sources["title"] == [{"url": None, "quote": "SIGNAL: Range 41 km"}]

    # -- vocabulary: every token form
    class FakeL:
        def __init__(s):
            s.subject = {"display_name": "Acme", "competitor_id": "c1", "company_role": "competitor", "subject_id": "c1"}
            s.now = datetime(2026, 10, 16, 9, 30, tzinfo=timezone.utc)
            s.today = date(2026, 10, 16)
            s.post = []
        def new_id(s, row, col): return f"id-{row.table}-{row.pos}"
        def coerce(s, row, col, v): return v
        def fill_text(s, t): return t.replace("{{client.name}}", "KSSL")
        def warn(s, m): pass
        def name_of(s, c, v): return {"category_id": {7: "Artillery"}}.get(c, {}).get(v)
        def country(s, n): return {"country_name": "India", "iso2": "IN", "latitude": 20.6, "longitude": 78.9, "region_name": "Asia"} if n == "India" else None
        def alpha_rank(s, row): return 2
        casefold_uuid = Loader.casefold_uuid

    L = FakeL()
    class R(Row):
        pass
    top = R(L, "competitive_partnership", None, key_col="relationship_id", items={})
    top.cols.update({"partner_name": "Rheinmetall", "competitor_id": "c1", "relationship_id": "p1", "client_position": "behind", "status": "open",
                     "event_date": date(2026, 9, 30), "country_name": "India", "fit_grade": "strong"})
    ev1 = R(L, "competitive_partnership_evidence", None, top, key_col="evidence_card_id", pos=0)
    ev1.cols.update({"evidence_card_id": "e1", "relationship_label": "MoU", "as_of_date": date(2025, 3, 1), "source_url": "https://www.thehindu.com/x/y",
                     "scope": "sc", "source_type": "Official source"})
    ev2 = R(L, "competitive_partnership_evidence", None, top, key_col="evidence_card_id", pos=1)
    ev2.cols.update({"evidence_card_id": "e2", "source_url": "https://www.reuters.com/z"})
    top.children = [ev1, ev2]
    det = R(L, "competitive_partnership_relationship_detail", None, top, ctx={"evidence": ev1}, key_col="detail_id", pos=0)
    top.children.append(det)
    ev = lambda tok, row=det, col="x": V.evaluate(tok, row, L, col)
    assert ev("new_id") == "id-competitive_partnership_relationship_detail-0" and ev("index", ev2) == 2 and ev("index_plus_1_of_output_order", ev1) == 1
    assert ev("parent_id") == "p1" and ev("subject.display_name") == "Acme" and ev("subject.subject_id_when_competitor") == "c1"
    assert ev("subject.subject_id_when_client") is None
    assert ev("run_date") == date(2026, 10, 16) and ev("run_time") == L.now and ev(False) is False and ev(True) is True
    assert ev("host_of_source_url", ev1) == "thehindu.com" and ev("host_of_url", ev1) == "thehindu.com"
    assert ev("copy_of_evidence_relationship_label") == "MoU" and ev("copy_of_evidence_as_of_date") == date(2025, 3, 1)
    assert ev("copy_of_evidence_source_url") == "https://www.thehindu.com/x/y" and ev("evidence_card_id") == "e1"
    assert ev("{subject.display_name} <-> {partner_name}") == "Acme <-> Rheinmetall"
    assert ev("{subject.display_name} - {relationship_label} - {year of as_of_date}") == "Acme - MoU - 2025"
    assert ev("{subject.display_name} - {relationship_label} - {year of nothing}") == "Acme - MoU"
    assert ev("copy_of_source_url", ev1) == "https://www.thehindu.com/x/y"
    assert ev("count_evidence_cards", top) == 2 and ev("true_when_evidence_exists", top) is True and ev("count_children", top) == 3
    assert ev("count_partners_of_competitor", top) is UNSET and L.post == [("partner_count", top)]
    assert ev("derive.matchup_edge") is UNSET and ev("keep") is UNSET and ev("keep_stub_value") is UNSET
    assert ev("constant_candidate") == "candidate" and ev("same_as_relationship_id", ev1) == "p1"
    assert ev("rank_by_event_date_desc", top) == (date(2100, 1, 1) - date(2026, 9, 30)).days
    top.cols["event_date"] = None
    assert ev("rank_by_event_date_desc", top) == (date(2100, 1, 1) - date(2026, 10, 16)).days           # null -> run date
    assert ev("rank_by_country", top) == 2
    assert ev("label_of_status", top) == "Open" and ev("status_is_open", top) is True
    u1 = ev("uuid5_of_casefolded_partner_name", top)
    top.cols["partner_name"] = "  RHEINMETALL "
    assert u1 == ev("uuid5_of_casefolded_partner_name", top) and str(uuid.UUID(u1)) == u1       # same partner, any case / spacing
    assert ev("country_reference_table", top, "country_code") == "IN" and ev("country_reference_table", top, "latitude") == 20.6
    top.cols["due_date"] = date(2026, 11, 5)
    assert ev("due_date_formatted_as_d_mon_yyyy", top) == "5 Nov 2026"
    assert ev({"behind": "{{client.name}} behind", "ahead": "ahead"}, ev1) == "KSSL behind"        # keyed by a parent's client_position
    top.cols["client_position"] = None
    assert ev({"behind": "b"}, ev1) is None                                                           # null stays null
    top.cols["category_id"] = 7
    assert ev("name_of_category_id", top) == "Artillery" and ev("title_of_category_id", top) == "Artillery"
    top.cols["title"] = "Long-Range Rocket  System!"
    assert ev("category_id_dash_slug_of_title", top) == "7-long-range-rocket-system"
    # timeline / project
    proj = R(L, "competitive_project", None, key_col="project_id")
    proj.cols["stage"] = "Contract"
    t1 = R(L, "competitive_project_timeline", None, proj, key_col="timeline_id")
    t1.cols.update({"event_date": date(2026, 1, 1), "event_title": "Awarded", "is_expected": False})
    t2 = R(L, "competitive_project_timeline", None, proj, key_col="timeline_id")
    t2.cols.update({"event_date": date(2026, 6, 1), "event_title": "Trials", "is_expected": False})
    t3 = R(L, "competitive_project_timeline", None, proj, key_col="timeline_id")
    t3.cols.update({"event_date": date(2027, 1, 1), "event_title": "Delivery", "is_expected": True})
    proj.children = [t1, t2, t3]
    st = R(L, "competitive_project_stage", None, proj, ctx={"ui": {"_table": "ui_project_stage_step", "stage_name": "Contract", "stage_order": 3}}, key_col="project_stage_id")
    proj.children.append(st)
    assert ev("title_of_latest_past_timeline_event", proj) == "Trials" and ev("date_of_latest_past_timeline_event", proj) == date(2026, 6, 1)
    assert ev("from_ui.ui_project_stage_step.stage_name", st) == "Contract" and ev("from_ui.ui_project_stage_step.stage_order", st) == 3
    st.cols["stage_name"] = "Contract"
    assert ev("stage_name_equals_project_stage", st) is True
    # specs
    mu = R(L, "competitive_matchup_specification", None, None, key_col="comparison_specification_id")
    mu.resolved = {"ref_client_spec": {"id": 1, "row": {"spec_name": "Range", "value_text": "41 km", "value_numeric": Decimal("41"), "unit": "km", "spec_group": "Fire"}},
                   "ref_competitor_spec": {"id": 2, "row": {"spec_label": "Range", "spec_value": "38", "unit": "km"}}}
    assert ev("copy_from_client_spec", mu, "client_value_text") == "41 km" and ev("copy_from_client_spec", mu, "client_value_numeric") == Decimal("41")
    assert ev("copy_from_client_spec", mu, "unit") == "km" and ev("copy_from_client_spec_else_none", mu, "spec_group") == "Fire"
    assert ev("copy_from_competitor_spec", mu, "competitor_value_text") == "38"
    assert ev("parse_plain_number_of_competitor_spec_value_else_null", mu) == Decimal("38")
    mu.resolved["ref_competitor_spec"]["row"]["spec_value"] = "about 38 km"
    assert ev("parse_plain_number_of_competitor_spec_value_else_null", mu) is None
    mu.resolved.pop("ref_client_spec")
    assert ev("copy_from_client_spec_else_competitor_spec", mu, "unit") == "km" and ev("copy_from_client_spec", mu, "unit") is None
    assert V.plain_number("1,200") is None and V.plain_number("-3.5") == Decimal("-3.5")
    rr = R(L, "competitive_geo_product_match", None, None, key_col="match_id")
    rr.resolved = {"ref_client_product": {"id": 9, "row": {"product_name": "ATAGS", "client_product_id": 9}}}
    assert ev("resolved_ref_client_product_id", rr) == 9 and ev("resolved_ref_client_product_name", rr) == "ATAGS"
    # fit label order, matched
    a1 = R(L, "market_tender_fit_assessment", None, key_col="assessment_id")
    cf = [R(L, "market_tender_competitor_fit", None, a1, key_col="competitor_fit_id", pos=i) for i in range(3)]
    for r_, lab in zip(cf, ("weak", "strong", "partial")):
        r_.cols["fit_label"] = lab
    a1.children = list(cf)
    assert [ev("sort_by_fit_label_strong_partial_weak_then_output_order", r_) for r_ in cf] == [3, 1, 2]
    assert ev("matched_when_a_product_match_exists_else_no_match", a1) == "no_match"
    a1.children.append(R(L, "market_tender_product_match", None, a1, key_col="tender_match_id"))
    assert ev("matched_when_a_product_match_exists_else_no_match", a1) == "matched"
    # tech overview
    oc = R(L, "technology_overview_company", None, None, key_col="overview_company_id")
    assert ev("competitor_when_ref_competitor_resolves_else_third_party", oc) == "third_party"
    oc.resolved["ref_competitor"] = {"id": 1, "row": {}}
    assert ev("competitor_when_ref_competitor_resolves_else_third_party", oc) == "competitor"
    osr = R(L, "market_opportunity_source", None, None, key_col="source_id")
    osr.cols["source_type"] = "official"
    assert ev("single_source_unless_publisher_is_official", osr) == "official"
    osr.cols["source_type"] = "news"
    assert ev("single_source_unless_publisher_is_official", osr) == "single_source"
    # unknown / literal
    try:
        ev("no such token!")
        raise AssertionError
    except Exception:
        pass
    lit = R(L, "technology_innovation_analysis", None, key_col="analysis_id", literal_ok=True)
    assert V.evaluate("background", lit, L, "section_code") == "background"

    # -- placeholders
    client, subj, ctx = {"name": "KSSL"}, {"headline": "H", "published_date": date(2026, 9, 1), "none": None}, {"categories": "Artillery"}
    assert render.fill("{{client.name}} / {{ subject.headline }} / {{subject.published_date}} / {{context.categories}} / {{documents}}",
                       client, subj, ctx, "DOC") == "KSSL / H / 2026-09-01 / Artillery / DOC"
    assert render.fill("{{subject.none}}", client, subj, ctx, "") == render.NONE_ON_RECORD
    for bad in ("{{client.nope}}", "{{subject.nope}}", "{{context.nope}}", "{{wat.x}}", "{{nothing}}"):
        try:
            render.fill(bad, client, subj, ctx, "")
            raise AssertionError(f"{bad} accepted")
        except render.PromptError:
            pass
    # subject placeholders in a documents query become bound parameters
    q, args = render.bind_subject("SELECT 1 WHERE a = '{{subject.cid}}' AND b = {{subject.n}} AND c LIKE 'x%' AND lower(trim('{{subject.cat}}')) = z",
                                  {"cid": "u1", "n": 5, "cat": "Artillery"})
    assert q == "SELECT 1 WHERE a = %(cid)s AND b = %(n)s AND c LIKE 'x%%' AND lower(trim(%(cat)s)) = z" and args == {"cid": "u1", "n": 5, "cat": "Artillery"}, q
    try:
        render.bind_subject("SELECT {{subject.zzz}}", {"cid": 1})
        raise AssertionError("unknown subject column accepted")
    except render.PromptError:
        pass
    shared = yaml.safe_load((Path(render.HERE) / "_shared.yml").read_text(encoding="utf-8"))
    rendered = render.fill(shared["system"], {"name": "KSSL", "legal_name": "L", "headquarters": "H"}, {}, {}, "")
    assert "{{" not in rendered and "KSSL" in rendered and '"prompt_id"' in rendered
    t = render.load_prompt("signal")
    assert t["model"] and t["version"] and render.required_context(t) == ["client", "client_portfolio", "client_capabilities", "client_markets", "client_partners",
                                                                        "competitors_extended", "categories", "stories", "competitor_catalogue"]
    html_doc = ("<html><head><title>T</title></head><body><nav>menu menu menu menu</nav><article><p>" + "Sentence one is here. " * 30
                + "</p><p>" + "Another paragraph follows. " * 20 + "</p></article><footer>footer text</footer></body></html>")
    title, text = render.page_text(html_doc)
    assert title == "T" and "Sentence one" in text and "menu" not in text and "footer" not in text

    # -- derive rules
    assert derive.gap_value(110, 90) == 20 and derive.gap_value(None, 1) is None and derive.gap_value(0, 0) is None
    assert derive.edge_score(0, 0) is None and derive.edge_score(3, 3) == 88 and derive.edge_score(0, 4) == 10
    assert derive.edge_score(1, 1) == 75 and derive.edge_score(0, 1) == 25 and derive.edge_score(50, 50) == 98
    assert [derive.decision_level(x) for x in (None, 41, 42, 57, 58)] == [None, 1, 2, 2, 3]
    assert derive.fit_percent(3, 4) == 75 and derive.fit_percent(1, 2) is None and derive.fit_percent(0, 3) == 0
    assert derive.lean_code("strong") == "go" and derive.lean_code("partial") == "maybe" and derive.lean_code("weak") == "pass"
    assert derive.overlap_status(["matched", "category_only"]) == "confirmed" and derive.overlap_status(["category_only"]) == "category" \
        and derive.overlap_status([]) == "none"
    assert set(derive.REGISTRY) >= {"matchup_edge", "renumber_signals", "tender_fit", "geo_rollup", "geo_match_edge"}
    # -- routine: recurring (entity-keyed) vs event-keyed prompts, dependency order, quote check
    from prompts import run as R
    sp = {pid: render.load_prompt(pid) for pid in render.prompt_ids()}
    assert sorted(pid for pid, x in sp.items() if not R.recurring(x)) == sorted(
        pid for pid, x in sp.items() if x["subject"]["key"] in R.EVENT_KEYS or x.get("handler")), "event prompts"
    assert R.recurring(sp["moment"]) and R.recurring(sp["partnership"]) and not R.recurring(sp["signal"]) and not R.recurring(sp["tender"])
    assert R.recurring(dict(sp["signal"], recurring=True)) and not R.recurring(dict(sp["moment"], recurring=False))
    order = R.ordered_ids()
    assert order.index("tender") < order.index("tender_assessment") < order.index("top_opportunity") and         order.index("innovation_discovery") < order.index("innovation_detail") and order.index("opportunity") < order.index("top_opportunity")
    qv = validate(good, "signal", out, sig_enums)
    qv.recs[0].sources["title"][0]["quote"] = "L&T wins the “Pinaka” order today"
    assert R.quote_check(qv, 'x https://www.thehindu.com/x  l&t WINS the "pinaka" order\ntoday') == []           # case / quotes / spacing
    assert R.quote_check(qv, "unrelated https://www.thehindu.com/x text") != []                      # url fetched, quote absent
    assert R.quote_check(qv, "no such url in the prompt") == []                                      # web page: cannot be checked
    _selftest_rules()
    print("loader self-check ok")


def _selftest_rules() -> None:
    """The foundations rules of prompts/spec.py (plain English, glance limits, key-point count / dedupe, unknown_when_empty, evidence
    pointer) on a synthetic output spec: no DB, no prompt file."""
    from prompts import plain_english as PE

    def spec(**over):
        ev = {"columns": ["evidence_group", "label", "value", "quote"], "enum": {"evidence_group": ["fact", "key_point"]},
              "dedupe": {"column": "value", "against": ["title", "summary"], "where": {"evidence_group": "key_point"}},
              "count": {"min": 3, "max": 6, "where": {"evidence_group": "key_point"}}}
        top = {"card": True, "columns": {"title": {"required": True}, "summary": {"plain": "strict"},
                                         "probability": {"type": "number"},
                                         "in_client_market": {"enum": ["yes", "no", "unknown"], "unknown_when_empty": "client_markets"}},
               "children": {"competitive_signal_detail": {"columns": ["drawer_title", "glance_who", "glance_move", "glance_when", "why_it_matters"],
                                                          "plain": {"why_it_matters": "warn"}},
                            "competitive_signal_evidence": ev}}
        top.update(over)
        return parse_output({"competitive_signal": top})

    def run(out, values=None, children=None, enums=None):
        v = {"title": "Veland orders 24 NV-155 wheeled guns from Nordvik", "summary": "Veland's army signed for 24 NV-155 truck-mounted 155 mm guns, with deliveries from 2028."}
        v.update(values or {})
        pts = [("fact", "Customer", "Veland Ministry of Defence")] + [("key_point", f"P{i}", t) for i, t in enumerate((
            "An option for 12 more guns can be taken until the end of 2029.", "Final assembly takes place at Veland Motor Works, a ministry condition.",
            "The ministry quoted 40 km with base-bleed ammunition as the accepted range.", "The contract covers training and an initial spares package."))]
        kids = {"competitive_signal_evidence": [{"evidence_group": g, "label": lab, "value": val} for g, lab, val in pts]}
        kids.update(children or {})
        r = validate({"prompt_id": "signal", "records": [{"table": "competitive_signal", "values": v, "children": kids}]}, "signal", out, enums or {"empty.client_markets": False})
        r.warnings = [w for w in r.warnings if "facts without _sources" not in w]          # (the sources rule is not under test here)
        return r

    out = spec()
    ok = run(out)
    assert len(ok.recs) == 1 and not ok.rejected and not ok.warnings, (ok.rejected, ok.warnings)
    assert [c.table for c in ok.recs[0].children] == ["competitive_signal_evidence"] * 5
    # glance fields: hard length limits and the move list apply with no rule in the prompt file
    det = lambda **k: {"competitive_signal_detail": [{"drawer_title": "D", **k}]}
    v = run(out, children=det(glance_who="x" * 41))
    assert any("glance_who is 41 characters, max 40" in r for r in v.rejected) and len(v.recs[0].children) == 5
    assert not run(out, children=det(glance_who="x" * 40, glance_when="y" * 60, glance_move="Export approval")).rejected
    assert any("glance_when" in r for r in run(out, children=det(glance_when="y" * 61)).rejected)
    assert any("glance_move='Weird'" in r for r in run(out, children=det(glance_move="Weird")).rejected)
    assert next(c for c in run(out, children=det(glance_move="contract")).recs[0].children if c.table == "competitive_signal_detail").values["glance_move"] == "Contract"        # case-insensitive, stored as listed
    # plain English: strict rejects the hard findings and warns for the soft ones; warn only warns
    v = run(out, {"summary": "The deal gives a robust base."})
    assert not v.recs and any("plain English (strict)" in r and "robust" in r for r in v.rejected)
    v = run(out, {"summary": " ".join(["Word"] * 25) + "."})
    assert v.recs and any("summary: plain English: sentence of 25 words" in w for w in v.warnings)
    v = run(out, children=det(why_it_matters="It will leverage local assembly."))
    assert v.recs and any("why_it_matters: plain English: banned phrase 'leverage'" in w for w in v.warnings)
    v = run(out, {"summary": "The FOO order was placed."}, det(why_it_matters="The FOO plant opens."))
    assert sum("acronym FOO" in w for w in v.warnings) == 1                                                                # explained once per record, across columns
    # key points: restating rows are dropped with a warning; fewer than 3 rejects the card; more than 6 is trimmed
    pts = lambda *t: {"competitive_signal_evidence": [{"evidence_group": "key_point", "label": "x", "value": x} for x in t]}
    v = run(out, children=pts("Veland orders 24 NV-155 guns from Nordvik.", "An option for 12 more guns until the end of 2029.", "Final assembly is at Veland Motor Works.",
                              "The ministry quoted 40 km as the accepted range.", "The contract covers training and spares."))
    assert [c.values["value"][:6] for c in v.recs[0].children] == ["An opt", "Final ", "The mi", "The co"] and any("restates the title" in w for w in v.warnings)
    v = run(out, children=pts("Veland orders 24 NV-155 guns from Nordvik.", "An option for 12 more guns until the end of 2029.", "Final assembly is at Veland Motor Works."))
    assert not v.recs and any("competitive_signal_evidence (evidence_group=key_point): 2 row(s), at least 3 needed" in r for r in v.rejected)
    v = run(out, children={"competitive_signal_evidence": [{"evidence_group": "fact", "label": "a", "value": "b"}] * 9})
    assert not v.recs                                                                                                      # facts do not count as key points
    many = [f"Point number {i} mentions item {chr(97 + i)}{i}{i} and place Q{i}Z{i}." for i in range(9)]
    v = run(out, children=pts(*many))
    assert v.recs and len(v.recs[0].children) == 6 and any("9 rows, only the first 6 kept" in w for w in v.warnings)
    soft = spec()
    soft["competitive_signal"].children["competitive_signal_evidence"].count["min_action"] = "warn"
    v = run(soft, children=pts("An option for 12 more guns until the end of 2029."))
    assert v.recs and any("at least 3 wanted" in w for w in v.warnings)
    # unknown_when_empty: yes / no are refused while the block is empty; unknown is always fine; coerce sets unknown
    v = run(out, {"in_client_market": "yes"}, enums={"empty.client_markets": True})
    assert not v.recs and any("in_client_market='yes' but the client_markets context block is empty" in r for r in v.rejected)
    assert run(out, {"in_client_market": "unknown"}, enums={"empty.client_markets": True}).recs and run(out, {}, enums={"empty.client_markets": True}).recs
    assert run(out, {"in_client_market": "yes"}, enums={"empty.client_markets": False}).recs[0].values["in_client_market"] == "yes"
    v = run(out, {"in_client_market": "yes"}, enums={"other": []})
    assert v.recs and any("client_markets' was not checked" in w for w in v.warnings)
    co = spec()
    co["competitive_signal"].columns["in_client_market"]["unknown_when_empty"] = {"block": "client_markets", "action": "coerce"}
    v = run(co, {"in_client_market": "no"}, enums={"empty.client_markets": True})
    assert v.recs[0].values["in_client_market"] == "unknown" and any("set to 'unknown'" in w for w in v.warnings)
    fake = _FakeCur()
    assert enum_sources(fake, out, {"client_markets": "none on record"}) == {"empty.client_markets": True}
    assert enum_sources(fake, out, {"client_markets": "India = sells, since 2019"}) == {"empty.client_markets": False}
    assert enum_sources(fake, out, {"client_markets": "  \n"}) == {"empty.client_markets": True}
    try:
        enum_sources(fake, out, {})
        raise AssertionError("missing block accepted")
    except ValueError:
        pass
    # enum_from: code_label.<table>.<column> reads the active codes of ui.code_label
    class CL:
        def __init__(self, rows): self.rows, self.args = rows, None
        def execute(self, sql, args): self.args = args
        def fetchall(self): return self.rows

    cl = parse_output({"competitive_signal": {"columns": {"time_to_effect": {"enum_from": "code_label.competitive_signal.time_to_effect"}}}})
    c = CL([{"code": "lt_1y"}, {"code": "1_3y"}])
    assert enum_sources(c, cl, {}) == {"code_label.competitive_signal.time_to_effect": ["lt_1y", "1_3y"]} and c.args == ("competitive_signal", "time_to_effect")
    try:
        enum_sources(CL([]), cl, {})
        raise AssertionError("empty code list accepted")
    except ValueError:
        pass
    # evidence pointer (table rule reason_pointer): a reason that names no sourced value or quote is a warning
    rp = spec(reason_pointer=True, columns={"title": {"required": True}, "summary": {"judgement": True}})
    base = {"summary": "S", "_sources": {"title": [{"url": "https://www.thehindu.com/x", "quote": "Veland's Ministry of Defence signed a contract on 9 October"}]}}
    v = run(rp, {**base, "_reason": {"summary": "It is indirect."}}, children={})
    assert any("names no value or quote" in w for w in v.warnings)
    v = run(rp, {**base, "_reason": {"summary": "The contract signed on 9 October decides the order."}}, children={})
    assert not any("names no value or quote" in w for w in v.warnings)
    # spec errors
    for bad in ({"columns": {"x": {"plain": "loud"}}}, {"columns": ["x"], "plain": {"x": "sometimes"}}, {"count": {"minimum": 2}}, {"count": {"min": 1, "min_action": "x"}},
                {"dedupe": {"column": "v"}}, {"columns": {"x": {"unknown_when_empty": 5}}}):
        try:
            parse_output({"competitive_signal": bad})
            raise AssertionError(f"bad spec accepted: {bad}")
        except ValueError:
            pass
    # table-level lists: plain: [a, b] means warn; every prompt file that uses unknown_when_empty names a block it renders
    assert parse_output({"competitive_signal": {"columns": ["a", "b"], "plain": ["a", "b"]}})["competitive_signal"].columns["a"]["plain"] == "warn"
    from prompts import render
    for pid in render.prompt_ids():
        sp = render.load_prompt(pid)
        if sp.get("handler"):
            continue
        for t in parse_output(sp["output"]).values():
            stack = [t]
            while stack:
                x = stack.pop()
                stack += list(x.children.values())
                for col, r in {**x.columns, **x.transient}.items():
                    if r.get("unknown_when_empty"):
                        assert spec_block(r["unknown_when_empty"]) in (sp.get("context") or []), f"{pid}.{col}: block not in context"
    assert PE.CLIENT_NAMES == ("KSSL",)
    # thumbnail_url: loader token article_image_url -> subject image, else the stored news image, else (fetching off here) nothing
    pt = parse_output({"competitive_signal": {"columns": ["title"], "loader": {"thumbnail_url": "article_image_url"}}})
    assert pt["competitive_signal"].loader == {"thumbnail_url": "article_image_url"}

    class C1:
        def __init__(self, row): self.row = row
        def execute(self, *a): pass
        def fetchone(self): return self.row

    def img(subject, row=None):
        x = Loader.__new__(Loader)
        x.subject, x.cur, x.fetch_images = subject, C1(row), False
        x.out = LoadResult()
        return x.article_image()

    assert img({"image_url": "https://i.test/a.jpg", "article_url": "https://x.test/a"}) == "https://i.test/a.jpg"
    assert img({"article_url": "https://x.test/a"}, {"image_url": "https://i.test/b.jpg"}) == "https://i.test/b.jpg"
    assert img({"article_url": "https://x.test/a"}, None) is None and img({}, None) is None

    # published_date: loader token article_published_date -> harvested record's date, else the subject's, never a future date
    def pub(subject, row=None):
        x = Loader.__new__(Loader)
        x.subject, x.cur = subject, C1(row)
        return x.article_published()

    assert pub({"article_url": "https://x.test/a", "published_date": date(2026, 9, 2)}, {"published_at": date(2026, 9, 1)}) == date(2026, 9, 1)
    assert pub({"article_url": "https://x.test/a", "published_date": date(2026, 9, 2)}, None) == date(2026, 9, 2)
    assert pub({"article_url": "https://x.test/a"}, {"published_at": date(2999, 1, 1)}) is None and pub({}, None) is None


def spec_block(v) -> str:
    return v["block"] if isinstance(v, dict) else v


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)
