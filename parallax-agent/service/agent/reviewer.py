"""The design reviewer: a second pair of eyes on every view before it reaches the canvas.

The UI agent proposes a spec; spec.validate() has already removed anything that names a
column that does not exist. The reviewer checks what validation cannot: that the view
answers the question, that the chart form fits the data, that each KPI tile's number is
the one its label promises, that nothing will be unreadable (40 bars, 12 series, a donut
of 20 slices), and that the summary only states numbers present in the data. It returns
the spec unchanged or a corrected one; the correction is validated again before use, and
if it is worse (fewer widgets survive) the original stands."""

import functools
import json

from . import adapter, config, spec
from .llm import LLMError, get_llm

@functools.lru_cache(maxsize=1)
def review_system() -> str:
    return f"""You are the design reviewer for the Parallax canvas, a dark analytics panel in a competitive-intelligence platform for {adapter.client()['name']}. You receive the user's question, the result sets (columns, sample rows, stats) and a proposed view spec. Check it and return either the same spec (verdict approve) or a corrected one (verdict revise) with the issues you fixed.

Check, in order:
1. It answers the question: the first widget after any KPI row shows the comparison, ranking, trend or breakdown that was asked for.
2. The form fits the data's job: ranking -> bar sorted value_desc (horizontal when labels are long or there are more than 8 categories); time -> line or column with sort x_asc; share of a whole -> donut with at most 7 slices, else a bar; two numeric measures -> scatter; two categorical dimensions -> heatmap; hierarchy -> treemap; flows -> sankey; relationships -> network. No form with more than about 12 bars on a vertical axis or more than 8 series.
3. KPI tiles state exactly what the label says. A per-company or per-segment tile needs filter_field and filter_value. Two tiles with different labels must not compute the same thing. Sum counts and amounts; average ratios and specs; never sum percentages or averages.
4. Aggregates match the column: aggregate none or avg for values that are already totals per row being shown once; sum when rows split a total.
5. Layout: widths pair up across each row of 12 (full; half + half; third x 3); no duplicate widgets; a table when the rows are entities the user may want to read.
6. The summary and subtitles only state numbers that appear in, or follow directly from, the result rows and stats. Remove any that don't.
7. Click actions point at real columns and make sense (filter on the column the mark shows; navigate only with an id column).
8. Subsets: when the question, a title or the summary names a subset (one segment, country, company, year) and the result holds more than that, every widget showing it needs filter_field/filter_value for that subset (check the stats' value_counts to see what the result holds).

The rows you see are a SAMPLE (rows_shown of row_count); the canvas receives every row. Judge whole-result facts (how many companies, totals) from row_count and stats (distinct values, sums), never from the sample alone, and never "correct" a figure the stats support. Remove any text that talks about samples, previews or rows shown.

Change only what is wrong. Keep every field of the schema; unused strings "", unused arrays []."""

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["approve", "revise"]},
        "issues": {"type": "array", "items": {"type": "string"}},
        "spec": spec.VIEW_SCHEMA,
    },
    "required": ["verdict", "issues", "spec"],
    "additionalProperties": False,
}


def _strip(clean: dict) -> dict:
    """The validated spec back in schema shape (drop the server-added widget ids)."""
    out = {k: v for k, v in clean.items() if k in spec.VIEW_SCHEMA["properties"]}
    out["widgets"] = [{k: v for k, v in w.items() if k != "id"} for w in clean["widgets"]]
    return out


async def review(question: str, results: list, clean: dict, conv_results: dict, rids: list, emit) -> tuple:
    """Return (spec, notes). Never raises: a failed review keeps the proposed spec."""
    emit({"type": "status", "stage": "review", "text": "Reviewing the design"})
    payload = {"question": question, "results": [rs.preview(n=60, cell_chars=160) for rs in results], "proposed_spec": _strip(clean)}
    try:
        turn = await get_llm().turn(
            role="reviewer", model=config.REVIEW_MODEL, system=review_system(),
            messages=[{"role": "user", "content": json.dumps(payload, default=str)}],
            effort=config.REVIEW_EFFORT, max_tokens=16000, output_schema=REVIEW_SCHEMA)
        if turn.stop_reason == "refusal":
            return clean, []
        out = turn.json()
    except LLMError as exc:
        return clean, [f"design review skipped: {exc}"]
    if out.get("verdict") != "revise":
        return clean, []
    revised, warnings = spec.validate(out.get("spec") or {}, conv_results, rids)
    if len(revised["widgets"]) < max(1, len(clean["widgets"]) - 1):
        return clean, [f"review discarded (it dropped widgets): {warnings[:3]}"]
    return revised, [f"review: {i}" for i in (out.get("issues") or [])][:8]
