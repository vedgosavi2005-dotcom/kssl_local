"""Area E: globals that belong to no page area. Today: sectionVisibility.

ui.section_visibility(section_key, visible, note) -> {section_key: bool}. The UI helper isVisible(data, key) is true
only for an explicit True, so a section with no row is hidden (MAPPING.md C1 / A: sectionVisibility).
"""

from backend.common import table, text


def build(database, d):
    # rupees per one unit, from the stored official rates (serving.fx_rate, scripts/load_fx_rates.py): the UI converts
    # every stated amount to INR with these and only these (src/lib/tenderValue.js)
    d["fxRates"] = {text(r.get("currency_code")).strip().upper(): float(r["inr_per_unit"])
                    for r in table(database, "serving", "fx_rate") if r.get("currency_code") and r.get("inr_per_unit")}
    d["sectionVisibility"] = {
        text(r.get("section_key")): bool(r.get("visible"))
        for r in table(database, "ui", "section_visibility") if r.get("section_key")
    }
