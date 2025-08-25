CBS bootstrap. Health endpoint at /healthz. Stack: Flask, Caddy, Postgres. Deployed on cbs.ktapps.net.

Badge images are served from `/badges/<slug>.webp` via Caddy from `/srv/badges` (local `./site/badges`). “Foundations” maps to `foundations.webp`.

## Mail setup

Environment variables:

- SMTP_HOST
- SMTP_PORT (default 587)
- SMTP_USER
- SMTP_PASS
- SMTP_FROM_DEFAULT
- SMTP_FROM_NAME

Authenticate as ktbooks@kepner-tregoe.com; default From is certificates@kepner-tregoe.com via settings.
