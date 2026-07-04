"""CendorTheme — a Gradio theme approximating the Cendor brand.

Dark navy ground (#0F172A), blue (#2563EB) primary, a monospace stack for the numbers that
fill the plumbing panels. Kept in its own module so CI can smoke-test theme construction on its
own, and so `app.py` reads as app logic rather than design tokens.

Fonts are plain family names (not `GoogleFont`), so the theme never reaches out to a font CDN —
the app stays fully offline, matching the rest of the cookbook.
"""

from __future__ import annotations

import gradio as gr

# Brand palette (Tailwind-slate ground + Cendor blue), one place to tune.
NAVY = "#0F172A"  # body ground
SURFACE = "#1E293B"  # panels / blocks
SURFACE_2 = "#111C30"  # inputs / recessed
BORDER = "#334155"  # hairlines
BLUE = "#2563EB"  # primary
BLUE_HOVER = "#1D4ED8"
TEXT = "#E2E8F0"  # primary text
TEXT_SUBDUED = "#94A3B8"  # labels / secondary

MONO = ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "Liberation Mono", "monospace"]
SANS = ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "sans-serif"]


class CendorTheme(gr.themes.Base):
    """A branded dark theme. Light and dark render the same navy ground, so the app looks like
    Cendor regardless of the viewer's system preference."""

    def __init__(self) -> None:
        super().__init__(
            primary_hue=gr.themes.colors.blue,
            secondary_hue=gr.themes.colors.blue,
            neutral_hue=gr.themes.colors.slate,
            font=SANS,
            font_mono=MONO,
        )
        # Light and *_dark variants share the same navy palette on purpose (see class doc).
        super().set(
            body_background_fill=NAVY,
            body_background_fill_dark=NAVY,
            background_fill_primary=SURFACE,
            background_fill_primary_dark=SURFACE,
            background_fill_secondary=NAVY,
            background_fill_secondary_dark=NAVY,
            block_background_fill=SURFACE,
            block_background_fill_dark=SURFACE,
            block_border_color=BORDER,
            block_border_color_dark=BORDER,
            block_label_text_color=TEXT_SUBDUED,
            block_label_text_color_dark=TEXT_SUBDUED,
            block_title_text_color=TEXT,
            block_title_text_color_dark=TEXT,
            border_color_primary=BORDER,
            border_color_primary_dark=BORDER,
            panel_background_fill=SURFACE,
            panel_background_fill_dark=SURFACE,
            panel_border_color=BORDER,
            panel_border_color_dark=BORDER,
            body_text_color=TEXT,
            body_text_color_dark=TEXT,
            body_text_color_subdued=TEXT_SUBDUED,
            body_text_color_subdued_dark=TEXT_SUBDUED,
            color_accent=BLUE,
            color_accent_soft=SURFACE,
            color_accent_soft_dark=SURFACE,
            link_text_color=BLUE,
            link_text_color_dark="#60A5FA",
            input_background_fill=SURFACE_2,
            input_background_fill_dark=SURFACE_2,
            input_border_color=BORDER,
            input_border_color_dark=BORDER,
            input_placeholder_color=TEXT_SUBDUED,
            input_placeholder_color_dark=TEXT_SUBDUED,
            code_background_fill=SURFACE_2,
            code_background_fill_dark=SURFACE_2,
            button_primary_background_fill=BLUE,
            button_primary_background_fill_dark=BLUE,
            button_primary_background_fill_hover=BLUE_HOVER,
            button_primary_background_fill_hover_dark=BLUE_HOVER,
            button_primary_text_color="#FFFFFF",
            button_primary_text_color_dark="#FFFFFF",
            button_secondary_background_fill=SURFACE,
            button_secondary_background_fill_dark=SURFACE,
            button_secondary_text_color=TEXT,
            button_secondary_text_color_dark=TEXT,
            slider_color=BLUE,
            slider_color_dark=BLUE,
            table_border_color=BORDER,
            table_border_color_dark=BORDER,
            table_even_background_fill=SURFACE,
            table_even_background_fill_dark=SURFACE,
            table_odd_background_fill=SURFACE_2,
            table_odd_background_fill_dark=SURFACE_2,
        )


if __name__ == "__main__":  # `python theme.py` prints a quick sanity line
    CendorTheme()
    print("CendorTheme constructed OK")
