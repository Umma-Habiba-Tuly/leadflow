"""Sending email. The rest of the app depends only on `EmailSender`; SMTP is one implementation,
so another transport can be added without touching the sending logic.
"""
import smtplib
import socket
import ssl
from dataclasses import dataclass
from email import policy
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Optional, Protocol


class SendError(RuntimeError):
    """`kind` tells the caller what to do next:
    - "recipient": this address was refused for good. Never retry it; suppress it.
    - "config":    login/sender/content was refused. A human must fix the mailbox. Stop.
    - "transient": network trouble or a temporary (4xx) refusal. Safe to try again later.
    """

    def __init__(self, kind: str, message: str):
        super().__init__(message[:200])
        self.kind = kind


@dataclass
class OutgoingEmail:
    from_email: str
    from_name: Optional[str]
    to_email: str
    subject: str
    text_body: str
    unsubscribe_url: str


class EmailSender(Protocol):
    def send(self, msg: OutgoingEmail) -> str:
        """Send one email, return its Message-ID. Raises SendError."""

    def check(self) -> None:
        """Verify we can connect and log in, without sending anything. Raises SendError."""


# Real unsubscribe links carry a long signed token with no spaces. Under the default 78-column
# folding the email library cannot wrap such a header, so it RFC-2047-encodes it
# ("=?utf-8?q?..."), which is invalid for List-Unsubscribe and makes mail clients drop the
# Unsubscribe button. 998 is the RFC 5322 hard limit, so long single-token headers stay intact.
_WIRE_POLICY = policy.SMTP.clone(max_line_length=998)


def build_message(msg: OutgoingEmail) -> EmailMessage:
    m = EmailMessage(policy=_WIRE_POLICY)
    m["From"] = formataddr((msg.from_name or "", msg.from_email))
    m["To"] = msg.to_email
    m["Subject"] = msg.subject
    m["Date"] = formatdate()
    m["Message-ID"] = make_msgid(domain=msg.from_email.rpartition("@")[2])
    # Mail clients show an "Unsubscribe" button from this header. The one-click flavour
    # (RFC 8058) is only valid over HTTPS, so we only claim it when the link is HTTPS.
    m["List-Unsubscribe"] = f"<{msg.unsubscribe_url}>"
    if msg.unsubscribe_url.lower().startswith("https://"):
        m["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    m.set_content(msg.text_body)
    return m


def _classify(exc: Exception) -> SendError:
    """Turn the many smtplib failures into the three outcomes that matter."""
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        codes = [code for code, _ in exc.recipients.values()]
        if codes and all(code >= 500 for code in codes):
            return SendError("recipient", f"Recipient refused ({codes[0]})")
        return SendError("transient", f"Recipient temporarily refused ({codes[0] if codes else '?'})")
    if isinstance(exc, (smtplib.SMTPAuthenticationError, smtplib.SMTPSenderRefused, smtplib.SMTPNotSupportedError)):
        return SendError("config", f"Mailbox login/sender problem: {type(exc).__name__}")
    if isinstance(exc, smtplib.SMTPResponseException):
        # Anything else with a code: 4xx is "try later", 5xx (e.g. rejected as spam) needs a human.
        text = exc.smtp_error.decode(errors="replace") if isinstance(exc.smtp_error, bytes) else str(exc.smtp_error)
        kind = "transient" if 400 <= exc.smtp_code < 500 else "config"
        return SendError(kind, f"SMTP {exc.smtp_code}: {text}")
    if isinstance(exc, (smtplib.SMTPException, socket.timeout, TimeoutError, OSError, ssl.SSLError)):
        return SendError("transient", f"Could not complete SMTP exchange: {type(exc).__name__}")
    return SendError("transient", f"Unexpected error: {type(exc).__name__}")


class SMTPSender:
    """Plain SMTP. `security` is "starttls" (port 587), "ssl" (port 465) or "none" (local dev only;
    skips TLS and login, so credentials are never sent unencrypted)."""

    def __init__(self, host: str, port: int, username: str, password: str, security: str = "starttls", timeout: float = 20):
        self.host, self.port = host, port
        self.username, self.password = username, password
        self.security, self.timeout = security, timeout

    def _connect(self) -> smtplib.SMTP:
        if self.security == "ssl":
            client = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=ssl.create_default_context())
        else:
            client = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
        try:
            client.ehlo()
            if self.security == "starttls":
                client.starttls(context=ssl.create_default_context())
                client.ehlo()
            if self.security != "none":
                client.login(self.username, self.password)
        except Exception:
            client.close()
            raise
        return client

    def send(self, msg: OutgoingEmail) -> str:
        try:
            message = build_message(msg)
        except ValueError as exc:  # e.g. a newline smuggled into a header
            raise SendError("config", f"Message could not be built: {exc}")
        client = None
        try:
            client = self._connect()
            client.send_message(message)
            return str(message["Message-ID"])
        except Exception as exc:
            raise _classify(exc)
        finally:
            if client is not None:
                try:
                    client.quit()
                except Exception:
                    client.close()

    def check(self) -> None:
        client = None
        try:
            client = self._connect()
            client.noop()
        except Exception as exc:
            raise _classify(exc)
        finally:
            if client is not None:
                try:
                    client.quit()
                except Exception:
                    client.close()
