
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
- **Health**: `GET /healthz` must respond `OK`
- **Language seeding**: optional `SEED_LANGUAGES=1` at boot inserts the default language set when the table is empty. Idempotent and safe — if languages exist it logs `Languages already present — skipping.`; on insert it logs `Seeded N languages.`; errors log `Language seed failed: <err>`.

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
- Certificates: `<certs_root>/<year>/<session_id>/<workshop_code>_<certificate_name_slug>_<YYYY-MM-DD>.pdf` (`<certs_root>` = `SITE_ROOT/certificates`, default `/srv/certificates`); `pdf_path` in DB is stored relative to `<certs_root>`.
- Emails lowercased-unique per table (see §2). Enforce in DB and app.
- Emails may exist in both **users** and **participant_accounts**; when both do, the **User** record governs authentication, menus, and profile.
- “KT Staff” is a **derived condition** (see §1.3), **not** a stored role.
- Experimental features must register in `shared.flags` and be disabled by default.

## 0.4 App Conventions & PR Hygiene
- Keep migrations idempotent and reversible; guard enum/DDL changes carefully.
- Add/modify routes with explicit permission checks close to controller entry.
- Update **this file** with any behavior or permission change.
- Include “Where code lives” pointers in PR descriptions for new pages.
- Tests: prefer integration tests that hit route + template path for core flows.
- Formatting: Black-compatible; imports grouped as stdlib, third-party, local with blank lines between groups.

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

- Tables: default `<table>` elements use `/static/css/table.css` with header/stripe/hover tints from `--kt-info`, text colors from `--kt-text` and `--kt-body`, borders `--kt-border`, and cell padding `var(--space-2)`/`var(--space-3)`.

## 0.7 Buttons & Links
- Native buttons (`button`, `[type=button]`, `[type=submit]`, `[type=reset]`) and elements with `.btn` share KT styling.
- Variants: default/`.btn-primary`, `.btn-secondary` (white background, `--kt-text`, `--kt-border`, light `--kt-info` hover), `.btn-success` (`--kt-accent-green`, `--kt-text`), `.btn-danger` (`--kt-accent-red`). Optional sizes `.btn-sm` and `.btn-lg` adjust padding and font size.
- Buttons show a `2px solid var(--kt-info)` focus ring with offset and reduce opacity with `cursor: not-allowed` when disabled.
- Links use `--kt-info`, darken toward `--kt-primary-hover` on hover/active, and show the same focus ring when focus-visible.
- Button styles live in `/static/css/buttons.css`; link styles live in `/static/css/ui.css`. Both load globally.

## 0.8 Form Controls
- Inputs, selects, textareas, radios, checkboxes, file controls, and helper/error text follow KT tokens for color, spacing, and focus rings.
- Styles live in `/static/css/forms.css` and load globally.

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

## 0.12 Cards
- `.kt-card` wraps tables or forms for visual grouping using brand tokens.
- `.kt-card-title` applies heading styling inside a card.

---

# 1. Roles & Menus

## 1.1 Roles (applies to **User** accounts only)
- **Sys Admin** — platform-wide admin incl. settings and user management.
- **Admin** — staff-level admin incl. user management.
- **CRM (Client Relationship Manager)** — owns session setup, client comms; can create/edit sessions, assign facilitators, manage participants, send prework/invites, finalize.
- **Delivery (Facilitator)** — sees and works own assigned sessions; delivery-centric UX.
- **Contractor** — limited internal user; access restricted to assigned sessions; no settings; see §1.4 for exact capabilities.

> **CSA** and **Participant/Learner** are **not user roles**; they are **participant accounts** (see §2).

## 1.2 Menus by Audience (explicit; no bundling)

- **Sys Admin** (default view: Admin)
  `Home • My Sessions • Training Sessions • Material Only Order • Material Dashboard • Surveys • My Resources • Settings ▾ • My Profile • Logout`
  **Settings ▾**: `Clients • Workshop Types • Material settings • Simulation Outlines • Resources • Languages • Certificate Templates • Users • Mail Settings`

- **Admin** (default view: Admin)  
  Same as Sys Admin. (System-wide toggles reserved for Sys Admin if any.)

- **CRM** (default view: Session Manager)  
  `Home • My Sessions • Training Sessions • Material Only Order • Material Dashboard • Surveys • My Resources • My Profile • Logout`
  **Default filters**: “My Sessions” = sessions I own / I’m assigned CRM on the client (if model supports client CRM; else owner fallback).

- **Delivery / Facilitator** (default view: Delivery)  
  `Home • My Sessions • My Resources • My Profile • Logout`  
  (No Materials or Surveys in menu.)

- **Contractor** (default view: Admin-lite)
  `Home • My Sessions • Training Sessions (read-only; assigned only) • My Resources • My Profile • Logout`
  - No Materials/Surveys/Settings in menu.
  - Can add/remove participants similar to CSA **including during session**; other session fields are read-only.

- **CSA (Session Admin)** — **participant account**, not a user  
  `Home • My Sessions • My Workshops • My Resources • My Profile • Logout`

- **Participant / Learner**
  `Home • My Workshops • My Resources • My Profile • Logout`
  - **My Certificates**: no persistent menu item; a link/section appears only if they have ≥1 certificate.

- Staff "My Profile → My Certificates" appears only when the staff user has certificates issued as a participant.

> Staff view switcher exists for **User** accounts (Sys Admin/Admin/CRM/Delivery/Contractor). **Participants/CSAs** do not see a switcher.

## 1.3 “KT Staff” definition (derived, not stored)
- KT Staff = any **User** account that is **not** Contractor and **not** a participant/CSA.  
- Do **not** persist `is_kt_staff`; if present in schema, stop using it and compute at runtime.

## 1.4 High-level permissions (delta highlights)
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
 - `workshop_types` (name, **code**, **simulation_based** bool, **supported_languages** list, **cert_series** code referencing an active certificate series)
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
- Catalog items include optional `description` (TEXT) and `sku_physical` (VARCHAR(100)).

### Workshop Type default materials

- `workshop_type_material_defaults` maps `(workshop_type_id, delivery_type, region_code, language)` to a `catalog_ref` material item, `default_format` (Digital/Physical/Self-paced), and `active`.
- `material_order_items` snapshot per-session ordered items with title, description, SKU, language, format, quantity, and processed state.
- Managed inline on the **Workshop Type edit page** under a “Default Materials” section (`/workshop-types/<id>/edit#defaults`). Legacy `/workshop-types/<id>/defaults` redirects here.
- Material item picker labels each choice as `<CatalogName> • <ItemTitle>` with optional language tags `• [en, es]`; typing searches those labels.
- Picker filters items by the row’s Language and excludes the “Client-run Bulk order” catalog. A per-row **Show all** checkbox bypasses the language filter (still excluding Bulk).
- The edit page header links to **Prework** as a separate action; the H1 remains “Edit Workshop Type.”

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
- Add/remove participants **until Ready for Delivery**; read-only after.

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
- Staff see the “My Resources” navigation link only if they're assigned to at least one session; they may still visit `/my-resources` directly without participant records, and the page returns HTTP 200 with an empty state when no resources apply.
- Workshop types are de-duplicated by ID in application code to avoid SQL `DISTINCT` on JSON columns such as `supported_languages`.
- `/my-resources` gracefully renders an empty state when no resources are available (never 500s).
- Files under `/resources/<title-as-filename>`; links download directly.

---

# 7. Validation & Forms

- **Dates**: `end_date >= start_date` (one-day workshops allowed).
- **New Session inline adds**: Add Client, Location, and Shipping within dialogs on the form. These dialogs mirror the full-page create forms (same fields and validation), show field-level errors inline, and saving selects the new item while preserving all other inputs.
- **Past-start acknowledgment**: triggers immediately when the **Start Date** field value is changed to a past date. Saving does not prompt unless the submitted value is past and unacknowledged. Changing the Start Date clears prior acknowledgment.
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
- Materials order view shows **Workshop Type** and **Delivery Type** above Order Type.
- **Workshop Type** settings include a **Default Materials Type** used to pre-fill the Materials order for newly created sessions.
- The Workshop Type edit page also provides a **Default Materials** tab mapping Delivery Type × Region × Language to catalog items with a default format and active flag.
- **Material Only Order** single-page create lives at `/materials-only` and makes a hidden session (`materials_only = true`) for logistics. These sessions appear only on the **Material Dashboard**.
- Region and Language are selects with human labels; changing Language immediately filters Workshop Type options by supported languages. Workshop Type codes display without names on `/materials-only`, and the full Materials form renders on first load.
- Client select supports inline **Add Client**; Shipping location offers **Add** and **Edit locations** dialogs without clearing other inputs.
- Simulation Outline appears when Order Type = Simulation or the Workshop Type is simulation-based; hides otherwise but retains any value.
- Order Date input above Latest arrival date defaults to today for new orders.
- When `materials_only = true`, Training-session features (participants, prework, certificates) are hidden/denied.
- Default Materials-only **Order Type** = “Client-run Bulk order”; after selecting Order Type, the session's Workshop Type default pre-fills **Materials Type**.
- **Material Sets** integer field (hidden only when Order Type = Simulation).
- **# of credits (2 teams per credit)** integer field (default 2; shown when Order Type = Simulation or the Workshop Type is simulation-based).
- Materials order header displays `Material Order <session_id> - <session_title>` with client name and delivery region, CRM, facilitators, and SFC project link. A **Shipping details** section lists contact, email, phone, and address (or “Digital only” when absent).
- Materials orders have global statuses: **New, In progress, Ordered, Shipped, Delivered, Cancelled, On hold**. Ordered ⇒ session `ready_for_delivery=true`; Delivered ⇒ session `status=Finalized`.
- POST `/sessions/<session_id>/materials/deliver` sets status to **Delivered** (403 on repeat with friendly flash); POST `/sessions/<session_id>/materials/undeliver` reverts to **In progress**.
- **Sessions list**: sortable columns (Title, Client, Location, Workshop Type, Start Date, Status, Region) with filters for keyword (Title/Client/Location), Status, Region, Delivery Type, and Start-date range; sort/filter state persists within `/sessions`.
- **Simulation Outline** shown when Order Type = Simulation or the Workshop Type is simulation-based.
- Material format is always visible. If **Order Type** = “Simulation” and no value is set, default to **SIM Only**. Non-editable roles see the value read-only.
- **Order Type** = “KT-Run Modular materials” → **Materials Type** becomes multi-select and all selected modules are shown; other order types remain single-select.
- On first Materials view for a new session, unset **Order Type** defaults to **KT-Run Standard materials** then **Materials Type** defaults from the Workshop Type (if defined).
- **Role Matrix**: view-only modal launched from `/users`; standalone `/settings/roles` page removed.

---

# 8. Certificates

- Issued post-delivery. Templates are configured under **Settings → Certificate Templates**, where admins define series and map (language, A4/Letter) → PDF and optional badge **filename**. Workshop Types must select one active series and no longer store any badge value. Generation resolves the mapping for the session's type series and language/size; badges reference files under `app/assets/badges`. If any mapping or file is missing, rendering aborts with a clear error (no auto-fallback).
- The template-mapping page offers bulk upload buttons for certificate template PDFs and badge WEBP files. Uploads overwrite by filename, refresh dropdown options, and never auto-change existing mappings. Badge uploads also copy files to the site root (`/srv/badges`) for static serving. Access is restricted to Sys Admin/Admin.
- Paper size derives from session Region (North America → Letter; others → A4).
- Name line: Y=145 mm; italic; auto-shrink 48→32; centered. On **Letter**, the recipient Name text box is narrowed by **2.5 cm** on the left and **2.5 cm** on the right (total horizontal reduction = 5.0 cm).
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
- Workshop line at 102 mm; date line at 83 mm in `d Month YYYY` using session end date.
- Learner nav shows **My Certificates** only if they own ≥1 certificate; staff see **My Profile → My Certificates** only when they have certificates as participants.

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
- Added no-op Alembic revision `0053_cert_template_badge_image` to maintain migration continuity for certificate-template badge filenames.
- Workshop Type edit normalizes language keys for material pickers to tolerate languages without explicit codes.
