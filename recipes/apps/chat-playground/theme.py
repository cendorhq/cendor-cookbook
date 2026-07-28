"""CendorTheme — the cendor.ai brand, as a Gradio theme.

Tokens are lifted 1:1 from the site's `global.css` (navy ground, blue primary, the six per-library
hues) and the type is the site's self-hosted **Manrope** + **JetBrains Mono**, embedded here as
base64 `@font-face` so the app matches the brand with **no font CDN and no network** — in keeping
with the rest of the cookbook. Kept in its own module so CI can smoke-test theme construction.
"""

from __future__ import annotations

import base64
from pathlib import Path

import gradio as gr

# ── brand tokens (the cendor.ai design tokens, kept in sync by hand) ────────────────────────
NAVY = "#0F172A"
NAVY_2 = "#111C33"  # panels / cards
NAVY_3 = "#0B1220"  # body ground (darkest)
CODE_BG = "#0A101F"  # code / feed windows
BLUE = "#2563EB"
BLUE_HI = "#3B82F6"
GREEN = "#10B981"
GRAY = "#94A3BB"
LIGHT = "#E5E7EB"
WHITE = "#FFFFFF"
LINE = "rgba(148, 163, 187, .16)"
LINE_2 = "rgba(148, 163, 187, .09)"

# The six library hues — each plumbing panel is tinted with its library's colour.
HUE = {
    "contextkit": "#3B82F6",
    "squeeze": "#22C55E",
    "tokenguard": "#8B5CF6",
    "cassette": "#14B8A6",
    "acttrace": "#F43F5E",
    "core": "#94A3BB",
}

MONO = '"JetBrains Mono", "Cascadia Code", "SF Mono", Consolas, monospace'
SANS = '"Manrope", system-ui, -apple-system, "Segoe UI", "Helvetica Neue", sans-serif'

_FONTS_DIR = Path(__file__).parent / "assets" / "fonts"
_FONT_FILES = [
    ("Manrope", 400, "manrope-400.woff2"),
    ("Manrope", 600, "manrope-600.woff2"),
    ("Manrope", 700, "manrope-700.woff2"),
    ("Manrope", 800, "manrope-800.woff2"),
    ("JetBrains Mono", 400, "jetbrains-mono-400.woff2"),
    ("JetBrains Mono", 700, "jetbrains-mono-700.woff2"),
]


def font_face_css() -> str:
    """Build `@font-face` rules with the woff2 files inlined as data URIs (offline, no CDN)."""
    rules = []
    for family, weight, filename in _FONT_FILES:
        path = _FONTS_DIR / filename
        if not path.exists():  # degrade gracefully to the system fallback stack
            continue
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        rules.append(
            f"@font-face{{font-family:'{family}';font-style:normal;font-weight:{weight};"
            f"font-display:swap;src:url(data:font/woff2;base64,{b64}) format('woff2');}}"
        )
    return "\n".join(rules)


class CendorTheme(gr.themes.Base):
    """The brand as a dark theme. Light and dark render the same navy ground so the app always
    reads as Cendor, matching the plumbing demos on cendor.ai."""

    def __init__(self) -> None:
        # Plain family names (not GoogleFont) so nothing is fetched — the real font bytes are
        # supplied by font_face_css(), which app.py injects into the page.
        super().__init__(
            primary_hue=gr.themes.colors.blue,
            secondary_hue=gr.themes.colors.blue,
            neutral_hue=gr.themes.colors.slate,
            font=["Manrope", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
            font_mono=["JetBrains Mono", "Cascadia Code", "SF Mono", "Consolas", "monospace"],
        )
        super().set(
            body_background_fill=NAVY_3,
            body_background_fill_dark=NAVY_3,
            background_fill_primary=NAVY_2,
            background_fill_primary_dark=NAVY_2,
            background_fill_secondary=NAVY_3,
            background_fill_secondary_dark=NAVY_3,
            block_background_fill=NAVY_2,
            block_background_fill_dark=NAVY_2,
            block_border_color=LINE,
            block_border_color_dark=LINE,
            block_border_width="1px",
            block_radius="12px",
            block_label_text_color=GRAY,
            block_label_text_color_dark=GRAY,
            block_title_text_color=WHITE,
            block_title_text_color_dark=WHITE,
            border_color_primary=LINE,
            border_color_primary_dark=LINE,
            panel_background_fill=NAVY_2,
            panel_background_fill_dark=NAVY_2,
            panel_border_color=LINE,
            panel_border_color_dark=LINE,
            body_text_color=LIGHT,
            body_text_color_dark=LIGHT,
            body_text_color_subdued=GRAY,
            body_text_color_subdued_dark=GRAY,
            color_accent=BLUE,
            color_accent_soft=NAVY_2,
            color_accent_soft_dark=NAVY_2,
            link_text_color=BLUE_HI,
            link_text_color_dark=BLUE_HI,
            input_background_fill=NAVY_3,
            input_background_fill_dark=NAVY_3,
            input_border_color=LINE,
            input_border_color_dark=LINE,
            input_border_color_focus=BLUE,
            input_border_color_focus_dark=BLUE,
            input_radius="8px",
            input_placeholder_color=GRAY,
            input_placeholder_color_dark=GRAY,
            code_background_fill=CODE_BG,
            code_background_fill_dark=CODE_BG,
            button_large_radius="8px",
            button_small_radius="8px",
            button_primary_background_fill=BLUE,
            button_primary_background_fill_dark=BLUE,
            button_primary_background_fill_hover=BLUE_HI,
            button_primary_background_fill_hover_dark=BLUE_HI,
            button_primary_border_color=BLUE,
            button_primary_border_color_dark=BLUE,
            button_primary_text_color=WHITE,
            button_primary_text_color_dark=WHITE,
            button_secondary_background_fill="transparent",
            button_secondary_background_fill_dark="transparent",
            button_secondary_background_fill_hover=NAVY_2,
            button_secondary_background_fill_hover_dark=NAVY_2,
            button_secondary_border_color=LINE,
            button_secondary_border_color_dark=LINE,
            button_secondary_text_color=LIGHT,
            button_secondary_text_color_dark=LIGHT,
            slider_color=BLUE,
            slider_color_dark=BLUE,
            checkbox_background_color_selected=BLUE,
            checkbox_background_color_selected_dark=BLUE,
            table_border_color=LINE,
            table_border_color_dark=LINE,
            table_even_background_fill=NAVY_2,
            table_even_background_fill_dark=NAVY_2,
            table_odd_background_fill=NAVY_3,
            table_odd_background_fill_dark=NAVY_3,
        )


if __name__ == "__main__":
    CendorTheme()
    print("CendorTheme constructed OK; font-face bytes:", len(font_face_css()))
