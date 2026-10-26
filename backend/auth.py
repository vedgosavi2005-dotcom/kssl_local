"""Sign-in sessions and the API lock (owner 2026-10-25: "lock the API with a session"; terms "saved on the server").

    python -m backend.auth --selftest
    python -m backend.auth --hash        (asks for a password, prints a KSSL_LOGIN_USERS entry)

A good POST /api/login sets an HttpOnly cookie `kssl_session` = "<user>.<expiry>.<hmac>" signed with KSSL_SESSION_SECRET (.env).
When KSSL_LOGIN_REQUIRED=1 (live API only; the review site has its own basic auth), every /api path except the sign-in ones needs
that cookie, or the X-KSSL-Service header = KSSL_SERVICE_TOKEN (server-to-server callers: the Ask Parallax service). Off when the
variable is unset, so a server that has not been configured keeps working as before.
ponytail: one shared secret, no server-side session table: a sign-out only drops the cookie; rotate KSSL_SESSION_SECRET to end every
session at once.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sys
import time

COOKIE = "kssl_session"
TTL_S = 12 * 3600
TERMS_VERSION = "2026-10-25"          # src/lib/terms.js shows this version's text; a new version asks every user again
OPEN_PATHS = ("/api/login", "/api/logout", "/api/session", "/api/health")


def required(review: bool) -> bool:
    return not review and os.environ.get("KSSL_LOGIN_REQUIRED", "").strip() == "1"


def _secret() -> bytes:
    s = os.environ.get("KSSL_SESSION_SECRET", "")
    if len(s) < 32:
        raise RuntimeError("KSSL_SESSION_SECRET (32+ characters) is not set in .env")
    return s.encode()


def _sig(payload: str, secret: bytes) -> str:
    return hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()


def make_token(user: str, now: float | None = None, secret: bytes | None = None) -> str:
    payload = f"{user}.{int((now or time.time()) + TTL_S)}"
    return f"{payload}.{_sig(payload, secret or _secret())}"


def user_of(token: str | None, now: float | None = None, secret: bytes | None = None) -> str | None:
    """the signed-in user of a cookie value, or None (bad signature, expired, malformed)"""
    try:
        user, exp, sig = str(token or "").rsplit(".", 2)
        if not user or not hmac.compare_digest(sig, _sig(f"{user}.{exp}", secret or _secret())):
            return None
        return user if int(exp) > (now or time.time()) else None
    except (ValueError, RuntimeError):
        return None


def service_ok(header: str | None) -> bool:
    want = os.environ.get("KSSL_SERVICE_TOKEN", "")
    return bool(want) and len(want) >= 32 and hmac.compare_digest(str(header or ""), want)


def allowed(path: str, cookie: str | None, service_header: str | None) -> bool:
    if not path.startswith("/api/") or path in OPEN_PATHS:
        return True
    return bool(user_of(cookie)) or service_ok(service_header)


def set_cookie(response, user: str, https: bool) -> None:
    response.set_cookie(COOKIE, make_token(user), max_age=TTL_S, httponly=True, secure=https, samesite="lax", path="/")


def terms_accepted(cur, user: str) -> bool:
    cur.execute("SELECT 1 FROM activity.terms_acceptance WHERE user_name = %s AND terms_version = %s", (user, TERMS_VERSION))
    return cur.fetchone() is not None


def accept_terms(cur, user: str, user_agent: str | None) -> None:
    cur.execute("""INSERT INTO activity.terms_acceptance (user_name, terms_version, user_agent) VALUES (%s, %s, %s)
                   ON CONFLICT (user_name, terms_version) DO NOTHING""", (user, TERMS_VERSION, (user_agent or "")[:300] or None))


def _selftest() -> None:
    s = b"x" * 40
    t = make_token("user1", now=1000, secret=s)
    assert user_of(t, now=1001, secret=s) == "user1"
    assert user_of(t, now=1000 + TTL_S + 1, secret=s) is None                       # expired
    assert user_of(t.replace("user1", "admin"), now=1001, secret=s) is None          # a changed user breaks the signature
    assert user_of(t, now=1001, secret=b"y" * 40) is None                            # another secret
    assert user_of("garbage", secret=s) is None and user_of(None, secret=s) is None
    os.environ["KSSL_SERVICE_TOKEN"] = "z" * 40
    assert service_ok("z" * 40) and not service_ok("z" * 39) and not service_ok(None)
    os.environ["KSSL_SESSION_SECRET"] = "x" * 40
    assert allowed("/api/login", None, None) and allowed("/api/health", None, None) and allowed("/index.html", None, None)
    assert not allowed("/api/dataset", None, None) and allowed("/api/dataset", make_token("u"), None)
    assert allowed("/api/dataset", None, "z" * 40)
    os.environ["KSSL_LOGIN_REQUIRED"] = "1"
    assert required(review=False) and not required(review=True)
    print("auth self-check ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    elif "--hash" in sys.argv:
        import getpass
        import secrets
        name = input("user: ").strip()
        salt = secrets.token_hex(16)
        h = hashlib.pbkdf2_hmac("sha256", getpass.getpass("password: ").encode(), bytes.fromhex(salt), 600_000).hex()
        print(f"{name}:pbkdf2_sha256.600000.{salt}.{h}")
    else:
        print(__doc__)
