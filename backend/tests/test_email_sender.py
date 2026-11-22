"""Low-level pieces: encryption, SSRF guard, how an email is built, and real SMTP conversations
against a local server (aiosmtpd) so smtplib is exercised for real, not mocked."""
import email
import smtplib
import socket
from email import policy

import pytest
from aiosmtpd.controller import Controller
from cryptography.fernet import Fernet

from app.core import crypto
from app.core.config import settings
from app.services.email_sender import OutgoingEmail, SendError, SMTPSender, _classify, build_message
from app.services.netguard import hostname_is_public, is_public_ip

# ---------- encryption ----------


def test_secret_round_trips_and_is_not_stored_readable():
    token = crypto.encrypt_secret("hunter2-app-password")
    assert "hunter2" not in token and token != "hunter2-app-password"
    assert crypto.decrypt_secret(token) == "hunter2-app-password"


def test_same_secret_encrypts_differently_each_time():
    assert crypto.encrypt_secret("same") != crypto.encrypt_secret("same")  # random IV, no pattern leaks


def test_wrong_key_cannot_decrypt(monkeypatch):
    token = crypto.encrypt_secret("secret")
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt_secret(token)


def test_tampered_ciphertext_is_rejected():
    token = crypto.encrypt_secret("secret")
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt_secret(token[:-4] + "AAAA")


@pytest.mark.parametrize("bad_key", ["", "not-a-fernet-key"])
def test_missing_or_invalid_key_refuses_to_encrypt(monkeypatch, bad_key):
    monkeypatch.setattr(settings, "encryption_key", bad_key)
    with pytest.raises(crypto.CryptoNotConfigured):
        crypto.encrypt_secret("x")


# ---------- SSRF guard ----------


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.1.2.3", "192.168.0.9", "172.16.5.5", "169.254.169.254", "::1", "0.0.0.0", "224.0.0.1"])
def test_non_public_ips_are_rejected(ip):
    assert is_public_ip(ip) is False


def test_public_ip_and_hostname_checks():
    assert is_public_ip("8.8.8.8") is True
    assert hostname_is_public("8.8.8.8") is True
    assert hostname_is_public("localhost") is False
    assert hostname_is_public("127.0.0.1") is False
    assert hostname_is_public("") is False
    assert hostname_is_public(None) is False
    assert hostname_is_public("this-host-does-not-exist.invalid") is False


# ---------- building the email ----------


def _msg(**kw):
    base = dict(
        from_email="sam@rivera.example", from_name="Sam Rivera", to_email="info@bright.example",
        subject="Quick idea", text_body="Hello there.\n\n--\nFooter", unsubscribe_url="https://app.example/u/abc",
    )
    base.update(kw)
    return OutgoingEmail(**base)


def test_message_has_the_required_headers():
    m = build_message(_msg())
    assert m["From"] == "Sam Rivera <sam@rivera.example>"
    assert m["To"] == "info@bright.example" and m["Subject"] == "Quick idea"
    assert m["Message-ID"].endswith("@rivera.example>")  # id is on the sender's own domain
    assert m["Date"]
    assert m["List-Unsubscribe"] == "<https://app.example/u/abc>"
    assert m["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert "Footer" in m.get_content()


def test_one_click_header_only_claimed_for_https_links():
    m = build_message(_msg(unsubscribe_url="http://localhost:8000/u/abc"))
    assert m["List-Unsubscribe"] == "<http://localhost:8000/u/abc>"
    assert m["List-Unsubscribe-Post"] is None  # RFC 8058 requires HTTPS


def test_message_ids_are_unique():
    assert build_message(_msg())["Message-ID"] != build_message(_msg())["Message-ID"]


@pytest.mark.parametrize("field", ["subject", "to_email"])
def test_header_injection_is_blocked(field):
    with pytest.raises(ValueError):
        build_message(_msg(**{field: "x\r\nBcc: victim@example.com"}))


def test_injection_in_display_name_is_blocked_too():
    # Second layer: the API schema already rejects this input; the email library refuses it as well.
    with pytest.raises(ValueError):
        build_message(_msg(from_name="Sam\r\nBcc: victim@example.com"))


def test_sender_reports_unbuildable_message_as_config_error():
    sender = SMTPSender("127.0.0.1", 1, "u", "p", security="none")
    with pytest.raises(SendError) as err:
        sender.send(_msg(subject="bad\r\nBcc: x@example.com"))
    assert err.value.kind == "config"


# ---------- classifying SMTP failures ----------


@pytest.mark.parametrize(
    "exc, kind",
    [
        (smtplib.SMTPRecipientsRefused({"a@x.test": (550, b"no such user")}), "recipient"),
        (smtplib.SMTPRecipientsRefused({"a@x.test": (451, b"try later")}), "transient"),  # greylisting is not a dead address
        (smtplib.SMTPAuthenticationError(535, b"bad credentials"), "config"),
        (smtplib.SMTPSenderRefused(553, b"not allowed", "me@x.test"), "config"),
        (smtplib.SMTPDataError(554, b"rejected as spam"), "config"),
        (smtplib.SMTPDataError(451, b"temporary local problem"), "transient"),
        (smtplib.SMTPServerDisconnected("gone"), "transient"),
        (socket.timeout("slow"), "transient"),
        (ConnectionRefusedError(), "transient"),
        (RuntimeError("???"), "transient"),
    ],
)
def test_failures_map_to_the_right_action(exc, kind):
    assert _classify(exc).kind == kind


def test_error_text_never_leaks_credentials():
    err = _classify(smtplib.SMTPAuthenticationError(535, b"hunter2 is wrong"))
    assert "hunter2" not in str(err)


# ---------- a real SMTP conversation ----------


class Capture:
    def __init__(self):
        self.messages, self.reject_rcpt, self.data_reply = [], {}, "250 OK"

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        if address in self.reject_rcpt:
            return self.reject_rcpt[address]
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, server, session, envelope):
        if self.data_reply.startswith("250"):
            self.messages.append(envelope)
        return self.data_reply


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def smtp_server():
    handler, port = Capture(), _free_port()
    controller = Controller(handler, hostname="127.0.0.1", port=port)
    controller.start()
    yield handler, port
    controller.stop()


def _sender(port):
    return SMTPSender("127.0.0.1", port, "", "", security="none", timeout=5)


def test_real_send_delivers_the_message(smtp_server):
    handler, port = smtp_server
    message_id = _sender(port).send(_msg())
    assert len(handler.messages) == 1
    got = email.message_from_bytes(handler.messages[0].content, policy=policy.default)
    assert got["Subject"] == "Quick idea" and got["From"] == "Sam Rivera <sam@rivera.example>"
    assert got["Message-ID"] == message_id
    assert got["List-Unsubscribe"] == "<https://app.example/u/abc>"
    assert "Footer" in got.get_content()
    assert handler.messages[0].rcpt_tos == ["info@bright.example"]


def test_refused_address_is_a_recipient_error(smtp_server):
    handler, port = smtp_server
    handler.reject_rcpt["gone@bright.example"] = "550 5.1.1 No such user"
    with pytest.raises(SendError) as err:
        _sender(port).send(_msg(to_email="gone@bright.example"))
    assert err.value.kind == "recipient" and handler.messages == []


def test_temporary_refusal_is_transient(smtp_server):
    handler, port = smtp_server
    handler.reject_rcpt["busy@bright.example"] = "451 4.7.1 Greylisted, try later"
    with pytest.raises(SendError) as err:
        _sender(port).send(_msg(to_email="busy@bright.example"))
    assert err.value.kind == "transient"


def test_content_rejected_as_spam_needs_a_human(smtp_server):
    handler, port = smtp_server
    handler.data_reply = "554 5.7.1 Message rejected as spam"
    with pytest.raises(SendError) as err:
        _sender(port).send(_msg())
    assert err.value.kind == "config" and "554" in str(err.value)


def test_nothing_listening_is_transient():
    with pytest.raises(SendError) as err:
        _sender(_free_port()).send(_msg())
    assert err.value.kind == "transient"


def test_check_connects_without_sending(smtp_server):
    handler, port = smtp_server
    _sender(port).check()
    assert handler.messages == []
    with pytest.raises(SendError):
        _sender(_free_port()).check()


def test_long_unsubscribe_link_reaches_the_wire_unmangled(smtp_server):
    """Found by reading a captured email: real unsubscribe links carry a ~200 character token. The
    email library RFC-2047-encoded the header ('=?utf-8?q?...'), which is invalid for
    List-Unsubscribe, so mail clients would show no Unsubscribe button. Checked on the RAW bytes,
    because parsing with the default policy silently decodes the damage and hides it."""
    handler, port = smtp_server
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." + "A" * 90 + "." + "B" * 43
    url = f"https://app.example/u/{token}"
    _sender(port).send(_msg(unsubscribe_url=url))
    raw = handler.messages[0].content.replace(b"\r\n ", b"").replace(b"\n ", b"")  # undo any folding
    assert f"List-Unsubscribe: <{url}>".encode() in raw
    assert b"=?utf-8?" not in raw.split(b"\n\n", 1)[0].split(b"\r\n\r\n", 1)[0]  # no encoded words in the headers
    assert b"List-Unsubscribe-Post: List-Unsubscribe=One-Click" in raw
