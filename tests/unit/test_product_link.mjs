/* A name on a tender is a link only when it is a model in a company's catalogue.
 *
 *     node tests/unit/test_product_link.mjs
 */
import assert from "node:assert/strict";
import { productOwner } from "../../src/lib/productLink.js";

const d = { competitors: {
  R: { products: [{ name: "Beta 90 DX (Mk3)" }] },
  A: { products: [{ name: "Gamma 12" }] },
  OWN: { products: [{ name: "Alpha 155 (Series 2)" }] },
} };
assert.equal(productOwner(d, "Gamma 12").cid, "A");
assert.equal(productOwner(d, "Alpha 155 (Series 2)").cid, "OWN");
// letters and digits only, case ignored; the owner's spelling comes back
assert.equal(productOwner(d, "beta 90 dx mk3").cid, "R");
assert.equal(productOwner(d, "beta 90 dx mk3").productName, "Beta 90 DX (Mk3)");
// a label that is not a model is not a link
assert.equal(productOwner(d, "Service job: no product to quote"), null);
assert.equal(productOwner(null, "x"), null);
assert.equal(productOwner(d, ""), null);
console.log("ok - productOwner links catalogue models only");
