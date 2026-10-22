import ReactDOM from "react-dom/client";
import { isDesktop } from "./lib/device";
import "./styles/index.css";

const root = ReactDOM.createRoot(document.getElementById("root"));

/* Desktop only (lib/device): a phone or tablet gets this notice and never loads the app or its data. */
if (isDesktop()) {
  import("./App").then(({ default: App }) => root.render(<App />));
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
