import { useState } from "react";
import { login } from "../../lib/login";

/* The temporary sign-in screen (lib/login.js). Shown before the app loads; a pass calls onDone. */
export default function Login({ onDone }) {
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      onDone(await login(user.trim(), password));
    } catch (x) {
      setErr(x.message);
      setBusy(false);
    }
  };
  return (
    <div className="device-gate">
      <form className="device-gate-box login-box" onSubmit={submit}>
        <b>137Parallax</b>
        <label>User<input autoComplete="username" value={user} onChange={(e) => setUser(e.target.value)} autoFocus /></label>
        <label>Password<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        {err && <p className="login-err">{err}</p>}
        <button type="submit" disabled={busy || !user || !password}>{busy ? "Signing in…" : "Sign in"}</button>
        <p className="device-gate-sub">Temporary test login.</p>
      </form>
    </div>
  );
}
