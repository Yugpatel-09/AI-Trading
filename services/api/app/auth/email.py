import smtplib
from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from services.api.app.core.config import settings
from services.api.app.core.logging import logger


class EmailSender(ABC):
    """Abstract Email Sender Interface for notifications and verification."""
    @abstractmethod
    def send_verification_email(self, to_email: str, token: str) -> bool:
        """Send account email verification link with token."""
        pass

    @abstractmethod
    def send_alert_email(self, to_email: str, subject: str, message: str) -> bool:
        """Send operational or risk alert email."""
        pass


class ConsoleEmailSender(EmailSender):
    """Development / Testing email sender. Outputs to logger."""
    sent_verification_tokens: dict[str, str] = {}

    def send_verification_email(self, to_email: str, token: str) -> bool:
        self.sent_verification_tokens[to_email.strip().lower()] = token
        logger.info(
            f"[EMAIL SENDER: DEV/TEST] Verification email to: {to_email} | Token: {token} "
            f"(Expires in 24 hours)"
        )
        return True

    def send_alert_email(self, to_email: str, subject: str, message: str) -> bool:
        logger.info(f"[EMAIL SENDER: DEV/TEST ALERT] To: {to_email} | Subject: {subject} | Body: {message}")
        return True


class SMTPEmailSender(EmailSender):
    """
    Production SMTP Email Sender.
    Security: Verification tokens are transmitted over TLS and NEVER written to logs.
    """
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        from_email: Optional[str] = None,
        use_tls: bool = True,
    ):
        self.host = host or settings.SMTP_HOST
        self.port = port or settings.SMTP_PORT
        self.username = username or settings.SMTP_USER
        self.password = password or settings.SMTP_PASSWORD
        self.from_email = from_email or settings.SMTP_FROM
        self.use_tls = use_tls

    def send_verification_email(self, to_email: str, token: str) -> bool:
        if not self.host or not self.from_email:
            logger.error("SMTP host or from_email is not configured. Email dispatch failed.")
            return False

        subject = "TradeForge - Verify Your Email Address"
        # In production logs, NEVER log the token!
        logger.info(f"Dispatching verification email via SMTP to: {to_email} (token concealed)")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_email
        msg["To"] = to_email

        body_text = (
            f"Welcome to TradeForge.\n\n"
            f"Please verify your email address to activate your account:\n"
            f"Token: {token}\n\n"
            f"This link expires in 24 hours. If you did not request this, please ignore."
        )
        body_html = f"""
        <html>
            <body>
                <h2>Welcome to TradeForge</h2>
                <p>Please enter the following token to verify your email address:</p>
                <p style="font-size: 18px; font-weight: bold; background: #f0f0f0; padding: 10px; border-radius: 4px; display: inline-block;">
                    {token}
                </p>
                <p>This verification token is valid for <strong>24 hours</strong>.</p>
                <hr />
                <p style="font-size: 11px; color: #888;">TradeForge AI Trading Platform - Intraday Risk Management</p>
            </body>
        </html>
        """
        msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))

        try:
            with smtplib.SMTP(self.host, self.port, timeout=10) as server:
                if self.use_tls:
                    server.starttls()
                if self.username and self.password:
                    server.login(self.username, self.password)
                server.send_message(msg)
            logger.info(f"Verification email successfully sent via SMTP to {to_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to dispatch verification email via SMTP to {to_email}: {str(e)}")
            return False

    def send_alert_email(self, to_email: str, subject: str, message: str) -> bool:
        if not self.host or not self.from_email:
            logger.error("SMTP host or from_email not configured for alert email.")
            return False

        msg = MIMEText(message, "plain")
        msg["Subject"] = f"[TradeForge Alert] {subject}"
        msg["From"] = self.from_email
        msg["To"] = to_email

        try:
            with smtplib.SMTP(self.host, self.port, timeout=10) as server:
                if self.use_tls:
                    server.starttls()
                if self.username and self.password:
                    server.login(self.username, self.password)
                server.send_message(msg)
            logger.info(f"Alert email sent to {to_email}: {subject}")
            return True
        except Exception as e:
            logger.error(f"Failed to send alert email to {to_email}: {str(e)}")
            return False


def get_email_sender() -> EmailSender:
    """Factory returning configured EmailSender."""
    if settings.is_dev or settings.EMAIL_PROVIDER == "console":
        return ConsoleEmailSender()
    return SMTPEmailSender()


email_sender = get_email_sender()
