/* One card per story: the latest signal of a stored story stands for the event; it carries the story's signal count.
 *
 *     node --test tests/unit/test_club_by_story.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import { clubByStory, capThreats } from "../../src/lib/overview.js";

const C = (id, storyId, ago, dir = "threat", seq = 0, risk = 10) => ({ id, storyId, ago, dir, seq, risk });

test("episodes of one story fold into the latest; cards without a story stand alone", () => {
  const out = clubByStory([
    C("apr", "s1", "2026-04-02", "watch"), C("oct12", "s1", "2026-10-12"), C("oct15", "s1", "2026-10-15"),
    C("solo", null, "2026-09-01", "watch"), C("other", "s2", "2026-08-01"),
  ]);
  assert.deepEqual(out.map((c) => c.id), ["oct15", "solo", "other"]);
  assert.equal(out[0].episodes, 3);
  assert.equal(out[2].episodes, undefined, "a one-signal story shows no count");
});

test("same day: the later sequence wins; an undated episode never beats a dated one", () => {
  assert.equal(clubByStory([C("a", "s", "2026-10-01", "watch", 1), C("b", "s", "2026-10-01", "watch", 2)])[0].id, "b");
  assert.equal(clubByStory([C("dated", "s", "2026-01-01"), C("undated", "s", null)])[0].id, "dated");
});

test("the threat cap counts stories, not episodes", () => {
  const cards = [...Array.from({ length: 12 }, (_, i) => C(`ep${i}`, "big", `2026-10-${String(i + 1).padStart(2, "0")}`)),
    ...Array.from({ length: 5 }, (_, i) => C(`t${i}`, `s${i}`, "2026-09-01"))];
  const shown = capThreats(clubByStory(cards), 10);
  assert.equal(shown.length, 6, "1 clubbed story + 5 others, all threats, under the cap");
});
