import { useEffect, useRef, useState } from "react";
import { acceptTerms, login, logout } from "../../lib/login";
import { TERMS } from "../../lib/terms";
import "../../styles/login.css";

/* The sign-in screen (lib/login.js), shown before the app loads; a pass calls onDone. The design is the frontend team's login
   page (owner 2026-10-25: "take the login page"); the check stays on the server (POST /api/login, hashed passwords in .env).
   After the password, a user who has not accepted the current terms reads them (scrolled to the end) and accepts; the
   acceptance is stored on the server (POST /api/terms/accept). No "forgot password" until there is an e-mail sender (owner). */
const Eye = ({ open }) => (
  <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    {open ? (
      <>
        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
        <line x1="1" y1="1" x2="23" y2="23" />
      </>
    ) : (
      <>
        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
        <circle cx="12" cy="12" r="3.2" />
      </>
    )}
  </svg>
);

export default function Login({ onDone, signedIn }) {
  const [view, setView] = useState(signedIn ? "terms" : "login");
  const [who, setWho] = useState(signedIn ? signedIn.user : "");
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    if (!user.trim() || !password) {
      setErr("Please enter both user and password.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const r = await login(user.trim(), password);
      if (r.termsAccepted) onDone(r.user);
      else {
        setWho(r.user);
        setView("terms");
        setBusy(false);
      }
    } catch (x) {
      setErr(x.message);
      setBusy(false);
    }
  };
  if (view === "terms") return <Terms user={who} onDone={onDone} />;
  return (
    <div className="login-viewport">
      <div className="login-box">
        <div className="login-container">
          <div className="login-brand-side">
            <div className="login-brand-content">
              <div className="login-wordmark">
                <span className="wm-number">137</span>
                <span className="wm-name">Parallax</span>
              </div>
            </div>
          </div>
          <div className="login-divider" />
          <div className="login-form-side">
            <form className="login-form" onSubmit={submit}>
              {err ? (
                <div className="login-error" role="alert">
                  <span className="login-error-icon">⚠</span>
                  <span>{err}</span>
                </div>
              ) : null}
              <div className="login-field login-field-email">
                <label className="auth-field-label" htmlFor="login-user">User</label>
                <input id="login-user" type="text" className="login-input" placeholder="Enter user name or e-mail" value={user}
                  onChange={(e) => { setUser(e.target.value); if (err) setErr(null); }} disabled={busy} autoComplete="username"
                  autoCapitalize="none" autoFocus />
              </div>
              <div className="login-field login-field-password">
                <label className="auth-field-label" htmlFor="login-password">Password</label>
                <input id="login-password" type={show ? "text" : "password"} className="login-input login-input-password"
                  placeholder="Enter password" value={password} onChange={(e) => { setPassword(e.target.value); if (err) setErr(null); }}
                  disabled={busy} autoComplete="current-password" />
                <button type="button" className="login-eye-btn" onClick={() => setShow(!show)} aria-label={show ? "Hide password" : "Show password"}
                  title={show ? "Hide password" : "Show password"} tabIndex={-1}>
                  <Eye open={show} />
                </button>
              </div>
              <button type="submit" className="login-submit-btn" disabled={busy}>
                <span>{busy ? "Opening Parallax…" : "Open Parallax"}</span>
                <svg className="login-btn-arrow-svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="5" y1="12" x2="19" y2="12" />
                  <polyline points="13 6 19 12 13 18" />
                </svg>
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}

/* the terms, once per user and version: the box must be scrolled to the end before the checkbox unlocks */
function Terms({ user, onDone }) {
  const box = useRef(null);
  const [atEnd, setAtEnd] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const onScroll = () => {
    const el = box.current;
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight <= 15) setAtEnd(true);
  };
  useEffect(() => {
    const el = box.current;
    if (el && el.scrollHeight <= el.clientHeight + 10) setAtEnd(true);   // short enough to need no scrolling
  }, []);
  const accept = async () => {
    setBusy(true);
    setErr(null);
    try {
      await acceptTerms();
      onDone(user);
    } catch (x) {
      setErr(x.message);
      setBusy(false);
    }
  };
  return (
    <div className="login-viewport">
      <div className="login-box login-box-wide">
        <div className="terms-page-container">
          <div className="terms-header">
            <div className="auth-mini-brand">
              <span className="wm-number">137</span>
              <span className="wm-name">Parallax</span>
            </div>
            <h2 className="terms-main-title">Platform terms</h2>
            <p className="terms-subtitle">Welcome, <strong>{user}</strong>. Please read and accept these terms before you open the platform.</p>
          </div>
          <div className="terms-scroll-box" ref={box} onScroll={onScroll} tabIndex={0} aria-label="Terms">
            <div className="terms-article">
              {TERMS.map(([h, p], i) => (
                <div key={h}>
                  <h3>{i + 1}. {h}</h3>
                  <p>{p}</p>
                </div>
              ))}
              <div className="terms-end-marker">End of the terms</div>
            </div>
          </div>
          <div className={`terms-scroll-prompt ${atEnd ? "terms-scroll-prompt-unlocked" : "terms-scroll-prompt-locked"}`}>
            <span className="terms-prompt-icon">{atEnd ? "✓" : "↓"}</span>
            <span>{atEnd ? "You have reached the end. Tick the box to continue." : "Scroll to the end of the terms to continue."}</span>
          </div>
          {err ? (
            <div className="login-error" role="alert"><span className="login-error-icon">⚠</span><span>{err}</span></div>
          ) : null}
          <div className="terms-checkbox-wrap">
            <label className={`terms-checkbox-label${atEnd ? "" : " terms-checkbox-disabled"}`} htmlFor="terms-accept">
              <input id="terms-accept" type="checkbox" className="terms-checkbox-input" disabled={!atEnd} checked={agreed}
                onChange={(e) => setAgreed(e.target.checked)} />
              <span className="terms-checkbox-text">I have read and accept the 137Parallax platform terms.</span>
            </label>
          </div>
          <div className="terms-actions">
            <button type="button" className="login-submit-btn terms-accept-btn" disabled={!atEnd || !agreed || busy} onClick={accept}>
              <span>{busy ? "Opening Parallax…" : "Accept and open Parallax"}</span>
            </button>
            <button type="button" className="auth-link-btn terms-cancel-btn" onClick={logout}>Cancel and sign out</button>
          </div>
        </div>
      </div>
    </div>
  );
}
