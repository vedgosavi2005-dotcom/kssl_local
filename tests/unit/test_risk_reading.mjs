/* The risk assessment in plain words: each check's reason and the analytical reading (owner 22 Oct).
 *
 *     node tests/unit/test_risk_reading.mjs
 */
import { riskReadingSelfCheck } from "../../src/lib/riskReading.js";

const bad = riskReadingSelfCheck();
console.log(bad.length ? "FAIL: " + bad.join("; ") : "all pass");
if (bad.length) process.exit(1);
