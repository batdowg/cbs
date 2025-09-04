# CONTEXT.md — CBS Project Context & Working Rules

## Project context
Kepner-Tregoe’s Certs & Badges System (CBS) manages workshops (“Sessions”), Participants, Certificates/Badges, and Materials/Shipping. It complements/gradually replaces Salesforce flows for delivery and credentialing.

**Why this matters**
- One place for session setup → participants → materials/shipping → delivery → certificates (+later: surveys).
- Learners get a clean portal; staff get predictable workflows; everything is auditable and scalable.

---

## 0) Codex operating rules (read first)
0.1 Read this file before any change.  
0.2 Don’t touch items marked **[DONE]** unless asked.  
0.3 Only change what the task requests; keep diffs small and reversible.  
0.4 All schema edits via Flask-Migrate migrations (no `create_all`).  
0.5 Never commit secrets. Use env vars and GitHub secrets.  
0.6 Update this file when you finish work (flip items to **[DONE]**).  
0.7 **Static assets:** Do **not** add/replace images under `app/assets/badges/`. Use what’s already there. Badges are served from `/srv/badges`. No binary churn in PRs.  
0.8 **Scope guard:** Don’t invent pages or routes. Follow sections below.
0.9 Utility modules live under `app/utils/`; import them as `from app.utils`.
    - Imports should use `app.utils.*` (top-level `utils/` was removed).

---

## 1) Authentication, accounts, RBAC
- Single front-door sign-in at `/` (alias `/login`) detects whether the email belongs to a **User** (staff) or **ParticipantAccount** (learner) and routes accordingly. If both exist, staff wins and we flash a heads-up. **[DONE]**
- Passwords via bcrypt helpers; shared reset flow: `/forgot-password` → token email → `/reset-password`. **[DONE]**
- Session keys (`user_id` or `participant_account_id`) live side-by-side; `/logout` clears either. **[DONE]**
- Cross-table uniqueness: new staff cannot reuse learner emails and vice-versa. **[DONE]**
- Roles (booleans on `users`): SysAdmin, Administrator, CRM, KT Facilitator, Contractor, Staff.  
  Access quick map:
  - **SysAdmin**: everything.
  - **Administrator**: sessions, participants, certificates, clients, materials settings; not app-wide secrets.
  - **CRM**: sessions, materials orders (create/edit), clients/locations (on their clients).
  - **KT Facilitator/Contractor**: view sessions/materials; limited edits where explicitly allowed.
  - **CSA**: manage participants for assigned session until Delivered; can add client locations but not edit materials orders.

Staff roles matrix:

| Function | App_Admin | is_kt_admin | is_kcrm | is_kt_delivery | is_kt_contractor | is_kt_staff |
| --- | --- | --- | --- | --- | --- | --- |
| Resources (Settings) | V/E/D | V/E/D | — | V/E | V | — |
| Workshop Types (Edit, Prework) | V/E | V/E | — | — | — | — |
| Sessions (View, Edit, Prework Send) | V/E/Send | V/E/Send | V | V | V | V |
| Materials | V/E | V/E | V/E | V | V | V |
| Surveys | V/E | V/E | V | V | V | V |
| Users | V/E/D | V/E | — | — | — | — |
| Importer | V | V | — | — | — | — |
| Certificates (Issue, View) | Issue/V | Issue/V | V | V | V | V |
| Verify Certificates | V | V | V | V | V | V |
| Settings (App Admin) | V/E | — | — | — | — | — |
| My Resources | V | V | V | V | V | V |
| My Workshops | V | V | V | V | V | V |
| My Profile | V/E | V/E | V/E | V/E | V/E | V/E |

This matrix is the product source of truth; the `/settings/roles` page mirrors it.

---

## 2) Clients & Locations
- Clients: name (unique, case-insensitive), SFC link, CRM (User), data region (NA/EU/SEA/Other), active flag. **[DONE]**
- Per-client locations (normalized, both may be used by the same session):
  - **Client Workshop Locations**: physical addresses or virtual presets (seed: MS Teams, Zoom, Google Meets, Webex, Other). **[DONE]**
  - **Client Shipping Locations**: contact_name/phone/email + full address. **[DONE]**
- Session creation filters both location dropdowns by the chosen Client; defaults are blank (not “None”). **[DONE]**
- Materials orders always inherit the Session’s **Shipping Location** (read-only on the order page). **[DONE]**

---

## 3) Sessions
- **Create & edit** (staff only): title, **Workshop Type** (Code), start/end (date-only), daily start/end time, timezone, delivery type (Onsite/Virtual/Self-paced/Hybrid), region, language, capacity, status notes, **Workshop Location**, **Shipping Location**, lead + additional facilitators (delivery/contractor users; lead excluded from additional list). Prefill times 08:00–17:00. “Include out-of-region facilitators” preserves form inputs. **[DONE]**
- Client selection keeps Title and displays CRM; Client Session Administrator accepts staff emails. **[DONE]**
- **Participants** tab: add/edit/remove, CSV import (FullName,Email,Title), lowercased emails, portal link after certs; accounts are created on demand and credentials are emailed. **[DONE]**
- Saving a session requires **end date ≥ start date** (single-day allowed). If the start date is in the past, the form warns in red and requires an explicit “The selected start date is in the past. I’m sure.” checkbox.
- Session form normalizes time fields to HH:MM; server validation enforces end > start; UI sets end.min = start; past-start requires acknowledgement.
- Sessions link to a managed catalog of **Simulation Outlines**. When the chosen Workshop Type is marked **Simulation based**, the Session form shows a "Simulation outline" dropdown labeled "<Number> – <Skill> – <Descriptor>"; otherwise the field is hidden. The detail view displays the selected outline or “—”.
- Session detail shows full physical workshop address (or "Virtual"), places Notes after CRM, and displays daily time range with timezone abbreviation.
- **Lifecycle flags & gates** (server-enforced):
  `materials_ordered`, `ready_for_delivery`, `info_sent`, `delivered`, `finalized`, `on_hold_at`, `cancelled_at`.  
  Gates:
  - Ready requires **participants > 0**.  
  - Delivered requires **Ready = true** and **end_date ≤ today**.  
  - Finalized requires **Delivered = true** and locks lifecycle edits.  
  - Cancelled/On-hold disables lifecycle edits.  
  Delivered auto-ticks Materials ordered + Workshop info sent. **[DONE]**
- **Status (derived)**: New → In Progress → Ready for Delivery → Delivered → Closed; Cancelled overrides; On-hold shows as In Progress with a note. **[DONE]**
- PRG everywhere; red flashes explain why a save is blocked. **[DONE]**
- **Prework**: session page `/sessions/<id>/prework` lists participants and lets staff send prework assignments when the workshop type has a template. List-style questions snapshot kind/min/max and show a download link for staff. **[DONE]**
- Session-level `no_prework` toggle disables "Send Prework" and marks assignment rows **WAIVED**; page also offers **Send Accounts without Prework** to email portal links only. Logs `[SESS] no_prework=<true|false> session=<id>` and `[MAIL-OUT] account-invite …`. **[DONE]**
- Prework send creates missing participant accounts on-the-fly (`[ACCOUNT]` logs), generates magic-link emails per participant, and logs `[MAIL-OUT]`/`[MAIL-FAIL]`. A session-level `no_material_order` flag is set via the New Session form. Sending prework does not gate certificates. **[DONE]**
- Learner “My Workshops” list shows a **Prework** action for each enrolled session, linking directly to that participant’s prework page (or “No prework” when none). **[2025-09-04]**
- Magic links are single-use passwordless sign-ins. They compare `SHA256(token + SECRET_KEY)` against `magic_token_hash`, expire via `magic_token_expires`, and log `[AUTH]` or `[AUTH-FAIL]` outcomes. **[DONE]**
- Staff can access Prework via a "Prework" button on the Workshop Type edit page and on Session list/detail pages. **[DONE]**
- On New Session, there are two actions: **Proceed to materials order** and **No Materials Order (Save)** — the latter sets the flag and returns to the Session detail view. The Prework page does not show materials controls. **[DONE]**
---

## 4) Workshop Types & Badges
- WorkshopTypes: `code` (unique uppercase), `name`, `status`, `description`, optional `badge` from: **None, Foundations, Practitioner, Advanced, Expert, Coach, Facilitator, Program Leader**, and a boolean `simulation_based`. **[DONE]**
- Certificates and session UI show a small badge chip and a **Badge** download link when the workshop type has a badge. **[DONE]**
- **Badges static delivery**: images live in `app/assets/badges`, synced to `/srv/badges`, served at `/badges/<slug>.webp`.
  Canonical filename/slug for Foundations is `foundations.webp`. **Do not commit new badge binaries.** **[DONE]**
  - Badge files live under `/srv/badges`.
  - Names map via slug (lowercase, no spaces). Helpers try `.webp` first, then `.png`.
  - To add a PNG alternative, drop `<slug>.png` in `/srv/badges`.
- **Prework templates**: staff edit per Workshop Type at `/workshop-types/<id>/prework` (info & questions). Questions can be **Long text** or **List** with Min/Max (≤10). **[DONE]**
- Info and question prompts support rich text (sanitized HTML: p, br, strong, em, u, ul, ol, li, a, h3, h4, blockquote). Answers are plain text rendered with `nl2br`. **[DONE]**
- Staff can access Prework via a "Prework" button on the Workshop Type edit page and on Session list/detail pages. **[DONE]**
---

## 5) Materials & Shipping (single shipment per session)
- Data: `session_shipping` (unique per session) + `session_shipping_items` (material, qty, notes). **[DONE]**
- Header fields on Materials page (mirrors Session + adds order bits):
  - **Order Type** (fixed list): KT-Run Standard materials / KT-Run Modular materials / KT-Run LDI materials / Client-run Bulk order / Simulation. **[DONE]**
  - **Materials type** dropdown filtered by Order Type (from **Materials Options** below). **[DONE]**
  - **Latest arrival date** (UI label, stored in `session_shipping.arrival_date`, required), **Workshop start date** (auto from Session), **SFC Project link**, **Delivery region** (from Session). **[DONE]**
  - Read-only **Shipping Location** (from Session). **[DONE]**
  - Status actions: Submit, Shipped (courier+tracking+ship date), Delivered (marks `materials_ordered = true`). **[DONE]**
- Header now includes **Material format** (All Physical / Mixed / All Digital / SIM Only), a always-visible **Physical components** block (4 checkboxes), and **PO Number**. All four boxes are pre-checked for **All Physical** and validation requires at least one; **Mixed** leaves boxes enabled but unchecked and also requires at least one. **All Digital** and **SIM Only** disable the checkboxes with no validation. On validation errors, the form preserves user input.
- If the Session's Workshop Type is **Simulation based**, the Materials Order page also displays a **Simulation outline** selector that updates the session.
- Materials list includes a **Latest Arrival Date** column (max of shipment arrival dates).
- **Permissions**:
  - Create/edit order: **Administrator, CRM**.  
  - Mark Delivered: **Administrator** only.  
  - View-only: **KT Facilitator, Contractor** (and CSA).  
  - CSA: may add shipping locations under Client; may not change orders. **[DONE]**
- **Materials Options (Settings → Materials)**: single table with
  - `order_type`, `title`, **languages (many-to-many)**, **formats** (`Digital (KTBooks)`, `Physical`, `Self-paced`, `Mixed`), `is_active`. **[DONE]**
  - Admin/SysAdmin only. **[DONE]**
- Materials view page no longer errors when accessed without imports. **[DONE]**

---

## 6) Languages (Settings)
- `languages` table with `name`, `active`, `sort_order`; used by Sessions and Materials Options. **[DONE]**
- Admin/SysAdmin manage list; sessions keep legacy language text but prefer dropdown values. **[DONE]**
- Participant accounts and users store `preferred_language` (default `en`); edited via My Profile. **[DONE]**

---

## 7) Certificates
- Template: `app/assets/certificate_template.pdf`. **[DONE]**
- Output path: `/srv/certificates/<year>/<session_id>/<email>.pdf`. **[DONE]**
- Layout: name Y=145 mm (Times-Italic autoshrink 48→32), workshop Y=102 mm (autoshrink), date Y=83 mm (session end date, `d Month YYYY`). **[DONE]**
- Bulk/per-row generate; **auto-generate on Finalize**; remove on Cancel. Re-generate allowed (overwrites). **[DONE]**
- Learner portal `/my-certificates` shows only their own PDFs. **[DONE]**

---

## 8) Email & notifications
- SMTP config stored in DB (host, port, auth user, default From, From Name); passwords via env/secret; test send in Settings. Logs `[MAIL-OUT]` in stub mode. **[DONE]**
- Category From mapping (prework, certs/badges, client setup). **[DONE]**

---

## 9) UI & Navigation
- Sidebar (role-aware):
  - **Participants**: Home, My Workshops, My Resources, My Profile, Logout.
  - **CSA**: Home, My Workshops, My Resources, My Profile, Logout.
  - **Staff (SysAdmin/Admin/Delivery/Contractor)**: Home, My Sessions, Sessions, Materials, Surveys, My Resources, My Profile, Settings, Logout. "My Certificates" lives under My Profile; no "Verify Certificates" link. **[DONE]**
- Learner-facing navigation and emails say "Workshop" (e.g., "My Workshops"); staff UI retains "Session" wording. **[DONE]**
- Root `/` shows branded login card (no nav). **[DONE]**
- Basic responsive styles; flashes consistent. **[DONE]**
- Participant nav gating: "My Prework" shows for pending assignments before sessions start; "My Resources" unlock after session start; "My Certificates" show when earned. **[DONE]**
- Participant home greets by certificate name (fallback full name/email). **[DONE]**
- My Profile includes a Language selector (`preferred_language`). **[DONE]**
- My Profile includes a Language selector (`preferred_language`) and password change form; first login after a temporary password forces a redirect here. **[DONE]**
- All displayed times omit seconds via a common formatter. **[DONE]**
- "My Workshops" lists only enrolled sessions with prework/resources/certificate actions. **[DONE]**
- Settings menu includes a read-only Roles Matrix for admins. **[DONE]**

-### Views
- UI-only modes for decluttering: **ADMIN**, **SESSION_MANAGER**, **CSA**, **MATERIALS**, **DELIVERY**, **LEARNER**.
- Staff profiles store `preferred_view` (enum, default **ADMIN**); participants implicitly use **LEARNER**.
- `active_view` cookie can temporarily override `preferred_view`; clearing it resets to profile.
- Switching views alters navigation and home dashboard only; **permissions (RBAC) are unchanged**.
- Sidebar footer has a "View" dropdown; a banner appears when not in **ADMIN** with a quick link back.
- CSA home = My Sessions. Participants and CSAs have no view switcher. Staff switcher includes a **Session Admin** option for the CSA view.

---

## 10) Ops & non-functional
- Docker Compose: app, db, caddy. Health: `/healthz`. **[DONE]**
- Idempotent migrations; seed guards; simple audit logs for key actions (logins, role changes, password admin resets, provisioning). **[DONE] (minimal)**
- Pagination on long tables; simple rate-limits on auth endpoints. **[DONE]**
- Prework autosave endpoint: soft rate limit 10 writes/10s per assignment. **[DONE]**
- Prework mails log `[ACCOUNT]`, `[MAIL-OUT]`, `[MAIL-FAIL]`; magic links expire after 30 days; accounts are created on send if missing. **[DONE]**
- CSA assignment email fires on change and logs `[MAIL-OUT] csa-assign`. Missing CSA accounts are auto-created with default password `KTRocks!CSA` (existing passwords unchanged), and credentials are included in the email. Unauthenticated session administration links redirect to login with a clear message. **[DONE]**
- Account creation uses normalize→lookup→create with race-safe fallback; emails are stored lowercased. New participant accounts use default password `KTRocks!` (CSAs use `KTRocks!CSA`), and credentials are included in the email. Plaintext passwords are never logged.
- All token timestamps are timezone-aware UTC. **[DONE]**
- External URLs default to HTTPS (`PREFERRED_URL_SCHEME='https'`); prework emails always use HTTPS links. **[DONE]**
- Migration 0032_prework_list_questions explicitly creates/drops PostgreSQL enum `prework_question_kind` for reliable upgrades/downgrades. **[DONE]**
- Migration 0037_preferred_view adds `users.preferred_view` to support UI Views. **[DONE]**
- Migration 0039_materials_enhancements explicitly creates/drops PostgreSQL enum `materials_format` for reliable upgrades/downgrades. **[DONE]**

---

## 11) Roadmap (prioritized)
1. **Surveys**: enable flag, basic post-session link + completion tracking.
2. **Certificate verification micro-site** (public verify by code).
3. **Learner resources** page (links/templates/prework), per-session attach.
4. **Materials UX**: bulk item templates per Materials Option; printable pick list.
5. **Client dashboards**: show upcoming sessions + shipment tracking.
6. **Salesforce**: CSV round-trip → API push/pull.
7. **Audit & exports**: filters + CSV/ZIP exports for admin reporting.
8. **Branding settings**: logo/color upload with safe storage.
9. **SSO (later)** if MS365 makes sense.

## 12) Resources
- **Purpose**: Provide participants with workshop materials (links, documents, apps) grouped by Workshop Type.  
- **Staff management**:  
  - Route: `/settings/resources` (Admin, SysAdmin, Delivery).  
  - Fields:  
    - **Name** (string, required)  
    - **Type** (enum: Link, Document, App)  
    - **Resource** (URL if Link/App; uploaded file if Document)  
    - **Workshop Types** (multi-select checkboxes; resource may apply to multiple types)  
  - Uploaded files are stored under `/srv/resources/<title-as-filename>`.  
  - Resources may be activated/deactivated (soft delete).  
- **Participant view**:  
  - Route: `/my-resources` (sidebar label: “My Resources”).  
  - Groups resources under each Workshop Type the participant is enrolled in.  
  - Each resource appears as a link:  
    - **Links/Apps** → open in new tab.  
    - **Documents** → download directly from `/resources/<filename>`.  
- **Permissions**:  
  - **SysAdmin, Administrator, Delivery**: full CRUD.  
  - **Facilitator, Contractor**: view only.
  - **Participants**: view only, scoped to their workshop types.
  - Resources pages use the standard base layout with persistent left sidebar; active nav: Settings→Resources; Learner→My Resources.


## 6.x Views (UI-only, RBAC stays the source of truth)

**Views** trim the homepage and menu to match a workflow. They **do not** grant or remove permissions — RBAC below controls access. Users can switch views with the footer switcher; staff default per role.

**Available Views**
- **Admin** – Everything allowed by RBAC; learner-only items hidden.
- **Session Manager** – Sessions dashboard; session-focused menu; learner-only hidden.
- **Materials** – Materials ordering dashboard; materials-focused menu; learner-only and certificates admin hidden.
- **Delivery** – “My Workshops,” Resources, and Prework quick links; learner links visible (useful for support).
- **Learner** – Learner home (My Prework • My Workshops • My Certificates); all staff pages hidden.

**Navigation defaults (2025-09-04):**
- Participants land on **My Workshops** after login.
- CSAs land on **My Sessions** and also have a **My Workshops** menu entry.
- Participants (non-CSA) menu: Home • My Workshops • My Profile • Logout.
- CSA menu: Home • My Sessions • My Workshops • My Profile • Logout.
- Delivery view home lists sessions where the user is a facilitator.
- Materials view home routes to the Materials dashboard list.

**Default View by Role**
- `App_Admin` → **Admin**
- `is_kt_admin` → **Admin**
- `is_kcrm` (CRM) → **Session Manager**
- `is_kt_delivery` → **Delivery**
- `is_kt_contractor` → **Delivery**
- `is_kt_staff` (general staff) → **Admin**
- Participant account → **Learner** (forced)

> Guarantee: Views affect layout only. If a page is hidden by View but allowed by RBAC, direct URL access still works.

---

## 10. RBAC: Roles → Permissions Matrix

Legend: **V**=View, **C**=Create, **E**=Edit, **D**=Delete, **A**=Action (send/generate/finalize, etc.)

| Feature / Page                                         | App_Admin | is_kt_admin | is_kcrm | is_kt_delivery | is_kt_contractor | is_kt_staff | Participant |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Sessions – list & detail**                           | V C E D   | V C E D     | V C E   | V (own & assigned) | V (own & assigned) | V | V (own via My Workshops) |
| **Sessions – core fields edit**                        | E         | E           | E       | —              | —                | —          | — |
| **Sessions – add participants**                        | A         | A           | A       | A (own & assigned) | A (own & assigned) | — | — |
| **Sessions – finalize / cancel**                       | A         | A           | A       | —              | —                | —          | — |
| **Prework – configure (by Workshop Type)**             | V C E D   | V C E D     | —       | —              | —                | —          | — |
| **Prework – send / mark no-prework (by Session)**      | A         | A           | A       | A (own & assigned) | A (own & assigned) | — | V (complete own only) |
| **Materials – create order**                           | A         | A           | A       | —              | —                | —          | — |
| **Materials – mark ready / delivered**                 | A         | A           | A       | —              | —                | —          | — |
| **Resources – manage (Settings → Resources)**          | V C E D   | V C E D     | —       | —              | —                | —          | — |
| **Resources – view (My Resources)**                    | —         | —           | —       | V              | V                | —          | V |
| **Certificates – generate/issue**                      | A         | A           | —       | —              | —                | —          | V (view own) |
| **Verify Certificates (public/staff view)**            | V         | V           | V       | V              | V                | V          | V |
| **Workshop Types – manage**                            | V C E D   | V C E D     | —       | —              | —                | —          | — |
| **Users – staff & learner admin (/users)**             | V C E D   | V C E D     | —       | —              | —                | —          | — |
| **Importer (/importer)**                               | V A       | V A         | —       | —              | —                | —          | — |
| **Issued / Cert Form (/issued, /cert-form)**           | V A       | V A         | —       | —              | —                | —          | — |
| **Settings – Roles Matrix**                            | V E       | V           | —       | —              | —                | —          | — |
| **Settings – App/System settings**                     | V E       | —           | —       | —              | —                | —          | — |
| **My Profile (change password, language)**             | V E       | V E         | V E     | V E            | V E              | V E        | V E |
| **My Workshops / My Prework / My Certificates**        | —         | —           | —       | V (own)        | V (own)          | —          | V |
| **Login flows (magic links, account invites)**         | A         | A           | A       | A (for own sessions) | A (for own sessions) | — | — |

> Notes
> • “own & assigned” = sessions where the user is on the delivery team or explicitly assigned the **CSA** role (see below).
> • “Participant” refers to **participant accounts** (learners).
> • App_Admin manages system-level settings in addition to is_kt_admin’s operational superuser scope.
> • Roles Matrix version 2024-06-13.

---

## 10.1 Per-Session CSA (Client Session Administrator)

**What CSA is:** A session-scoped assignment to a user (often client-facing operations). It *does not* change the user’s global role; it adds privileges **only for the assigned session(s)**.

**CSA Capabilities (session-scoped)**
- **Sessions (assigned only):** V (detail).
- **Participants:** **A** add/remove participants until the session start time; view roster.
- **No prework, materials, certificates, workshop-type, users, or settings access.**
- **No session field edits** beyond participant management.
- Landing page lists assigned sessions (**My Sessions**); CSA menu also includes **My Workshops**. CSAs do not have a view switcher.

**CSA Email/Logs**
- When CSA is assigned or changed, the system sends a “CSA assigned” email to the user and logs `[MAIL-OUT] csa-assign session=<id> user=<id> to=<email> result=sent]`. Re-sending occurs only when the assignment changes.

---

## 10.2 Gating Rules (applies in **every** View)

- **Prework (Learner):** Visible if the learner has an assignment; must answer required questions; can download allowed resources.  
- **Resources (Learner):** Visible starting **workshop start date**; earlier only if the participant already has access from a previous course.  
- **Certificates (Learner):** Visible after **workshop delivered** (session delivered flag set).  
- **Date validation (Sessions):** `end_date >= start_date`. If `start_date < today`, staff must acknowledge the past start date.  
- **File locations:** Certificates under `/srv/certificates/<year>/<session>/<email>.pdf`; public URL helper provides links.

---

## 10.3 Audit & Logging

- All mail sends include `[MAIL-OUT]` / `[MAIL-FAIL]` with type tags (`prework`, `account-invite`, `csa-assign`).  
- Role/permission changes and sensitive actions (issue certificates, finalize sessions) are logged with user id, timestamp (no seconds displayed in UI), and object id.

---
