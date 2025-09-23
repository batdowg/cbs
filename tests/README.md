# Lean Smoke Suite

The smoke suite focuses on business-critical flows that keep Certs & Badges stable. Each test guards a distinct behavior:

- `tests/smoke/test_auth_roles.py` – unified login and home routing for Administrators, CRM, delivery/contractor staff, learners, and CSAs.
- `tests/smoke/test_dashboards_filters.py` – sessions dashboard excludes material-only engagements and the materials dashboard excludes workshop-only sessions.
- `tests/smoke/test_materials_lifecycle.py` – materials order finalization blocks when items remain unprocessed and promotes the session lifecycle flags on success.
- `tests/smoke/test_delivered_finalize_flow.py` – ready/delivered guardrails, finalize visibility, and workshop view behavior for material-only vs. standard sessions.
- `tests/smoke/test_prework_invites_and_disable.py` – invite status transitions plus notify/silent disable flows (including silent allowing Delivered with zero participants).
- `tests/smoke/test_attendance_cert_gate.py` – attendance recording drives certificate eligibility and enforces the full-attendance gate.
- `tests/smoke/test_resources_visibility.py` – facilitator vs. participant resource visibility and collapsed facilitator resources.
- `tests/smoke/test_profile_contacts.py` – profile contact/location/photo persistence for staff and linked participant records.

## Adding a new test

Add a test only when it protects a business-critical behavior described in `CONTEXT.md`. Prefer full-stack route coverage (request → database) that fails fast when the feature regresses.
