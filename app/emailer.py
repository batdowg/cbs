import logging
import os
import smtplib
import sys
from email.message import EmailMessage

logger = logging.getLogger("cbs.mailer")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


def send(to_addr: str, subject: str, body: str):
    host = os.getenv("SMTP_HOST")
    port = os.getenv("SMTP_PORT")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    from_addr = os.getenv("SMTP_FROM_DEFAULT")
    from_name = os.getenv("SMTP_FROM_NAME", "")

    mode = "real"
    if not host or not port or not from_addr:
        mode = "stub"

    logger.info(
        f"[MAIL-OUT] mode={mode} to={to_addr} subject=\"{subject}\" host={host}"
    )

    if mode == "stub":
        return {"ok": False, "detail": "stub: missing config"}

    try:
        with smtplib.SMTP(host, int(port)) as server:
            if user and password:
                server.login(user, password)
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["To"] = to_addr
            msg["From"] = f"{from_name} <{from_addr}>" if from_name else from_addr
            msg.set_content(body)
            server.send_message(msg)
        return {"ok": True, "detail": "sent"}
    except Exception as e:
        logger.error(f"[MAIL-OUT] error={e}")
        return {"ok": False, "detail": str(e)}
