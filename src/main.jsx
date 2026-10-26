import ReactDOM from "react-dom/client";
import { isDesktop } from "./lib/device";
import { LOGIN_REQUIRED, session } from "./lib/login";
import Login from "./components/login/Login";
import "./styles/index.css";

const root = ReactDOM.createRoot(document.getElementById("root"));

/* Ask Parallax (parallax-agent/): its widget mounts itself (button at the bottom left) from the agent service.
   On in local dev; a build turns it on with VITE_ASK_PARALLAX=1 (off on the VPS until the service runs there). */
function loadAskParallax() {
  if (!(import.meta.env.DEV || import.meta.env.VITE_ASK_PARALLAX === "1")) return;
  // not over the loading screen: only once the dataset is in (state/DataProvider announces it)
  if (!window.__ksslDataReady) {
    window.addEventListener("kssl:data-ready", loadAskParallax, { once: true });
    return;
  }
  const css = Object.assign(document.createElement("link"), { rel: "stylesheet", href: "/parallax-agent/widget.css" });
  const js = Object.assign(document.createElement("script"), { type: "module", src: "/parallax-agent/widget.js" });
  document.head.append(css, js);
}

/* Desktop only (lib/device): a phone or tablet gets this notice and never loads the app or its data.
   /flow is the review site's Flow dashboard (pages/flow): its own page, no dataset; on the live site its API answers 404. */
const startApp = () =>
  window.location.pathname.replace(/\/+$/, "") === "/flow"
    ? import("./pages/flow/FlowDashboard").then(({ default: Flow }) => root.render(<Flow />))
    : import("./App").then(({ default: App }) => {
      root.render(<App />);
      loadAskParallax();
    });

if (isDesktop()) {
  // sign-in (lib/login): the app and its data load only for a signed-in user who has accepted the current terms
  if (LOGIN_REQUIRED) {
    session().then((s) => (s && s.termsAccepted ? startApp() : root.render(<Login onDone={startApp} signedIn={s} />)));
  } else startApp();
} else {
  root.render(
    <div className="device-gate" role="alert">
      <div className="device-gate-box">
        <b>137Parallax</b>
        <p>This platform opens on a laptop or desktop computer only.</p>
        <p className="device-gate-sub">Phones and tablets are not supported, including in desktop-site mode. Please open it on a computer.</p>
      </div>
    </div>,
  );
}
