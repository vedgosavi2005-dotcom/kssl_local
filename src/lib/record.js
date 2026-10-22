/* PAGE RECORDING (owner 23 Oct; live site only): rrweb records the page itself -- a snapshot of it, then every change, the
   mouse and scrolling -- so the review site's player shows a visit exactly as the person saw it: that day's data, that day's
   UI. The usage log (track.js) says WHAT was done; this says what the screen looked like. -> POST /api/track/rec ->
   activity.recording (db/setup/37_activity_recording.sql), under the same session id as the usage log (track.js sets
   window.__ksslSession on every event). Masked as the usage log is: passwords (and e-mail / phone boxes) never leave the
   browser. Off on the review site and while the replay player drives the page. Do Not Track is not honoured (owner 23 Oct:
   every visit is logged and recorded). */
import { record } from "rrweb";
import { REVIEW_SITE } from "./sources.js";

const FLUSH_MS = 4000;
const CHECKOUT_MS = 10 * 60 * 1000;   // a fresh full snapshot every 10 minutes: a lost upload costs at most that much
const NO_SESSION_MAX = 20000;         // events held while the usage log has no session id yet; past this it never will: stop

function start() {
  let visitor = null;
  try {
    visitor = localStorage.getItem("kssl_visitor");
  } catch (e) {
    /* storage blocked: track.js has an id for this page load only, which we cannot see */
  }
  let sid = null;
  let buf = [];

  const send = async (events, session, leaving) => {
    let user = null;
    try {
      user = localStorage.getItem("kssl_user");
    } catch (e) {
      /* storage blocked */
    }
    const qs = new URLSearchParams({ session, visitor: visitor || session, ...(user ? { user } : {}) });
    const json = JSON.stringify(events);
    let body = json;
    // gzip in the browser (a page snapshot is a few MB of text); not on page exit, where there is no time to wait for it
    if (!leaving && typeof CompressionStream !== "undefined") {
      body = await new Response(new Blob([json]).stream().pipeThrough(new CompressionStream("gzip"))).blob();
    }
    fetch(`/api/track/rec?${qs}`, { method: "POST", keepalive: !!leaving && json.length < 60000, body,
                                    headers: { "Content-Type": "application/octet-stream", "X-KSSL-Write": "1" } })
      .catch(() => {});                  // the recording never breaks the page
  };
  const flush = (leaving) => {
    if (!sid || !buf.length) return;
    const events = buf;
    buf = [];
    send(events, sid, leaving).catch(() => {});
  };

  const stop = record({
    emit(e) {
      if (window.__ksslReplay) return;
      const s = window.__ksslSession || null;    // read on every event: login, logout and 30 min idle start a new session
      if (s && sid && s !== sid) {               // a new session starts with its own snapshot, so it plays on its own
        flush();
        sid = s;
        record.takeFullSnapshot(true);           // emits the snapshot through here, now under the new session
        return;                                  // ponytail: the one event that noticed the change is dropped; the snapshot shows its result
      }
      if (s) sid = s;                            // the first session id: what was recorded before it (the page load) is its
      buf.push(e);
      if (!sid && buf.length > NO_SESSION_MAX) {  // the usage log is not running (blocked storage...): do not hold memory
        buf = [];
        setTimeout(() => stop && stop(), 0);
      }
    },
    checkoutEveryNms: CHECKOUT_MS,
    maskInputOptions: { password: true, email: true, tel: true },
    slimDOMOptions: true,
    sampling: { mousemove: 50, scroll: 150, input: "last" },
  });

  setInterval(flush, FLUSH_MS);
  addEventListener("pagehide", () => flush(true));
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") flush(); });
}

if (typeof window !== "undefined" && typeof document !== "undefined" && !REVIEW_SITE) {
  try {
    start();
  } catch (e) {
    /* never break the app for the recording */
  }
}
