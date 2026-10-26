// CloudFront Function (runtime cloudfront-js-2.0, viewer request) on the CACHED behaviours /api/dataset* and /api/image/*:
// they are served only to a signed-in viewer, without the API seeing each request. Checks the kssl_session cookie the same
// way as backend/auth.py user_of(): "<user>.<exp>.<sig>", split on the LAST two dots, sig = lowercase hex
// HMAC-SHA256(KSSL_SESSION_SECRET, "<user>.<exp>"), exp (unix seconds) > now. The secret comes from the KeyValueStore
// associated with this function (key "session_secret"); rotating it there + in the API's .env signs everyone out.
// Missing / bad / expired cookie: 401 at the edge. Every other /api path is not cached and the API checks the cookie itself.
import cf from 'cloudfront';
const crypto = require('crypto');
const kvs = cf.kvs();

function valid(token, secret, now) {
    const b = token.lastIndexOf('.'), a = b > 0 ? token.lastIndexOf('.', b - 1) : -1;
    if (a <= 0) return false;                                           // no user, or not three parts
    const exp = token.slice(a + 1, b), sig = token.slice(b + 1);
    if (!/^\d+$/.test(exp) || Number(exp) <= now) return false;
    const want = crypto.createHmac('sha256', secret).update(token.slice(0, b)).digest('hex');
    if (sig.length !== want.length) return false;
    let d = 0;
    for (let i = 0; i < want.length; i++) d |= sig.charCodeAt(i) ^ want.charCodeAt(i);   // constant time
    return d === 0;
}

async function handler(event) {
    const c = event.request.cookies.kssl_session;
    let ok = false;
    if (c && c.value) {
        try { ok = valid(c.value, await kvs.get('session_secret'), Math.floor(Date.now() / 1000)); } catch (e) { ok = false; }
    }
    if (ok) return event.request;
    return {
        statusCode: 401, statusDescription: 'Unauthorized',
        headers: { 'content-type': { value: 'application/json' }, 'cache-control': { value: 'no-store' } },
        body: { encoding: 'text', data: '{"detail": "sign in first"}' },
    };
}
