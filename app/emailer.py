import os
import smtplib
from email.message import EmailMessage

from .app import db, AppSetting


def _get_setting(key: str) -> str | None:
    try:
        setting = db.session.get(AppSetting, key)
    except Exception:
        setting = None
    return setting.value if setting else None


def get_from_for(category: str, default_from: str) -> str:
    setting = db.session.get(AppSetting, f"mail.from.{category}")
    if setting:
        return setting.value
    return default_from


def send_mail(to_email: str, subject: str, text_body: str, category: str = "certificates"):
    host = _get_setting("mail.smtp.host") or os.environ.get(
        "SMTP_HOST", "smtp.office365.com"
    )
    port = int(
        _get_setting("mail.smtp.port")
        or os.environ.get("SMTP_PORT", 587)
    )
    user = _get_setting("mail.smtp.user") or os.environ.get("SMTP_USER")
    from_default = _get_setting("mail.from.default") or os.environ.get(
        "SMTP_FROM_DEFAULT", "certificates@kepner-tregoe.com"
    )
    from_name = _get_setting("mail.from.name") or os.environ.get("SMTP_FROM_NAME", "")
    resolved_from = get_from_for(category, from_default)
    pwd = os.environ.get("SMTP_PASS")
    from_header = f'"{from_name}" <{resolved_from}>' if from_name else resolved_from
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
    with smtplib.SMTP(host, int(port)) as s:
        s.starttls()
        s.login(user, pwd)
        s.send_message(msg)
    return {"sent": True}

