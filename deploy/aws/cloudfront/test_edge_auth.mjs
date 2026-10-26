// Self-check: edge_auth.js accepts exactly the tokens backend/auth.py accepts.   node deploy/aws/cloudfront/test_edge_auth.mjs
// Tokens are made by backend.auth.make_token itself (python), so a format change on either side fails here.
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';

const SECRET = 'x'.repeat(40);
const src = readFileSync(new URL('./edge_auth.js', import.meta.url), 'utf8')
    .replace(/^import cf from 'cloudfront';$/m, '').replace(/^const kvs = cf\.kvs\(\);$/m, '');
const handler = new Function('require', 'kvs', `${src}; return handler;`)(
    createRequire(import.meta.url), { get: async (k) => (k === 'session_secret' ? SECRET : undefined) });

const token = (user, now) => execFileSync('python', ['-c',
    `import sys; from backend.auth import make_token; print(make_token(sys.argv[1], now=${now}, secret=b"${SECRET}"))`, user],
    { encoding: 'utf8' }).trim();
const ask = (value) => handler({ request: { uri: '/api/dataset', cookies: value === undefined ? {} : { kssl_session: { value } } } });
const now = Math.floor(Date.now() / 1000);

const good = token('owner.kssl', now);                                   // a user name with a dot
assert.equal((await ask(good)).uri, '/api/dataset', 'valid token passes');
assert.equal((await ask(undefined)).statusCode, 401, 'no cookie');
assert.equal((await ask(good.slice(0, -1) + (good.endsWith('0') ? '1' : '0'))).statusCode, 401, 'tampered signature');
assert.equal((await ask(token('owner', now - 50000))).statusCode, 401, 'expired (made 50000 s ago, lives 43200 s)');
assert.equal((await ask(good.replace('owner.kssl', 'admin'))).statusCode, 401, 'other user, same signature');
assert.equal((await ask('garbage')).statusCode, 401, 'malformed');
console.log('edge_auth.js OK');
