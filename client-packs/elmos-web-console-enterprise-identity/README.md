# ELMOS Web Console enterprise identity

This experimental Batch 32 client pack replaces browser-supplied tenant and role
headers with an OIDC Authorization Code + PKCE session. The BFF stores credentials
only in secure HttpOnly cookies, and the control plane validates the access token
again before authorizing repository or operations requests.

Local builds and negative authorization tests are engineering evidence only.
External IdP execution, revocation behavior, independent security review,
cross-browser lifecycle evidence and customer acceptance remain `NOT_RUN`; this
pack is not certified.
