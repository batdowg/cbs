# CONTEXT.md — CBS Project Context and Master Plan

## 0. Instructions for Codex
0.1 Always read this file first.  
0.2 Do not redo items marked [DONE].  
0.3 Only work on the numbered items I ask for, for example: “Do 1.2 through 1.6.”  
0.4 Keep changes minimal and consistent with this context.  
0.5 Never commit real secrets. Use environment variables and GitHub secrets.  
0.6 All database changes must use Flask‑Migrate migrations. No create_all on startup.  
0.7 Email must authenticate with the SMTP auth account but send from configured From addresses.  
0.8 Update this file when a task is completed by marking it [DONE].

## 1. Core User Authentication and Access
1.1 Magic link login (email token) [DONE]  
1.2 Password login with bcrypt hashing [DONE]  
1.3 Logout route and session clear [DONE]  
1.4 Password reset flow (request, email token, reset form)  
1.5 Role based access control (RBAC) middleware for routes  
1.6 Session persistence and timeout configuration  
1.7 Basic audit log for logins and role changes

## 2. Email and Notifications
2.1 Wire SMTP using Microsoft 365 auth account (authenticate as `ktbooks@kepner-tregoe.com`)  
2.2 Outbound From address mapping in Settings: [UI + scaffold DONE]  
 • Prework emails From = configurable (default `certificates@kepner-tregoe.com`)  
 • Certificates and badges emails From = configurable (default `certificates@kepner-tregoe.com`)  
 • Client session setup emails From = configurable (default `certificates@kepner-tregoe.com`)  
2.3 If SMTP env is missing, do not fail; log the composed message with a `[MAIL-OUT]` prefix [DONE]  
2.4 Message templates stored in DB with simple placeholders (name, session, date)  
2.5 Test mail endpoint in Settings to send a one‑off test to an address  
2.6 Delivery logging table (to, subject, status, error text)

Environment variables (reference only, do not hardcode secrets in repo):  
`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER` (auth account), `SMTP_PASS` (secret), `SMTP_FROM_DEFAULT`, `SMTP_FROM_NAME`

Note: SMTP env surfaced in UI (read-only), emailer defaults and mock logging in place. Real send depends on env on VPS.

## 3. Session Management (with client self‑service)
3.1 Create Session form (staff only): title, code, start date, end date, timezone, location, delivery type, facilitator(s)  
3.2 Materials and shipping block on the Session:  
 • Shipping contact name, phone, email  
 • Shipping address lines, city, state, postal code, country  
 • Special instructions, courier, tracking, ship date  
 • Materials list (simple initially: item name, qty, notes)  
3.3 Participants tab on the Session: add/remove participants, mark attendance, completion date  
3.4 Status fields: planned, ready to ship, shipped, delivered, completed  
3.5 Client self‑service link for a Session (tokenized URL): client can edit participant list, confirm shipping details, confirm primary contact  
3.6 Session list and filters: upcoming, past, by facilitator, by client

## 4. Participant Management
4.1 Import participants from Salesforce CSV (`SFC Participant Import Template.csv`)  
4.2 Link imported participants to a Session during import  
4.3 Participant profile: name, email (lowercased unique), company, region, notes  
4.4 Participant portal: “My Certificates” page that shows only their PDFs  
4.5 Bulk import validation and error report (downloadable CSV)

## 5. Certificates
5.1 Generate certificate PDFs using template and layout rules  
5.2 Store PDFs on disk under `/srv/certificates/<year>/<session>/<email>.pdf`  
5.3 Link PDF path to participant record and show on Participant portal  
5.4 Resend certificate email action (uses Certificates From address)  
5.5 Unique certificate ID and simple validation endpoint  
5.6 Layout rules to follow exactly:  
 • Name Y from bottom 145 mm, italic, autoshrink 48 pt down to 32 pt, centered  
 • Workshop Y 102 mm, larger font, centered  
 • Date Y 83 mm, format “d Month YYYY”, centered  
 • Use session end date as completion date

## 6. UI and Navigation
6.1 Left‑hand menu, persistent across pages, role aware  
6.2 Admin dashboard for quick system status and recent actions  
6.3 Participant view: only “My Certificates”  
6.4 Consistent KT brand styles (logo, colors, typography)  
6.5 Responsive layout basics for mobile

## 7. Settings (Application Admin only)
7.1 Settings landing page visible only to Application Admin (see Roles in section 11)  
7.2 Mail Settings page: [UI + scaffold DONE]  
 • Display and edit From address mapping per category (prework, certs and badges, client session setup)  
 • Read SMTP host, port, auth user from environment; allow test send only  
 • Never display or store SMTP password in DB; it is provided via environment/secret  
7.3 Branding Settings (later): upload logo, set brand name, primary color, footer text  
7.4 Feature flags (later): enable surveys, enable Salesforce sync, etc.  
7.5 Menu management (later): simple ordering and visibility per role

## 8. Salesforce Integration (later phase)
8.1 Import Sessions from Salesforce export initially (CSV)  
8.2 API integration to pull Sessions and Participants  
8.3 Push completion and certificate status back to Salesforce

## 9. Deployment and Ops
9.1 Docker Compose: app, db, caddy [DONE]  
9.2 Flask‑Migrate configured; migrations used for all schema changes [DONE]  
9.3 GitHub Actions deploy workflow: push to main triggers VPS pull and compose rebuild  
9.4 Health check endpoint `/healthz` returns JSON ok and counts  
9.5 Ops cheatsheet kept in README for routine commands

## 10. Non‑functional
10.1 Simple logs for mail sends, imports, certificate generation  
10.2 Error pages for 404 and 500 with support link  
10.3 Basic rate limiting on login and magic link requests  
10.4 Pagination on lists (sessions, users)  
10.5 Timezone handling for sessions

## 11. Data and Security Rules
11.1 One account per email across the entire system; enforce lower(email) unique in DB and app logic  
11.2 Roles (boolean flags on user):  
 • Application Admin: can change Settings (section 7), manage users and roles  
 • Admin (information admin): manage sessions, participants, certificates; cannot change core Settings  
 • CRM, Delivery, Contractor, Staff as needed for access scopes  
 • Participant: access only to their own certificates  
11.3 Staff‑only pages: `/importer`, `/cert-form`, `/issued`, `/users`  
11.4 Learner page: `/my-certificates` shows only their own PDFs  
11.5 Secrets policy: never commit secrets; use environment variables and GitHub secrets  
11.6 Certificate completion date uses session end date

## 12. Current State Snapshot
12.1 App, DB, Caddy running via Docker Compose on VPS  
12.2 Domain: https://cbs.ktapps.net  
12.3 Health check: `/healthz`  
12.4 Migrations configured and working  
12.5 Magic link login working  
12.6 Password login working (bcrypt)  
12.7 Admin user present: `cackermann@kepner-tregoe.com` (password set manually on VPS)  
12.8 SMTP not yet configured in app; auth account is `ktbooks@kepner-tregoe.com` and From defaults to `certificates@kepner-tregoe.com` once wired

## 13. Reference Files in repo or project
13.1 Process flow: `CBS Level1 Flow.pdf`  
13.2 Import template: `SFC Participant Import Template.csv`  
13.3 Data models: `CBS Data tables.xlsx`  
13.4 Branding asset: `KT-KepnerTregoe-CMYK-wtag (trans).png`  
13.5 Site map and access: `Site Map and access.xlsx`


## Latest update done by codex 08/19/2025 11:24 EST
Added an app_settings table and seeded default From addresses for prework, certificates, and client setup mail categories
Introduced a reusable emailer module that resolves From addresses from settings or environment variables and logs mock sends with [MAIL-OUT] when SMTP details are missing
Implemented an admin-only Settings blueprint with UI for editing mail From addresses and triggering test sends
Created a shared navigation template that shows a Settings link only to application admins
Documented required SMTP environment variables and default authentication details in the README
Updated project context to mark mail settings scaffolding as complete and note [MAIL-OUT] behavior when SMTP is absent
