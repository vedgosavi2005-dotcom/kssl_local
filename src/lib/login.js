/* TEMPORARY LOGIN (owner 22 Oct: "a temporary login for user1, to test locally"; the real login page comes later).
   The live API checks the password (POST /api/login, hashes in the gitignored .env); a pass stores the user id in
   localStorage "kssl_user", which the usage log (lib/track.js) puts on every event, so the review site's Session
   replay can find this user's visits. Log out clears it.
   ponytail: a gate on the UI only -- the API itself is not locked, and there is no session token. Fine for a local
   test; the real login must lock the API too. */
import { REVIEW } from "../components/review/Review";

const KEY = "kssl_user";

// on for the live site in local dev; a build turns it on with VITE_LOGIN=1. The review site never asks.
export const LOGIN_REQUIRED = !REVIEW && (import.meta.env.DEV || import.meta.env.VITE_LOGIN === "1");

export function currentUser() {
  try {
    return localStorage.getItem(KEY) || null;
  } catch (e) {
    return null;
  }
}

export async function login(user, password) {
  const r = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-KSSL-Write": "1" },
    body: JSON.stringify({ user, password }),
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || "Could not sign in");
  localStorage.setItem(KEY, body.user);
  return body.user;
}

export function logout() {
  try {
    localStorage.removeItem(KEY);
  } catch (e) {
    /* storage blocked: nothing stored either */
  }
  location.reload();
}
