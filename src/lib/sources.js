/* Where sources show (owner 2026-10-22):
     review site  -- a source on everything
     live site    -- sources only on what was read from articles or notices (signals, news, movement, stories,
                     projects, partnerships, geo, tenders, awards, innovations); curated records (company
                     details, leaders, product specs, patents, KPI tiles) show none
   import.meta.env is undefined under node (unit tests): that reads as the live site. */
export const REVIEW_SITE = !!(import.meta.env && import.meta.env.VITE_REVIEW === "1");
export const showCuratedSources = REVIEW_SITE;
