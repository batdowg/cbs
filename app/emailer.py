import os
import smtplib
from email.message import EmailMessage

from .app import get_setting


def send_mail(to_email: str, subject: str, text_body: str, category: str = "certificates"):
    host = get_setting("mail.smtp.host") or os.environ.get("SMTP_HOST", "smtp.office365.com")
    port_val = get_setting("mail.smtp.port") or os.environ.get("SMTP_PORT", "587")
    try:
        port = int(port_val)
    except (TypeError, ValueError):
        port = 587
    user = get_setting("mail.smtp.user") or os.environ.get("SMTP_USER")
    from_default = get_setting("mail.from.default") or os.environ.get(
        "SMTP_FROM_DEFAULT", "certificates@kepner-tregoe.com"
    )
    from_name = get_setting("mail.from.name") or os.environ.get("SMTP_FROM_NAME", "")
    resolved_from = get_setting(f"mail.from.{category}", from_default)
    pwd = os.environ.get("SMTP_PASS")
    from_header = f'{from_name} <{resolved_from}>' if from_name else resolved_from
    if not all([host, port, user, pwd]):
        snippet = text_body[:120].replace("\n", " ")
        print(
            f'[MAIL-OUT] to={to_email} from="{from_header}" subject="{subject}" body="{snippet}"'
        )
        return {"mock": True}
    msg = EmailMessage()
    msg["From"] = from_header
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(text_body)
    try:
        with smtplib.SMTP(host, port) as s:
            s.starttls()
            s.login(user, pwd)
            s.send_message(msg)
        return {"sent": True}
    except Exception as e:
        return {"sent": False, "error": str(e)}

