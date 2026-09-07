# Temporary development administrator

`/admin/login` offers password login only with explicit development/test configuration.
The sole identity is `zpchoney@gmail.com`. Passwords are never defaulted or embedded in
source: provide a random 16-byte hexadecimal `ELMOS_TEMP_ADMIN_PASSWORD_SALT` and a
64-byte hexadecimal `ELMOS_TEMP_ADMIN_PASSWORD_HASH` generated with Node's `scryptSync`
(password, decoded salt, 64; default N=16384, r=8, p=1).

Set `ELMOS_TEMP_ADMIN_ENABLED=true`, a random `ELMOS_SESSION_SECRET` (at least 32
characters), and the exact loopback `ELMOS_PUBLIC_ORIGIN` in the private, gitignored
`.env.development.local`. Bind the development server to `127.0.0.1`; do not publish
it behind a tunnel or a proxy rewriting requests to localhost. The development
throttle locks this one account for 15 minutes after five failures and is
process-local, not a distributed production defense.

The HttpOnly, SameSite=Strict cookie expires after one hour. Disabling the flag,
rotating the password hash/salt or signing secret, changing the tenant, or switching
to production invalidates it. Sign-out clears it. Mailbox verification remains
false; this local path does not call mail providers. OIDC login, mailbox
verification, and OIDC login notifications retain their existing behavior.

The session can open administrator pages. It does not impersonate an OIDC bearer
token. Existing operations-key endpoints still require their separately configured,
tenant-bound, expiring backend credential; OIDC-only backend endpoints and Runner
Fleet governance remain unavailable to this bootstrap. No backend enforcement is
weakened and no production deployment is performed by this configuration.

Run `pnpm test:temporary-admin-login` for password, session, origin, rotation,
production-denial, cookie, entry-isolation, and lockout regression tests.
