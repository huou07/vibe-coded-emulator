# Live HTTPS and edge-header check

Status: PASS for observed headers; Cloudflare WAF/rate-limit/Bot configuration remains UNVERIFIED.

Read-only observations:

- Production `/`: HTTP 200 via `server: cloudflare`, HSTS enabled, `X-Content-Type-Options: nosniff`, CSP, Permissions-Policy, Referrer-Policy, and `cf-cache-status: DYNAMIC`.
- Production `/service-worker.js`: HTTP 200, JavaScript content type, `cf-cache-status: EXPIRED`.
- Staging `/health`: HTTP 200, `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`.
- The observed staging server identifies Python 3.13.7; local development was Python 3.9.6. The local standard-library baseline and staging smoke both passed, but this runtime difference is recorded for future compatibility review.

Headers alone do not prove Cloudflare Managed WAF, Bot Fight Mode, or rate-limit rules are configured. No authenticated Cloudflare dashboard/API inspection was performed.
