
# 0. Engineering Context & Rules

This is the **authoritative functional & architectural context** for Certs & Badges (CBS). It supersedes prior drafts.  
Every functional change must update this file **in the same PR**.

## 0.1 Environment & Stack
- **App**: Python (Flask), Gunicorn
- **DB**: PostgreSQL 16
- **Proxy**: Caddy → `app:8000`
- **Caddy config**: repo-managed at `caddy/Caddyfile` and bind-mounted to `/etc/caddy/Caddyfile`; `/certificates/*` and `/badges/*` are served via `handle` from `/srv` while Flask serves `/static/*`
- **Docker Compose services**: `cbs-app-1`, `cbs-db-1`, `cbs-caddy-1`
- **In-container paths**: code at `/app/app/...`; site mount at `/srv` (host `./site`)
- **Certificate templates**: host `./data/cert-assets` is bind-mounted to `/app/app/assets`; seed it from `app/assets/` on first deploy and keep it backed up for persistence.
- **Health**: `GET /healthz` must respond `OK`
- **Language seeding**: optional `SEED_LANGUAGES=1` at boot inserts the default language set when the table is empty. Idempotent and safe — if languages exist it logs `Languages already present — skipping.`; on insert it logs `Seeded N languages.`; errors log `Language seed failed: <err>`.

## 0.2 Deploy & Migrations (no local aliases)
- **Deploy on VPS** (`~/cbs`):
  1) `git pull origin main`
  2) Ensure `data/cert-assets/` exists and mirrors any new templates (e.g. `cp -a app/assets/. data/cert-assets/` when seeding a fresh host).
  3) `docker compose up -d --build`
  4) `docker compose ps`
  5) `docker logs cbs-app-1 --tail 80`
- **DB** (inside app container):
  - Create: `python manage.py db migrate -m "message"`
  - Apply: `python manage.py db upgrade`

- We favor idempotent SQL (`IF NOT EXISTS`, `COALESCE` backfills) to allow safe re-runs.

- 2025-10-05: Corrected migration `0074_workshop_type_active` to chain after `0073_user_profile_contact_fields` and keep its upgrade/downgrade reversible.
- 2025-09-29: Fixed Alembic metadata header for migration `0071_prework_invites` so it imports cleanly.
- 2025-09-23: Added shim migration `0072_prework_disable_fields` to chain `9e9d34b28f26` to the renumbered `0073_user_profile_contact_fields` migration.

## 0.3 Coding Rules
- Do **not** include local PowerShell aliases in docs or code.
- Business logic stays server-side; small JS for UI only.
- All timestamps stored UTC; display with short timezone labels; **never show seconds**.
- Certificates: `<certs_root>/<year>/<session_id>/<workshop_code>_<certificate_name_slug>_<YYYY-MM-DD>.pdf` (`<certs_root>` = `SITE_ROOT/certificates`, default `/srv/certificates`); `pdf_path` in DB is stored relative to `<certs_root>`.
- Certificate generation is blocked unless the participant has Full attendance recorded for every class day; the server rejects attempts that bypass the UI.
- Certificate templates resolve under `app/assets`. Explicit series mappings from Settings take precedence regardless of filename, falling back to canonical `fncert_template_{paper}_{lang}.pdf` then legacy `fncert_{paper}_{lang}.pdf`. Inputs normalize case (`A4`/`LETTER`, `en`/`pt-br`), errors list attempted names alongside available PDFs, preview and generation share the same resolver, and caches include absolute path + file mtime to avoid stale templates.
- Template Preview is resilient: falls back to a default font or blank background with visible warnings; generation behavior is unchanged.
- Emails lowercased-unique per table (see §2). Enforce in DB and app.
- Emails may exist in both **users** and **participant_accounts**; when both do, the **User** record governs authentication, menus, and profile.
 - “KT Staff” is a **derived condition** (see §1.4), **not** a stored role.
- Experimental features must register in `shared.flags` and be disabled by default.
- `/forgot-password` redirects to `/login?forgot=1` (optionally `&email=`) to surface the forgot-password modal on the unified login page.
- The login page uses the auth-only layout: flashes render centered above the auth card, auto-fade after ~3 seconds with no manual close, and modal spacing matches auth inputs (email field full-width) for visual alignment.
- The login page's “Forgot password?” link keeps KT primary coloring, adds underline + focus-outline feedback on hover/focus, and maintains AA contrast (visited state included) without shifting layout.
- Save-required forms include `data-dirty-guard="true"`, enabling `app/static/js/dirty_guard.js` to warn about unsaved changes; elements or auxiliary forms that should bypass the prompt must include `data-dirty-guard-bypass="true"`.
- GET filter forms tagged `data-autofilter="true"` auto-submit on change/typing via `app/static/js/auto_filter.js`; templates surface a left-aligned “Clear all filters” link (use `macros/filters.clear_filters_link`) that points to the route without query parameters.

## 0.4 App Conventions & PR Hygiene
- Keep migrations idempotent and reversible; guard enum/DDL changes carefully.
- Add/modify routes with explicit permission checks close to controller entry.
- Update **this file** with any behavior or permission change.
- Include “Where code lives” pointers in PR descriptions for new pages.
- Tests: prefer integration tests that hit route + template path for core flows.
- Formatting: Black-compatible; imports grouped as stdlib, third-party, local with blank lines between groups.
- Templates render language names via `lang_label`; codes are never shown directly.
- Workshop Types expose an `active` boolean (checkbox in forms); the legacy free-text `status` field is deprecated and ignored by new code. Session create lists only active types, while session edit keeps an already-selected inactive type available so existing workshops remain stable.
- Materials order creation flows list only clients with `status = 'active'`. Edit forms keep the bound inactive client selectable but hide other inactive clients. Server-side validation rejects inactive client IDs on create and blocks switching to a different inactive client during edit.
- Smoke suite is limited to eight tests covering auth/roles, dashboards segregation, materials lifecycle, delivered/finalize guardrails, prework invites & disable modes, attendance certificate gating, resources visibility, and profile contact persistence.

## 0.5 Test Strategy
- **Buckets**:
  - **Smoke** – fast, deterministic core flows.
  - **Full** – all tests except `slow` and `quarantine`.
  - **Slow** – long-running tests executed nightly.
  - **Quarantine** – flaky tests excluded until stabilized.
- **Run policy**:

| Context         | Buckets                     |
|-----------------|-----------------------------|
| Local / PR      | Smoke                       |
| CI push / merge | Full (parallel)             |
| Nightly         | Full + Slow + static checks |

- **Running**: use the marker name (`smoke`, `full`, `slow`, `quarantine`) to select buckets.
- `pytest` runs `-q -m "smoke"` by default; use `pytest -m "not slow"` for the full suite.
- **Timing (top 5 tests, seconds)**:
  - `test_passwords::test_manual_participant_create_login` – 0.91
  - `test_passwords::test_forgot_password_flow` – 0.83
  - `test_passwords::test_admin_set_password_logs` – 0.83
  - `test_csa_assign_email::test_csa_assign_email_logs` – 0.81
  - `test_passwords::test_add_staff_user_as_participant` – 0.81
- **Quarantined tests**: none

## 0.6 Brand Fonts & Tokens
- Fonts:
  - Headings use **Raleway**.
  - Body text uses **Roboto**.
  - `.kt-display` applies **Neptune** for opt-in display/hero text.
- Tokens (defined in `/static/css/brand.css`):
  - Colors:
    - `--kt-primary`: `#0057B7` (Sapphire)
    - `--kt-primary-hover`: `#007DC5` (Medium Blue)
    - `--kt-info`: `#009CDE` (Azure)
    - `--kt-text`: `#002C5B` (Navy)
    - `--kt-body`: `#111111` (approved dark for long text)
    - `--kt-muted`: `#6D6E71` (Ash)
    - `--kt-border`: `#D1D3D4` (Light Gray)
    - `--kt-bg`: `#FFFFFF` (White)
    - `--kt-accent-green`: `#A4D65E`
    - `--kt-accent-yellow`: `#F4E501`
    - `--kt-accent-orange`: `#F68D2E`
    - `--kt-accent-red`: `#E03C31`
  - Spacing scale (`8px` rhythm): `--space-1: 4px` … `--space-6: 32px`
  - Radius: `--radius-md: 12px`; `--radius-lg: 16px`
  - Focus outline: `2px solid var(--kt-info)`

- Tables: default `<table>` elements use `/static/css/table.css` with header/stripe/hover tints from `--kt-info`, text colors from `--kt-text` and `--kt-body`, borders `--kt-border`, and cell padding `var(--space-2)`/`var(--space-3)`. Empty states render via `shared/_table_empty.html`, which outputs a muted “No data to display” row spanning the table.

## 0.7 Buttons & Links
- Native buttons (`button`, `[type=button]`, `[type=submit]`, `[type=reset]`) and elements with `.btn` share KT styling.
- Variants: default/`.btn-primary`, `.btn-secondary` (white background, `--kt-text`, `--kt-border`, light `--kt-info` hover), `.btn-success` (`--kt-accent-green`, `--kt-text`), `.btn-danger` (`--kt-accent-red`). Optional sizes `.btn-sm` and `.btn-lg` adjust padding and font size.
- Buttons show a `2px solid var(--kt-info)` focus ring with offset and reduce opacity with `cursor: not-allowed` when disabled.
- Links use `--kt-info`, darken toward `--kt-primary-hover` on hover/active, and show the same focus ring when focus-visible.
- Button styles live in `/static/css/buttons.css`; link styles live in `/static/css/ui.css`. Both load globally.

## 0.8 Form Controls
- Inputs, selects, textareas, radios, checkboxes, file controls, and helper/error text follow KT tokens for color, spacing, and focus rings.
- Styles live in `/static/css/forms.css` and load globally.
- Single-line controls include default 10px horizontal and 8px vertical margins to keep adjacent fields separated; inline actions like "Add" or "Edit" links sit 8px away.
- `.filters` and `.filter-row` provide optional flex wrapping with these gaps via `column-gap`/`row-gap`.
- Date/datetime inputs use a compact global style (tight WebKit indicator spacing with the icon translated flush to the right edge, ~14ch width with a 160px cap) so fields stay narrow by default; add `.kt-date--wide` when a wider field is necessary. Their left padding is trimmed globally so text sits closer to the edge without affecting height or the calendar icon gutter.
- `.form-align__control--wide` widens multiline fields (currently the session Notes and Materials Special instructions textareas) to ~640px on desktop while staying responsive below 576px.

## 0.9 Navigation & Breadcrumbs
- Header and main navigation use `/static/css/nav.css` with `--kt-bg` background, `--kt-text`/`--kt-info` links, and Raleway headings.
- Links show underline and `--kt-primary-hover` on hover, a `--focus-outline` ring on focus, and a `--kt-primary` underline/border for the current page.
- Breadcrumbs use Raleway, muted separators, `--kt-info` links, and mark the current page with `--kt-text`.

## 0.10 Sidebar
- Left sidebar uses `--kt-bg` background and `--kt-text` links.
- Links underline and shift toward `--kt-primary-hover` on hover, keep a `2px solid var(--kt-info)` outline on focus, and show a `--kt-primary` left border with semibold text when active.
- Active links are marked with `aria-current="page"` only when the path exactly matches; ancestor items add `is-ancestor` and show a light `--kt-border` left border with medium weight. Expansion continues to use native `<details>` elements.
- Footer select follows global form control styling.

## 0.11 Flash/Alerts
- Flash messages render as `.flash` elements with variants `.flash-success`, `.flash-error`, `.flash-warning`, and `.flash-info`.
- Markup: `<div class="flash flash-{{ category }}" role="alert" aria-live="polite" tabindex="0">…</div>`.
- Styles live in `/static/css/alerts.css` and load globally after `sidebar.css`.
- Flashes persist for their auto-dismiss window; there is no manual close button.

## 0.12 Cards
- `.kt-card` wraps tables or forms for visual grouping using brand tokens.
- `.kt-card-title` applies heading styling inside a card.

---

# 1. Roles & Menus

Roles control permissions; Views control menu visibility.

## 1.1 Roles (applies to **User** accounts only)
- **Sys Admin** — platform-wide admin incl. settings and user management.
- **Admin** — staff-level admin incl. user management.
- **CRM (Client Relationship Manager)** — owns session setup, client comms; can create/edit sessions, assign facilitators, manage participants, send prework/invites, finalize.
- **Delivery (Facilitator)** — sees and works own assigned sessions; delivery-centric UX.
- **Contractor** — limited internal user; access restricted to assigned sessions; no settings; see §1.5 for exact capabilities.

> **CSA** and **Participant/Learner** are **not user roles**; they are **participant accounts** (see §2).

## 1.2 Views & Menus

### 1.2.1 Home & view defaults

- Users with **Delivery** or **Contractor** land on `/my-sessions`. Delivery-only staff (no Admin/CRM roles) see the selector with **Delivery** (default), Session Admin, Learner; Contractors do not see a selector.
- Users with **CRM** but no Delivery/Contractor land on `/my-sessions` with default view **Session Manager** and selector options Session Manager, Material Manager, Learner. Their My Sessions table is scoped to sessions whose client CRM matches the user.
- Staff who have Delivery plus other roles still land on `/my-sessions` and retain the full selector; facilitator-linked sessions continue opening `/workshops/<id>`.
- Admin-only staff (no CRM/Delivery) keep the existing `/home` landing and selector behavior.
- Learner-facing landings (Home for the Learner view, `/my-workshops`, and `/csa/my-sessions`) open with a single shared heading: `Welcome to KT Workshops, <First name>!`. The heading lives in `shared/_welcome.html`, uses the standard section-title scale, and derives the name from the first token of the user's full name (falling back to certificate name/email). No other greeting banners render for Learner/CSA contexts.

- **Admin**
  - Home
  - New Order
  - Workshop Dashboard
  - Material Dashboard
  - Surveys
  - My Profile ▾: My Profile, My Resources, My Certificates
  - Settings ▾: Clients, Workshop Types, Material Settings, Simulation Outlines, Resources, Languages, Certificate Templates, Users, Mail & Notification
  - Logout
- **Session Manager**
  - Home
  - New Order
  - Workshop Dashboard
  - Material Dashboard
  - Surveys
  - My Profile ▾: My Profile, My Resources, My Certificates
  - Settings ▾: Clients, Workshop Types, Resources, Certificate Templates
  - Logout
- **Session Admin**
  - Home
  - My Sessions
  - Workshop Dashboard
  - Material Dashboard
  - My Profile ▾: My Profile, My Resources, My Certificates
  - Logout
- **Material Manager**
  - Home
  - New Order
  - Material Dashboard
  - My Profile ▾: My Profile, My Resources, My Certificates
  - Settings ▾: Clients, Workshop Types, Material Settings, Simulation Outlines, Resources
  - Logout
- **Delivery**
  - Home
  - My Sessions
  - Workshop Dashboard
  - Surveys
  - My Profile ▾: My Profile, My Resources, My Certificates
  - Settings ▾: Resources
  - Logout
- **Learner**
  - Home
  - My Workshops
  - My Resources
  - My Certificates
  - My Profile
  - Logout

Delivery (KT Facilitator) and Contractor accounts open the workshop runner view when selecting sessions from **My Sessions**. Other staff and CSA roles continue to the staff session detail page.
- **My Sessions**: Admin, CRM, and Delivery roles see an **Edit** action per row; Contractors, CSA, and Learner accounts do not.

## 1.3 View Selector
Only SysAdmin, Administrator, CRM, and KT Facilitator roles see the View selector. CSA, Participant, and Contractor do not. For KT Staff, a muted "Switch views here." hint appears directly beneath the selector inside the left navigation; there is no banner elsewhere.

## 1.4 “KT Staff” definition (derived, not stored)
- KT Staff = any **User** account that is **not** Contractor and **not** a participant/CSA.  
- Do **not** persist `is_kt_staff`; if present in schema, stop using it and compute at runtime.

## 1.5 High-level permissions (delta highlights)
- **CRM**: full session lifecycle; Materials access; default owner/CRM filters.
- **Delivery**: operates own sessions; no Materials/Surveys menu.
- **Contractor**: no Settings/Materials/Surveys; can add/remove participants and send prework like CSA even after start; cannot change prework settings; other session fields read-only; access limited to assigned sessions.
- **CSA**: add/remove participants **until Ready for Delivery**; read-only after; no email sending; no Materials/Settings.

## 1.5 Detailed Permissions Matrix

| Action / Capability                                   | SysAdmin | Admin | CRM | Delivery | Contractor | CSA*                              | Learner                    |
|-------------------------------------------------------|:-------:|:-----:|:---:|:--------:|:----------:|:---------------------------------:|:--------------------------:|
| Settings – System settings                            |   ✓     |   –   |  –  |    –     |     –      |                –                  |            –               |
| Settings – Certificate Templates                      |   ✓     |   ✓   |  –  |    –     |     –      |                –                  |            –               |
| Settings – Languages / Workshop Types / Matrix        |   ✓     |   ✓   |  –  |    –     |     –      |                –                  |            –               |
| Users – Create/Edit/Disable                           |   ✓     |   ✓   |  –  |    –     |     –      |                –                  |            –               |
| Users – Toggle SysAdmin                               |   ✓     |   –   |  –  |    –     |     –      |                –                  |            –               |
| Clients – CRUD                                        |   ✓     |   ✓   |  ✓  |   view   |    view    |                –                  |            –               |
| Sessions – View (list/detail)                         |   ✓     |   ✓   |  ✓  |    ✓     |     ✓      |             assigned              |            own             |
| Sessions – Create                                     |   ✓     |   ✓   |  ✓  |    ✓     |     –      |                –                  |            –               |
| Sessions – Edit (non-participant fields)              |   ✓     |   ✓   |  ✓  |    ✓     |  read-only |                –                  |            –               |
| Sessions – Delete                                     | **✓**   |   –   |  –  |    –     |     –      |                –                  |            –               |
| Sessions – Mark Delivered / Confirm complete          |   ✓     |   ✓   |  ✓  |    ✓     |    **✓**   |                –                  |            –               |
| Participants – Add/Remove                             |   ✓     |   ✓   |  ✓  |    ✓     |     ✓      | **assigned until Ready for Delivery** |            –           |
| Session Prework – access                              |   ✓     |   ✓   |  ✓  |    ✓     |    view    |            assigned view           |            –               |
| Prework – Complete (participant action)               |   –     |   –   |  –  |    –     |     –      |                –                  | **until Delivered**        |
| Materials Order – configure/place                     |   ✓     |   ✓   |  ✓  |   view   |     –      |                –                  |            –               |
| Certificates – Generate (when Delivered)              |   ✓     |   ✓   |  ✓  |    ✓     |    **✓**   |                –                  |            –               |
| Certificates – See (when Delivered)                   |   ✓     |   ✓   |  ✓  |    ✓     |     ✓      |        **assigned sessions**       |   own (via My Certificates) |

*CSA applies only to sessions they are assigned to.

## 1.6 Route Permission Mapping

| Route | Method | Roles | Session Status | Notes |
|-------|--------|-------|----------------|-------|
| `/workshops/<id>` | GET | Delivery, Contractor (assigned) | Any (assigned; materials-only sessions show empty state) | Workshop runner view with overview + participant management |
| `/sessions/<id>/prework` | GET/POST | SysAdmin, Admin, CRM, Delivery, Contractor (assigned) | Any | Staff access only |
| `/sessions/<id>/participants/add` | POST | CSA (assigned) | Until Ready for Delivery | Uses `csa_can_manage_participants` |
| `/sessions/<id>/generate` | POST | SysAdmin, Admin, CRM, Delivery, Contractor | Delivered | Generates certificates |
| `/sessions/<id>/delete` | POST | SysAdmin | Cancelled | SysAdmin-only deletion |
| `/learner/prework/<assignment_id>` | POST | Learner | Until Delivered | Locked after delivery |

---

# 2. Accounts & Identity

Two separate tables by design; emails unique per table. If both tables hold the same email, the **User** record governs authentication, menus, and profile.

## 2.1 Users (internal)
- Table: `users`
- Unique: `lower(email)`
- Roles: booleans/role map (Sys Admin, Admin, CRM, Delivery, Contractor).
- Auth: standard password hash.
- Profile: full_name, **title**, preferred_language, region, optional `phone`, optional location fields (`city`, `state`, `country`), and `profile_image_path` (relative path under `/uploads/profile_pics/<user_id>/<filename>`).

## 2.2 Participant Accounts (learners & CSAs)
- Table: `participant_accounts`
- Unique: `lower(email)`
- Profile: full_name, certificate_name, preferred_language, is_active, last_login, optional `phone` and location fields mirroring the `users` table, plus `profile_image_path` (relative under `/uploads/profile_pics/participant-<id>/<filename>`).
- **Defaults**:  
  - Participant/Learner temp password: **`KTRocks!`**  
  - **CSA** temp password: **`KTRocks!CSA`**
- No forced password change. Users can change under **My Profile**.

---

# 3. Data Model (summary)

## 3.1 Catalog & Sessions
 - `workshop_types` (name, **code**, **simulation_based** bool, **supported_languages** list, **cert_series** code referencing an active certificate series)
 - `simulation_outlines` (6-digit **number**, **skill** enum: Systematic Troubleshooting/Frontline/Risk/PSDMxp/Refresher/Custom, **descriptor**, **level** enum: Novice/Competent/Advanced)
- `sessions` (fk workshop_type_id, optional fk simulation_outline_id, start_date, end_date, timezone, location fields, **paper_size** enum A4/LETTER, **workshop_language** enum en/es/fr/ja/de/nl/zh, notes, crm_notes, delivered_at, finalized_at, **no_prework**, **prework_disabled** (boolean), **prework_disable_mode** (`notify`/`silent`), **no_material_order**, optional **csa_participant_account_id**)
- `session_facilitators` (m:n users↔sessions)
- `session_participants` (m:n participant_accounts↔sessions + per-person status)

### Sessions – Staff shortcuts

- Session Detail exposes a **Delivered** button in the header for staff with edit rights on non–material only sessions; it posts to mark the session delivered without opening the edit form.
- The Participants card shows an **Export all certificates (zip)** button for staff, streaming a zip of existing certificate PDFs from `/srv/certificates/<year>/<session_id>/` without regenerating files.
- Participant CSV import on Session Detail uses a single file chooser that auto-submits and preserves the existing success/error flash behavior.

## 3.2 Prework
- `prework_templates` (by workshop type & language; rich text info; unique per `(workshop_type_id, language)`)
- `prework_questions` (fk template_id, text, kind enum TEXT/LIST, min_items, max_items, index)
- `prework_assignments` (session × participant; snapshot; due_date; status)
- `prework_answers` (assignment_id, question snapshot, text, item_index)
- `prework_invites` (session_id, participant_id, sender_id, sent_at; records every invite attempt for invite status tracking)
- Prework editor exposes a language selector limited to the workshop type’s supported languages; switching languages loads or creates that language’s template and questions without affecting others.
- A **Copy from workshop** control lets staff pick a source workshop type and language, copying that template’s questions (and info text) into the current language after confirming replacements when questions already exist.
- Workshop View and the staff Prework tab show a read-only summary grouped by question with bullets formatted as "**Name**; answer; answer2" using ';' separators (multi-part answers join with '; ' and multiline responses collapse to spaces). Each question displays only its headline — the explicit question title when provided, otherwise the first line of the sanitized prompt — so long instructional paragraphs stay hidden; empty prompts surface as "(Untitled question)".
- Learner submissions keep every entered response (including the first item in list questions) in order; whitespace-only rows are dropped during save.

## 3.3 Resources
- `resources` (name, type enum LINK/DOCUMENT/APP, value/url/path, `description_html`, `language` code, `audience` enum Participant/Facilitator/Both, active)
- `workshop_type_resources` (m:n; unique pair)

## 3.4 Certificates
- `certificates` (session_id, participant_account_id, file_path, issued_at, layout_version; unique pair)
  Files under `/srv/certificates/<year>/<session_id>/<workshop_code>_<certificate_name_slug>_<YYYY-MM-DD>.pdf` (using `workshop_types.code`).

## 3.5 Materials
- `materials_orders` (session_id, **format** enum: All Physical/All Digital/Mixed/SIM Only; four **physical_components** booleans; **po_number**; **latest_arrival_date**; ship_date; courier; tracking; special_instructions)
- `materials_order_items` (order_id, sku/desc, qty, notes)
- `session_shipping` (address/contact fields)
- Catalog items include optional `description` (TEXT) and `sku_physical` (VARCHAR(100)).

### Workshop Type default materials

- `workshop_type_material_defaults` maps `(workshop_type_id, delivery_type, region_code, language)` to a `catalog_ref` material item, `default_format` (Digital/Physical/Self-paced), and `active`. Quantity basis derives from the referenced Material Item.
- `material_order_items` snapshot per-session ordered items with title, description, SKU, language, format, quantity, and processed state.
- Managed inline on the **Workshop Type** form under a “Default Materials” section (`/workshop-types/new` and `/workshop-types/<id>/edit#defaults`). Legacy `/workshop-types/<id>/defaults` redirects here.
- Material item dropdown labels each choice as `<Family> • <ItemTitle>` with optional language tags `• [en, es]`; “KT-Run Standard materials” and “KT-Run Modular materials” display as “Standard” and “Modular.”
- The dropdown filters items by the row’s Language and excludes the “Client-run Bulk order” catalog; no “Show all” toggle.
- The edit page header links to **Prework** as a separate action; the H1 remains “Edit Workshop Type.”

## 3.6 Clients (if present)
- `clients`, `client_locations` and linkage tables as per migrations.
- Admins may delete clients only when no sessions reference them. Successful deletes flash confirmation; attempts with related records respond with a 4xx and surface the existing “Cannot delete client with sessions” or integrity error message.

## 3.7 Attendance storage & endpoints
- Table: `participant_attendance` (`session_id`, `participant_id`, `day_index`, `attended` boolean default `false`, timestamps). Unique per `(session_id, participant_id, day_index)` with cascade deletes tied to sessions/participants.
- API:
  - `POST /sessions/<id>/attendance/toggle` – upserts a single record and returns `{ok, attended}`.
  - `POST /sessions/<id>/attendance/mark_all_attended` – bulk sets all `day_index` 1..N to attended for the session and returns `{ok, updated_count}`.
  - Endpoints respond with JSON only; they do not emit global flash messages.
- Auth: Admin/CRM staff or Delivery/Contractor assigned to the session. Learners/CSA accounts receive `403`.
- Material only sessions (`delivery_type = "Material only"`) reject both endpoints with `403`.
- UI:
  - `number_of_class_days` controls the Day 1..N columns. Increasing the count surfaces new unchecked days; decreasing hides extra columns without deleting stored attendance rows.
  - Workshop View (`/workshops/<id>`) and Session Detail (`/sessions/<id>`) show per-participant Day 1..N checkboxes plus a “Mark all attended” bulk action. Controls render for staff and assigned facilitators only.
  - Attendance actions display inline notices (“Saved”, “All marked attended”, or error text) at the top of the Participants card; each fades after ~3 seconds.
  - Learners/CSA never see attendance controls. Certificate generation remains unchanged.

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
- Add/remove participants **until Ready for Delivery**; read-only after.

## 4.3 Delivery (facilitator)
- **My Sessions**: sessions where user is a facilitator; delivery data visible (address, timezone, notes). Delivery (KT Facilitator) and Contractor accounts always open `/workshops/<session_id>` for sessions where they are lead or co-facilitators, even when they also hold Admin/CRM roles. Other staff retain the `/sessions/<id>` detail link.

  - **Workshop View** (`/workshops/<session_id>`): runner-focused layout with the heading `"<id> <title>: <workshop_code> (<delivery_type>) - <status>"`, a slimmed overview card (location moved left; type/delivery/status removed), and a Participants card above Resources. Facilitators manage participants inline (add, edit, remove, completion date, CSV import) with certificate links mirroring staff detail. The Resources card lists active resources assigned to the session's workshop type where `audience ∈ {Facilitator, Both}` and `resource.language == session.workshop_language`, using the same tile layout as the learner view (expanded by default) and showing the standard empty-state copy when none match. A Prework summary card groups responses by question using ';' separators. Materials-only sessions render an empty state message instead of workshop details.
    - Delivered button blocks sessions with zero participants unless `session.prework_disable_mode == "silent"` (red “No prework & don’t send accounts” action).


## 4.4 CRM
- Full session lifecycle. Defaults on **My Sessions** to owner/CRM scope.

---

# 5. Prework

- Configured per **Workshop Type & language** (rich text + questions; editor includes a language selector limited to the type’s supported languages).
- Session **Send Prework** (staff) provisions participant accounts (see defaults in §2.2) and emails access.
  - Allowed roles: Sys Admin, Admin, CRM, Delivery, Contractor.
- Workshop View toolbar includes **No prework – Create accounts** (disables assignments, provisions ParticipantAccounts/Users for all current participants, and emails the standard account invite; sets `session.prework_disabled=True`, `session.prework_disable_mode="notify"`) and **No prework & don’t send accounts** (same provisioning without email, sets `prework_disable_mode="silent"`, and is the only path that permits Delivered with zero participants). Both states hide row/bulk prework send actions and replace the column with a “None for workshop” label.
- Learner links, email invites, and assignment snapshots always resolve the prework template by `(session.workshop_type_id, session.workshop_language)`; if that language has no template configured the flows display the empty-state instead of falling back to another language.
- Participant prework hidden after session starts.
- Workshop View Participants card now surfaces invite status (“Not sent” or “Sent <date> (x times)” using `prework_invites` history, falling back to assignment sent timestamps for legacy data). KT staff and assigned facilitators can still trigger row-level **Send prework** or the bulk **Send prework to all not sent** action; learners/CSA never see invite state or actions. Successful sends update the status cells immediately via JSON responses so the card reflects the latest invite count without reloading.
- After a successful send (row-level or bulk), the session’s **Workshop info sent** flag flips to **Yes** and records the first-send timestamp.
- Prework summaries on Workshop View and the staff Prework tab only render responses for the session language template.
- Learner prework forms render question text as sanitized rich text (allowed tags: `<p>`, `<br>`, `<strong>`, `<em>`, `<ul>`, `<ol>`, `<li>`, `<a href>` with forced `target="_blank" rel="noopener"`). Inline scripts/styles are stripped on render.

---

# 6. Resources

- Managed at **Settings → Resources**; mapped to Workshop Types with per-resource language and audience selectors. The list view adds Audience/Language filters and surfaces both columns alongside Name/Type/Target/Workshop Types/Active.
- Learner/CSA **My Resources** shows only workshop types associated with sessions for that participant **whose start date has passed** and filters resources to `audience ∈ {Participant, Both}` with `resource.language` matching any started session for that workshop type.
- Staff see the “My Resources” navigation link only if they're assigned to at least one session; they may still visit `/my-resources` directly without participant records, and the page returns HTTP 200 with an empty state when no resources apply.
- Resources include an optional rich-text **Description** stored as sanitized HTML and entered in Settings via a Trix editor; on **My Resources** the resource title toggles a collapsible panel whose expanded state shows the link/file tile followed by the sanitized description.
- Facilitator Workshop View uses the same tile styling, auto-expanding each item, and restricts visibility to facilitator/Both audiences for the session language; the learner view remains unchanged visually.
- “Open resource” buttons use KT primary styling on both Workshop View and My Resources; Settings → Resources constrains the “Target” column with ellipsis + tooltip to prevent layout blowouts.
- Workshop types are de-duplicated by ID in application code to avoid SQL `DISTINCT` on JSON columns such as `supported_languages`.
- `/my-resources` gracefully renders an empty state when no resources are available (never 500s).

- Uploaded files persist under `/srv/resources/<resource_id>/<sanitized_filename>` and are publicly served by Caddy at `/resources/<resource_id>/<sanitized_filename>`; filenames are sanitized (slugged + short hash) to avoid traversal/collisions. Flask exposes the same `/resources/...` path as a development/test fallback when Caddy isn't fronting the app. Certificate and badge storage paths remain unchanged.
- Settings → Resources edit view surfaces the current uploaded file with a download link when present; My Resources prefers the file tile when a stored file URL exists and falls back to the external link otherwise.

---

# 7. Validation & Forms

- **Dates**: `end_date >= start_date` (one-day workshops allowed).
- **New Session inline adds**: Add Client, Location, and Shipping within dialogs on the form. These dialogs mirror the full-page create forms (same fields and validation), show field-level errors inline, and saving selects the new item while preserving all other inputs.
- **Past-start acknowledgment**: triggers immediately when the **Start Date** field value is changed to a past date. Saving does not prompt unless the submitted value is past and unacknowledged. Changing the Start Date clears prior acknowledgment.
- **Times**: display `HH:MM` only + short timezone.
- **Profile**: staff `/profile` shows **Certificate Name**; saving sets the participant `certificate_name` for the same email (creating the participant if missing). Learners edit `ParticipantAccount.full_name` and `certificate_name`. Both staff and learners can update phone, city, state, and country; when any location detail is provided, City is required and at least one of State/Country must also be present. Phone accepts digits plus `+`, spaces, parentheses, and hyphen. Profile photo uploads accept PNG/JPG ≤2&nbsp;MB and store under `/srv/uploads/profile_pics/<owner>/`. Removing a photo clears the database field and deletes the stored image.
- **Staff-as-Participant**: adding a participant with a staff email is allowed; if a matching `participant_account` is missing, create it seeded with `User.full_name`, `User.title` (if any), and `certificate_name = User.full_name`. Existing accounts are reused.
- **/profile**: staff edit `User.full_name`, `User.title`, and Certificate Name; learners edit `ParticipantAccount.full_name` and `certificate_name`. Optional sync button copies staff full_name to participant.
- **Session language**: single `workshop_language` field; selected before Workshop Type. Type options filter to those whose `supported_languages` include it. Changing the language clears incompatible types, and saving with a mismatch errors.

## User Profile — contact info
- The profile form exposes phone, city, state, and country to all authenticated users. Location is optional, but when any field is supplied the city must be filled and at least one of state or country must also be present. Phone input accepts digits plus `+`, spaces, parentheses, and hyphen.
- Profile photos accept PNG/JPG up to 2&nbsp;MB. Files are stored under `/srv/uploads/profile_pics/<owner>/` where `<owner>` is either the numeric user ID or `participant-<id>` for learner accounts; only the relative path (e.g. `/uploads/profile_pics/42/avatar.png`) is persisted.
- Invalid uploads (wrong extension, oversize, or not an image) flash an error without altering stored data. Removing a photo clears the database column and deletes the stored file. Templates fall back to `/static/img/avatar_silhouette.png` whenever `profile_image_path` is empty or missing on disk.
- Stored photos are served through `/uploads/profile_pics/<owner>/<filename>` with path traversal guards so tests and development environments work without Caddy.

## Participant → My Workshops — card layout
- The learner dashboard replaces the table with a vertical accordion of `.kt-card` elements. Each header renders `"<Workshop Type name> – <Start date (d Mon YYYY)> – <language label>"` and is a full-width `<button>` with `aria-expanded` and focus styles. Cards start collapsed; clicking or pressing Space/Enter toggles the associated region (`role="region"`) via accessible JavaScript that also updates `data-expanded` for styling.
- Card body rows display, in order: (1) Prework — links to `Complete prework` when the session has an active assignment (`status != 'WAIVED'`) and `prework_disabled` is false; otherwise shows `No prework`. (2) Facilitators — lists the lead facilitator plus any co-facilitators flagged `is_kt_delivery`/`is_kt_contractor`, each on a single line with a 32px rounded avatar, name, `mailto:` link, and optional phone. Missing photos use the silhouette fallback. When no facilitators qualify, the row shows a muted placeholder. (3) Location — `session.location` when populated, otherwise the workshop location label/city/country, or `Location TBD` if nothing is set. (4) Schedule — renders the date range and the daily start/end time with timezone using `fmt_time_range_with_tz`.
- Only participants assigned to the session (by email) reach these cards; no facilitator data is exposed elsewhere. Layout uses responsive flex so labels stack above values on small screens while preserving WCAG-AA contrast.
- **Region default**: `/sessions/new` preselects the current user's Region when available; users may change it before saving.
- **Sessions & Settings**: all language pickers and labels show human names; templates use global `lang_label` helper to render codes; database stores codes; deactivated languages are not selectable; sort by configured order.
- Materials order view shows **Workshop Type** and **Delivery Type** above Order Type.
 - The **"Default Materials Type"** dropdown has been removed; Workshop Types rely solely on the Default Materials table.
 - The Workshop Type edit page and **New Workshop Type** view include a **Default Materials** table mapping Delivery Type × Region × Language to catalog items with a default format and active flag.
 - Default Materials rows use a dropdown Materials selector; selecting a Material Item limits the row's Language and Default Format lists to that item's allowed values. The selector has no "Show all" toggle. Quantity basis comes from Materials Settings and is not editable on Workshop Types.
- **Materials-only orders** share the session form. `/sessions/new` shows an **Order Information** section (Title, Client with CRM, Region, SFC Project link (optional), Language) with a **No workshop, material order only** button that creates a hidden session (`materials_only = true`, `delivery_type = "Material only"`) and redirects to that session's Materials Order page. Certificates and badges are unaffected and remain gated. The SFC input defaults blank and includes inline help text “Paste the Salesforce Cloud (SFC) project URL if available.”
- **Material only invariant**: when `delivery_type = "Material only"`, setting **Ready for delivery** or **Finalized** forces `status = "Closed"`, and `delivered` remains `False`. Workshop view (`/workshops/<id>`) redirects to the staff session detail. The **Delivered** action is hidden for material-only sessions.
- Staff session detail header now mirrors the Workshop View overview (two-column layout with the same title format, client/location block, notes, and status chips) and they share a single lifecycle toolbar:
  - **Delivered** keeps the “Are you sure? This can’t be undone.” confirm and honors any `next` redirect, flipping the delivered flag and backfilling `ready_for_delivery`/timestamps when needed.
  - A standalone **Ready for delivery** button marks the session ready and stamps `materials_ordered`/`materials_ordered_at` when they were unset. When the session has a materials order and isn’t material-only, the action requires every Material Order item to be processed (`Materials ordered` must already read **Yes**) or it blocks with “There are still material order items outstanding”.
  - Toggling **Materials ordered = Yes** from Session Detail runs the same validation: unprocessed Material Order items block the save with the outstanding-items message; successful flips record the timestamp.
  - **Finalize** remains hidden until **Delivered = Yes** and still enforces the Delivered prerequisite at submit time, including the outstanding-items guard before stamping `materials_ordered`.
- Workshop View exposes the same Delivered button for non–material-only sessions with the shared confirmation copy and redirect handling.
- Clicking **No workshop, material order only** removes `required` constraints from later form fields so only Order Information entries are enforced before submission.
- When `materials_only = true`, training-session features (participants, prework, certificates) are hidden/denied.
 - Default Materials-only **Order Type** = “Client-run Bulk order”.
- **Material Sets** integer field (hidden only when Order Type = Simulation).
- Material Sets default equals the Session Capacity when set; otherwise 0.
- **# of credits (2 teams per credit)** integer field (default 2; shown when Order Type = Simulation or the Workshop Type is simulation-based).


- Materials order header displays `Material Order <session_id> - <session_title>` with client name and delivery region, CRM, and facilitators. A **Shipping details** section lists contact, email, phone, and address (or “Digital only” when absent) and always includes a **Shipping location** dropdown with **Add/Edit locations**, even for materials-only sessions. The Shipping location selector renders above the contact rows, and the read-only contact/address values share the standard single-line control height so their baselines align with editable inputs. Selecting or adding a location immediately refreshes the displayed contact and address. Materials managers may continue editing these header fields after a session is finalized; the form becomes read-only only once the shipment is marked delivered or when the viewer lacks manage permissions. The SFC project link is managed on the session form and does not render on the Materials page.
  - Shipping locations include an optional **Title** field; when blank the UI falls back to `<client name> / <city>` (or the first address/contact value) for display only.
- Materials orders lifecycle:
  - Status values cover **New**, **In progress**, **Processed**, **Finalized**, with legacy **Ordered/Shipped/Delivered/Cancelled/On hold** still available for manual overrides.
  - Newly created shipments default to **New**.
  - Saving changes to header, shipping, or material items moves the status to **In progress** when the prior value was **New** or **Processed**; **Finalized** orders stay untouched by auto-updates.
  - After item updates, if every material row is marked processed the status advances to **Processed**. Unmarking any processed row while the order is **Processed** reverts to **In progress**. **Finalized** never auto-downgrades.
  - The **Ready for Delivery/Finalized** action saves the form, validates that every Material Order item is processed, and blocks with “There are still material order items outstanding” when any remain. On success it sets status to **Finalized**, flips the session's `materials_ordered`/`ready_for_delivery` flags (stamping timestamps as needed), and closes the session (`status = "Closed"`) when the order type is **Client-run Bulk order**.
  - Materials status changes do not alter certificate or badge generation flows.
- Session Materials page uses inline-editable Material Items with per-row Language and Format selects and quantity, saved with a single action; Order date derives from creation time and is read-only; Status is read-only and shown in the title; Courier, Tracking, and Ship date fields render below the items table.
- Material Item rows restrict Language and Format choices to those supported by the selected Material Item. Format defaults from Workshop Type → Default Materials when available.
- Each Material Item row includes a **Processed** checkbox that records the current user and a `yyyy-mm-dd HH:MM UTC` timestamp when checked; unchecking clears the stamp.
- Apply Defaults is enabled only when Order Type = “KT-Run Standard materials” and Material Sets > 0 (disabled tooltip: “Select # of Material sets first.”). The action keeps the selected Material format and adds any missing items from defaults using each item's Quantity basis (“Per learner” → Material Sets, “Per order” → 1) without altering existing rows. The Materials selector is a dropdown with no “Show all” checkbox. The action preserves every shipping field (location, contacts, address lines, courier, tracking, ship date, latest arrival date) exactly as saved.
- The Materials “Special instructions” textarea uses the `form-align` grid, mirrors the ~640px width from the session form, and stays responsive on smaller screens.
- Saving or updating a materials order sends `[CBS] NEW Materials Order – …` / `[CBS] UPDATED Materials Order – …` to the processors matrix (Region × Processing Type) using the bucket mapping and fallback described in §10. Workshop-only sessions never send these notifications.
- POST `/sessions/<session_id>/materials/deliver` sets status to **Delivered** (403 on repeat with friendly flash); POST `/sessions/<session_id>/materials/undeliver` reverts to **In progress**.
- **Sessions list**: sortable columns with default order **ID, Title, Client, Location, Workshop Type, Start Date, Status, Region, Actions**. Title links to the session detail; the **ID** column is the integer session id (plain text) and remains the first column. Filters cover keyword (Title/Client/Location), Status, Region, Delivery Type, and Start-date range; sort/filter state persists within `/sessions`. Optional columns exposed via the chooser include **Facilitator(s)**, **Material order status**, and **CSA Name**. The dashboard suppresses every **Material only** engagement for all users and shows an empty-state message when no workshops match the filters.
- **Dashboard column chooser**:
  - `/sessions`, `/materials`, and `/my-sessions` share the same keyboard-accessible column chooser. **ID** and **Title** stay locked in the first two positions; all other columns may be shown/hidden or reordered.
  - Column layout preferences persist in `localStorage` as `cbs.sessions.columns.<user_id>`, `cbs.materials.columns.<user_id>`, and `cbs.mysessions.columns.<user_id>` (fallbacks omit the user id). Column widths are adjustable via drag handles on header dividers and persist to `cbs.sessions.colwidths.<user_id>`, `cbs.materials.colwidths.<user_id>`, and `cbs.mysessions.colwidths.<user_id>`. Resetting clears both layout and stored widths while leaving filters and sort order intact.
  - `/sessions` defaults remain **ID, Title, Client, Location, Workshop Type, Start Date, Status, Region, Actions** with optional **Facilitator(s)**, **Material order status**, and **CSA Name**.
  - `/materials` defaults now read **Order ID, Title, Status, Workshop start date, Client, Order type, Workshop, Latest arrival date, Workshop status**. Optional columns include **Processed — Digital**, **Processed — Physical**, **Bulk Receiver**, **Outline**, **Credits/Teams** (displayed as `<credits> / <teams>` only when the session has a Simulation Outline; otherwise the cell shows `—`; teams remain derived as two per credit), **Facilitator(s)**, **Learner list**, **Region**, and **Shipping location title**. Bulk Receiver values wrap to reveal long contact names or emails. The processed columns show the latest `yyyy-mm-dd HH:MM UTC` timestamp and processor when available.
  - `/my-sessions` defaults start **ID, Title, Client, Location, Workshop Type, Dates, Region, Delivery Type, Status, Actions**, with Title linking to the staff session detail.
  - Material and session dashboards preload facilitators/CSA data and annotate material order metrics server-side to avoid N+1 queries.
  - Column chooser behavior does not change RBAC; visibility is purely per-user preference.
- **Simulation Outline** shown when Order Type = Simulation or the Workshop Type is simulation-based.
- Material format is always visible. If **Order Type** = “Simulation” and no value is set, default to **SIM Only**. Non-editable roles see the value read-only.
- **Order Type** = “KT-Run Modular materials” → **Materials Type** becomes multi-select and all selected modules are shown; other order types remain single-select.
- On first Materials view for a new session, unset **Order Type** defaults to **KT-Run Standard materials** then **Materials Type** defaults from the Workshop Type (if defined).
- **Role Matrix**: view-only modal launched from `/users`; standalone `/settings/roles` page removed.

---

# 8. Certificates

- Issued post-delivery. Templates are configured under **Settings → Certificate Templates**, where admins define series and map (language, A4/Letter) → PDF and optional badge **filename**. Workshop Types must select one active series and no longer store any badge value. Generation resolves the mapping for the session's type series and language/size; badges reference files under `app/assets/badges`. If any mapping or file is missing, rendering aborts with a clear error (no auto-fallback).
- The Templates page also exposes a **Template Preview** per paper size (A4 and Letter). Staff can render an in-memory PNG preview using sample certificate data, honoring the current on-page layout (fonts, Y-mm positions, details side/size/variables) and language-specific font rules. Previewing never writes to `/srv` or the database; template/background assets load from `app/assets` and font fallbacks surface as non-blocking warnings within the preview panel.
- The template-mapping page offers bulk upload buttons for certificate template PDFs and badge WEBP files. Uploads overwrite by filename, refresh dropdown options, and never auto-change existing mappings. Badge uploads also copy files to the site root (`/srv/badges`) for static serving. Access is restricted to Sys Admin/Admin.
- Paper size derives from session Region (North America → Letter; others → A4).
- **Settings → Languages** tracks an Allowed fonts list. Certificate rendering restricts line fonts to the language’s allowed set; if the configured font is missing or disallowed the renderer falls back to the first allowed+available option (or Helvetica) and logs `[CERT-FONT]` once per substituted line.
- The Languages list view reminds admins to align allowed fonts with KT branding and to upload/install required TTFs when updating the allowed set.
- Each certificate series stores per-size layout metadata covering Learner name, Workshop name, and Completion date (font + Y mm). Defaults preserve prior behavior — learner name at 145 mm (auto-shrink 48→32), workshop at 102 mm, date at 83 mm using the session end date — and Letter layouts continue narrowing the learner name text box by **2.5 cm** on both sides (total 5.0 cm).
- An optional details panel can be enabled per size with Left/Right placement. Each size stores a Size % (50–100) that scales the detail line font/spacing, and rendered lines follow a fixed order regardless of selection order: Facilitators, Location, Dates, and Class days/Contact hours. Location and Dates suppress labels (Location → `City, ST` for US sessions or `City, Country` otherwise, falling back to the saved string when formatting data is incomplete). Class days and Contact hours share a single line with a bullet separator when both values are present; empty variables continue to be skipped without aborting generation.
- Certificates are written to `<certs_root>/<YYYY>/<session_id>/` where `<certs_root>` = `SITE_ROOT/certificates` (default `/srv/certificates`). `YYYY` uses the session start-date year; if missing, use the current year.
- Filenames: `<workshop_type.code>_<certificate_name_slug>_<YYYY-MM-DD>.pdf`.
- `pdf_path` stores the relative path `YYYY/session_id/filename.pdf`. Generation overwrites existing files atomically.
- PDFs are saved with mode `0644` so the Caddy process can read them.
- Download endpoint reads the stored path and serves the file; if the row or file is missing it returns `404` and logs `[CERT-MISSING]`.
- Staff session detail pages left-join `certificates` on `(session_id, participant_id)` and link directly to `/certificates/<pdf_path>` for each participant with a stored path (no id-based proxy).
- Learner and staff profile certificate listings resolve the current account's `participants` and join `certificates` on `participant_id`, linking to `/certificates/<pdf_path>` without recomputing filenames.
- Older builds used `YYYY/<workshop_code>/…`; these paths are legacy.
- Maintenance CLI `purge_orphan_certs` scans the certificates root and deletes files lacking a `certificates` table row. Filenames may vary; presence is determined by DB record.
- `--dry-run` lists candidate paths and a summary without deleting.
- In production, set `ALLOW_CERT_PURGE=1` to enable deletions.
- One-off CLI `backfill_cert_paths` (run: `python manage.py backfill_cert_paths`) updates legacy `YYYY/<workshop_code>/…` rows when a `YYYY/session_id/…` file exists. Safe to skip if not needed.
- Learner nav shows **My Certificates** only if they own ≥1 certificate; staff see **My Profile → My Certificates** only when they have certificates as participants.

---

# 9. Materials Dashboard (current behavior)

- **Default sort**: **Latest Arrival Date ascending** (earliest due first).
- **Eligibility filter**: rows render only when the session involves materials — either `materials_only`, an affirmative `materials_ordered`, a shipment with order detail (order type, material sets/options), or at least one `MaterialOrderItem`. Sessions flagged `no_material_order` stay excluded. Material-only engagements appear here and never on the Workshops dashboard.
- **Columns**: default order **Order ID, Title, Status, Workshop start date, Client, Order type, Workshop, Latest arrival date, Workshop status** with Order ID leading and Title linking to the materials detail page. Additional optional columns surface Processed timestamps, Bulk Receiver, Outline, Credits/Teams (shown as `<credits> / <teams>` only when the session has a Simulation Outline; otherwise the column shows `—`; teams stay calculated as two per credit), Facilitator(s), Learner list, Region, and Shipping location title via the chooser noted above. Bulk Receiver entries wrap so long contact names or emails remain visible within the column width.
- **Column chooser**: matches the Workshops dashboard behavior; see §7 for chooser details.
- **Data prep**: dashboard queries join clients, workshop types, shipping locations, facilitators, and participant names in bulk and use SQL window functions to surface the latest processed Digital/Physical timestamps per order.
- **Filters** (currently implemented): status, format. (Future: date range, components, type, facilitator.)
- **Workshop Status** defaults to **not Closed** (excludes `Session.status = 'Closed'`) until the user explicitly changes the filter. The Show/Hide Closed toggle mutates the `workshop_status` query param (`not_closed` ↔ `all`) and the toolbar shows a chip while the exclusion is active.
- **Row actions** per permissions: Open, Edit, Mark Shipped, Mark Delivered.

---

# 10. Emails & Auth

- **Mail & Notification settings** store SMTP configuration and manage processor assignments mapping (Region, Processing type) → Users for future notifications.
  - Processors render in a table with columns **Region**, **Type**, and **Processors**.
  - Rows auto-populate for every existing Region × {Digital, Physical, Simulation, Other}; only user assignments are editable.
  - Each row shows assigned users as removable chips and supports adding multiple users at once via a searchable selector. Duplicates are prevented.
  - Only users with the **Administrator** role may be assigned as processors. The “Add” selector lists Administrators only and server-side validation skips non-admin submissions.
  - Access requirements are unchanged and saving assignments triggers no notifications.
- Materials order emails now target the processors matrix. Buckets resolve to `Simulation` (Order Type = Simulation, Workshop Type flagged `simulation_based`, or Material Format = SIM Only), `Digital` (Material Format = All Digital), `Physical` (All Physical or Mixed), otherwise `Other`. The lookup falls back `(region, bucket)` → `(region, Other)` → `(Other, bucket)` → `(Other, Other)`; if every rung is empty we log `[MAIL-NO-RECIPIENTS] session=<id> region=<code> bucket=<bucket>` and skip sending. Subjects remain `[CBS] NEW Materials Order – …` / `[CBS] UPDATED Materials Order – …`, Region and Processing Type appear in the email header, and fingerprint guards continue to gate duplicate sends via `Session.materials_order_fingerprint`/`materials_notified_at`.
- Materials processors notification email renders the Client row as `Client - Region` when a region label is present, concatenating into a single macro value to avoid arity errors and 500s when saving materials orders.
  - Outbound mail normalizes recipient inputs (comma/semicolon splitting, whitespace trim, case-insensitive dedupe, invalid token warnings) and passes the SMTP envelope a list of addresses so multi-processor deliveries succeed on Office365 while the To header stays human-readable.
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

The repo is organized **feature-first**. Top-level packages:

- `accounts/`
- `sessions/`
- `materials/`
- `certificates/`
- `surveys/`
- `settings/`
- `admin/`
- `shared/` – cross-cutting concerns (see below)

Each feature package contains `routes/`, `models/`, `services/` (business rules), `forms/`, `templates/`, and a `README.md` noting scope and owner.

`shared/` contains common infrastructure and is imported via `from app.shared`:

- `permissions.py` – single decision point for all role/permission checks used by routes and templates.
- `labels.py` – registry mapping codes → human-readable labels for languages, regions, etc.
- `constants.py` – roles, statuses, regions, order types, material formats, certificate series.
- `dates.py` – date/time helpers and validation rules (start/end, past-date acknowledgement).
- `ui/partials/` – base layout, nav, common table filters, form controls, and modal shell.
- `flags.py` – simple feature-flag registry for experimental work.

Route inventory lives at `sitemap.txt` (admin-only, linked from Settings) and lists each route, owning module, and required permission.

- Workshop runner view template: `app/templates/sessions/workshop_view.html`.

---

# 13. QA Checklists

- **Menus** match §1.2 per view; View selector visible only to SysAdmin/Administrator/CRM/KT Facilitator; CSA/Participant/Contractor have no switcher.
- **Learner gating** per §4.1; CSA window per §4.2; Contractor behavior per §1.2/§1.5.
- **Resources** list only workshop types whose sessions have **started** for that participant.
- **Materials** UI rules per §7; dashboard sort & columns match §9.
- **Emails** include URL/username/password; no magic links.
- **Validation**: one-day allowed; past-start acknowledgment only when start date **changes** to a past date.

---

# 14. Change Control Notes

- Magic-link infra disabled and endpoints should return 410/redirect.  
- “KT Staff” is a derived condition; any stored boolean is deprecated and must not drive logic.  
- CSA password default is **`KTRocks!CSA`**; other participants **`KTRocks!`**.  
- Contractor menu/capabilities updated per §1.2/§1.5.
- Materials dashboard documented to current behavior (default hides Closed workshops via the Workshop Status filter).
- Session detail pages render a minimal order view for materials-only sessions and guard full details with `{% if not session.materials_only %}`; workshop-type and facilitator sections now use `{% if %}` guards to avoid null dereferences.
- Added no-op Alembic revision `0053_cert_template_badge_image` to maintain migration continuity for certificate-template badge filenames.
- Material Settings items include a **Quantity basis** (`Per learner`/`Per order`) stored on `materials_options` and used wherever the item is selected.
- Workshop Type edit default-materials dropdown filters by `Language.name`, posts `material_option_id`, and hides "Bulk" options (no "Show all").
- Session Materials page provides an **Apply Defaults** button that adds any missing `workshop_type_material_defaults` for the session's workshop type, delivery type, region, and language as `material_order_items` using each item's quantity basis (Material Sets for “Per learner”, 1 for “Per order”). Existing rows remain unchanged. Items support inline quantity, language, and format edits, per-row removal, and a dropdown to add new items.
- Simulation-based workshops require a selected Simulation Outline before Materials Apply Defaults or Save will persist. The server responds `400` with a “Select a Simulation Outline to continue.” flash, the outline selector is highlighted with inline helper text, and the client disables Apply Defaults/Save while surfacing a “Choose a Simulation Outline first.” hint linking to `#simulation-outline`.
- Materials Apply Defaults keeps the simulation credits row idempotent: it upserts exactly one `SIM Credits (<outline_number>)` line (Language=English, Format=Digital, Qty from credits), renames legacy “Simulation Credits”/“SIM Credits” rows, and removes the entry when credits are set to zero.
- Materials Apply Defaults preserves shipping selections (shipping location, courier, tracking, ship/arrival dates) from the current request so unsaved inputs remain after defaults run. The client only submits shipping fields that changed on the page to avoid blank hidden inputs clearing saved data for users who can’t edit a given field.
- Sessions track a manual `number_of_class_days` (1–10, default 1) edited on the staff session form for future attendance features.
- Workshop Type default-material rows drop the "Remove" checkbox in favor of a
  per-row delete action (`POST /workshop-types/defaults/<id>/delete`).
- PO Number field removed from materials orders and underlying storage.
- Session create/edit forms filter workshop locations based on delivery type: Onsite shows onsite-only, Virtual shows virtual-only, incompatible selections are cleared, and an inline notice surfaces when no locations match.
- Shared welcome partial now splits display names via Python `.split()` to avoid the unavailable Jinja `|split` filter while preserving graceful handling for empty or single-word names.
- Session create form keeps the Simulation Outline row aligned with adjacent fields when toggled for simulation-based workshops, and the Notes & Special instructions textarea now spans roughly 640px on desktop while remaining full-width on small screens.
