import { STANCES } from "./chrome.js";
/* THREAT: a stored judgement, read as it is.

   A competitor's threat level is a field of its row (serving.competitive_competitor.threat_level, shipped as
   `threat`: threat or watch; any other stored value is no stance). A signal's direction is the stored `dir`. This module only reads
   the first. The browser used to re-grade competitor signals with keyword lists (which subsystems a client does
   not build, which markets count as home, which partners to excuse) and to write its own reasons; those are
   analyst judgements the database does not hold, so they are gone. A field that is absent reads as null. */
export const threatOf = (c) => {
  const v = c && c.threat;
  return STANCES.includes(v) ? v : null;
};
