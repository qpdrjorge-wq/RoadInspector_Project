import streamlit as st

PAGES = [
    ("Home", "Home.py"),
    ("Dashboard", "pages/1_Dashboard.py"),
    ("Dashcam Audit", "pages/2_Dashcam_Audit.py"),
    ("Mapillary Scanner", "pages/3_Mapillary_Scanner.py"),
    ("Reports and Logs", "pages/4_Reports_and_Logs.py"),
]

_BASE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Barlow:wght@500&display=swap');
[data-testid="stSidebarNav"] { display: none !important; }
.st-key-topnav, .st-key-topnav_bar {
  flex-direction: row !important; flex-wrap: wrap; justify-content: flex-end; gap: 0.4rem !important;
}
.st-key-topnav > div, .st-key-topnav_bar > div { width: auto !important; }
.st-key-topnav a, .st-key-topnav_bar a {
  background: rgba(20,23,27,0.78); backdrop-filter: blur(8px);
  border: 1px solid rgba(245,245,242,0.18); border-radius: 999px; padding: 0.35rem 1rem;
  transition: background 0.15s;
}
.st-key-topnav a p, .st-key-topnav_bar a p {
  color: #F5F5F2 !important; font-family: 'Barlow', 'Segoe UI', sans-serif; font-weight: 500; font-size: 0.95rem;
}
.st-key-topnav a:hover, .st-key-topnav_bar a:hover,
.st-key-topnav a[aria-current="page"], .st-key-topnav_bar a[aria-current="page"] { background: #F2B705; }
.st-key-topnav a:hover p, .st-key-topnav_bar a:hover p,
.st-key-topnav a[aria-current="page"] p, .st-key-topnav_bar a[aria-current="page"] p { color: #1B1E23 !important; }
"""

_OVERLAY_CSS = """
.st-key-topnav { position: absolute; top: 5.1rem; right: 3.2rem; z-index: 20; width: auto !important; }
@media (max-width: 800px) { .st-key-topnav { top: 5.8rem; right: 1.8rem; left: 1.8rem; } }
"""

_BAR_CSS = """
.st-key-topnav_bar { width: 100% !important; margin-bottom: 0.5rem; }
"""

_HIDE_SIDEBAR_CSS = """
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"] { display: none !important; }
"""


def render_top_nav(overlay=False, hide_sidebar=True):
    css = _BASE_CSS + (_OVERLAY_CSS if overlay else _BAR_CSS)
    if hide_sidebar:
        css += _HIDE_SIDEBAR_CSS
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

    key = "topnav" if overlay else "topnav_bar"
    try:
        box = st.container(key=key)
    except TypeError:
        box = st.container()
    with box:
        for label, path in PAGES:
            st.page_link(path, label=label)