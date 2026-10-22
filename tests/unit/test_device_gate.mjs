/* Desktop only: phones and tablets are refused, also in "desktop site" mode (owner 22 Oct).
 *
 *     node tests/unit/test_device_gate.mjs
 */
import { deviceSelfCheck } from "../../src/lib/device.js";

const bad = deviceSelfCheck();
console.log(bad.length ? "FAIL: " + bad.join("; ") : "all pass");
if (bad.length) process.exit(1);
