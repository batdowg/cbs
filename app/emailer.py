import logging
import os
import smtplib
import sys
from email.message import EmailMessage

from .models import Settings

logger = logging.getLogger("cbs.mailer")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


def send(to_addr: str, subject: str, body: str):
    settings = Settings.get()
    host = (settings.smtp_host if settings and settings.smtp_host else os.getenv("SMTP_HOST"))
    port = (settings.smtp_port if settings and settings.smtp_port else os.getenv("SMTP_PORT"))
    user = (settings.smtp_user if settings and settings.smtp_user else os.getenv("SMTP_USER"))
    from_addr = (
        settings.smtp_from_default if settings and settings.smtp_from_default else os.getenv("SMTP_FROM_DEFAULT")
    )
    from_name = (
        settings.smtp_from_name if settings and settings.smtp_from_name else os.getenv("SMTP_FROM_NAME", "")
    )
    password = (
        settings.get_smtp_pass() if settings and settings.get_smtp_pass() else os.getenv("SMTP_PASS")
    )

    mode = "real"
    if not host or not port or not from_addr:
        mode = "stub"
        logger.info(
            f"[MAIL-OUT] mode={mode} to={to_addr} subject=\"{subject}\" host={host} result=stub"
        )
        return {"ok": False, "detail": "stub: missing config"}

    try:
        port_int = int(port)
        if port_int == 465:
            server = smtplib.SMTP_SSL(host, port_int)
        else:
            server = smtplib.SMTP(host, port_int)
            if port_int == 587:
                server.starttls()
        if user and password:
            server.login(user, password)
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["To"] = to_addr
        msg["From"] = f"{from_name} <{from_addr}>" if from_name else from_addr
        msg.set_content(body)
        server.sendmail(from_addr, [to_addr], msg.as_string())
        server.quit()
        logger.info(
            f"[MAIL-OUT] mode={mode} to={to_addr} subject=\"{subject}\" host={host} result=sent"
        )
        return {"ok": True, "detail": "sent"}
    except Exception as e:
        logger.info(
            f"[MAIL-OUT] mode={mode} to={to_addr} subject=\"{subject}\" host={host} result={e}"
        )
        return {"ok": False, "detail": str(e)}
