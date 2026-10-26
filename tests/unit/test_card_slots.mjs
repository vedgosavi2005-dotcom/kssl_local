// Product cards: the same four labels across a category; components split out by their stored type
import assert from "node:assert/strict";
import { cardSpecsFor, isComponent } from "../../src/lib/cardSlots.js";

const ammo = (key) => ({ category: "Ammunition", vs: "artillery_ammo", sheet: { key } });
const a = cardSpecsFor(ammo([{ l: "Calibre", v: "155 mm" }, { l: "Complete round mass", v: "45 kg" }]));
const b = cardSpecsFor(ammo([{ l: "Muzzle velocity", v: "945 m/s" }, { l: "Maximum range", v: ["40 km", "52 km (base bleed)"] }]));
assert.deepEqual(a.map(([l]) => l), b.map(([l]) => l));                         // same four labels on every ammunition card
assert.deepEqual(a, [["Calibre", "155 mm"], ["Projectile mass", "45 kg"], ["Muzzle velocity", "—"], ["Maximum range", "—"]]);
assert.equal(b[3][1], "40 km; 52 km (base bleed)");
const sight = { category: "Small Arms", vs: "accessory", sheet: { key: [{ l: "Magnification", v: "1x" }, { l: "Weight", v: "300 g" }] } };
assert.ok(isComponent(sight) && !isComponent({ vs: "assault_rifle" }) && !isComponent({}));
assert.deepEqual(cardSpecsFor(sight), [["Magnification", "1x"], ["Weight", "300 g"]]);      // a component keeps its own figures
assert.deepEqual(cardSpecsFor({ category: "Other", sheet: { key: [{ l: "Density", v: "1.6" }] } }), [["Density", "1.6"]]);
console.log("card slots ok");
