# CONTEXT.md — CBS Project Context and Master Plan

## Project Context

The Certs and Badges System (CBS) is a standalone web application built to manage training workshops, participants, and the issuing of certificates and badges. It replaces or supplements Salesforce CRM (SFC) for these functions, providing a dedicated learner and facilitator database and certificate management platform.

### Purpose
* Centralize sessions, participants, and certificate data in a single system.
* Automate certificate generation and delivery using Kepner-Tregoe branded templates.
* Provide a secure participant portal where learners can view and download their own certificates.
* Support staff workflows for session setup, participant import, materials and shipping management, and certificate issuing.
* Ensure data integrity with one account per email, consistent RBAC enforcement, and auditability.

### Scope
* **Sessions**: Staff can create and manage sessions, including fields like title, dates, facilitators, delivery type, and location.
* **Participants**: Add manually or import from Salesforce CSV; ensure lowercased unique emails; manage attendance and completion dates.
* **Certificates**: Generated per participant or in bulk, stored under `/srv/certificates/<year>/<session>/<email>.pdf`, linked to participant portal. Layout rules follow KT branding exactly, using the session end date as completion date.
* **Materials & Shipping**: Staff can track shipping contact details, address, courier, tracking, ship date, and materials list.
* **Prework**: Support distribution of prework emails with configurable “From” address and templates.
* **Surveys**: Provide survey instructions to learners post-session and allow completion tracking (feature-flagged, enabled later).
* **Portal**: Learners log in to see only their own certificates; staff have access to importer, cert-form, issued, users, and certificates pages.
* **Integration**: Salesforce sync planned (initial CSV import/export, later API push/pull).

### Why it matters
* Streamlines end-to-end workshop delivery (from session setup → prework → materials/shipping → workshop delivery → certificates/surveys).
* Reduces manual effort in certificate production, shipping coordination, and distribution.
* Provides learners and clients reliable, professional access to credentials and post-session feedback.
* Creates a scalable foundation for KT-branded training delivery, with options for surveys, branding controls, and Salesforce integration in later phases.

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
1.5 Role based access control (RBAC) middleware for routes [DONE]
1.6 Session persistence and timeout configuration  
1.7 Basic audit log for logins and role changes

## 2. Email and Notifications
2.1 Wire SMTP using Microsoft 365 auth account (authenticate as `ktbooks@kepner-tregoe.com`) [UI + backend working; real SMTP depends on env on VPS.]
2.2 Outbound From address mapping in Settings [UI + backend working; real SMTP depends on env on VPS.]
 • Prework emails From = configurable (default `certificates@kepner-tregoe.com`)
 • Certificates and badges emails From = configurable (default `certificates@kepner-tregoe.com`)
 • Client session setup emails From = configurable (default `certificates@kepner-tregoe.com`)
 • SMTP settings (host, port, auth user, default From, From Name) editable and stored in DB (except password)
 • Emailer uses DB overrides with environment fallback
2.3 If SMTP config is incomplete, log the composed message with a `[MAIL-OUT]` prefix [UI + backend working; real SMTP depends on env on VPS.]
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
7.2 Mail Settings page: [UI + backend working; real SMTP depends on env on VPS.]
 • Display and edit SMTP host, port, auth user, default From, From Name
 • Edit From address mapping per category (prework, certs and badges, client session setup)
 • SMTP settings stored in DB except password; emailer uses DB with env fallback
 • Logs `[MAIL-OUT]` if SMTP config incomplete
7.3 Branding Settings (later): upload logo, set brand name, primary color, footer text  
7.4 Feature flags (later): enable surveys, enable Salesforce sync, etc.  
7.5 Menu management (later): simple ordering and visibility per role

## 7.x SMTP persistence and test-send
7.1 Settings model [DONE]
7.2 Mail settings form save/reload [DONE]
7.3 Emailer env fallback and safe stub [DONE]
7.4 Test send route and log proof [DONE]
    • Mailer logs [MAIL-OUT] lines to stdout and test route logs its result.
    • Example: `docker compose logs app | grep '\[MAIL-OUT\]'`
Note: Settings row is singleton id=1 with env fallback on first load

7.5 smtp_pass_enc stored with SECRET_KEY-derived obfuscation [DONE]
7.6 emailer real send with [MAIL-OUT] proof [DONE]
7.7 "/" home + sidebar [DONE]
7.8 Mail Settings top-level; Navigation Freeze v1 [DONE]

Navigation Freeze v1 locks the sidebar links and Mail Settings placement. SMTP passwords are obfuscated using a SECRET_KEY-derived XOR with base64, and the mailer still falls back to environment variables when settings are incomplete. Sample real send log:
`[MAIL-OUT] mode=real to=test@example.com subject="Test" host=smtp.example.com result=sent`

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
9.6 Initial admin seeding gated by users table presence and `FLASK_SKIP_SEED` [DONE]

## 9.x Core Schema
9.1 Core schema created via migration for Sessions, Participants, SessionParticipant, Certificates [DONE]
9.2 Idempotent guards used so upgrades are safe [DONE]
9.3 Next: expand remaining tables from Excel in subsequent migrations after validation [DONE]

## 9.x Certificates
9.1 DB tables for Participant, SessionParticipant, Certificate [DONE]
9.2 Session details page with CSV import and participant edit [DONE]
9.3 Bulk generate PDFs per session using template and layout rules [DONE]
9.4 ZIP export for a session [DONE]
9.5 Learner page lists own certificates [DONE]
Notes: name/workshop/date placement per layout rules; uses session end date as completion; autoshrink name; unique(session_id, participant_email)

## 10. Non‑functional
10.1 Simple logs for mail sends, imports, certificate generation  
10.2 Error pages for 404 and 500 with support link  
10.3 Basic rate limiting on login and magic link requests  
10.4 Pagination on lists (sessions, users)  
10.5 Timezone handling for sessions

## 11. Database Completion
11.1 All remaining tables from Excel added via migration [DONE]
11.2 Idempotent guards and FK relationships documented [DONE]
11.3 Users table and Users admin UI implemented [DONE]
11.4 Next: wire Session Details to shipping/materials where needed

## 12. Data and Security Rules
12.1 One account per email across the entire system; enforce lower(email) unique in DB and app logic  
12.2 Roles (boolean flags on user):  
 • Application Admin: can change Settings (section 7), manage users and roles  
 • Admin (information admin): manage sessions, participants, certificates; cannot change core Settings  
 • CRM, Delivery, Contractor, Staff as needed for access scopes  
 • Participant: access only to their own certificates  
12.3 Staff‑only pages: `/importer`, `/cert-form`, `/issued`, `/users`
12.4 Learner page: `/my-certificates` shows only their own PDFs
12.5 Secrets policy: never commit secrets; use environment variables and GitHub secrets
12.6 Certificate completion date uses session end date
12.7 Users admin UI live with audit logging [DONE]

## 13. Current State Snapshot
13.1 App, DB, Caddy running via Docker Compose on VPS  
13.2 Domain: https://cbs.ktapps.net  
13.3 Health check: `/healthz`  
13.4 Migrations configured and working  
13.5 Magic link login working  
13.6 Password login working (bcrypt)  
13.7 Admin user present: `cackermann@kepner-tregoe.com` (password set manually on VPS)
13.8 SMTP not yet configured in app; auth account is `ktbooks@kepner-tregoe.com` and From defaults to `certificates@kepner-tregoe.com` once wired
13.9 Users admin UI live; additional users/roles can be created

## 14. Reference Files in repo or project
14.1 Process flow: `CBS Level1 Flow.pdf`  
14.2 Import template: `SFC Participant Import Template.csv`  
14.3 Data models: `CBS Data tables.xlsx`  
14.4 Branding asset: `KT-KepnerTregoe-CMYK-wtag (trans).png`  
14.5 Site map and access: `Site Map and access.xlsx`


## Latest update done by codex 08/19/2025 11:24 EST
Added an app_settings table and seeded default From addresses for prework, certificates, and client setup mail categories
Introduced a reusable emailer module that resolves From addresses from settings or environment variables and logs mock sends with [MAIL-OUT] when SMTP details are missing
Implemented an admin-only Settings blueprint with UI for editing mail From addresses and triggering test sends
Created a shared navigation template that shows a Settings link only to application admins
Documented required SMTP environment variables and default authentication details in the README
Updated project context to mark mail settings scaffolding as complete and note [MAIL-OUT] behavior when SMTP is absent
## Latest update done by codex 09/10/2025
SMTP host, port, auth user, default From, and From Name are editable and stored in app_settings
Emailer reads SMTP config from DB with environment fallback and logs [MAIL-OUT] when incomplete
Mail Settings page updated with editable SMTP fields and category overrides, plus test send
Navigation link labeled “App Settings” and context items 2.1–2.3 and 7.2 marked done
## Latest update done by codex 09/15/2025
Made users.password_hash migration idempotent using IF NOT EXISTS/IF EXISTS
Hardened Mail Settings with safe defaults, port validation, and test send feedback
Emailer attempts real SMTP send with DB/env config and logs mock sends when incomplete
Context items 2.1–2.3 and 7.2 noted as UI + backend working; real SMTP depends on env on VPS
## Latest update done by codex 09/21/2025
Fixed seed migration to upsert SMTP defaults using a bound connection
Added helpers to read and write app_settings with safe upserts
Mail Settings page saves without 500s and emailer pulls SMTP/From values from settings with env fallback
## Latest update done by codex 09/30/2025
Mailer logs [MAIL-OUT] lines to stdout and /admin/test-mail logs route results for easier debugging
## Latest update done by codex 10/10/2025
Introduced a dedicated User model with role flags and bcrypt helpers
Added admin-only Users management pages with create/edit and audit logging
Implemented app_admin_required RBAC decorator and guarded navigation link
## Latest update done by codex 10/20/2025
Gated initial admin seeding behind users table presence and `FLASK_SKIP_SEED`
Marked Users table and Users admin UI as complete in context
## Diagnostics 2025-08-19
- Route exists: admin_test_mail GET /admin/test-mail
- /healthz returns 200 OK
- Unauthenticated curl showed no headers, likely redirect to login
- Next step: confirm HTTP status with verbose curl and follow redirects; verify admin-only access with a logged-in request
- Logged in admin received JSON {"ok": false, "detail": "stub: missing config"} from GET /admin/test-mail
- Sample log: [MAIL-OUT] to=foo@example.com subject="CBS test mail" host=None mode=stub
- 7.4 [DONE]
