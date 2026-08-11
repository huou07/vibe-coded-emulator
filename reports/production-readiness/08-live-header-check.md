# Live HTTPS and edge-header check

Status: PASS for observed headers; authenticated Cloudflare dashboard review completed with plan/configuration limits recorded.

Read-only observations:

- Production `/`: HTTP 200 via `server: cloudflare`, HSTS enabled, `X-Content-Type-Options: nosniff`, CSP, Permissions-Policy, Referrer-Policy, and `cf-cache-status: DYNAMIC`.
- Production `/service-worker.js`: HTTP 200, JavaScript content type, `cf-cache-status: EXPIRED`.
- Staging `/health`: HTTP 200, `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`.
- The observed staging server identifies Python 3.13.7; local development was Python 3.9.6. The local standard-library baseline and staging smoke both passed, but this runtime difference is recorded for future compatibility review.

Authenticated dashboard review of `an3tocom.space` security rules showed no visible custom rules or rate-limiting rules, Managed Rules presented an upgrade requirement, and Bot traffic settings showed Search/Agent/Training allowed. No Cloudflare settings were changed.

This is evidence of the currently visible dashboard state, not a claim that additional account-level protections outside the page are absent.
