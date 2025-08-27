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
- **Participants** tab: add/edit/remove, CSV import (FullName,Email,Title), lowercased emails, portal link after certs; accounts auto-created with default password "KTRocks!" and staff emails allowed. **[DONE]**
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

---

## 4) Workshop Types & Badges
- WorkshopTypes: `code` (unique uppercase), `name`, `status`, `description`, optional `badge` from: **None, Foundations, Practitioner, Advanced, Expert, Coach, Facilitator, Program Leader**. **[DONE]**
- Certificates and session UI show a small badge chip and a **Badge** download link when the workshop type has a badge. **[DONE]**
- **Badges static delivery**: images live in `app/assets/badges`, synced to `/srv/badges`, served at `/badges/<slug>.webp`.
  Canonical filename/slug for Foundations is `foundations.webp`. **Do not commit new badge binaries.** **[DONE]**
  - Badge files live under `/srv/badges`.
  - Names map via slug (lowercase, no spaces). Helpers try `.webp` first, then `.png`.
  - To add a PNG alternative, drop `<slug>.png` in `/srv/badges`.

---

## 5) Materials & Shipping (single shipment per session)
- Data: `session_shipping` (unique per session) + `session_shipping_items` (material, qty, notes). **[DONE]**
- Header fields on Materials page (mirrors Session + adds order bits):
  - **Order Type** (fixed list): KT-Run Standard materials / KT-Run Modular materials / KT-Run LDI materials / Client-run Bulk order / Simulation. **[DONE]**
  - **Materials type** dropdown filtered by Order Type (from **Materials Options** below). **[DONE]**
  - **Latest arrival date** (UI label, stored in `session_shipping.arrival_date`, required), **Workshop start date** (auto from Session), **SFC Project link**, **Delivery region** (from Session). **[DONE]**
  - Read-only **Shipping Location** (from Session). **[DONE]**
  - Status actions: Submit, Shipped (courier+tracking+ship date), Delivered (marks `materials_ordered = true`). **[DONE]**
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
- Sidebar (role-aware): Home, Sessions, Materials (orders), My Sessions, My Certificates, Settings (Users, Workshop Types, Clients, Materials, Languages, Mail Settings), Logout. Guests see only Login. **[DONE]**
- Root `/` shows branded login card (no nav). **[DONE]**
- Basic responsive styles; flashes consistent. **[DONE]**

---

## 10) Ops & non-functional
- Docker Compose: app, db, caddy. Health: `/healthz`. **[DONE]**
- Idempotent migrations; seed guards; simple audit logs for key actions (logins, role changes, password admin resets, provisioning). **[DONE] (minimal)**
- Pagination on long tables; simple rate-limits on auth endpoints. **[DONE]**

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
