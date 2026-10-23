"""At a glance in plain words (backend/areas/a_competitive.glance_value).   python tests/unit/test_glance_plain.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from backend.areas.a_competitive import glance_value as g

D = "·"
assert g("glance_move", "Capacity", "KSSL") == "Added production capacity" and g("glance_move", "Odd", "KSSL") == "Odd"
assert g("glance_impact", f"Orders {D} high", "KSSL") == "Big effect on KSSL's orders"
assert g("glance_impact", f"Policy {D} medium", "KSSL") == "Some effect on KSSL through policy"
assert g("glance_when", f"23 Oct 2026 {D} Army adoption decision after soldier use", "KSSL") == "23 Oct 2026"
assert g("glance_when", f"18 Sep 2026 (published) {D} no later date stated", "KSSL") == "18 Sep 2026"
assert g("glance_when", "Saturday (date not stated)", "KSSL") is None                      # no date: row dropped ...
assert g("glance_when", "Saturday (date not stated)", "KSSL", "2026-10-18") == "18 Oct 2026"  # ... or the article's date
print("glance ok")
