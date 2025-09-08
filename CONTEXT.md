
# 0. Engineering Context & Rules

This is the **authoritative functional & architectural context** for Certs & Badges (CBS). It supersedes prior drafts.  
Every functional change must update this file **in the same PR**.

## 0.1 Environment & Stack
- **App**: Python (Flask), Gunicorn
- **DB**: PostgreSQL 16
- **Proxy**: Caddy → `app:8000`
- **Docker Compose services**: `cbs-app-1`, `cbs-db-1`, `cbs-caddy-1`
- **In-container paths**: code at `/app/app/...`; site mount at `/srv` (host `./site`)
- **Health**: `GET /healthz` must respond `OK`

## 0.2 Deploy & Migrations (no local aliases)
- **Deploy on VPS** (`~/cbs`):  
  1) `git pull origin main`  
  2) `docker compose up -d --build`  
  3) `docker compose ps`  
  4) `docker logs cbs-app-1 --tail 80`
- **DB** (inside app container):  
  - Create: `python manage.py db migrate -m "message"`  
  - Apply: `python manage.py db upgrade`

## 0.3 Coding Rules
- Do **not** include local PowerShell aliases in docs or code.
- Business logic stays server-side; small JS for UI only.
- All timestamps stored UTC; display with short timezone labels; **never show seconds**.
- Certificates: `/srv/certificates/<year>/<session_id>/<workshop_code>_<certificate_name_slug>_<YYYY-MM-DD>.pdf` (where `workshop_code = workshop_types.code`) and linked in-portal.
- Emails lowercased-unique per table (see §2). Enforce in DB and app.
- Emails may exist in both **users** and **participant_accounts**; when both do, the **User** record governs authentication, menus, and profile.
- “KT Staff” is a **derived condition** (see §1.3), **not** a stored role.

## 0.4 App Conventions & PR Hygiene
- Keep migrations idempotent and reversible; guard enum/DDL changes carefully.
- Add/modify routes with explicit permission checks close to controller entry.
- Update **this file** with any behavior or permission change.
- Include “Where code lives” pointers in PR descriptions for new pages.
- Tests: prefer integration tests that hit route + template path for core flows.

---

# 1. Roles & Menus

## 1.1 Roles (applies to **User** accounts only)
- **Sys Admin** — platform-wide admin incl. settings and user management.
- **Admin** — staff-level admin incl. user management.
- **CRM (Client Relationship Manager)** — owns session setup, client comms; can create/edit sessions, assign facilitators, manage participants, send prework/invites, finalize.
- **Delivery (Facilitator)** — sees and works own assigned sessions; delivery-centric UX.
- **Contractor** — limited internal user; no settings; see §1.4 for exact capabilities.

> **CSA** and **Participant/Learner** are **not user roles**; they are **participant accounts** (see §2).

## 1.2 Menus by Audience (explicit; no bundling)

- **Sys Admin** (default view: Admin)  
  `Home • My Sessions • Sessions • Materials • Surveys • My Resources • Settings ▾ • My Profile • Logout`  
  **Settings ▾**: `Users • Roles Matrix • Workshop Types • Resources • Simulation Outlines`

- **Admin** (default view: Admin)  
  Same as Sys Admin. (System-wide toggles reserved for Sys Admin if any.)

- **CRM** (default view: Session Manager)  
  `Home • My Sessions • Sessions • Materials • Surveys • My Resources • My Profile • Logout`  
  **Default filters**: “My Sessions” = sessions I own / I’m assigned CRM on the client (if model supports client CRM; else owner fallback).

- **Delivery / Facilitator** (default view: Delivery)  
  `Home • My Sessions • My Resources • My Profile • Logout`  
  (No Materials or Surveys in menu.)

- **Contractor** (default view: Admin-lite)  
  `Home • My Sessions • Sessions (read-only) • My Resources • My Profile • Logout`  
  - No Materials/Surveys/Settings in menu.  
  - Can add/remove participants similar to CSA **including during session**; other session fields are read-only.

- **CSA (Session Admin)** — **participant account**, not a user  
  `Home • My Sessions • My Workshops • My Resources • My Profile • Logout`

- **Participant / Learner**  
  `Home • My Workshops • My Resources • My Profile • Logout`  
  - **My Certificates**: no persistent menu item; a link/section appears only if they have ≥1 certificate.

> Staff view switcher exists for **User** accounts (Sys Admin/Admin/CRM/Delivery/Contractor). **Participants/CSAs** do not see a switcher.

## 1.3 “KT Staff” definition (derived, not stored)
- KT Staff = any **User** account that is **not** Contractor and **not** a participant/CSA.  
- Do **not** persist `is_kt_staff`; if present in schema, stop using it and compute at runtime.

## 1.4 High-level permissions (delta highlights)
- **CRM**: full session lifecycle; Materials access; default owner/CRM filters.
- **Delivery**: operates own sessions; no Materials/Surveys menu.
- **Contractor**: no Settings/Materials/Surveys; can add/remove participants and send prework like CSA **even after start**; cannot change prework settings; other session fields read-only.
- **CSA**: add/remove participants **before** start only; read-only after; no email sending; no Materials/Settings.

---

# 2. Accounts & Identity

Two separate tables by design; emails unique per table. If both tables hold the same email, the **User** record governs authentication, menus, and profile.

## 2.1 Users (internal)
- Table: `users`
- Unique: `lower(email)`
- Roles: booleans/role map (Sys Admin, Admin, CRM, Delivery, Contractor).
- Auth: standard password hash.
- Profile: full_name, **title**, preferred_language, region

## 2.2 Participant Accounts (learners & CSAs)
- Table: `participant_accounts`  
- Unique: `lower(email)`  
- Profile: full_name, certificate_name, preferred_language, is_active, last_login
- **Defaults**:  
  - Participant/Learner temp password: **`KTRocks!`**  
  - **CSA** temp password: **`KTRocks!CSA`**
- No forced password change. Users can change under **My Profile**.

---

# 3. Data Model (summary)

## 3.1 Catalog & Sessions
- `workshop_types` (name, **code**, **simulation_based** bool, **supported_languages** list, **cert_series** string)
- `simulation_outlines` (6-digit **number**, **skill** enum: Systematic Troubleshooting/Frontline/Risk/PSDMxp/Refresher/Custom, **descriptor**, **level** enum: Novice/Competent/Advanced)
- `sessions` (fk workshop_type_id, optional fk simulation_outline_id, start_date, end_date, timezone, location fields, **paper_size** enum A4/LETTER, **workshop_language** enum en/es/fr/ja/de/nl/zh, notes, crm_notes, delivered_at, finalized_at, **no_prework**, **no_material_order**, optional **csa_participant_account_id**)
- `session_facilitators` (m:n users↔sessions)
- `session_participants` (m:n participant_accounts↔sessions + per-person status)

## 3.2 Prework
- `prework_templates` (by workshop type; rich text info)
- `prework_questions` (fk template_id, text, kind enum TEXT/LIST, min_items, max_items, index)
- `prework_assignments` (session × participant; snapshot; due_date; status)
- `prework_answers` (assignment_id, question snapshot, text, item_index)

## 3.3 Resources
- `resources` (name, type enum LINK/DOCUMENT/APP, value/url/path, active)
- `workshop_type_resources` (m:n; unique pair)

## 3.4 Certificates
- `certificates` (session_id, participant_account_id, file_path, issued_at, layout_version; unique pair)
  Files under `/srv/certificates/<year>/<session_id>/<workshop_code>_<certificate_name_slug>_<YYYY-MM-DD>.pdf` (using `workshop_types.code`).

## 3.5 Materials
- `materials_orders` (session_id, **format** enum: All Physical/All Digital/Mixed/SIM Only; four **physical_components** booleans; **po_number**; **latest_arrival_date**; ship_date; courier; tracking; special_instructions)
- `materials_order_items` (order_id, sku/desc, qty, notes)
- `session_shipping` (address/contact fields)

## 3.6 Clients (if present)
- `clients`, `client_locations` and linkage tables as per migrations.

---

# 4. Gating by Lifecycle

## 4.1 Participant/Learner
- **Before start**:  
  - If prework enabled → sees **Prework** for that workshop.  
  - **My Resources** hidden (unless prior workshops started).  
- **From start → before delivered**: **My Resources** visible for that session (plus any past sessions).  
- **After delivered/finalized**: **My Certificates** section/link appears if ≥1 cert exists.

## 4.2 CSA (participant)
- **My Sessions**: only sessions where this participant account is CSA; link opens participant management.  
- Add/remove participants **until start**; read-only after.

## 4.3 Delivery (facilitator)
- **My Sessions**: sessions where user is a facilitator; delivery data visible (address, timezone, notes).

## 4.4 CRM
- Full session lifecycle. Defaults on **My Sessions** to owner/CRM scope.

---

# 5. Prework

- Configured per **Workshop Type** (rich text + questions).  
- Session **Send Prework** (staff) provisions participant accounts (see defaults in §2.2) and emails access.
  - Allowed roles: Sys Admin, Admin, CRM, Delivery, Contractor.
- “No prework for this workshop” disables assignment; **Send Accounts (no prework)** sends credentials only.  
- Participant prework hidden after session starts.

---

# 6. Resources

- Managed at **Settings → Resources**; mapped to Workshop Types.  
- Learner/CSA **My Resources** shows only workshop types associated with sessions for that participant **whose start date has passed**.  
- Files under `/resources/<title-as-filename>`; links download directly.

---

# 7. Validation & Forms

- **Dates**: `end_date >= start_date` (one-day workshops allowed).
- **New Session inline adds**: Add Client, Location, and Shipping within dialogs on the form. These dialogs mirror the full-page create forms (same fields and validation), show field-level errors inline, and saving selects the new item while preserving all other inputs.
- **Past-start acknowledgment**: required **only when the start date is changed in this save** and becomes a past date.
  - Prompt appears immediately when Start Date changes to a past value and stores acknowledgment for that exact date. Changing the date again clears prior ack and re-prompts only if the new value is also in the past.
- **Times**: display `HH:MM` only + short timezone.
- **Profile**: staff `/profile` shows **Certificate Name**; saving sets the participant `certificate_name` for the same email (creating the participant if missing). Learners edit `ParticipantAccount.full_name` and `certificate_name`.
- **Staff-as-Participant**: adding a participant with a staff email is allowed; if a matching `participant_account` is missing, create it seeded with `User.full_name`, `User.title` (if any), and `certificate_name = User.full_name`. Existing accounts are reused.
- **/profile**: staff edit `User.full_name`, `User.title`, and Certificate Name; learners edit `ParticipantAccount.full_name` and `certificate_name`. Optional sync button copies staff full_name to participant.
- **Session language**: single `workshop_language` field; selected before Workshop Type. Type options filter to those whose `supported_languages` include it. Changing the language clears incompatible types, and saving with a mismatch errors.
- **Sessions & Settings**: all language pickers and labels show human names; templates use global `lang_label` helper to render codes; database stores codes; deactivated languages are not selectable; sort by configured order.
- **Materials**: physical components UI:
  - **All Physical** → 4 checkboxes visible and auto-checked (editable)
  - **Mixed** → 4 visible, unchecked
  - **All Digital / SIM Only** → 4 visible, disabled

---

# 8. Certificates

- Issued post-delivery. Template name: `<cert_series>cert_template_{a4|letter}_{lang}.pdf` (falls back to `fncert_template_*` if missing, logging a warning). Stored under `app/assets/`.
- Paper size derives from session Region (North America → Letter; others → A4).
- Name line: Y=145 mm; italic; auto-shrink 48→32; centered. On **Letter**, the recipient Name text box is narrowed by **2.5 cm** on the left and **2.5 cm** on the right (total horizontal reduction = 5.0 cm).
- Filename rule: `<workshop_type.code>_<certificate_name_slug>_<YYYY-MM-DD>.pdf` saved under `/srv/certificates/<year>/<session_id>/`.
- Workshop line at 102 mm; date line at 83 mm in `d Month YYYY` using session end date.
- Learner sees **My Certificates** only if they own ≥1 certificate.

---

# 9. Materials Dashboard (current behavior)

- **Default sort**: **Latest Arrival Date ascending** (earliest due first).  
- **Columns**: Session, Client, Workshop Type, Latest Arrival, Format, Physical Components, PO Number, Status, Ship Date, Courier/Tracking.  
- **Filters** (currently implemented): status, format. (Future: date range, components, type, facilitator.)  
- **Row actions** per permissions: Open, Edit, Mark Shipped, Mark Delivered.

---

# 10. Emails & Auth

- **Magic links are disabled.** Any legacy endpoints must return HTTP 410 Gone or redirect to sign-in.  
- Prework & account-invite emails include: **URL, username (email), temp password** (`KTRocks!` or `KTRocks!CSA`).  
- Users can change passwords in **My Profile**; no forced password change.

---

# 11. Promotion/Demotion

- **Promote participant → user** (Admin/Sys Admin): creates a **User** entry; participant record remains.  
- **Demote user → contractor** (Admin/Sys Admin): strips roles, sets Contractor. Prevent demoting last Admin/Sys Admin.  
- **CSA** is a participant linked to session; no staff role granted.

---

# 12. Where Code Lives (pointers)

- **Nav & Menus**: `app/templates/nav.html`, helpers `app/utils/nav.py`, view prefs `app/utils/views.py`
- **Home**: `app/templates/home.html` (+ role/view partials)
- **Sessions**: routes `app/routes/sessions.py`
  - Form: `app/templates/sessions/form.html`
  - Detail: `app/templates/session_detail.html`
  - Prework tab (staff): `app/templates/sessions/prework.html`
  - Materials tab (session): `app/templates/sessions/materials.html`
  - Participant add/import: `/sessions/<id>/participants/add` in `app/routes/sessions.py`
- **Session language**: field on sessions form/route (`app/templates/sessions/form.html`, `app/routes/sessions.py`); consumed by `app/utils/certificates.py`
- **Learner**: routes `app/routes/learner.py`
  - My Workshops: `app/templates/my_sessions.html`
  - My Certificates: `app/templates/my_certificates.html`
  - Prework: `app/templates/my_prework.html`, `app/templates/prework_form.html`, `app/templates/prework_download.html`
  - Profile (Certificate Name): `app/routes/learner.py`, `app/templates/profile.html`
- **CSA**: routes `app/routes/csa.py`, template `app/templates/csa/my_sessions.html`
- **Workshop Types**: `app/routes/workshop_types.py`, templates under `app/templates/workshop_types/`
  - Prework config: `app/templates/workshop_types/prework.html`
- **Resources (settings)**: `app/routes/settings_resources.py`, `app/templates/settings_resources/*.html`
- **Simulation Outlines**: `app/routes/settings_simulations.py`, `app/templates/settings_simulations/*.html`
- **Materials (dashboard & orders)**: `app/routes/materials.py`, `app/routes/materials_orders.py`, templates `app/templates/materials/*.html`, `app/templates/materials_orders.html`
- **Users & Roles**: `app/routes/users.py`, `app/templates/users/*.html`; matrix `app/routes/settings_roles.py`, `app/templates/settings_roles.html`
- **Email**: `app/emailer.py`, `app/templates/email/*.html|.txt`
- **Certificates**: generator `app/utils/certificates.py` (region→paper mapping, explicit asset path); templates under `app/assets/`
- **Utils**: `app/utils/materials.py` (arrival logic), `app/utils/time.py`, `app/utils/acl.py`, `app/utils/languages.py` (`code_to_label` powering global `lang_label` filter)
- **Ops CLI**: `manage.py account_dupes`

---

# 13. QA Checklists

- **Menus** match §1.2 per role; staff switcher excludes CSA/Learner; participants/CSAs have no switcher.
- **Learner gating** per §4.1; CSA window per §4.2; Contractor behavior per §1.2/§1.4.
- **Resources** list only workshop types whose sessions have **started** for that participant.
- **Materials** UI rules per §7; dashboard sort & columns match §9.
- **Emails** include URL/username/password; no magic links.
- **Validation**: one-day allowed; past-start acknowledgment only when start date **changes** to a past date.

---

# 14. Change Control Notes

- Magic-link infra disabled and endpoints should return 410/redirect.  
- “KT Staff” is a derived condition; any stored boolean is deprecated and must not drive logic.  
- CSA password default is **`KTRocks!CSA`**; other participants **`KTRocks!`**.  
- Contractor menu/capabilities updated per §1.2/§1.4.  
- Materials dashboard documented to current behavior.
