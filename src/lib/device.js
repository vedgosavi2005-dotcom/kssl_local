/* DESKTOP ONLY (owner 22 Oct): the site opens on a laptop / desktop / Mac, never on a phone or tablet -- also not
   when the phone or tablet browser is switched to "desktop site", which swaps the user agent and the page width but
   not the device. So no single signal decides; any one of these says "not a computer":

     - the browser's own flag (navigator.userAgentData.mobile, Chromium);
     - a phone / tablet user agent;
     - an iPad in desktop mode: it reports a Mac user agent, but Macs have no touch screen;
     - no fine pointer at all (no mouse, no trackpad): every computer has one, a phone in desktop mode does not;
     - a phone-sized screen: screen.width / height are the device's, whatever page width desktop mode asks for.

   A touch-screen laptop passes: it has a trackpad (fine pointer) and a laptop-sized screen.
   ponytail: a client-side check -- someone who edits the page or the API calls can get past it; it keeps phones and
   tablets out, it is not access control. */

export const MIN_SHORT_SIDE = 600;    // CSS px; phones are ~360-430, tablets 744+ but caught by touch / pointer / user agent

export function isDesktop(env = browserEnv()) {
  const ua = env.ua || "";
  if (env.uaMobile === true) return false;
  if (/Android|iPhone|iPad|iPod|Mobile|Tablet|Silk|Kindle|PlayBook|BlackBerry|Opera Mini|IEMobile|webOS/i.test(ua)) return false;
  if (/Macintosh/i.test(ua) && env.touchPoints > 1) return false;
  if (env.anyFinePointer === false) return false;
  if (env.shortSide && env.shortSide < MIN_SHORT_SIDE) return false;
  return true;
}

export function browserEnv() {
  const n = typeof navigator !== "undefined" ? navigator : {};
  const mm = (q) => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia(q).matches : null);
  const s = typeof screen !== "undefined" ? screen : {};
  return {
    ua: n.userAgent || "",
    uaMobile: n.userAgentData ? n.userAgentData.mobile : null,
    touchPoints: n.maxTouchPoints || 0,
    anyFinePointer: mm("(any-pointer: fine)"),
    shortSide: s.width && s.height ? Math.min(s.width, s.height) : null,
  };
}

/* Self-check: node src/lib/device.js */
export function deviceSelfCheck() {
  const pc = { ua: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126", uaMobile: false, touchPoints: 0, anyFinePointer: true, shortSide: 1080 };
  const bad = [];
  const t = (name, ok) => { if (!ok) bad.push(name); };
  t("a Windows PC opens it", isDesktop(pc));
  t("a Mac opens it", isDesktop({ ...pc, ua: "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) Safari/605", uaMobile: null, shortSide: 900 }));
  t("a touch-screen laptop opens it", isDesktop({ ...pc, touchPoints: 10 }));
  t("an Android phone is refused", !isDesktop({ ...pc, ua: "Mozilla/5.0 (Linux; Android 14; Pixel 8) Mobile", uaMobile: true, touchPoints: 5, anyFinePointer: false, shortSide: 412 }));
  t("an Android phone in desktop mode is refused (desktop user agent, no mouse, phone screen)",
    !isDesktop({ ua: "Mozilla/5.0 (X11; Linux x86_64) Chrome/126", uaMobile: false, touchPoints: 5, anyFinePointer: false, shortSide: 412 }));
  t("an iPhone in desktop mode is refused", !isDesktop({ ua: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605", uaMobile: null, touchPoints: 5, anyFinePointer: false, shortSide: 393 }));
  t("an iPad in desktop mode is refused (Mac user agent with a touch screen)",
    !isDesktop({ ua: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605", uaMobile: null, touchPoints: 5, anyFinePointer: false, shortSide: 820 }));
  t("an iPad with a trackpad in desktop mode is still refused", !isDesktop({ ua: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605", touchPoints: 5, anyFinePointer: true, shortSide: 820 }));
  t("an Android tablet in desktop mode is refused (no mouse)", !isDesktop({ ua: "Mozilla/5.0 (X11; Linux x86_64) Chrome/126", uaMobile: false, touchPoints: 10, anyFinePointer: false, shortSide: 800 }));
  return bad;
}

if (typeof process !== "undefined" && process.argv && /device\.js$/.test(process.argv[1] || "")) {
  const bad = deviceSelfCheck();
  console.log(bad.length ? "FAIL: " + bad.join("; ") : "device self-check ok");
  if (bad.length) process.exit(1);
}
