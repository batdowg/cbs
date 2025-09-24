import json
import logging
import os
import smtplib
import sys
from email.message import EmailMessage
from typing import Sequence

from .shared.mail_utils import normalize_recipients

logger = logging.getLogger("cbs.mailer")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


def _stringify_envelope(recipients: Sequence[str]) -> str:
    return json.dumps(list(recipients))


def send(
    recipients: Sequence[str] | str | None,
    subject: str,
    body: str,
    html: str | None = None,
):
    from .models import Settings  # local import to avoid circular import at module load

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

    envelope, header = normalize_recipients(recipients)
    mode = "real"
    if not host or not port or not from_addr:
        mode = "stub"
        logger.info(
            "[MAIL-OUT] mode=%s to_header=%s envelope=%s subject=\"%s\" host=%s result=stub",
            mode,
            header,
            _stringify_envelope(envelope),
            subject,
            host,
        )
        return {"ok": False, "detail": "stub: missing config"}

    if not envelope:
        logger.warning(
            "[MAIL-NO-RECIPIENTS] subject=\"%s\" host=%s", subject, host
        )
        return {"ok": False, "detail": "no valid recipients"}

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
        if header:
            msg["To"] = header
        msg["From"] = f"{from_name} <{from_addr}>" if from_name else from_addr
        msg.set_content(body)
        if html:
            msg.add_alternative(html, subtype="html")
        server.sendmail(from_addr, envelope, msg.as_string())
        server.quit()
        logger.info(
            "[MAIL-OUT] mode=%s to_header=%s envelope=%s subject=\"%s\" host=%s result=sent",
            mode,
            header,
            _stringify_envelope(envelope),
            subject,
            host,
        )
        return {"ok": True, "detail": "sent"}
    except Exception as e:
        logger.info(
            "[MAIL-OUT] mode=%s to_header=%s envelope=%s subject=\"%s\" host=%s result=%s",
            mode,
            header,
            _stringify_envelope(envelope),
            subject,
            host,
            e,
        )
        return {"ok": False, "detail": str(e)}
