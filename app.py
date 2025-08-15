# Landing page route
from flask import render_template

@app.route("/landing")
def landing():
    # Replace with real queries and RBAC filters
    work_tiles = [
        {"title":"Sessions awaiting client details","count":3,"value":None,"action":"Open list","href":"/sessions?status=awaiting_client"},
        {"title":"Participants pending import review","count":1,"value":None,"action":"Review","href":"/imports/pending"},
        {"title":"Upcoming sessions this week","count":2,"value":None,"action":"View","href":"/sessions?range=week"},
        {"title":"Attendance confirmations required","count":4,"value":None,"action":"Confirm","href":"/attendance/confirm"},
        {"title":"Certificates ready to send","count":12,"value":None,"action":"Send","href":"/credentials/ready"},
        {"title":"Surveys not yet shared","count":2,"value":None,"action":"Share","href":"/surveys/share"},
    ]
    sessions = [
        {"id":"S-1234","date":"2025-08-18","title":"PSDMxp Workshop","client":"Hilmar","facilitator":"AB"},
        {"id":"S-1235","date":"2025-08-20","title":"PSDM","client":"Acme Manufacturing","facilitator":"LT"},
    ]
    activity = [
        "AB issued 24 certificates for S-1232",
        "LT confirmed attendance for S-1231",
        "Participant import completed for Acme Manufacturing",
    ]
    notices = [
        "New field added to participant import template",
        "Survey link text updated in email templates",
    ]
    return render_template(
        "landing.html",
        work_tiles=work_tiles,
        sessions=sessions,
        last_import="2025-08-14 16:22",
        import_errors=2,
        creds_pending_validation=3,
        creds_ready=12,
        creds_sent_week=46,
        activity=activity,
        notices=notices,
    )
from flask import redirect, url_for
from flask_login import login_required

@app.route("/")
@login_required
def home_redirect():
    return redirect(url_for("landing"))
if __name__ == "__main__":
    from os import environ
    app.run(host="0.0.0.0", port=int(environ.get("PORT", 5000)), debug=False)
