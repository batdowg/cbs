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
1.4 Password reset flow (request, email token, reset form) [DONE]
1.5 Role based access control (RBAC) middleware for routes [DONE]
1.6 Session persistence and timeout configuration  
1.7 Basic audit log for logins and role changes
1.8 Two login surfaces:
    • **Users** (staff) managed in Users admin.
    • **ParticipantAccount** (learners) auto-provisioned via sessions with default password "KTRocks!"; not shown in Users admin.
    One email across system; provisioning skips any email that already exists in Users.

Passwords are hashed via a shared bcrypt helper. When manually creating Users or ParticipantAccounts, SysAdmins (and for learner accounts, Administrators) may set a password that will not be overwritten. Provisioning only applies the default "KTRocks!" password when creating new accounts or filling a null `password_hash`, and reports accounts where an existing password was kept. Forgot‑password is available at `/forgot-password` with 1‑hour tokens handled by `/reset-password`. SysAdmins can set user passwords on the Users form, and Admin/SysAdmin can set participant passwords from session participant rows; admin‑initiated resets are logged via `password_reset_admin` entries in `audit_logs`.

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
2.7 Clients: manage client records (Name unique case-insensitive, SFC Link, CRM (User), Data Region NA/EU/SEA/Other, Status active/inactive). SysAdmin or Administrator can CRUD under Settings.
2.8 SMTP test button uses saved settings and flashes success or error.

Environment variables (reference only, do not hardcode secrets in repo):  
`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER` (auth account), `SMTP_PASS` (secret), `SMTP_FROM_DEFAULT`, `SMTP_FROM_NAME`

Note: SMTP env surfaced in UI (read-only), emailer defaults and mock logging in place. Real send depends on env on VPS.

## 3. Session Management (with client self‑service)
3.1 Create Session form (staff only): title, Workshop Type (dropdown labeled by Code only), date-only start/end, daily start/end times, timezone, location, delivery type (Onsite, Virtual, Self-paced, Hybrid), region (NA, EU, SEA, Other), language (dropdown, default English), capacity, status, sponsor, notes, simulation outline, lead facilitator (single select) and additional facilitators (addable selects from KT Delivery or Contractor users); session.code derives from selected Workshop Type. Defaults: daily times prefill 08:00-17:00; lead facilitator removed from additional facilitator options. “Include out-of-region facilitators” toggle preserves current inputs.
3.2 Materials and shipping block on the Session:
 • Shipping contact name, phone, email  
 • Shipping address lines, city, state, postal code, country  
 • Special instructions, courier, tracking, ship date  
 • Materials list (simple initially: item name, qty, notes)  
3.3 Participants tab on the Session: add/remove participants, mark attendance, completion date, edit/remove entries, CSV import (FullName,Email,Title) with sample download [DONE]
3.4 Session lifecycle and status: UI shows checkboxes for Materials ordered, Ready for delivery, Workshop info sent, Delivered, Finalized. Materials ordered allowed anytime. Ready requires participants > 0. Delivered requires Ready and End Date not in the future. Finalized requires Delivered. Cancel removes PDFs and locks edits; On Hold blocks participant edits. `*_at` timestamps record the first True transition and remain if later unchecked. Status options remain `New`, `Confirmed`, `On Hold`, `Delivered`, `Closed`, `Cancelled` with Confirmed-Ready gating and provisioning behavior. A Delivered checkbox gates certificate generation. Cancelling or placing on hold deactivates accounts with no other active sessions.
3.5 Client self‑service link for a Session (tokenized URL): client can edit participant list, confirm shipping details, confirm primary contact
3.6 Session list and filters: upcoming, past, by facilitator, by client
3.7 Client Session Admin (CSA): per-session email assignment creating ParticipantAccount if missing. CSA may add/remove participants for that session until Delivered but cannot toggle lifecycle flags; no other access.

## 4. Participant Management
4.1 Import participants from Salesforce CSV (`SFC Participant Import Template.csv`)  
4.2 Link imported participants to a Session during import  
4.3 Participant profile: full name, certificate name, email (lowercased unique), company, region, notes
4.4 Participant portal: “My Certificates” page that shows only their PDFs
4.5 Bulk import validation and error report (downloadable CSV); Session Participants tab also supports CSV import with columns FullName,Email,Title and per-row error report
4.6 ParticipantAccount stores `full_name` (account owner name) and `certificate_name` (printed on certificates); `certificate_name` defaults from `full_name` on creation but may be changed.
4.7 Login & password reset:
    • Single front-door login at `/` (alias `/login`) accepts staff or learner emails and routes accordingly.
    • Internal/test emails (e.g., `c@c.c`) are accepted; validator normalization is best-effort only.
    • If an email exists in both Users and ParticipantAccounts, staff login wins; a heads-up is flashed and `login_dupe_email` is audited.
    • Creation-time checks prevent cross-table duplicate emails going forward.
    • `/forgot-password` is shared for both kinds of accounts.
    • `/logout` clears any role.

## 5. Certificates
5.1 Generate certificate PDFs using template and layout rules [DONE]
5.2 Store PDFs on disk under `/srv/certificates/<year>/<session>/<email>.pdf` [DONE]
5.3 Link PDF path to participant record and show on Participant portal [DONE]
 • Output path pattern and Generate Certificates buttons are staff-only
5.4 Resend certificate email action (uses Certificates From address)  
5.5 Unique certificate ID and simple validation endpoint  
5.6 Layout rules to follow exactly:
    • Text overlays on `app/assets/certificate_template.pdf`.
    • Name Y from bottom 145 mm, Times-Italic, autoshrink 48→32 pt, centered.
    • Workshop Y 102 mm, start 56 pt and shrink to 40 pt if needed, centered.
    • Date Y 83 mm, format “d Month YYYY”, centered using session end date.
    • Workshop text always uses Workshop Type Name.

## 6. UI and Navigation
6.1 Left‑hand menu, persistent across pages, role aware. When signed out it shows only a Login link. When signed in the order is: Home, Sessions, My Certificates, Settings (accordion: Users, Workshop Types, Mail Settings, Clients), Logout.
6.2 Admin dashboard for quick system status and recent actions
6.3 Participant view: only “My Certificates”
6.4 Consistent KT brand styles (logo at `app/static/ktlogo1.png`, colors, typography)
6.5 Responsive layout basics for mobile
6.6 Forms disable autocomplete on sensitive fields (New User email/password, Mail Settings SMTP credentials)
6.7 Root path shows the branded “Welcome to KT Workshop Tools” login card; `/login` aliases to it.

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
9.7 WSGI module `app.app` exports top-level `app`; seeding remains guarded [DONE]

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
11.4 Users migration fixed for Postgres using inspector checks; enforces unique lower(email) index [DONE]
11.5 Next: wire Session Details to shipping/materials where needed
11.6 WorkshopTypes table with unique uppercase code; sessions reference it via workshop_type_id

## 12. Data and Security Rules
12.1 One account per email across the entire system; enforce lower(email) unique in DB and app logic  
12.2 Roles (boolean flags on user):  
 • Application Admin: can change Settings (section 7), manage users and roles  
 • Admin (information admin): manage sessions, participants, certificates; cannot change core Settings  
 • CRM, Delivery, Contractor, Staff as needed for access scopes  
 • Participant: access only to their own certificates  
12.3 Staff‑only pages: `/importer`, `/cert-form`, `/issued`, `/users`
12.4 Facilitators selectable only from users flagged as KT Delivery
12.5 Learner page: `/my-certificates` shows only their own PDFs
12.6 Secrets policy: never commit secrets; use environment variables and GitHub secrets
12.7 Certificate completion date uses session end date
12.7 Users admin UI live with audit logging [DONE]
12.8 Participant accounts are deactivated when all their sessions are Cancelled, Closed, or On Hold; provisioning another confirmed session reactivates them.
12.9 Users admin table includes inline role checkboxes (SysAdmin, Administrator, CRM, KT Facilitator, Contractor) with bulk save.
12.10 Administrators can access Users admin but only SysAdmin can toggle the SysAdmin role.

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
## Latest update done by codex 10/30/2025
Added region field and delivery type/region dropdowns to Session forms
Workshop Type dropdown now shows Code only; session.code derives automatically
Facilitators selectable from Delivery or Contractor users and saved via session_facilitators
Documented Session field changes and WorkshopType Name usage for certificates
## Latest update done by codex 11/05/2025
Replaced free-text language with dropdown (default English) and lead/additional facilitator controls on Sessions
Participants tab gains Title field, edit/remove, and CSV import with sample download
Context updated for session fields and participant CSV behavior
## Latest update done by codex 11/15/2025
Participant accounts provision with default password "KTRocks!" and flash summary; Confirmed-Ready auto-sets status to Confirmed with gated status options; Delivered checkbox blocks certificate generation until checked; Users admin lists inline role checkboxes with bulk save.
## Diagnostics 2025-08-19
- Route exists: admin_test_mail GET /admin/test-mail
- /healthz returns 200 OK
- Unauthenticated curl showed no headers, likely redirect to login
- Next step: confirm HTTP status with verbose curl and follow redirects; verify admin-only access with a logged-in request
- Logged in admin received JSON {"ok": false, "detail": "stub: missing config"} from GET /admin/test-mail
- Sample log: [MAIL-OUT] to=foo@example.com subject="CBS test mail" host=None mode=stub
- 7.4 [DONE]

## Latest update done by codex 08/21/2025
- Administrators can manage users except the SysAdmin flag, which only SysAdmin may change.
- Delivered cannot be set before session End Date and forces Confirmed-Ready on.
- Saving with Confirmed-Ready on runs provisioning, sets status to Confirmed, and flashes provisioning counts.
- Certificate generation remains blocked until a session is marked Delivered.

## Latest update done by codex 11/25/2025
- Sign-in now lands on Home and "/dashboard" redirects to "/".
- Left nav adds a Settings accordion for SysAdmin or Administrator with Users, Workshop Types, Clients, and Mail Settings (SysAdmin only); placeholder Certificates link removed.
- Users list includes a Role Matrix modal.
- Delivered cannot be set before End Date. Saving with Delivered forces Confirmed-Ready on and locks it.

## Latest update done by codex 12/10/2025
- Sidebar logo served from `app/static/KTlogo1.png`.
- Left nav order: Home, Sessions, My Certificates, Settings (Users, Workshop Types, Mail Settings, Clients), Logout.
- Settings summary styled like other links and error flashes render bold red.

## Latest update done by codex 12/20/2025
- Clients model and admin CRUD added; sessions can link to clients and show their CRM read-only.
- Per-session Client Session Admin (CSA) assignment by email; CSA may manage participants until Delivered.
- Mail Settings page has “Send test email” using saved SMTP config.
- New User and Mail Settings forms disable autocomplete on sensitive fields.
- Sidebar logo path fixed to `app/static/ktlogo1.png`.

## Latest update done by codex 01/15/2026
- Sidebar logo always loads from `app/static/ktlogo1.png`.
- Added “My Sessions” page listing sessions where the user is lead or additional facilitator, client CRM, or the assigned CSA; excluded Closed/Cancelled unless toggled. Link shown for staff or CSA accounts.
- CSA and staff may view session info and, before delivery, add/remove participants, edit participant full name and title, and import CSV; all CSA abilities disabled once Delivered.
- Home page simplified to a welcome message with links to My Sessions and My Certificates when available.

## Latest update done by codex 02/01/2026
- Sidebar logo served from `/static/ktlogo1.png` with `/logo.png` passthrough fallback.
- Delivered cannot be set before session End Date (server-enforced) and remains off until the End Date passes.
- Session POST actions use PRG with flashes, keeping navigation consistent after saves.

## Latest update done by codex 03/01/2026
- CSA login now lands on Home with a Sessions table mirroring My Sessions, and CSA-only accounts see “Sessions” in the left nav.
- CSA session detail shows read-only fields (Title, Workshop Type, Facilitator(s), Dates HH:MM–HH:MM, Timezone, Language, Delivery Type, Location, Client, CRM, Confirmed-Ready, Delivered) hiding Region and Status.
- Delivered checkbox performs a pre-check and alerts “This session cannot be marked as Delivered — the workshop End Date is in the future.” when end date is in the future.
- Users require a Region (NA/EU/SEA/Other). Admin Sessions list defaults to the admin’s region with a “Show Global Sessions” toggle, and facilitator pickers default to in-region with an “Include out-of-region facilitators” override.

## Latest update done by codex 03/15/2026
- Users Edit supports Full name + Region; Email is immutable; audit log recorded.

## Latest update done by codex 04/20/2026
- Confirmed-Ready independent; Delivered requires Confirmed-Ready.
- “My Profile” adds Certificate Name; certs use it; typography updated.

## Latest update done by codex 05/01/2026
- Checkboxes accept y/yes/on/1 and Confirmed-Ready persists independently of Delivered.

## Latest update done by codex 06/01/2026
- Session model gains lifecycle flags (materials_ordered, ready_for_delivery, info_sent, delivered, finalized, on_hold, cancelled) with corresponding timestamps.
- Sessions expose a read-only `computed_status` derived from those flags and a `participants_locked` helper when on hold, finalized, or cancelled.
- Added certificate cleanup utility `remove_session_certificates` and generation now skips cancelled sessions.

## Latest update done by codex 07/10/2026
- New Session form shows Daily Start Time 08:00 and Daily End Time 17:00 before typing.
- Lifecycle fieldset adds Materials ordered, Ready for delivery, Workshop info sent, Delivered, Finalized with server-side gating.
- Delivered requires Ready for delivery and End Date not in the future; Finalized requires Delivered and locks participant edits.
- Session pages flash saved changes and display Status and lifecycle flags.

## Latest update done by codex 08/22/2025
- Checkbox parsing consolidated with local `_cb` accepting y/yes/on/1 variants and treating missing fields as false.
- Session forms drop Status and Confirmed-Ready fields; lifecycle flags only appear on Edit and drive a derived `computed_status`.
- Profile page allows editing Full name and Certificate name; new participant accounts default certificate_name to full_name.
- Sessions can be cancelled or finalized via detail page actions; cancelled sessions remove stored certificates and block generation.

## Latest update done by codex 07/20/2026
- Added on_hold_at timestamp and audit logging for lifecycle flag flips.
- Lifecycle gating enforces participant count for Ready, end-date check for Delivered, and Finalize after Delivered.
- Facilitator region toggle preserves form inputs via local storage.
- Adding or importing participants provisions accounts when session is Ready.

## Latest update done by codex 08/01/2026
- Centralized bcrypt helpers in `app/utils/passwords.py` and all password operations use them.
- Manual account creation can set a password without it being overwritten by provisioning; provisioning keeps existing hashes and reports `kept_password`.
- Forgot-password flow added with `/forgot-password` and `/reset-password` using 1-hour tokens; token shown on page when mail is stubbed.
- SysAdmin/Admin interfaces allow setting passwords for Users and ParticipantAccounts with audit logging (`password_reset_admin`).

## Latest update done by codex 09/01/2026
- WorkshopType includes optional `badge` field with choices None, Foundations, Practitioner, Advanced, Expert, Coach, Facilitator, Program Leader.
- Badge images served at `/badges/<slug>.webp` from repo or `/app/assets` fallback.
- Certificate views show a **Download Badge** link when the session's workshop type has a badge.
- Existing workshop types seeded to Foundations.
