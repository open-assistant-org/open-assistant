"""Convert the Markdown that LLMs write into Slack's mrkdwn flavour.

Slack doesn't render standard Markdown: ``**bold**`` shows literal asterisks,
``# Heading`` shows a hash, ``[text](url)`` isn't a link. This rewrites the
common constructs into their mrkdwn equivalents and leaves code untouched.
"""

import re

_CODE = re.compile(r"```.*?```|`[^`\n]+`", re.DOTALL)
_FENCE_LANG = re.compile(r"^```[\w+-]*\n")
_STASHED = re.compile("\x00(\\d+)\x00")

_HEADING = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t#]*$", re.MULTILINE)
_BULLET = re.compile(r"^([ \t]*)[*+-][ \t]+", re.MULTILINE)
_RULE = re.compile(r"^[ \t]*([-*_])([ \t]*\1){2,}[ \t]*$", re.MULTILINE)
_LINK = re.compile(r"!?\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_ITALIC = re.compile(r"(?<![*\w])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![*\w])")
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_STRIKE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")


def markdown_to_mrkdwn(text: str) -> str:
    """Rewrite Markdown as Slack mrkdwn. Slack mentions and ``<url|text>`` links pass through."""
    if not text:
        return text

    # Set code and tables aside so the inline rules below can't touch them.
    stash: list[str] = []

    def keep(block: str) -> str:
        stash.append(block)
        return f"\x00{len(stash) - 1}\x00"

    text = _CODE.sub(lambda m: keep(_FENCE_LANG.sub("```\n", m.group(0))), text)
    text = _wrap_tables(text, keep)

    text = _RULE.sub("──────────", text)
    text = _HEADING.sub(lambda m: f"**{m.group(1).replace('**', '')}**", text)
    text = _BULLET.sub(r"\1• ", text)
    text = _LINK.sub(lambda m: f"<{m.group(2)}|{m.group(1) or m.group(2)}>", text)
    text = _ITALIC.sub(r"_\1_", text)  # before bold, so **x** isn't read as italic
    text = _BOLD.sub(r"*\1*", text)
    text = _STRIKE.sub(r"~\1~", text)

    return _STASHED.sub(lambda m: stash[int(m.group(1))], text)


def _wrap_tables(text: str, keep) -> str:
    """Put Markdown tables in a code block; Slack has no tables, but this keeps columns aligned."""
    out: list[str] = []
    table: list[str] = []
    for line in text.split("\n") + [""]:
        if line.lstrip().startswith("|"):
            table.append(line)
            continue
        if table:
            out.append(keep("```\n" + "\n".join(table) + "\n```"))
            table = []
        out.append(line)
    return "\n".join(out[:-1])
