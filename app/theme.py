"""Theme configuration: Primer-aligned color tokens + Plotly template.

Primer token values from:
  https://primer.style/foundations/color/overview

We map the Primer color scale to the dataviz skill's palette where they align
closely (both use blue as the primary accent) and inject CSS custom properties
via solara.Style so charts and UI components share one token set.
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio


# Categorical palette (dataviz skill, default order, validated)
SERIES = {
    "light": {
        1: "#2a78d6",   # blue   — scope
        2: "#eb6834",   # orange — completed
        3: "#1baf7a",   # aqua
        4: "#eda100",   # yellow
        5: "#e87ba4",   # magenta
        6: "#008300",   # green
        7: "#4a3aa7",   # violet
        8: "#e34948",   # red
    },
    "dark": {
        1: "#3987e5",
        2: "#d95926",
        3: "#199e70",
        4: "#c98500",
        5: "#d55181",
        6: "#008300",
        7: "#9085e9",
        8: "#e66767",
    },
}

# Chart chrome
CHROME = {
    "light": {
        "surface": "#fcfcfb",
        "page": "#f6f8fa",       # Primer canvas-default
        "text_primary": "#1f2328",   # Primer fg-default
        "text_secondary": "#636c76", # Primer fg-muted
        "text_muted": "#898781",
        "gridline": "#d0d7de",   # Primer border-default
        "baseline": "#d0d7de",
        "border": "rgba(31,35,40,0.10)",
    },
    "dark": {
        "surface": "#1a1a19",
        "page": "#0d1117",       # Primer canvas-default dark
        "text_primary": "#e6edf3",
        "text_secondary": "#8d96a0",
        "text_muted": "#898781",
        "gridline": "#2c2c2a",
        "baseline": "#383835",
        "border": "rgba(230,237,243,0.10)",
    },
}

# Status tokens
STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

# Confidence shading for approximate regions in burn-up
APPROXIMATE_FILL = "rgba(200,200,200,0.18)"
APPROXIMATE_LINE = "rgba(160,160,160,0.50)"


CSS = """
:root {
  --color-accent:        #0969da;   /* Primer accent */
  --color-accent-subtle: #ddf4ff;
  --color-fg-default:    #1f2328;
  --color-fg-muted:      #636c76;
  --color-border:        #d0d7de;
  --color-canvas:        #f6f8fa;
  --color-canvas-subtle: #f6f8fa;

  --series-1: #2a78d6;
  --series-2: #eb6834;
  --series-3: #1baf7a;
  --series-4: #eda100;
}

@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    --color-accent:        #4493f8;
    --color-accent-subtle: #121d2f;
    --color-fg-default:    #e6edf3;
    --color-fg-muted:      #8d96a0;
    --color-border:        #30363d;
    --color-canvas:        #0d1117;
    --color-canvas-subtle: #161b22;

    --series-1: #3987e5;
    --series-2: #d95926;
    --series-3: #199e70;
    --series-4: #c98500;
  }
}

:root[data-theme="dark"] {
  --color-accent:        #4493f8;
  --color-fg-default:    #e6edf3;
  --color-fg-muted:      #8d96a0;
  --color-border:        #30363d;
  --color-canvas:        #0d1117;
  --series-1: #3987e5;
  --series-2: #d95926;
  --series-3: #199e70;
  --series-4: #c98500;
}

/* App layout */
.sidebar { background: var(--color-canvas-subtle); border-right: 1px solid var(--color-border); }
.issue-link { color: var(--color-accent); text-decoration: none; }
.issue-link:hover { text-decoration: underline; }
.stat-value { font-size: 2rem; font-weight: 600; color: var(--color-fg-default); }
.stat-label { font-size: 0.85rem; color: var(--color-fg-muted); }
.approx-note { font-size: 0.78rem; color: var(--color-fg-muted); font-style: italic; }
"""


def _make_plotly_template(mode: str = "light") -> go.layout.Template:
    s = SERIES[mode]
    c = CHROME[mode]
    return go.layout.Template(
        layout=go.Layout(
            paper_bgcolor=c["surface"],
            plot_bgcolor=c["surface"],
            font=dict(
                family='system-ui, -apple-system, "Segoe UI", sans-serif',
                color=c["text_primary"],
                size=12,
            ),
            title=dict(font=dict(size=14, color=c["text_primary"])),
            colorway=[s[i] for i in sorted(s)],
            xaxis=dict(
                gridcolor=c["gridline"],
                linecolor=c["baseline"],
                tickcolor=c["baseline"],
                tickfont=dict(color=c["text_muted"], size=11),
                showgrid=False,
                zeroline=False,
            ),
            yaxis=dict(
                gridcolor=c["gridline"],
                linecolor="rgba(0,0,0,0)",
                tickcolor="rgba(0,0,0,0)",
                tickfont=dict(color=c["text_muted"], size=11),
                showgrid=True,
                zeroline=False,
                gridwidth=1,
            ),
            legend=dict(
                bgcolor="rgba(0,0,0,0)",
                bordercolor="rgba(0,0,0,0)",
                font=dict(color=c["text_secondary"], size=12),
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="left",
                x=0,
            ),
            margin=dict(l=40, r=20, t=48, b=40),
            hovermode="x unified",
        )
    )


def register_templates() -> None:
    """Register Plotly templates. Call once at app startup."""
    pio.templates["primer_light"] = _make_plotly_template("light")
    pio.templates["primer_dark"] = _make_plotly_template("dark")
    pio.templates.default = "primer_light"


# Call at import time so any module that imports theme gets working templates.
register_templates()
