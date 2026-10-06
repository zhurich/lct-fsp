import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger("app.mail")


def send_mail(to: str, subject: str, body: str) -> None:
    if not settings.smtp_host:
        logger.warning("SMTP не настроен, письмо для %s:\n%s\n%s", to, subject, body)
        return
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        smtp.send_message(message)
