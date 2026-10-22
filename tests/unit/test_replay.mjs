/* Session replay: the playback clock and captions (owner 22 Oct).
 *
 *     node tests/unit/test_replay.mjs
 */
import { replaySelfCheck } from "../../src/lib/replay.js";

const bad = replaySelfCheck();
console.log(bad.length ? "FAIL: " + bad.join("; ") : "all pass");
if (bad.length) process.exit(1);
