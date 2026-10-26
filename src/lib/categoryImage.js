/* The default picture of a product category (owner 2026-10-25): public/img/category/*.jpg, public-domain photos listed in
   public/img/category/CREDITS.md. Matched on the category's words, so "Uavs & Drones" and "UAVs & Drones" both find uav.jpg.
   null for a category with no picture. */
const RULES = [
  [/aircraft|aerostructure/, "aircraft"], [/ammunition/, "ammunition"], [/artillery/, "artillery"], [/c4isr|comms|\bew\b/, "c4isr"],
  [/missile|air defen/, "missiles"], [/marine|naval/, "naval"], [/\bmro\b/, "mro"], [/armou?red vehicle|protected/, "vehicles"],
  [/sensor|electro/, "sensors"], [/small arms/, "small-arms"], [/training|simulation/, "training"], [/uav|drone/, "uav"],
  [/component|forging/, "components"], [/^other$/, "other"],
];

export function categoryImage(category) {
  const c = String(category || "").toLowerCase().trim();
  const hit = RULES.find(([re]) => re.test(c));
  return hit ? `${(import.meta.env && import.meta.env.BASE_URL) || "/"}img/category/${hit[1]}.jpg` : null;
}
