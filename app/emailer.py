import logging
import os
import smtplib
from email.message import EmailMessage

from .models import Settings

logger = logging.getLogger("cbs.mailer")


def send_mail(to_email: str, subject: str, text_body: str, category: str = "certificates"):
    settings = Settings.get()
    host = (settings.smtp_host if settings and settings.smtp_host else os.getenv("SMTP_HOST"))
    port = settings.smtp_port if settings and settings.smtp_port else os.getenv("SMTP_PORT")
    user = (settings.smtp_user if settings and settings.smtp_user else os.getenv("SMTP_USER"))
    from_default = (
        settings.smtp_from_default if settings and settings.smtp_from_default else os.getenv("SMTP_FROM_DEFAULT")
    )
    from_name = (
        settings.smtp_from_name if settings and settings.smtp_from_name else os.getenv("SMTP_FROM_NAME", "")
    )
    use_tls = settings.use_tls if settings else True
    use_ssl = settings.use_ssl if settings else False
    pwd = os.getenv("SMTP_PASS")
    try:
        port = int(port) if port else None
    except (TypeError, ValueError):
        port = None
    from_header = f"{from_name} <{from_default}>" if from_name else (from_default or "")
    if not all([host, port, user, pwd, from_default]):
        snippet = text_body[:120].replace("\n", " ")
        logger.info(
            f"[MAIL-OUT] stub to={to_email} subject=\"{subject}\" body=\"{snippet}\""
        )
        return {"mock": True}
    msg = EmailMessage()
    msg["From"] = from_header
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(text_body)
    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(host, port)
        else:
            server = smtplib.SMTP(host, port)
            if use_tls:
                server.starttls()
        server.login(user, pwd)
        server.send_message(msg)
        server.quit()
        logger.info(
            f"[MAIL-OUT] to={to_email} subject=\"{subject}\" host={host}"
        )
        return {"sent": True}
    except Exception as e:  # pragma: no cover - depends on SMTP
        return {"sent": False, "error": str(e)}
