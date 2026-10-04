"""Shared routing for incoming Slack message events in multi-participant threads.

Both Slack entry points (Socket Mode and the Events API webhook) decide here
whether an incoming message is ignored, passively ingested as thread context,
or answered. The decision covers:

* telling Open Assistant's own posts apart from other bots' posts, so other
  agents in a thread are recorded instead of being dropped wholesale;
* the human allow-list (``slack.allowed_user_ids``) for humans and the
  separate bot allow-list (``slack.allowed_bot_ids``) for bot-triggered
  replies;
* a per-conversation cap on consecutive bot-triggered replies, so two agents
  that @mention each other cannot loop forever.

It also labels messages with their speaker (``[Mike]: ...``) so the model can
tell participants apart in a shared thread.
"""

import re
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional, Tuple

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Subtypes worth looking at: plain text, file uploads, and messages posted by
# legacy bots / incoming webhooks (which carry ``subtype == "bot_message"``).
ACCEPTED_SUBTYPES = {None, "file_share", "bot_message"}

# Bot-triggered replies allowed in one conversation before a human posts again.
SLACK_MAX_CONSECUTIVE_BOT_REPLIES = 3

# How long a resolved display name is cached.
_NAME_CACHE_TTL_SECONDS = 60 * 60

_MENTION_RE = re.compile(r"<@([UW][A-Z0-9]+)(?:\|[^>]*)?>")


class Action(str, Enum):
    IGNORE = "ignore"
    INGEST = "ingest"
    REPLY = "reply"


@dataclass(frozen=True)
class SlackSender:
    """Who posted a Slack message event."""

    id: str
    is_bot: bool
    bot_id: Optional[str] = None
    name_hint: Optional[str] = None


@dataclass(frozen=True)
class Route:
    """What to do with an incoming Slack message event."""

    action: Action
    reason: str
    sender: Optional[SlackSender] = None
    # Message text with Open Assistant's own @mention removed (for replies).
    text: str = ""


def sender_from_event(event: Dict[str, Any]) -> SlackSender:
    """Build the sender of a message event.

    Messages posted by apps carry a ``bot_id``; ``bot_message`` events from
    legacy bots and webhooks may have no ``user`` at all, in which case the
    ``bot_id`` identifies the sender.
    """
    bot_id = event.get("bot_id") or None
    is_bot = bool(bot_id) or event.get("subtype") == "bot_message"
    profile = event.get("bot_profile") or {}
    name_hint = profile.get("name") or event.get("username") or None
    return SlackSender(
        id=event.get("user") or bot_id or "",
        is_bot=is_bot,
        bot_id=bot_id,
        name_hint=name_hint if is_bot else None,
    )


def is_own_message(
    event: Dict[str, Any], own_user_id: Optional[str], own_bot_id: Optional[str]
) -> bool:
    """True when the event was posted by this Open Assistant bot."""
    if own_user_id and event.get("user") == own_user_id:
        return True
    if own_bot_id and event.get("bot_id") == own_bot_id:
        return True
    return False


def parse_id_list(value: Optional[str]) -> set:
    """Parse a comma-separated ID list setting."""
    return {part.strip() for part in (value or "").split(",") if part.strip()}


def bot_in_allowlist(sender: SlackSender, allowed_ids: set) -> bool:
    """A bot matches the allow-list by its user ID (U…) or its bot ID (B…)."""
    return bool(allowed_ids) and (sender.id in allowed_ids or sender.bot_id in allowed_ids)


class BotReplyGuard:
    """Caps consecutive bot-triggered replies per conversation.

    Any human message in the conversation resets the count.
    """

    def __init__(self, max_consecutive: int = SLACK_MAX_CONSECUTIVE_BOT_REPLIES):
        self.max_consecutive = max_consecutive
        self._counts: Dict[str, int] = {}
        self._lock = threading.Lock()

    def try_acquire(self, key: str) -> bool:
        """Reserve one bot-triggered reply for ``key`` if under the cap."""
        with self._lock:
            count = self._counts.get(key, 0)
            if count >= self.max_consecutive:
                return False
            self._counts[key] = count + 1
            return True

    def reset(self, key: str) -> None:
        with self._lock:
            self._counts.pop(key, None)


bot_reply_guard = BotReplyGuard()


def route_message_event(
    event: Dict[str, Any],
    *,
    has_files: bool,
    own_user_id: Optional[str],
    own_bot_id: Optional[str],
    mention_only: bool,
    ingest_all: bool,
    reply_to_bots: bool,
    thread_scoped: bool,
    conversation_key: str,
    is_user_allowed: Callable[[str], bool],
    is_bot_allowed: Callable[[SlackSender], bool],
    guard: BotReplyGuard = bot_reply_guard,
) -> Route:
    """Decide whether a Slack message event is ignored, ingested or answered.

    Args:
        event: The Slack ``message`` event payload.
        has_files: Whether the event carries downloadable files.
        own_user_id / own_bot_id: This bot's identity (from ``auth.test``).
        mention_only: "Reply Only on Mention".
        ingest_all: "Ingest All Thread Messages" (only meaningful with mention_only).
        reply_to_bots: "Reply to Bots & Mention Participants".
        thread_scoped: Whether the conversation is scoped to a Slack thread.
        conversation_key: The conversation's contact identifier (loop-guard key).
        is_user_allowed: Human allow-list check.
        is_bot_allowed: Bot allow-list check.
        guard: Consecutive bot-reply guard.
    """
    if event.get("type") != "message":
        return Route(Action.IGNORE, "not a message event")

    subtype = event.get("subtype")
    if subtype not in ACCEPTED_SUBTYPES:
        return Route(Action.IGNORE, f"subtype {subtype}")

    sender = sender_from_event(event)
    text = event.get("text") or ""

    if sender.is_bot:
        # Without "Reply Only on Mention" every message would get a reply,
        # so bots stay ignored there to rule out reply loops.
        if not mention_only:
            return Route(Action.IGNORE, "bot message without mention-only mode", sender)
        if not own_user_id and not own_bot_id:
            # Without our own identity we cannot tell our posts from others'.
            return Route(Action.IGNORE, "bot message but own identity unknown", sender)
        if is_own_message(event, own_user_id, own_bot_id):
            return Route(Action.IGNORE, "own message", sender)

    if not text.strip() and not has_files:
        return Route(Action.IGNORE, "empty message", sender)

    if not sender.is_bot:
        if not is_user_allowed(sender.id):
            return Route(Action.IGNORE, "user not allowed", sender)
        guard.reset(conversation_key)

    if not mention_only:
        return Route(Action.REPLY, "message", sender, text)

    mention_token = f"<@{own_user_id}>" if own_user_id else None
    is_mention = bool(mention_token and mention_token in text)
    can_ingest = ingest_all and thread_scoped and bool(text.strip())

    if is_mention:
        stripped = text.replace(mention_token, "").strip()
        if not sender.is_bot:
            return Route(Action.REPLY, "mention", sender, stripped)
        if not reply_to_bots:
            reason = "bot mention but replying to bots is off"
        elif not is_bot_allowed(sender):
            reason = "bot mention from a bot not in allowed_bot_ids"
        elif not guard.try_acquire(conversation_key):
            reason = "bot mention but consecutive bot reply cap reached"
        else:
            return Route(Action.REPLY, "bot mention", sender, stripped)
        if can_ingest:
            return Route(Action.INGEST, reason, sender)
        return Route(Action.IGNORE, reason, sender)

    if can_ingest:
        return Route(Action.INGEST, "non-mention thread message", sender)
    return Route(Action.IGNORE, "non-mention message", sender)


# ---------------------------------------------------------------------------
# Speaker labels
# ---------------------------------------------------------------------------

_name_cache: Dict[str, Tuple[str, float]] = {}
_name_cache_lock = threading.Lock()


def _name_from_user_info(info: Any) -> Optional[str]:
    if not isinstance(info, dict):
        return None
    for key in ("display_name", "real_name", "name"):
        value = info.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def resolve_name(user_id: str, lookup: Callable[[str], Any]) -> str:
    """Resolve a Slack user ID to a display name, falling back to the ID.

    ``lookup`` returns a user-info dict (``display_name`` / ``real_name`` /
    ``name``). Results are cached; lookup failures fall back to the raw ID.
    """
    now = time.monotonic()
    with _name_cache_lock:
        cached = _name_cache.get(user_id)
        if cached and cached[1] > now:
            return cached[0]

    try:
        name = _name_from_user_info(lookup(user_id))
    except Exception as e:
        logger.debug(f"[Slack] Could not resolve name for {user_id}: {e}")
        name = None

    if not name:
        return user_id

    with _name_cache_lock:
        _name_cache[user_id] = (name, now + _NAME_CACHE_TTL_SECONDS)
    return name


def _is_mentionable(slack_id: str) -> bool:
    return slack_id[:1] in ("U", "W")


def _label(name: str, slack_id: str, include_ids: bool) -> str:
    if include_ids and _is_mentionable(slack_id) and name != slack_id:
        return f"{name} <@{slack_id}>"
    if include_ids and _is_mentionable(slack_id):
        return f"<@{slack_id}>"
    return name


def format_with_speaker(
    text: str,
    sender: SlackSender,
    lookup: Callable[[str], Any],
    include_ids: bool,
) -> str:
    """Prefix ``text`` with its speaker and annotate inline @mentions.

    ``[Mike]: hi @Steven`` — or, with ``include_ids``, ``[Mike <@U0MIKE>]: hi
    @Steven (<@U0STEVEN>)`` so the model can @mention participants back.
    """
    if sender.is_bot and sender.name_hint:
        speaker = sender.name_hint
    elif sender.id and _is_mentionable(sender.id):
        speaker = resolve_name(sender.id, lookup)
    else:
        speaker = sender.id or "unknown"

    def _annotate(match: "re.Match[str]") -> str:
        user_id = match.group(1)
        name = resolve_name(user_id, lookup)
        if name == user_id:
            return match.group(0)
        if include_ids:
            return f"@{name} (<@{user_id}>)"
        return f"@{name}"

    body = _MENTION_RE.sub(_annotate, text)
    return f"[{_label(speaker, sender.id, include_ids)}]: {body}"


def clear_name_cache() -> None:
    """Clear cached display names (used by tests)."""
    with _name_cache_lock:
        _name_cache.clear()
