import os
import smtplib
from email.message import EmailMessage

from .app import db, AppSetting


def get_from_for(category: str) -> str:
    try:
        setting = db.session.get(AppSetting, f"mail.from.{category}")
    except Exception:
        setting = None
    if setting:
        return setting.value
    return os.getenv("SMTP_FROM_DEFAULT", "certificates@kepner-tregoe.com")


def send_mail(to_email: str, subject: str, text_body: str, category: str = "certificates"):
    resolved_from = get_from_for(category)
    host = os.getenv("SMTP_HOST", "smtp.office365.com")
    port = int(os.getenv("SMTP_PORT", 587))
    user = os.getenv("SMTP_USER")
    pwd = os.getenv("SMTP_PASS")
    from_name = os.getenv("SMTP_FROM_NAME")
    from_header = f"{from_name} <{resolved_from}>" if from_name else resolved_from
    if not all([host, port, user, pwd]):
        snippet = text_body[:120].replace("\n", " ")
        print(
            f'[MAIL-OUT] to={to_email} from={from_header} subject="{subject}" body="{snippet}"'
        )
        return {"mock": True}
    msg = EmailMessage()
    msg["From"] = from_header
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(text_body)
    with smtplib.SMTP(host, int(port)) as s:
        s.starttls()
        s.login(user, pwd)
        s.send_message(msg)
    return {"sent": True}
