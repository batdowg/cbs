CBS bootstrap. Health endpoint at /healthz. Stack: Flask, Caddy, Postgres. Deployed on cbs.ktapps.net.

Badge images are served from `/badges/<slug>.webp` via Caddy from `/srv/badges` (local `./site/badges`).
“Foundations” maps to `foundations.webp`.

## Certificate templates

Certificate PDFs live in `app/assets/` in the repo and must be copied to `data/cert-assets/` on the host. Docker Compose bind-mounts that directory into the container at `/app/app/assets`, so keep it backed up and re-seed it from `app/assets/` when provisioning a fresh environment (e.g. `cp -a app/assets/. data/cert-assets/`).

## Mail setup

Environment variables:

- SMTP_HOST
- SMTP_PORT (default 587)
- SMTP_USER
- SMTP_PASS
- SMTP_FROM_DEFAULT
- SMTP_FROM_NAME

Authenticate as ktbooks@kepner-tregoe.com; default From is certificates@kepner-tregoe.com via settings.

## CSA helpers
RBAC helpers live in `app/shared/acl.py`. CSAs may add or remove participants only until a session is marked Ready for Delivery.
