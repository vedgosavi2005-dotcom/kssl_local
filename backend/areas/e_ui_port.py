"""Area E: globals that belong to no page area. Today: sectionVisibility.

ui.section_visibility(section_key, visible, note) -> {section_key: bool}. The UI helper isVisible(data, key) is true
only for an explicit True, so a section with no row is hidden (MAPPING.md C1 / A: sectionVisibility).
"""

from backend.common import table, text


def build(database, d):
    d["sectionVisibility"] = {
        text(r.get("section_key")): bool(r.get("visible"))
        for r in table(database, "ui", "section_visibility") if r.get("section_key")
    }
