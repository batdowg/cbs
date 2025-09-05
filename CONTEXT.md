
# 0. Engineering Context & Rules

This document is the **authoritative functional and architectural context** for Certs & Badges (CBS). It replaces prior drafts of `CONTEXT.md`.
Every functional change must update this file in the same pull request.

## 0.1 Environment & Stack
- **App**: Python (Flask), Gunicorn workers
- **DB**: Postgres 16
- **Reverse proxy**: Caddy → `app:8000`
- **Containers** (compose): `cbs-app-1`, `cbs-db-1`, `cbs-caddy-1`
- **App workdir in container**: `/app`, code at `/app/app/...`
- **Static/site mount**: host `./site` → container `/srv` (certificates, exports)
- **Health check**: `GET /healthz` (should return “OK” when healthy)

## 0.2 Deploy & Migrations (no shell aliases)
- **Deploy (manual)**: On VPS, in `~/cbs`
  1. `git pull origin main`
  2. `docker compose up -d --build`
  3. `docker compose ps`
  4. `docker logs cbs-app-1 --tail 80` (verify boot)
- **DB migrate** (inside app container):  
  - Create migration: `python manage.py db migrate -m "message"`  
  - Apply: `python manage.py db upgrade`
- **Logs**: `docker logs cbs-app-1 --tail 200` (or `-f` to follow)

## 0.3 Coding Rules
- **Do not** hardcode PowerShell shortcuts in code/docs.
- Keep business logic server-side (Flask); only light JS for form UX.
- All times are stored UTC in DB; display with short timezone labels (no seconds).
- Certificates are generated to `/srv/certificates/<year>/<session>/<email>.pdf` and linked in-portal.
- Keep one lowercased-unique constraint for **email** on each account table (see §2).
- “KT Staff” is **not** a role; it is a **derived condition** (see §1.3). Do not add a “KT Staff” checkbox anywhere.

---

# 1. Roles & Accounts (Who can do what)

## 1.1 Roles (authorization flags on **User** accounts)
- **Sys Admin** — full control, all settings and user management.
- **Admin** — full staff-level features including user management.
- **CRM (Client Relationship Manager)** — owns session setup, client comms; can create/edit sessions, assign facilitators, manage participants, send prework, generate/finalize sessions.
- **Delivery (Facilitator)** — sees/operates their assigned sessions; delivery-centric home.
- **Contractor** — limited internal user; no user management; not “KT Staff” (see §1.3).
- **CSA (Session Admin)** — *not* a user role; CSAs are **participant accounts** linked to sessions; they can manage participants before start (see §4.2, §4.3).
- **Participant (Learner)** — attendee-only account (participant table).

> **User vs Participant:** Users are internal accounts (staff/contractor/facilitator). Participants (incl. CSAs) live in a separate table and get the learner UX (see §2).

## 1.2 Default Views & Menus (per role)
Menus are explicit; no bundling.

- **Sys Admin (default view: Admin)**  
  `Home • Sessions • Materials • Surveys • My Resources • Users • Roles Matrix • Workshop Types • Resources (Settings) • Simulation Outlines • My Profile • Logout`

- **Admin (default view: Admin)**  
  Same as Sys Admin *minus* platform/system settings reserved for Sys Admin, if any.

- **CRM (default view: Session Manager)**  
  `Home • My Sessions • Sessions • Materials • Surveys • My Resources • My Profile • Logout`

- **Delivery / Facilitator (default view: Delivery)**  
  `Home • My Sessions • My Resources • My Profile • Logout`

- **Contractor (default view: Admin-lite)**  
  `Home • Sessions (read-limited) • Materials (if granted) • My Resources • My Profile • Logout`  
  (No user management; not KT Staff.)

- **CSA (Session Admin)**  
  `Home • My Sessions • My Workshops • My Profile • Logout`  
  (CSA is a participant account; see §4.2.)

- **Participant / Learner**  
  `Home • My Workshops • My Profile • Logout` (+ **My Certificates** appears only if they own ≥1 certificate)

> Staff view switcher exists for **User** accounts (Sys Admin/Admin/CRM/Delivery/Contractor). **Participants/CSAs** do not see a switcher.

## 1.3 “KT Staff” (definition, not a role)
“KT Staff” is a **condition** used in copy/UI, *not a stored role*:
- KT Staff = any **User** account that is **not** Contractor and **not** a Participant/CSA.  
- Therefore **Contractor, Learner, CSA** are **not** KT Staff.  
- Do **not** persist a “KT Staff” boolean; compute it from roles at runtime.

---

# 2. Accounts & Identity (the two account tables)

## 2.1 Tables
- **users** — internal portal users (Sys Admin, Admin, CRM, Delivery, Contractor).  
  - Uniqueness: `lower(email)` unique index
  - Auth: password hash (bcrypt or pbkdf2), standard Flask-Login integration
  - Role flags: booleans or role mapping (implementation detail), but *no* “KT Staff” field

- **participant_accounts** — learners & CSAs (participant UX).  
  - Uniqueness: `lower(email)` unique index
  - Auth: password hash
  - Profile: full name, certificate name, preferred language
  - CSA usage: a participant account may act as **CSA** when linked to a session (see §4.2)

> Credentials for new participant/CSA: default temp password **`KTRocks!`** (no forced change).

## 2.2 One-person, two records
A person can exist in **both** tables with the same email (e.g., a staff member who also attends a course). These identities are kept separate for clean UX and permissions.

---

# 3. Data Model (high-level schema & relationships)

This section maps main tables, relationships, and key constraints. Column names are illustrative; check migrations for exact fields.

## 3.1 Sessions & Catalog
- **workshop_types**  
  - name, `simulation_based` (bool)
- **simulation_outlines**  
  - number (6-digit), skill (enum), descriptor, level (enum)
- **sessions**  
  - fk: workshop_type_id, fk: simulation_outline_id (nullable)  
  - dates: start_date, end_date, timezone  
  - logistics: location fields (city/state/country or virtual), notes, CRM notes  
  - status flags: delivered_at, finalized_at, no_prework (bool), no_material_order (bool)  
  - fk: csa_participant_account_id (nullable)  
- **session_facilitators** (m:n users↔sessions)  
- **session_participants** (m:n participant_accounts↔sessions + status per person)

## 3.2 Prework
- **prework_templates** (by workshop type)  
  - rich text info
- **prework_questions**  
  - fk: template_id, text, kind (enum: TEXT, LIST), min_items, max_items, index
- **prework_assignments** (per session × participant)  
  - snapshot of questions, due_date, status (draft/sent/completed/waived)
- **prework_answers**  
  - fk: assignment_id, question_id/snapshot_id, text, item_index (for LIST), timestamps

## 3.3 Resources
- **resources**  
  - name, type (enum: LINK, DOCUMENT, APP), value (URL/path), active
- **workshop_type_resources** (m:n)  
  - fk: resource_id, fk: workshop_type_id (unique pair)

## 3.4 Certificates
- **certificates** (issued per participant per session)  
  - fk: session_id, fk: participant_account_id, file_path, issued_at, layout/version
  - file materialized under `/srv/certificates/...`
  - unique `(session_id, participant_account_id)`

## 3.5 Materials
- **materials_orders** (per session; single active order)  
  - format (enum: All Physical, All Digital, Mixed, SIM Only)  
  - physical_components (4 booleans): learner kits, session materials, process cards, Box F  
  - po_number, latest_arrival_date, ship_date, courier, tracking, special_instructions
- **materials_order_items**  
  - sku/description, qty, notes
- **session_shipping** (address/contact for a session)  
  - address lines, city, state/province, postal, country, attention, phone, email

## 3.6 Clients (if present)
- **clients**, **client_locations** and session-client linkage tables (names vary by migration)

## 3.7 Common constraints
- All emails lowercased-unique in their respective tables.
- Most m:n tables enforce unique pairs (e.g., resource↔workshop_type).
- One-day workshops allowed: `end_date >= start_date` (see §7).

---

# 4. Views, Gating & Capabilities

## 4.1 Participant (Learner)
- **Before start, with prework**: sees **My Workshops → Prework**. Resources/certs hidden.  
- **Before start, no prework**: neutral message; resources/certs hidden.  
- **From start → before delivered**: sees **Resources** (for this workshop + previous ones).  
- **Delivered/Finalized**: sees **Resources** and **My Certificates** (if they own ≥1 certificate).

## 4.2 CSA (Session Admin — participant account)
- **Menu**: `Home • My Sessions • My Workshops • My Profile • Logout`
- **My Sessions**: only sessions where **this participant account** is the CSA (link to session detail).
- **Capabilities**:  
  - **Before start**: add/remove participants.  
  - **From start**: read-only (participant management locked).  
  - At no time can CSAs send emails, edit session fields, or manage materials/resources.

## 4.3 Delivery (Facilitator)
- **Menu**: `Home • My Sessions • My Resources • My Profile • Logout`
- Sees sessions where they are assigned as facilitator. Read-only admin functions; has access to delivery notes, times, timezone.

## 4.4 CRM
- **Menu**: `Home • My Sessions • Sessions • Materials • Surveys • My Resources • My Profile • Logout`
- Can create/edit sessions, assign facilitators, manage participants, send prework/account emails, generate/finalize sessions.

## 4.5 Admin / Sys Admin
- Full access to settings, user management, role matrix, workshop types, resources, simulations, etc.

## 4.6 Contractor
- Admin-lite: restricted reads and actions as granted; no user management; not KT Staff (see §1.3).

---

# 5. Prework (Configure, Send, Complete)

## 5.1 Configure by Workshop Type
- Rich text “Information” block
- Questions: TEXT or LIST; LIST has min/max; index controls order
- Resource links can be referenced via §6 resources

## 5.2 Assignments per Session
- Creating a session-specific assignment clones the template snapshot.
- **Send Prework** (staff only) creates participant accounts as needed with default password `KTRocks!` and sends prework email (see §10).  
- **No prework for this workshop**: disables assignment; staff can **Send Accounts (no prework)**.

## 5.3 Participant UX
- Prework visible up to **session start**, then hidden.
- LIST answers use `item_index`; min/max enforced server-side.
- Save & return; can download a printable version.

---

# 6. Resources

- Created and edited by Admin/Sys Admin/Delivery via **Settings → Resources**.  
- Types: LINK, DOCUMENT, APP. Storage under `/resources/<title-as-filename>` for docs.  
- Mapped to **Workshop Types** (grid multiselect).  
- Learners see resources for their workshop type **starting at session start** (plus all prior-course resources).

---

# 7. Validation Rules

- **Dates**
  - `end_date >= start_date` (one-day allowed).
  - **Past-start acknowledgment**: required **only when `start_date` is changed in this save** *and* the new value is in the past.
- **Times**
  - Display without seconds; show compact timezone abbreviation near times.
- **Materials**
  - If format is **All Physical** → all four physical components auto-selected (editable).  
  - If **Mixed** → all four visible, unchecked by default.  
  - If **All Digital** or **SIM Only** → all four visible but **disabled** (greyed).  
  - Server validation enforces at least one component when physical/mixed.

---

# 8. Certificates

- Generated post-delivery per participant; file saved to `/srv/certificates/<year>/<session>/<email>.pdf`.
- One certificate per `(session, participant)`.
- Learner sees **My Certificates** only when they own ≥1 certificate; session detail provides download.

---

# 9. Materials Dashboard

## 9.1 Landing (Materials view home for staff)
- **Default sort**: **Latest Arrival Date** descending (nearest due first).  
- **Columns** (sortable): Session, Client, Workshop Type, Latest Arrival, Format, Physical Components, PO Number, Status, Ship Date, Courier/Tracking.
- **Row actions**: Open Order, Edit, Mark Shipped, Mark Delivered (per permissions).

## 9.2 Filters
- **Status**: Draft, Ordered, Shipped, Delivered, Cancelled.
- **Date range**: Latest Arrival (from–to).
- **Format**: All Physical, All Digital, Mixed, SIM Only.
- **Components** (multi): Learner kits, Session materials, Process cards, Box F.
- **Workshop Type**: multi-select.
- **Facilitator**: multi-select.
- Reset & Apply buttons; filters persist in session storage.

---

# 10. Emails & Authentication

- **Magic links are disabled.** Users sign in with email + password.
- **Prework email** (staff-initiated) and **Account invite email** include:
  - Portal URL
  - Username (email)
  - Temporary password: **`KTRocks!`**
  - A note that password can be changed in **My Profile** (not mandatory).

Email sender: `app/emailer.py` and templates under `app/templates/email/`.

---

# 11. Promotion/Demotion & Identity Edges

- **Promote participant → user**: Admin/Sys Admin only; creates a **User** record for the same email (participant record remains for learner artifacts).  
- **Demote user → contractor**: Admin/Sys Admin only; replaces roles with **Contractor**. Guard rails prevent demoting Sys Admin or removing the last Admin.  
- **CSA linking**: A CSA is a **participant account** linked to a session; no staff role is granted.

---

# 12. File/Route Index (where things live)

> Paths are canonical; verify with ripgrep if your tree differs.

- **Navigation & menus**: `app/templates/nav.html`, helpers `app/utils/nav.py`, view prefs `app/utils/views.py`
- **Home dashboards**: `app/templates/home.html` (+ role/view partials in `app/templates/home/`)
- **Sessions (routes)**: `app/routes/sessions.py`
  - **New/Edit Session form**: `app/templates/sessions/form.html`
  - **Session detail (staff)**: `app/templates/session_detail.html`
  - **Prework (staff tab)**: `app/templates/sessions/prework.html`
  - **Materials (session tab)**: `app/templates/sessions/materials.html`
- **Participant (learner) area**: `app/routes/learner.py`
  - **My Workshops**: `app/templates/my_sessions.html`
  - **My Certificates**: `app/templates/my_certificates.html`
  - **My Prework**: `app/templates/my_prework.html`, `app/templates/prework_form.html`, `app/templates/prework_download.html`
- **CSA area**: `app/routes/csa.py` (list & session bridge), templates `app/templates/csa/my_sessions.html`
- **Workshop Types**: `app/routes/workshop_types.py`, templates under `app/templates/workshop_types/`
  - **Prework config UI**: `app/templates/workshop_types/prework.html`
- **Resources (settings)**: `app/routes/settings_resources.py`, templates `app/templates/settings_resources/*.html`
- **Simulation Outlines**: `app/routes/settings_simulations.py`, templates `app/templates/settings_simulations/*.html`
- **Materials Dashboard & Orders**:  
  - Dashboard: `app/routes/materials.py`, templates under `app/templates/materials/` or `home/` partials  
  - Orders: `app/routes/materials_orders.py`, form `app/templates/materials_orders.html`
- **Users & Roles**: `app/routes/users.py`, `app/templates/users/*.html`; Role matrix `app/routes/settings_roles.py`, `app/templates/settings_roles.html`
- **Email**: `app/emailer.py`, `app/templates/email/*.html|.txt`
- **Utilities**: `app/utils/materials.py` (e.g., latest_arrival_date), `app/utils/time.py` (display helpers)

---

# 13. QA Checklists (what to verify after changes)

- **Roles & menus**: each role gets exactly the menu in §1.2.
- **Learner gating**: prework before start; resources at start; certs after delivered.
- **CSA window**: add/remove only before start; read-only after.
- **Materials**: format ↔ components UI logic; dashboard filters + sorting.
- **Emails**: prework/account emails include URL, username, `KTRocks!`.
- **Validation**: one-day allowed; past-start ack only when start date **changes** to a past value.

---

# 14. Change Control Notes

- Magic links are turned **off**.
- KT Staff is a **derived condition**, not a stored role.
- Default participant/CSA password is **`KTRocks!`**; no forced first-login change.
- One-day workshops allowed; end ≥ start.
- Materials dashboard is the home for the “Materials” view.
