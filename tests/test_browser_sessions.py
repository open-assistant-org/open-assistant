"""Tests for authenticated browser sessions (parser + encrypted store)."""

import json

import pytest

from src.core.encryption import EncryptionService
from src.core.repositories.credentials import CredentialsRepository
from src.integrations.browser.sessions import (
    SERVICE_NAME,
    BrowserSessionStore,
    ParsedSession,
    SessionParseError,
    parse_session_export,
)

NOW = 1_800_000_000  # fixed "current time" for deterministic expiry checks
FUTURE = NOW + 86_400 * 30
SECRET = "s3cr3t-cookie-value-XYZ"


def _by_name(parsed: ParsedSession, name: str) -> dict:
    return next(c for c in parsed.cookies if c["name"] == name)


# ----------------------------------------------------------------------------
# Parser
# ----------------------------------------------------------------------------


class TestParsePlaywright:
    def test_storage_state_with_origins(self):
        raw = json.dumps(
            {
                "cookies": [
                    {
                        "name": "sid",
                        "value": SECRET,
                        "domain": ".example.com",
                        "path": "/",
                        "expires": FUTURE,
                        "httpOnly": True,
                        "secure": True,
                        "sameSite": "Lax",
                    }
                ],
                "origins": [
                    {
                        "origin": "https://example.com/",
                        "localStorage": [{"name": "t", "value": "1"}],
                    }
                ],
            }
        )
        parsed = parse_session_export(raw, now=NOW)
        assert parsed.cookies[0]["domain"] == ".example.com"
        assert parsed.cookies[0]["httpOnly"] is True
        assert parsed.origins == [
            {"origin": "https://example.com", "localStorage": [{"name": "t", "value": "1"}]}
        ]

    def test_invalid_origin_scheme_skipped(self):
        raw = json.dumps(
            {
                "cookies": [{"name": "a", "value": "b", "domain": "example.com"}],
                "origins": [
                    {"origin": "javascript:alert(1)", "localStorage": [{"name": "x", "value": "y"}]}
                ],
            }
        )
        parsed = parse_session_export(raw, now=NOW)
        assert parsed.origins == []
        assert any("origin" in w for w in parsed.warnings)


class TestParseCookieEditor:
    def test_field_mapping(self):
        raw = json.dumps(
            [
                {
                    "name": "a",
                    "value": "1",
                    "domain": ".example.com",
                    "hostOnly": False,
                    "path": "/",
                    "secure": True,
                    "httpOnly": True,
                    "sameSite": "no_restriction",
                    "session": False,
                    "expirationDate": FUTURE + 0.5,
                },
                {
                    "name": "b",
                    "value": "2",
                    "domain": "example.com",
                    "hostOnly": True,
                    "path": "/",
                    "secure": False,
                    "sameSite": "unspecified",
                    "session": True,
                },
                {
                    "name": "c",
                    "value": "3",
                    "domain": "example.com",
                    "hostOnly": False,
                    "sameSite": "strict",
                },
            ]
        )
        parsed = parse_session_export(raw, now=NOW)
        a, b, c = (_by_name(parsed, n) for n in "abc")
        assert a["sameSite"] == "None" and a["expires"] == FUTURE
        assert b["domain"] == "example.com" and b["expires"] == -1 and b["sameSite"] == "Lax"
        assert c["domain"] == ".example.com" and c["sameSite"] == "Strict"

    def test_millisecond_expiry_is_converted(self):
        raw = json.dumps(
            [{"name": "a", "value": "1", "domain": "example.com", "expirationDate": FUTURE * 1000}]
        )
        assert parse_session_export(raw, now=NOW).cookies[0]["expires"] == FUTURE

    def test_expired_cookies_dropped_and_reported(self):
        raw = json.dumps(
            [
                {"name": "old", "value": "1", "domain": "example.com", "expirationDate": NOW - 10},
                {"name": "new", "value": "2", "domain": "example.com", "expirationDate": FUTURE},
            ]
        )
        parsed = parse_session_export(raw, now=NOW)
        assert [c["name"] for c in parsed.cookies] == ["new"]
        assert any("expired" in w for w in parsed.warnings)

    def test_all_expired_is_an_error(self):
        raw = json.dumps(
            [{"name": "old", "value": "1", "domain": "example.com", "expirationDate": NOW - 10}]
        )
        with pytest.raises(SessionParseError, match="No usable cookies"):
            parse_session_export(raw, now=NOW)


class TestChromiumFixups:
    def _parse(self, cookie: dict) -> ParsedSession:
        return parse_session_export(json.dumps([cookie]), now=NOW)

    def test_samesite_none_forces_secure(self):
        parsed = self._parse(
            {
                "name": "a",
                "value": "1",
                "domain": "example.com",
                "secure": False,
                "sameSite": "None",
            }
        )
        assert parsed.cookies[0]["secure"] is True
        assert any("SameSite=None" in w for w in parsed.warnings)

    def test_host_prefix_becomes_host_only(self):
        parsed = self._parse(
            {
                "name": "__Host-sid",
                "value": "1",
                "domain": ".example.com",
                "path": "/app",
                "secure": False,
                "hostOnly": False,
            }
        )
        c = parsed.cookies[0]
        assert (c["domain"], c["path"], c["secure"]) == ("example.com", "/", True)

    def test_secure_prefix_forces_secure(self):
        parsed = self._parse({"name": "__Secure-x", "value": "1", "domain": "example.com"})
        assert parsed.cookies[0]["secure"] is True

    def test_ip_and_localhost_stay_host_only(self):
        parsed = parse_session_export(
            json.dumps(
                [
                    {"name": "a", "value": "1", "domain": "127.0.0.1", "hostOnly": False},
                    {"name": "b", "value": "1", "domain": "localhost", "hostOnly": False},
                ]
            ),
            now=NOW,
        )
        assert [c["domain"] for c in parsed.cookies] == ["127.0.0.1", "localhost"]

    def test_malformed_entries_skipped(self):
        parsed = parse_session_export(
            json.dumps(
                [{"name": "ok", "value": "1", "domain": "example.com"}, "nope", {"name": "x"}]
            ),
            now=NOW,
        )
        assert [c["name"] for c in parsed.cookies] == ["ok"]
        assert any("malformed" in w for w in parsed.warnings)

    def test_duplicates_keep_first(self):
        parsed = parse_session_export(
            json.dumps(
                [
                    {"name": "a", "value": "first", "domain": "example.com"},
                    {"name": "a", "value": "second", "domain": "example.com"},
                ]
            ),
            now=NOW,
        )
        assert len(parsed.cookies) == 1 and parsed.cookies[0]["value"] == "first"


class TestParseNetscape:
    def test_cookies_txt(self):
        raw = (
            "# Netscape HTTP Cookie File\n"
            f".example.com\tTRUE\t/\tTRUE\t{FUTURE}\tsid\t{SECRET}\n"
            "#HttpOnly_www.example.com\tFALSE\t/app\tFALSE\t0\ttok\tabc\n"
            "# a comment\n"
        )
        parsed = parse_session_export(raw, now=NOW)
        sid, tok = _by_name(parsed, "sid"), _by_name(parsed, "tok")
        assert (
            sid["domain"] == ".example.com" and sid["secure"] is True and sid["expires"] == FUTURE
        )
        assert tok["domain"] == "www.example.com" and tok["httpOnly"] is True
        assert tok["expires"] == -1 and tok["path"] == "/app"

    def test_space_separated_lines_tolerated(self):
        raw = f".example.com TRUE / FALSE {FUTURE} sid abc"
        # Single line without tabs is ambiguous with a header; force the format.
        parsed = parse_session_export(raw, fmt="netscape", now=NOW)
        assert parsed.cookies[0]["name"] == "sid"


class TestParseHeader:
    def test_header_requires_domain(self):
        with pytest.raises(SessionParseError, match="domain is required"):
            parse_session_export("a=1; b=2")

    def test_header_with_prefix_and_domain(self):
        parsed = parse_session_export("Cookie: a=1; b=2=3", domain="example.com", now=NOW)
        assert {c["name"]: c["value"] for c in parsed.cookies} == {"a": "1", "b": "2=3"}
        assert all(c["secure"] and c["expires"] == -1 for c in parsed.cookies)


class TestParseErrors:
    @pytest.mark.parametrize("raw", ["", "   \n  "])
    def test_empty(self, raw):
        with pytest.raises(SessionParseError, match="empty"):
            parse_session_export(raw)

    def test_garbage(self):
        with pytest.raises(SessionParseError, match="detect"):
            parse_session_export("hello world\nthis is not cookies")

    def test_bad_json(self):
        with pytest.raises(SessionParseError, match="Invalid JSON"):
            parse_session_export("[{not json")

    def test_unknown_format(self):
        with pytest.raises(SessionParseError, match="Unknown format"):
            parse_session_export("a=1", fmt="xml")

    def test_error_messages_never_leak_values(self):
        raw = json.dumps([{"name": "x", "value": SECRET}])  # missing domain
        with pytest.raises(SessionParseError) as exc:
            parse_session_export(raw)
        assert SECRET not in str(exc.value)

    def test_oversized_payload(self):
        with pytest.raises(SessionParseError, match="larger"):
            parse_session_export("a" * 2_100_000)


# ----------------------------------------------------------------------------
# Store
# ----------------------------------------------------------------------------


@pytest.fixture
def store(clean_temp_db, test_encryption_key) -> BrowserSessionStore:
    repo = CredentialsRepository(clean_temp_db, EncryptionService(test_encryption_key))
    return BrowserSessionStore(repo)


def _parsed(*cookies: dict, origins=None) -> ParsedSession:
    return parse_session_export(
        json.dumps({"cookies": list(cookies), "origins": origins or []}), now=NOW
    )


def _cookie(name="sid", value=SECRET, domain=".example.com", **kw) -> dict:
    base = {
        "name": name,
        "value": value,
        "domain": domain,
        "path": "/",
        "expires": FUTURE,
        "secure": True,
        "httpOnly": True,
        "sameSite": "Lax",
    }
    base.update(kw)
    return base


class TestStoreCrud:
    def test_create_list_roundtrip_is_encrypted(self, store):
        meta = store.create("Personal", _parsed(_cookie()))
        assert meta["cookie_count"] == 1 and meta["domains"] == ["example.com"]

        raw_row = store.credentials_repo.fetch_one(
            "SELECT credential_data FROM service_credentials WHERE service_name = ?",
            (SERVICE_NAME,),
        )
        assert SECRET not in raw_row["credential_data"]  # ciphertext only
        assert store.list_metadata()[0]["id"] == meta["id"]

    def test_metadata_never_contains_values_or_names(self, store):
        store.create("Personal", _parsed(_cookie()))
        dumped = json.dumps(store.list_metadata())
        assert (
            SECRET not in dumped
            and '"sid"' not in dumped
            and "cookies" not in dumped.replace("cookie_count", "")
        )

    def test_name_validation(self, store):
        store.create("Personal", _parsed(_cookie()))
        with pytest.raises(ValueError, match="already exists"):
            store.create("personal", _parsed(_cookie(name="b")))
        with pytest.raises(ValueError, match="required"):
            store.create("  ", _parsed(_cookie()))
        with pytest.raises(ValueError, match="at most"):
            store.create("x" * 65, _parsed(_cookie()))

    def test_update_flags_rename_and_replace(self, store):
        pid = store.create("Personal", _parsed(_cookie()))["id"]
        meta = store.update(pid, name="Work", enabled=False, persist_updates=False)
        assert (meta["name"], meta["enabled"], meta["persist_updates"]) == ("Work", False, False)
        meta = store.update(pid, parsed=_parsed(_cookie("a"), _cookie("b")))
        assert meta["cookie_count"] == 2
        assert store.update("missing", name="x") is None

    def test_delete_removes_row_when_last(self, store):
        pid = store.create("Personal", _parsed(_cookie()))["id"]
        first = store.delete(pid)
        second = store.delete(pid)
        assert first is True
        assert second is False
        assert store.credentials_repo.get(SERVICE_NAME) is None


class TestLoadStorageState:
    def test_none_when_empty(self, store):
        assert store.load_storage_state() is None

    def test_only_enabled_profiles_and_expired_dropped(self, store):
        store.create("A", _parsed(_cookie("a"), _cookie("old", expires=NOW - 5)))
        b = store.create("B", _parsed(_cookie("b", domain="other.com")))["id"]
        store.update(b, enabled=False)
        state = store.load_storage_state(now=NOW)
        assert [c["name"] for c in state["cookies"]] == ["a"]

    def test_later_profile_wins_on_conflict_and_origins_merge(self, store):
        store.create(
            "A",
            _parsed(
                _cookie("sid", "from-a"),
                origins=[
                    {"origin": "https://example.com", "localStorage": [{"name": "k", "value": "a"}]}
                ],
            ),
        )
        store.create(
            "B",
            _parsed(
                _cookie("sid", "from-b"),
                origins=[
                    {
                        "origin": "https://example.com",
                        "localStorage": [{"name": "k2", "value": "b"}],
                    }
                ],
            ),
        )
        state = store.load_storage_state(now=NOW)
        assert [c["value"] for c in state["cookies"]] == ["from-b"]
        assert {i["name"] for i in state["origins"][0]["localStorage"]} == {"k", "k2"}

    def test_only_id_loads_disabled_profile(self, store):
        pid = store.create("A", _parsed(_cookie()))["id"]
        store.update(pid, enabled=False)
        assert store.load_storage_state(now=NOW) is None
        assert store.load_storage_state(only_id=pid, now=NOW) is not None


class TestUrlMatching:
    def test_domain_path_and_secure(self, store):
        store.create(
            "A",
            _parsed(
                _cookie("dom", domain=".example.com"),
                _cookie("host", domain="www.example.com"),
                _cookie("scoped", path="/app"),
                _cookie("insecure", secure=False),
            ),
        )

        def names(url):
            return sorted(c["name"] for c in store.cookies_for_url(url, now=NOW))

        assert names("https://www.example.com/") == ["dom", "host", "insecure"]
        assert names("https://api.example.com/") == ["dom", "insecure"]
        assert names("https://www.example.com/app/x") == ["dom", "host", "insecure", "scoped"]
        assert names("https://www.example.com/application") == ["dom", "host", "insecure"]
        assert names("http://www.example.com/") == ["insecure"]  # secure cookies not sent over http
        assert names("https://notexample.com/") == []
        assert names("javascript:alert(1)") == []
        assert names("file:///etc/passwd") == []

    def test_profile_for_url_returns_names_only(self, store):
        store.create("Personal Gmail", _parsed(_cookie(domain=".example.com")))
        assert store.profile_for_url("https://www.example.com/x") == "Personal Gmail"
        assert store.profile_for_url("https://other.org/") is None
        assert store.profile_for_url("not a url") is None


def _state(*cookies: dict, origins=None) -> dict:
    return {"cookies": list(cookies), "origins": origins or []}


class TestApplyUpdates:
    def test_rotated_value_is_persisted(self, store):
        pid = store.create("A", _parsed(_cookie("sid", "old")))["id"]
        assert store.apply_updates(_state(_cookie("sid", "rotated")), now=NOW) is True
        cookies = store.load_storage_state(now=NOW)["cookies"]
        assert cookies[0]["value"] == "rotated"
        assert store.get_metadata(pid)["cookie_count"] == 1

    def test_no_change_means_no_write(self, store):
        store.create("A", _parsed(_cookie("sid", "v")))
        before = store.list_metadata()[0]["updated_at"]
        # Playwright reports float expiry; must not look like a change.
        assert (
            store.apply_updates(_state(_cookie("sid", "v", expires=float(FUTURE))), now=NOW)
            is False
        )
        assert store.list_metadata()[0]["updated_at"] == before

    def test_new_domains_are_never_added(self, store):
        store.create("A", _parsed(_cookie("sid")))
        store.apply_updates(_state(_cookie("sid"), _cookie("tracker", domain=".ads.net")), now=NOW)
        assert store.list_metadata()[0]["domains"] == ["example.com"]

    def test_new_cookie_on_existing_domain_is_adopted(self, store):
        store.create("A", _parsed(_cookie("sid")))
        store.apply_updates(
            _state(_cookie("sid"), _cookie("fresh", domain="www.example.com")), now=NOW
        )
        assert store.list_metadata()[0]["cookie_count"] == 2

    def test_site_deleted_cookie_is_dropped(self, store):
        store.create("A", _parsed(_cookie("sid"), _cookie("other")))
        store.apply_updates(_state(_cookie("other")), now=NOW)
        names = [c["name"] for c in store.load_storage_state(now=NOW)["cookies"]]
        assert names == ["other"]

    def test_persist_updates_false_is_read_only(self, store):
        pid = store.create("A", _parsed(_cookie("sid", "old")), persist_updates=False)["id"]
        assert store.apply_updates(_state(_cookie("sid", "rotated")), now=NOW) is False
        assert store.load_storage_state(only_id=pid, now=NOW)["cookies"][0]["value"] == "old"

    def test_update_routed_to_owning_profile_only(self, store):
        store.create("A", _parsed(_cookie("a", "a-old")))
        store.create("B", _parsed(_cookie("b", "b-old", domain=".other.com")))
        store.apply_updates(
            _state(_cookie("a", "a-new"), _cookie("b", "b-old", domain=".other.com")), now=NOW
        )
        values = {c["name"]: c["value"] for c in store.load_storage_state(now=NOW)["cookies"]}
        assert values == {"a": "a-new", "b": "b-old"}

    def test_ambiguous_new_cookie_is_not_adopted(self, store):
        store.create("A", _parsed(_cookie("a")))
        store.create("B", _parsed(_cookie("b")))  # both cover example.com
        store.apply_updates(_state(_cookie("a"), _cookie("b"), _cookie("new")), now=NOW)
        assert sum(m["cookie_count"] for m in store.list_metadata()) == 2

    def test_local_storage_refreshed_for_known_origins_only(self, store):
        store.create(
            "A",
            _parsed(
                _cookie("sid"),
                origins=[
                    {
                        "origin": "https://example.com",
                        "localStorage": [{"name": "k", "value": "old"}],
                    }
                ],
            ),
        )
        store.apply_updates(
            _state(
                _cookie("sid"),
                origins=[
                    {
                        "origin": "https://example.com",
                        "localStorage": [{"name": "k", "value": "new"}],
                    },
                    {"origin": "https://evil.com", "localStorage": [{"name": "x", "value": "y"}]},
                ],
            ),
            now=NOW,
        )
        origins = store.load_storage_state(now=NOW)["origins"]
        assert origins == [
            {"origin": "https://example.com", "localStorage": [{"name": "k", "value": "new"}]}
        ]

    def test_replaced_profile_is_skipped_via_expected_revisions(self, store):
        pid = store.create("A", _parsed(_cookie("sid", "old")))["id"]
        snapshot = store.snapshot_revisions()
        assert snapshot == {pid: 0}

        # User re-imports while an older browser session (snapshot) is still open.
        store.update(pid, parsed=_parsed(_cookie("sid", "fresh")))
        assert store.snapshot_revisions() == {pid: 1}

        wrote = store.apply_updates(
            _state(_cookie("sid", "stale-rotation")), now=NOW, expected_revisions=snapshot
        )
        assert wrote is False
        assert store.load_storage_state(now=NOW)["cookies"][0]["value"] == "fresh"

    def test_matching_revision_still_writes(self, store):
        store.create("A", _parsed(_cookie("sid", "old")))
        snapshot = store.snapshot_revisions()
        assert store.apply_updates(
            _state(_cookie("sid", "rotated")), now=NOW, expected_revisions=snapshot
        )
        assert store.load_storage_state(now=NOW)["cookies"][0]["value"] == "rotated"

    def test_toggling_flags_does_not_invalidate_a_running_session(self, store):
        pid = store.create("A", _parsed(_cookie("sid", "old")))["id"]
        snapshot = store.snapshot_revisions()
        store.update(pid, name="Renamed", persist_updates=True)  # not a cookie replacement
        assert store.apply_updates(
            _state(_cookie("sid", "rotated")), now=NOW, expected_revisions=snapshot
        )

    def test_profile_created_after_snapshot_is_not_written(self, store):
        store.create("A", _parsed(_cookie("a", "a-old")))
        snapshot = store.snapshot_revisions()
        store.create("B", _parsed(_cookie("b", "b-old", domain=".other.com")))
        store.apply_updates(
            _state(_cookie("a", "a-new"), _cookie("b", "tampered", domain=".other.com")),
            now=NOW,
            expected_revisions=snapshot,
        )
        values = {c["name"]: c["value"] for c in store.load_storage_state(now=NOW)["cookies"]}
        assert values == {"a": "a-new", "b": "b-old"}

    def test_none_state_is_noop(self, store):
        store.create("A", _parsed(_cookie()))
        assert store.apply_updates(None) is False
