"""Find a public contact email on a business website.

Safety rules baked in:
- SSRF guard: never fetch private/loopback/link-local addresses (checked on every redirect hop).
- Respect robots.txt.
- Small, bounded requests: timeout, redirect limit, response size cap, HTML only.
"""
import html as html_lib
import re
from typing import Callable, List, Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.services.netguard import hostname_is_public

USER_AGENT = "LeadFlowBot/0.1"
TIMEOUT_SECONDS = 8
MAX_REDIRECTS = 3
MAX_BYTES = 500_000
CONTACT_PATHS = ["/", "/contact", "/contact-us", "/about"]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
FILE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "svg", "webp", "css", "js", "ico", "woff", "woff2"}
JUNK_DOMAINS = {"example.com", "domain.com", "email.com", "yourdomain.com", "sentry.io", "wixpress.com"}
JUNK_LOCAL_PARTS = {"noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon", "postmaster"}
PREFERRED_LOCAL_PARTS = ["info", "contact", "hello", "office", "admin", "support", "sales"]

Fetcher = Callable[[str], Optional[str]]


# ---------- SSRF guard ----------

def is_safe_url(url: str) -> bool:
    """True only for http(s) URLs whose host resolves exclusively to public IPs."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        return hostname_is_public(parsed.hostname, parsed.port or 80)
    except ValueError:
        return False


# ---------- Fetching ----------

def fetch_page(url: str) -> Optional[str]:
    """Fetch one HTML page safely. Returns None on any problem."""
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=False,
                          headers={"User-Agent": USER_AGENT}) as client:
            current = url
            for _ in range(MAX_REDIRECTS + 1):
                if not is_safe_url(current):
                    return None
                with client.stream("GET", current) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            return None
                        current = urljoin(current, location)
                        continue
                    if resp.status_code != 200:
                        return None
                    if "text/html" not in resp.headers.get("content-type", ""):
                        return None
                    body = b""
                    for chunk in resp.iter_bytes():
                        body += chunk
                        if len(body) > MAX_BYTES:
                            break
                    return body[:MAX_BYTES].decode(resp.encoding or "utf-8", errors="replace")
            return None  # too many redirects
    except httpx.HTTPError:
        return None


def allowed_by_robots(base_url: str) -> bool:
    """Check robots.txt. If it can't be read, we allow (standard convention)."""
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}) as client:
            if not is_safe_url(robots_url):
                return False
            resp = client.get(robots_url)
        if resp.status_code != 200:
            return True
        parser.parse(resp.text.splitlines())
    except httpx.HTTPError:
        return True
    return all(parser.can_fetch(USER_AGENT, urljoin(base_url, p)) for p in CONTACT_PATHS)


# ---------- Extraction ----------

def _site_domain(host: str) -> str:
    parts = host.lower().removeprefix("www.").split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host.lower()


def extract_emails(page_html: str) -> List[str]:
    """All plausible contact emails in a page, junk removed, order preserved."""
    text = html_lib.unescape(page_html)
    found = []
    for match in EMAIL_RE.findall(text):
        email = match.strip(".").lower()
        local, _, domain = email.partition("@")
        tld = domain.rsplit(".", 1)[-1]
        is_junk_domain = any(domain == j or domain.endswith("." + j) for j in JUNK_DOMAINS)
        if tld in FILE_EXTENSIONS or is_junk_domain or local in JUNK_LOCAL_PARTS:
            continue
        if email not in found:
            found.append(email)
    return found


def pick_best_email(emails: List[str], site_host: str) -> Optional[str]:
    """Prefer an address on the business's own domain, then role addresses like info@."""
    if not emails:
        return None
    domain = _site_domain(site_host)

    def rank(email: str):
        local, _, email_domain = email.partition("@")
        on_site = _site_domain(email_domain) == domain
        role = PREFERRED_LOCAL_PARTS.index(local) if local in PREFERRED_LOCAL_PARTS else len(PREFERRED_LOCAL_PARTS)
        return (not on_site, role)

    return min(emails, key=rank)


def normalize_website(website: str) -> str:
    website = website.strip()
    return website if re.match(r"^https?://", website, re.I) else f"https://{website}"


def find_email_for_site(website: str, fetch: Fetcher = fetch_page, check_robots: bool = True) -> Optional[str]:
    base = normalize_website(website)
    host = urlparse(base).hostname
    if not host or not is_safe_url(base):
        return None
    if check_robots and not allowed_by_robots(base):
        return None

    collected: List[str] = []
    best: Optional[str] = None
    for path in CONTACT_PATHS:
        page = fetch(urljoin(base, path))
        if page:
            collected.extend(e for e in extract_emails(page) if e not in collected)
        best = pick_best_email(collected, host)
        if best and _site_domain(best.split("@")[1]) == _site_domain(host):
            break  # found an address on the business's own domain, stop crawling
    return best
