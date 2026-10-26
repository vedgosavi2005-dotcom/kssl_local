/* SIGN-IN (owner 22 Oct: temporary login; 25 Oct: the frontend team's login page, the API locked with a session, terms saved on
   the server). The live API checks the password (POST /api/login, hashes in the gitignored .env) and sets an HttpOnly session
   cookie (backend/auth.py); with KSSL_LOGIN_REQUIRED=1 every data call needs it. The page never trusts its own storage: at
   start-up it asks GET /api/session who is signed in. localStorage "kssl_user" only names the user for the usage log
   (lib/track.js) and the top bar. */
import { REVIEW } from "../components/review/Review";

const KEY = "kssl_user";
const WRITE = { "Content-Type": "application/json", "X-KSSL-Write": "1" };

// on for the live site in local dev; a build turns it on with VITE_LOGIN=1. The review site never asks.
const ENV = import.meta.env || {};   // node test bundles have no import.meta.env
export const LOGIN_REQUIRED = !REVIEW && (ENV.DEV || ENV.VITE_LOGIN === "1");

const remember = (user) => {
  try {
    if (user) localStorage.setItem(KEY, user);
    else localStorage.removeItem(KEY);
  } catch (e) {
    /* storage blocked: the session cookie still works */
  }
};

export function currentUser() {
  try {
    return localStorage.getItem(KEY) || null;
  } catch (e) {
    return null;
  }
}

/* {user, termsAccepted} of the signed-in user, or null */
export async function session() {
  try {
    const r = await fetch("/api/session", { headers: { Accept: "application/json" } });
    if (!r.ok) return null;
    const body = await r.json();
    remember(body.user);
    return body;
  } catch (e) {
    return null;
  }
}

export async function login(user, password) {
  const r = await fetch("/api/login", { method: "POST", headers: WRITE, body: JSON.stringify({ user, password }) });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || "Could not sign in");
  remember(body.user);
  return body;
}

export async function acceptTerms() {
  const r = await fetch("/api/terms/accept", { method: "POST", headers: WRITE });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || "Could not save your acceptance");
  return body;
}

/* the cookie is dropped by the server; then the page reloads to the sign-in screen */
export async function logout() {
  try {
    await fetch("/api/logout", { method: "POST", headers: WRITE });
  } catch (e) {
    /* offline: the cookie expires on its own */
  }
  remember(null);
  location.reload();
}
