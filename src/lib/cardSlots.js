/* The four figures on a product card, the same four for every card of a category (owner 2026-10-26: "all the ammunition boxes
   should be the same; same for artillery, aircraft ..."). Each slot takes the first of its labels the product's spec sheet
   (product.sheet, backend/spec_sheet.py) carries; a product without any of them shows "—" in that slot, so the labels line up.
   A category not listed here keeps the product's own first four figures (its products are too mixed for one set).
   Components and accessories (a sight, a fuze, an aerostructure part ...) are split from a category's products by their stored
   type (product.vs = product_class sub_type) and keep their own first four figures. */

export const CARD_SLOTS = {
  "Ammunition": [["Calibre"], ["Projectile mass", "Complete round mass", "Weight"], ["Muzzle velocity"], ["Maximum range", "Effective range", "Range"]],
  "Artillery": [["Calibre"], ["Maximum range", "Range"], ["Rate of fire"], ["Weight", "Combat weight", "Weight in action"]],
  "Small Arms": [["Calibre"], ["Weight"], ["Barrel length", "Overall length"], ["Magazine capacity", "Effective range"]],
  "Protected & Armoured Vehicles": [["Configuration"], ["Gross vehicle weight", "Combat weight", "Weight"], ["Maximum road speed", "Maximum speed"], ["Operating range", "Range"]],
  "Missiles & Air Defence": [["Maximum range", "Range"], ["Warhead"], ["Guidance", "Guidance and seeker", "Seeker"], ["Launch mass", "Weight"]],
  "UAVs & Drones": [["Endurance"], ["Range"], ["Payload", "Warhead"], ["Maximum take-off weight", "Weight"]],
  "Aircraft & Aerostructures": [["Maximum speed"], ["Range", "Combat radius"], ["Maximum take-off weight", "Empty weight"], ["Engines", "Engine", "Thrust"]],
  "Marine / Naval": [["Length"], ["Displacement", "Weight"], ["Maximum speed", "Speed"], ["Range", "Endurance"]],
  "Sensors & Electro-optics": [["Sensor type"], ["Frequency band"], ["Detection range"], ["Weight"]],
  "C4ISR, Comms & EW": [["Frequency range", "Frequency band"], ["Power", "Transmit power", "Power consumption"], ["Interfaces", "Waveforms"], ["Weight"]],
  "Precision Components & Forgings": [["Component type"], ["Material"], ["Process"], ["Qualification"]],
};

// product types that are a part of, or an add-on to, another product
export const COMPONENT_TYPES = new Set([
  "accessory", "fuze_component", "assembly_subsystem", "machined_component", "support_equipment", "support_system",
  "aerostructure_part", "engine_avionics", "naval_sensor_system",
]);

export const isComponent = (p) => !!(p && p.vs && COMPONENT_TYPES.has(String(p.vs).split("/")[0]));

const SECTIONS = ["key", "other", "armament"];
const valueText = (v) => (Array.isArray(v) ? v.join("; ") : String(v ?? ""));

/* [[label, value], ...] for a card: the category's four slots, or the product's own first four figures */
export function cardSpecsFor(p) {
  const sheet = (p && p.sheet) || null;
  const rows = sheet ? SECTIONS.flatMap((s) => (Array.isArray(sheet[s]) ? sheet[s] : [])) : [];
  const slots = CARD_SLOTS[p && p.category];
  if (slots && !isComponent(p) && rows.length) {
    const byLabel = new Map(rows.map((r) => [String(r.l).toLowerCase(), r]));
    return slots.map((names) => {
      const r = names.map((n) => byLabel.get(n.toLowerCase())).find(Boolean);
      return [names[0], r ? valueText(r.v) : "—"];
    });
  }
  if (sheet && Array.isArray(sheet.key)) return sheet.key.slice(0, 4).map((r) => [r.l, valueText(r.v)]);
  return Object.entries((p && p.specs) || {}).slice(0, 4);
}
