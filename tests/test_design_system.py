"""Guards for the web UI design system (src/ui/static, docs/design-system.md).

These are static checks over the CSS, HTML and JS sources. They keep the
rules in docs/design-system.md true without anyone having to remember
them: semantic tokens only, no inline styles, no retired class or token
names, and every hand-kept copy of a token value in sync with tokens.css.
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ui" / "static"
CSS_DIR = STATIC / "css"
TOKENS = CSS_DIR / "tokens.css"

CSS_FILES = sorted(CSS_DIR.rglob("*.css"))
NON_TOKEN_CSS = [p for p in CSS_FILES if p != TOKENS]
# Application markup: every page plus every hand-written script.
# (Vendored, minified libraries are excluded.)
HTML_FILES = sorted(STATIC.glob("*.html"))
JS_FILES = sorted(p for p in (STATIC / "js").glob("*.js") if ".min." not in p.name)
MARKUP_FILES = HTML_FILES + JS_FILES

PRIMITIVE_PREFIXES = ("--gray-", "--green-", "--orange-", "--red-")


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def declarations(css: str):
    """Yield (property, value) for every declaration in a stylesheet."""
    body = strip_comments(css)
    # Drop selectors/at-rule preludes: keep only text inside braces.
    for block in re.findall(r"\{([^{}]*)\}", body):
        for decl in block.split(";"):
            if ":" not in decl:
                continue
            prop, _, value = decl.partition(":")
            prop = prop.strip()
            if re.fullmatch(r"-{0,2}[a-zA-Z][\w-]*", prop):
                yield prop, value.strip()


def block_body(css: str, selector_regex: str) -> str:
    """Return the body of the first rule whose selector matches exactly."""
    match = re.search(selector_regex + r"\s*\{", css)
    assert match, f"selector {selector_regex!r} not found"
    depth, i = 1, match.end()
    start = i
    while depth:
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
        i += 1
    return css[start : i - 1]


def custom_props(body: str) -> dict:
    return {
        name: value.strip()
        for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", strip_comments(body))
    }


TOKENS_CSS = read(TOKENS)
LIGHT = custom_props(block_body(TOKENS_CSS, r"(?m)^:root"))
DARK = custom_props(block_body(TOKENS_CSS, r':root\[data-theme="dark"\]'))


def resolve(value: str, scope: dict, depth: int = 0) -> str:
    """Resolve var() chains in a token value (fallbacks included)."""
    assert depth < 20, f"var() cycle while resolving {value!r}"

    def replace(match):
        name, fallback = match.group(1), match.group(2)
        if name in scope:
            return resolve(scope[name], scope, depth + 1)
        if fallback is not None:
            return resolve(fallback.strip(), scope, depth + 1)
        return match.group(0)

    return re.sub(r"var\((--[\w-]+)(?:,\s*([^()]*(?:\([^()]*\))?[^()]*))?\)", replace, value)


# --------------------------------------------------------------------------
# Tokens are the only source of raw values
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", NON_TOKEN_CSS, ids=rel)
def test_no_raw_colours_outside_tokens(path):
    offenders = [
        f"{prop}: {value}"
        for prop, value in declarations(read(path))
        if re.search(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab)\(", value)
    ]
    assert not offenders, f"{rel(path)} uses raw colours; add a token instead: {offenders}"


@pytest.mark.parametrize("path", NON_TOKEN_CSS + MARKUP_FILES, ids=rel)
def test_no_primitive_tokens_outside_tokens(path):
    used = set(re.findall(r"var\((--[\w-]+)", read(path)))
    primitives = sorted(n for n in used if n.startswith(PRIMITIVE_PREFIXES))
    assert not primitives, f"{rel(path)} uses palette primitives directly: {primitives}"


def test_every_referenced_token_is_defined():
    defined = set()
    for path in CSS_FILES + MARKUP_FILES:
        defined |= set(re.findall(r"(--[\w-]+)\s*:", read(path)))
    # Optional, installation-defined hooks (see "Adding a brand accent").
    optional = {"--brand", "--brand-contrast", "--brand-dark", "--brand-dark-contrast"}
    missing = {}
    for path in CSS_FILES + MARKUP_FILES:
        for name in re.findall(r"var\((--[\w-]+)", read(path)):
            if name not in defined and name not in optional:
                missing.setdefault(name, rel(path))
    assert not missing, f"var() references with no definition (typo?): {missing}"


@pytest.mark.parametrize("path", NON_TOKEN_CSS, ids=rel)
def test_font_sizes_use_the_type_scale(path):
    # Relative units (em, %) are fine for prose inside a component.
    offenders = [
        value
        for prop, value in declarations(read(path))
        if prop == "font-size"
        and not re.fullmatch(r"var\(--text-[\w-]+\)|inherit|[\d.]+(em|%)|1em", value)
    ]
    assert not offenders, f"{rel(path)} has off-scale font sizes: {offenders}"


@pytest.mark.parametrize("path", NON_TOKEN_CSS, ids=rel)
def test_z_index_uses_layer_tokens(path):
    # Small integers are allowed for stacking inside one component.
    offenders = [
        value
        for prop, value in declarations(read(path))
        if prop == "z-index" and not re.fullmatch(r"var\(--z-[\w-]+\)|-?\d", value)
    ]
    assert not offenders, f"{rel(path)}: use a --z-* token for app-level layers: {offenders}"


@pytest.mark.parametrize("path", CSS_FILES, ids=rel)
def test_media_queries_use_the_shared_breakpoints(path):
    widths = re.findall(
        r"@media[^{]*?\((?:max|min)-width:\s*([\d.]+)px\)", strip_comments(read(path))
    )
    unknown = sorted(set(widths) - {"768", "769", "1024"})
    assert not unknown, f"{rel(path)} uses non-standard breakpoints {unknown}; see tokens.css"


# --------------------------------------------------------------------------
# Theming
# --------------------------------------------------------------------------


def test_no_js_dark_fallback_matches_dark_theme():
    media = block_body(TOKENS_CSS, r"@media \(prefers-color-scheme: dark\)")
    fallback = custom_props(block_body(media, r":root:not\(\[data-theme\]\)"))
    assert (
        fallback == DARK
    ), "The prefers-color-scheme fallback in tokens.css drifted from [data-theme=dark]"


def test_light_tokens_built_on_primitives_have_a_dark_value():
    # A colour token that points at a (light-oriented) primitive must be
    # redefined for dark mode, or dark mode silently shows the light value.
    missing = sorted(
        name
        for name, value in LIGHT.items()
        if name.startswith("--color-")
        and re.search(r"var\(--(gray|green|orange|red)-", value)
        and name not in DARK
    )
    assert not missing, f"Colour tokens with no dark-theme value: {missing}"


def test_theme_color_copies_match_canvas_token():
    light_bg = resolve(LIGHT["--color-bg"], LIGHT).lower()
    dark_bg = resolve(DARK["--color-bg"], {**LIGHT, **DARK}).lower()

    theme_js = read(STATIC / "js" / "theme.js").lower()
    assert (
        f"'{light_bg}'" in theme_js and f"'{dark_bg}'" in theme_js
    ), "theme.js theme-color drifted from --color-bg"

    for page in HTML_FILES:
        for colour in re.findall(r'name="theme-color" content="([^"]+)"', read(page)):
            assert (
                colour.lower() == light_bg
            ), f"{rel(page)} theme-color {colour} != --color-bg {light_bg}"

    manifest = json.loads(read(STATIC / "manifest.json"))
    pwa = read(ROOT / "src" / "api" / "pwa.py").lower()
    for key in ("background_color", "theme_color"):
        assert manifest[key].lower() == light_bg, f"manifest.json {key} drifted from --color-bg"
        assert f'"{key}": "{light_bg}"' in pwa, f"src/api/pwa.py {key} drifted from --color-bg"


def test_artifact_unlock_mirrors_tokens():
    page = read(STATIC / "artifact-unlock.html")
    light_copy = custom_props(block_body(page, r"(?m)^\s*:root"))
    dark_copy = custom_props(
        block_body(block_body(page, r"@media \(prefers-color-scheme: dark\)"), r":root")
    )
    dark_scope = {**LIGHT, **DARK}

    for copy, scope, theme in ((light_copy, LIGHT, "light"), (dark_copy, dark_scope, "dark")):
        for name, value in copy.items():
            if name not in scope:
                continue
            expected = resolve(scope[name], scope)
            if "color-mix(" in expected:  # derived; can't be compared statically
                continue
            assert (
                value.lower() == expected.lower()
            ), f"artifact-unlock.html {theme} {name} is {value}, tokens.css says {expected}"


# --------------------------------------------------------------------------
# Markup hygiene
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", MARKUP_FILES, ids=rel)
def test_no_inline_styles(path):
    # Inline styles may only pass data to CSS through custom properties,
    # e.g. style="--chip-color:${color}".
    offenders = [
        style
        for style in re.findall(r'style="([^"]*)"', read(path))
        if not all(part.strip().startswith("--") for part in style.split(";") if part.strip())
    ]
    assert not offenders, f"{rel(path)} has inline styles; use a class or utility: {offenders[:5]}"


@pytest.mark.parametrize("path", JS_FILES + HTML_FILES, ids=rel)
def test_visibility_uses_hidden_attribute(path):
    assert ".style.display" not in read(
        path
    ), f"{rel(path)}: toggle visibility with el.hidden, not style.display"


RETIRED_CLASSES = [
    # Buttons: colour means an outcome, so there are no green/orange buttons.
    "btn-success",
    "btn-warning",
    "btn-solid",
    "btn-neutral",
    # Badges: use .badge + a tone (or statusBadgeClass()).
    "status-badge",
    "status-badge-inline",
    "session-badge",
    "setting-source",
    "status-enabled",
    "status-disabled",
    "status-success",
    "status-error",
    "status-warning",
    "status-info",
    "source-db",
    "source-env",
    "source-default",
    "badge-accent",
    "badge-running",
    "badge-stopped",
    "badge-deleted",
    "badge-pending",
    "badge-provisioning",
    "badge-error",
    # Alerts
    "alert-error",
    "banner",
    "banner-warning",
    "info-box",
]

RETIRED_TOKENS = [
    "--color-primary",
    "--color-primary-dark",
    "--color-on-primary",
    "--color-primary-glow",
    "--color-bg-darker",
    "--color-text-muted",
    "--color-text-dim",
    "--color-text-dimmer",
    "--color-border-accent",
    "--color-success",
    "--color-warning",
    "--color-error",
    "--color-error-bg",
    "--color-info",
    "--color-info-bg",
    "--color-neutral",
    "--primary-color",
    "--primary-dark",
    "--primary-glow",
    "--primary-gradient",
    "--background-color",
    "--background-darker",
    "--background-secondary",
    "--bg-secondary",
    "--card-background",
    "--text-primary",
    "--text-secondary",
    "--text-muted",
    "--border-color",
    "--error-color",
    "--error-background",
    "--success-color",
    "--success-background",
    "--warning-color",
    "--warning-background",
    "--radius",
    "--shadow",
    "--shadow-hover",
    "--shadow-xl",
]


@pytest.mark.parametrize("path", CSS_FILES + MARKUP_FILES, ids=rel)
def test_no_retired_names(path):
    text = read(path)
    if path.name == "design-system.html":
        # The reference page may name retired classes in prose.
        text = re.sub(r"<p[^>]*>.*?</p>", "", text, flags=re.S)
    classes = [
        c
        for c in RETIRED_CLASSES
        if re.search(r"(?<![\w-])\.?" + re.escape(c) + r"(?![\w-])", text)
    ]
    # Ignore plain-English words in JS/HTML (e.g. a variable named banner)
    # by only counting class-like uses: in CSS selectors or class="..." lists.
    if path.suffix != ".css":
        class_attrs = " ".join(re.findall(r'class(?:Name)?\s*[=:]\s*["\'`]([^"\'`]*)', text))
        classes = [
            c
            for c in classes
            if re.search(r"(?<![\w-])" + re.escape(c) + r"(?![\w-])", class_attrs)
        ]
    else:
        classes = [
            c
            for c in classes
            if re.search(r"\." + re.escape(c) + r"(?![\w-])", strip_comments(text))
        ]
    tokens = [t for t in RETIRED_TOKENS if re.search(re.escape(t) + r"(?![\w-])", text)]
    assert not classes and not tokens, f"{rel(path)} uses retired names: {classes + tokens}"
