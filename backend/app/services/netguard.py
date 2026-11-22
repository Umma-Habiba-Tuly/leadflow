"""Shared SSRF guard: decide whether a hostname is safe for the SERVER to connect to.

Used wherever a user-supplied address becomes an outbound connection (website crawling,
SMTP hosts). Resolves the name and requires every address to be on the public internet.
"""
import ipaddress
import socket
from typing import Optional


def is_public_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def hostname_is_public(hostname: Optional[str], port: int = 80) -> bool:
    """True only if the host resolves, and every address it resolves to is public."""
    if not hostname:
        return False
    try:
        infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, ValueError, UnicodeError):
        return False
    ips = {info[4][0] for info in infos}
    return bool(ips) and all(is_public_ip(ip) for ip in ips)
