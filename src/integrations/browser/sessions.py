"""Authenticated browser sessions (cookies + localStorage).

Lets the user hand the browser a logged-in session without the LLM ever seeing
the secrets. Sessions are stored as *profiles* in a single Fernet-encrypted
``service_credentials`` row and are injected into Playwright / Scrapling below
the tool layer. Nothing in this module logs or returns cookie *values* except
the two methods that exist to feed a browser (``load_storage_state`` and
``cookies_for_url``).

Two halves live here:

* ``parse_session_export`` -- turns the common cookie export formats into
  Playwright's ``storage_state`` shape, fixing up combinations Chromium rejects.
* ``BrowserSessionStore`` -- CRUD over profiles, URL matching, and write-back of
  cookies the site rotated during a browsing session.
"""

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from src.utils.logger import get_logger

logger = get_logger(__name__)

SERVICE_NAME = "browser_sessions"
CREDENTIAL_TYPE = "cookie_jar"

FORMATS = ("auto", "playwright", "cookie_editor", "netscape", "header")

MAX_PAYLOAD_BYTES = 2_000_000
MAX_COOKIES_PER_PROFILE = 1000
MAX_NAME_LENGTH = 64

_SAMESITE_MAP = {
    "none": "None",
    "no_restriction": "None",
    "lax": "Lax",
    "strict": "Strict",
    "unspecified": "Lax",
    "": "Lax",
}

_IP_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$|^\[?[0-9a-fA-F:]+\]?$")
_DOMAIN_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class SessionParseError(ValueError):
    """The supplied export could not be turned into a usable session."""


class DuplicateSessionName(ValueError):
    """Another profile already uses this name (names are unique, case-insensitive)."""


@dataclass
class ParsedSession:
    """Result of parsing an export: Playwright-shaped data plus warnings."""

    cookies: List[Dict[str, Any]] = field(default_factory=list)
    origins: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class _Warnings:
    """Collects warnings, collapsing repeats into a single counted message."""

    def __init__(self) -> None:
        self._counts: Dict[str, int] = {}
        self._templates: Dict[str, str] = {}

    def add(self, key: str, template: str) -> None:
        self._templates[key] = template
        self._counts[key] = self._counts.get(key, 0) + 1

    def render(self) -> List[str]:
        return [self._templates[k].format(n=n) for k, n in self._counts.items()]


# ----------------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------------


def parse_session_export(
    raw: str,
    fmt: str = "auto",
    domain: Optional[str] = None,
    now: Optional[float] = None,
) -> ParsedSession:
    """Parse a cookie export into Playwright ``storage_state`` data.

    Args:
        raw: The pasted/uploaded export.
        fmt: One of ``FORMATS``. ``auto`` detects the format.
        domain: Required for the raw ``Cookie:`` header format.
        now: Override for the current time (tests).

    Raises:
        SessionParseError: Input is empty, oversized, malformed, or yields no
            usable cookies. Messages never include cookie values.
    """
    if fmt not in FORMATS:
        raise SessionParseError(f"Unknown format '{fmt}'. Use one of: {', '.join(FORMATS)}")
    if raw is None or not raw.strip():
        raise SessionParseError("The export is empty")
    if len(raw.encode("utf-8", errors="ignore")) > MAX_PAYLOAD_BYTES:
        raise SessionParseError(f"The export is larger than {MAX_PAYLOAD_BYTES // 1_000_000} MB")

    text = raw.strip().lstrip("﻿")
    detected = _detect_format(text) if fmt == "auto" else fmt
    warnings = _Warnings()
    origins: List[Dict[str, Any]] = []

    if detected == "playwright":
        data = _load_json(text)
        if not isinstance(data, dict) or not isinstance(data.get("cookies", []), list):
            raise SessionParseError(
                "Expected a Playwright storage_state object with a 'cookies' list"
            )
        raw_cookies = data.get("cookies", [])
        origins = _normalize_origins(data.get("origins", []), warnings)
    elif detected == "cookie_editor":
        data = _load_json(text)
        if isinstance(data, dict) and isinstance(data.get("cookies"), list):
            data = data["cookies"]
        if not isinstance(data, list):
            raise SessionParseError("Expected a JSON array of cookies")
        raw_cookies = data
    elif detected == "netscape":
        raw_cookies = _parse_netscape(text)
    elif detected == "header":
        raw_cookies = _parse_header(text, domain)
    else:  # pragma: no cover - guarded by FORMATS check
        raise SessionParseError(f"Unsupported format '{detected}'")

    if len(raw_cookies) > MAX_COOKIES_PER_PROFILE:
        raise SessionParseError(f"Too many cookies (limit {MAX_COOKIES_PER_PROFILE} per profile)")

    now_ts = time.time() if now is None else now
    cookies: List[Dict[str, Any]] = []
    seen = set()
    for item in raw_cookies:
        cookie = _normalize_cookie(item, warnings, now_ts)
        if cookie is None:
            continue
        key = _cookie_key(cookie)
        if key in seen:
            warnings.add("dup", "{n} duplicate cookie(s) ignored (first occurrence kept)")
            continue
        seen.add(key)
        cookies.append(cookie)

    if not cookies and not origins:
        msgs = warnings.render()
        detail = f" ({'; '.join(msgs)})" if msgs else ""
        raise SessionParseError(f"No usable cookies found in the export{detail}")

    return ParsedSession(cookies=cookies, origins=origins, warnings=warnings.render())


def _load_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise SessionParseError(
            f"Invalid JSON: {e.msg} (line {e.lineno}, column {e.colno})"
        ) from None


def _detect_format(text: str) -> str:
    if text[0] in "{[":
        data = _load_json(text)
        if isinstance(data, dict) and ("cookies" in data or "origins" in data):
            return "playwright"
        if isinstance(data, list):
            return "cookie_editor"
        raise SessionParseError(
            "Unrecognised JSON: expected a Playwright storage_state object or a cookie array"
        )
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if text.startswith("# Netscape") or text.startswith("# HTTP Cookie File"):
        return "netscape"
    if any(
        len(ln.split("\t")) >= 7
        for ln in lines
        if not ln.startswith("#") or ln.startswith("#HttpOnly_")
    ):
        return "netscape"
    if "=" in text and "\n" not in text.strip():
        return "header"
    raise SessionParseError(
        "Could not detect the format. Choose one explicitly "
        "(Playwright storage_state, Cookie-Editor JSON, cookies.txt, or Cookie header)."
    )


def _parse_netscape(text: str) -> List[Dict[str, Any]]:
    cookies: List[Dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip("\r\n")
        if not line.strip():
            continue
        http_only = False
        if line.startswith("#HttpOnly_"):
            http_only = True
            line = line[len("#HttpOnly_") :]
        elif line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            # Copy/paste often turns tabs into spaces.
            parts = line.split(None, 6)
        if len(parts) < 7:
            continue
        dom, flag, path, secure, expiry, name, value = parts[:7]
        include_subdomains = flag.strip().upper() == "TRUE"
        dom = dom.strip()
        bare = dom.lstrip(".")
        dom = ("." + bare) if include_subdomains else bare
        try:
            expires = int(float(expiry))
        except ValueError:
            expires = -1
        cookies.append(
            {
                "name": name,
                "value": value,
                "domain": dom,
                "path": path or "/",
                "expires": expires if expires > 0 else -1,
                "httpOnly": http_only,
                "secure": secure.strip().upper() == "TRUE",
                "sameSite": "Lax",
            }
        )
    if not cookies:
        raise SessionParseError("No cookie lines found in the cookies.txt export")
    return cookies


def _parse_header(text: str, domain: Optional[str]) -> List[Dict[str, Any]]:
    if not domain or not domain.strip():
        raise SessionParseError("A domain is required when importing a raw Cookie header")
    header = text.strip()
    if header.lower().startswith("cookie:"):
        header = header[len("cookie:") :]
    cookies = []
    for pair in header.split(";"):
        name, sep, value = pair.strip().partition("=")
        if not sep or not name:
            continue
        cookies.append(
            {
                "name": name.strip(),
                "value": value.strip(),
                "domain": domain.strip(),
                "path": "/",
                "expires": -1,
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax",
            }
        )
    if not cookies:
        raise SessionParseError("No name=value pairs found in the Cookie header")
    return cookies


def _clean_domain(value: Any) -> Optional[str]:
    """Return a bare, lower-cased domain (optional leading dot kept) or None."""
    if not isinstance(value, str):
        return None
    dom = value.strip().lower()
    if "://" in dom:
        dom = urlsplit(dom).hostname or ""
    dom = dom.split("/")[0]
    if not dom or not (_DOMAIN_RE.match(dom.lstrip(".")) or _IP_RE.match(dom)):
        return None
    return dom


def _is_ip(host: str) -> bool:
    return bool(_IP_RE.match(host.strip("[]"))) and (":" in host or host.replace(".", "").isdigit())


def _normalize_cookie(item: Any, warnings: _Warnings, now: float) -> Optional[Dict[str, Any]]:
    """Normalize one raw cookie dict to Playwright's shape, or None to drop it."""
    if not isinstance(item, dict):
        warnings.add("bad", "{n} malformed cookie entr(y/ies) skipped")
        return None

    name = item.get("name")
    value = item.get("value")
    domain = _clean_domain(item.get("domain"))
    if not isinstance(name, str) or not name or value is None or domain is None:
        warnings.add("bad", "{n} malformed cookie entr(y/ies) skipped")
        return None
    value = str(value)

    # Domain scoping: Cookie-Editor tells us whether it was host-only.
    host_only = item.get("hostOnly")
    bare = domain.lstrip(".")
    if _is_ip(bare) or bare == "localhost":
        domain = bare
    elif host_only is True:
        domain = bare
    elif host_only is False:
        domain = "." + bare

    path = item.get("path") or "/"
    if not isinstance(path, str) or not path.startswith("/"):
        path = "/"

    # Expiry: seconds since epoch, -1 for session cookies. Tolerate ms and
    # the alternate key names used by different exporters.
    expires: Any = item.get("expires", item.get("expirationDate", item.get("expiry")))
    if item.get("session") is True or expires in (None, "", 0, -1):
        expires = -1
    else:
        try:
            expires = float(expires)
        except (TypeError, ValueError):
            expires = -1
        if expires > 1e11:  # milliseconds
            expires = expires / 1000.0
        if expires != -1 and expires <= now:
            warnings.add("expired", "{n} already-expired cookie(s) dropped")
            return None
        expires = int(expires) if expires != -1 else -1

    secure = bool(item.get("secure", False))
    http_only = bool(item.get("httpOnly", False))

    raw_same = item.get("sameSite")
    same_site = _SAMESITE_MAP.get(str(raw_same).lower() if raw_same is not None else "", None)
    if same_site is None:
        # Already-correct Playwright casing or an unknown token.
        same_site = raw_same if raw_same in ("Strict", "Lax", "None") else "Lax"

    if same_site == "None" and not secure:
        secure = True
        warnings.add(
            "samesite", "{n} SameSite=None cookie(s) forced to Secure (required by Chromium)"
        )
    if name.startswith("__Host-"):
        if not secure or path != "/" or domain.startswith("."):
            warnings.add("host", "{n} __Host- cookie(s) adjusted to host-only, Secure, path=/")
        secure, path, domain = True, "/", bare
    elif name.startswith("__Secure-") and not secure:
        secure = True
        warnings.add("secure", "{n} __Secure- cookie(s) forced to Secure")

    return {
        "name": name,
        "value": value,
        "domain": domain,
        "path": path,
        "expires": expires,
        "httpOnly": http_only,
        "secure": secure,
        "sameSite": same_site,
    }


def _normalize_origins(raw: Any, warnings: _Warnings) -> List[Dict[str, Any]]:
    origins: List[Dict[str, Any]] = []
    if not isinstance(raw, list):
        return origins
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        origin = entry.get("origin")
        items = entry.get("localStorage") or []
        if (
            not isinstance(origin, str)
            or urlsplit(origin).scheme not in ("http", "https")
            or not isinstance(items, list)
        ):
            warnings.add("origin", "{n} invalid localStorage origin(s) skipped")
            continue
        clean = [
            {"name": str(i["name"]), "value": str(i.get("value", ""))}
            for i in items
            if isinstance(i, dict) and "name" in i
        ]
        if clean:
            origins.append({"origin": origin.rstrip("/"), "localStorage": clean})
    return origins


# ----------------------------------------------------------------------------
# Cookie helpers
# ----------------------------------------------------------------------------


def _cookie_key(cookie: Dict[str, Any]) -> Tuple[str, str, str]:
    return (cookie["name"], cookie["domain"].lstrip(".").lower(), cookie.get("path") or "/")


def _bare(domain: str) -> str:
    return domain.lstrip(".").lower()


def _domain_matches(cookie_domain: str, host: str) -> bool:
    """RFC 6265 domain-match. A leading dot means 'this domain and subdomains'."""
    host = host.lower()
    bare = _bare(cookie_domain)
    if host == bare:
        return True
    return cookie_domain.startswith(".") and host.endswith("." + bare)


def _path_matches(cookie_path: str, request_path: str) -> bool:
    request_path = request_path or "/"
    if request_path == cookie_path:
        return True
    if request_path.startswith(cookie_path):
        return cookie_path.endswith("/") or request_path[len(cookie_path)] == "/"
    return False


def _is_expired(cookie: Dict[str, Any], now: float) -> bool:
    exp = cookie.get("expires", -1)
    return exp not in (None, -1, 0) and exp <= now


_LOGIN_PATH_RE = re.compile(
    r"(^|[/._-])(log[-_]?in|sign[-_]?in|sign[-_]?on|sso|auth(enticate)?|oauth2?|"
    r"account/login|servicelogin|identifier)([/._?-]|$)",
    re.IGNORECASE,
)


def looks_like_login_url(url: str) -> bool:
    """Heuristic: does ``url`` look like a login / sign-in page?

    Used to tell the model (and the Test button) that a saved session has
    probably expired when a site bounces back to its login form.
    """
    parts = urlsplit(url or "")
    return bool(_LOGIN_PATH_RE.search(parts.path or "")) or bool(
        _LOGIN_PATH_RE.search((parts.hostname or "").split(".")[0])
    )


def _iso(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# ----------------------------------------------------------------------------
# Profiles and store
# ----------------------------------------------------------------------------


@dataclass
class SessionProfile:
    """One named login (e.g. 'Personal Gmail'): cookies plus localStorage."""

    id: str
    name: str
    enabled: bool = True
    persist_updates: bool = True
    cookies: List[Dict[str, Any]] = field(default_factory=list)
    origins: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    # Bumped whenever the cookies are replaced by the user, so a browser session
    # that started earlier can't overwrite a fresh import when it closes.
    revision: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "persist_updates": self.persist_updates,
            "cookies": self.cookies,
            "origins": self.origins,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionProfile":
        return cls(
            id=data["id"],
            name=data["name"],
            enabled=bool(data.get("enabled", True)),
            persist_updates=bool(data.get("persist_updates", True)),
            cookies=list(data.get("cookies", [])),
            origins=list(data.get("origins", [])),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            revision=int(data.get("revision", 0)),
        )

    @property
    def domains(self) -> List[str]:
        return sorted({_bare(c["domain"]) for c in self.cookies})

    def metadata(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Non-secret summary. Never includes cookie names or values."""
        now_ts = time.time() if now is None else now
        expiries = [c["expires"] for c in self.cookies if c.get("expires", -1) not in (None, -1)]
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "persist_updates": self.persist_updates,
            "domains": self.domains,
            "cookie_count": len(self.cookies),
            "expired_count": sum(1 for c in self.cookies if _is_expired(c, now_ts)),
            "earliest_expiry": _iso(min(expiries)) if expiries else None,
            "latest_expiry": _iso(max(expiries)) if expiries else None,
            "has_local_storage": any(o.get("localStorage") for o in self.origins),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BrowserSessionStore:
    """Encrypted CRUD for session profiles plus URL matching and write-back.

    All profiles live in one ``service_credentials`` row so the existing
    ``CredentialsRepository`` (Fernet) handles encryption at rest.

    Every mutation is a synchronous read-modify-write of that row. The app runs
    them on the event-loop thread with no ``await`` in between, which makes them
    atomic within the single server process; it is not safe across processes.
    """

    def __init__(self, credentials_repo: Any):
        self.credentials_repo = credentials_repo

    # -- persistence ---------------------------------------------------------

    def _load(self) -> List[SessionProfile]:
        record = self.credentials_repo.get(SERVICE_NAME)
        if not record:
            return []
        raw_profiles = (record.get("credential_data") or {}).get("profiles", [])
        profiles = []
        for raw in raw_profiles:
            try:
                profiles.append(SessionProfile.from_dict(raw))
            except (KeyError, TypeError):
                logger.warning("Skipping malformed browser session profile")
        return profiles

    def _save(self, profiles: List[SessionProfile]) -> None:
        if not profiles:
            self.credentials_repo.delete(SERVICE_NAME)
            return
        self.credentials_repo.store(
            service_name=SERVICE_NAME,
            credential_type=CREDENTIAL_TYPE,
            credential_data={"profiles": [p.to_dict() for p in profiles]},
        )

    # -- CRUD ----------------------------------------------------------------

    def list_metadata(self) -> List[Dict[str, Any]]:
        return [p.metadata() for p in self._load()]

    def get_metadata(self, profile_id: str) -> Optional[Dict[str, Any]]:
        for p in self._load():
            if p.id == profile_id:
                return p.metadata()
        return None

    @staticmethod
    def _validate_name(
        name: str, profiles: List[SessionProfile], exclude_id: Optional[str] = None
    ) -> str:
        name = (name or "").strip()
        if not name:
            raise ValueError("Profile name is required")
        if len(name) > MAX_NAME_LENGTH:
            raise ValueError(f"Profile name must be at most {MAX_NAME_LENGTH} characters")
        if any(p.name.lower() == name.lower() and p.id != exclude_id for p in profiles):
            raise DuplicateSessionName(f"A session named '{name}' already exists")
        return name

    def create(
        self,
        name: str,
        parsed: ParsedSession,
        persist_updates: bool = True,
        enabled: bool = True,
    ) -> Dict[str, Any]:
        profiles = self._load()
        name = self._validate_name(name, profiles)
        ts = _now_iso()
        profile = SessionProfile(
            id=uuid.uuid4().hex,
            name=name,
            enabled=enabled,
            persist_updates=persist_updates,
            cookies=parsed.cookies,
            origins=parsed.origins,
            created_at=ts,
            updated_at=ts,
        )
        profiles.append(profile)
        self._save(profiles)
        logger.info(
            "Created browser session profile (domains=%s, cookies=%d)",
            profile.domains,
            len(profile.cookies),
        )
        return profile.metadata()

    def update(
        self,
        profile_id: str,
        name: Optional[str] = None,
        enabled: Optional[bool] = None,
        persist_updates: Optional[bool] = None,
        parsed: Optional[ParsedSession] = None,
    ) -> Optional[Dict[str, Any]]:
        profiles = self._load()
        profile = next((p for p in profiles if p.id == profile_id), None)
        if profile is None:
            return None
        if name is not None:
            profile.name = self._validate_name(name, profiles, exclude_id=profile.id)
        if enabled is not None:
            profile.enabled = enabled
        if persist_updates is not None:
            profile.persist_updates = persist_updates
        if parsed is not None:
            profile.cookies = parsed.cookies
            profile.origins = parsed.origins
            profile.revision += 1
        profile.updated_at = _now_iso()
        self._save(profiles)
        logger.info("Updated browser session profile (domains=%s)", profile.domains)
        return profile.metadata()

    def delete(self, profile_id: str) -> bool:
        profiles = self._load()
        remaining = [p for p in profiles if p.id != profile_id]
        if len(remaining) == len(profiles):
            return False
        self._save(remaining)
        logger.info("Deleted browser session profile")
        return True

    # -- consumption (these return secrets; callers must not expose them) -----

    def _enabled(self, only_id: Optional[str] = None) -> List[SessionProfile]:
        """Enabled profiles, oldest first; or just ``only_id`` even if disabled."""
        if only_id is not None:
            profiles = [p for p in self._load() if p.id == only_id]
        else:
            profiles = [p for p in self._load() if p.enabled]
        return sorted(profiles, key=lambda p: p.created_at)

    def load_storage_state(
        self, only_id: Optional[str] = None, now: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """Merge enabled profiles into one Playwright ``storage_state``.

        Later profiles win on (name, domain, path) conflicts. Expired cookies
        are dropped. Returns None when there is nothing to inject.
        """
        now_ts = time.time() if now is None else now
        cookies: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        origins: Dict[str, Dict[str, str]] = {}
        for profile in self._enabled(only_id):
            for c in profile.cookies:
                if not _is_expired(c, now_ts):
                    cookies[_cookie_key(c)] = dict(c)
            for o in profile.origins:
                store = origins.setdefault(o["origin"], {})
                for item in o.get("localStorage", []):
                    store[item["name"]] = item["value"]
        if not cookies and not origins:
            return None
        return {
            "cookies": list(cookies.values()),
            "origins": [
                {
                    "origin": origin,
                    "localStorage": [{"name": k, "value": v} for k, v in items.items()],
                }
                for origin, items in origins.items()
            ],
        }

    def snapshot_revisions(self) -> Dict[str, int]:
        """Profile id -> revision, to pass back to ``apply_updates`` later."""
        return {p.id: p.revision for p in self._load()}

    def cookies_for_url(self, url: str, now: Optional[float] = None) -> List[Dict[str, Any]]:
        """Cookies from enabled profiles that apply to ``url`` (RFC 6265 matching)."""
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if parts.scheme not in ("http", "https") or not host:
            return []
        now_ts = time.time() if now is None else now
        matched: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        for profile in self._enabled():
            for c in profile.cookies:
                if _is_expired(c, now_ts):
                    continue
                if c.get("secure") and parts.scheme != "https":
                    continue
                if not _domain_matches(c["domain"], host):
                    continue
                if not _path_matches(c.get("path") or "/", parts.path or "/"):
                    continue
                matched[_cookie_key(c)] = dict(c)
        return list(matched.values())

    def profile_for_url(self, url: str) -> Optional[str]:
        """Name of the profile supplying cookies for ``url`` (non-secret hint)."""
        parts = urlsplit(url or "")
        host = (parts.hostname or "").lower()
        if parts.scheme not in ("http", "https") or not host:
            return None
        names = [
            p.name
            for p in self._enabled()
            if any(_domain_matches(c["domain"], host) for c in p.cookies)
        ]
        return ", ".join(names) if names else None

    # -- write-back ----------------------------------------------------------

    def apply_updates(
        self,
        state: Optional[Dict[str, Any]],
        now: Optional[float] = None,
        expected_revisions: Optional[Dict[str, int]] = None,
    ) -> bool:
        """Persist cookies/localStorage the site rotated during a session.

        Only profiles with ``persist_updates`` are touched. A cookie is routed to
        the profile that supplied it; a *new* cookie is only adopted when exactly
        one persisting profile already covers its domain. New domains are never
        added. Profiles whose revision differs from ``expected_revisions`` (replaced
        or created after the browser session started) are left alone. Returns True
        if anything was written.
        """
        if not state:
            return False
        now_ts = time.time() if now is None else now
        profiles = self._load()
        enabled = sorted((p for p in profiles if p.enabled), key=lambda p: p.created_at)
        if not enabled:
            return False

        def writable(p: SessionProfile) -> bool:
            if not p.persist_updates:
                return False
            return expected_revisions is None or expected_revisions.get(p.id) == p.revision

        # Who supplied each cookie key at load time (later profiles win).
        owner: Dict[Tuple[str, str, str], SessionProfile] = {}
        for p in enabled:
            for c in p.cookies:
                if not _is_expired(c, now_ts):
                    owner[_cookie_key(c)] = p

        new_by_profile: Dict[str, Dict[Tuple[str, str, str], Dict[str, Any]]] = {
            p.id: {} for p in enabled
        }
        seen_keys = set()
        for raw in state.get("cookies", []):
            try:
                exp = raw.get("expires", -1)
                cookie = {
                    "name": raw["name"],
                    "value": str(raw["value"]),
                    "domain": raw["domain"],
                    "path": raw.get("path") or "/",
                    "expires": -1 if exp in (None, -1) else int(exp),
                    "httpOnly": bool(raw.get("httpOnly", False)),
                    "secure": bool(raw.get("secure", False)),
                    "sameSite": raw.get("sameSite") or "Lax",
                }
            except (KeyError, TypeError, ValueError):
                continue
            key = _cookie_key(cookie)
            seen_keys.add(key)
            target = owner.get(key)
            if target is None:
                covering = [
                    p
                    for p in enabled
                    if writable(p)
                    and any(_domain_matches("." + d, _bare(cookie["domain"])) for d in p.domains)
                ]
                if len(covering) != 1:
                    continue
                target = covering[0]
            if writable(target):
                new_by_profile[target.id][key] = cookie

        changed = False
        for p in enabled:
            if not writable(p):
                continue
            updated: List[Dict[str, Any]] = []
            for c in p.cookies:
                key = _cookie_key(c)
                if owner.get(key) is not p:
                    updated.append(c)  # shadowed by another profile; leave untouched
                elif key in new_by_profile[p.id]:
                    updated.append(new_by_profile[p.id].pop(key))
                elif _is_expired(c, now_ts):
                    updated.append(c)
                # else: the site deleted it (logout / revoked) -> drop
            updated.extend(new_by_profile[p.id].values())

            origins = self._merge_origins(p, state.get("origins", []))

            if updated != p.cookies or origins != p.origins:
                p.cookies, p.origins = updated, origins
                p.updated_at = _now_iso()
                changed = True

        if changed:
            self._save(profiles)
            logger.info("Persisted rotated browser session cookies")
        return changed

    @staticmethod
    def _merge_origins(
        profile: SessionProfile, new_origins: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Refresh localStorage for origins the profile already has."""
        fresh = {o.get("origin", "").rstrip("/"): o for o in new_origins if isinstance(o, dict)}
        merged = []
        for o in profile.origins:
            update = fresh.get(o["origin"])
            if update is not None:
                items = [
                    {"name": str(i["name"]), "value": str(i.get("value", ""))}
                    for i in update.get("localStorage", [])
                    if isinstance(i, dict) and "name" in i
                ]
                merged.append({"origin": o["origin"], "localStorage": items})
            else:
                merged.append(o)
        return merged
