import base64
import io
import os
import re
import sqlite3
from contextlib import closing

import streamlit as st
from PIL import Image

from utils.nav import render_top_nav

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "inspections.db")   # Home.py lives next to inspections.db
HERO_DIR = os.path.join(ROOT, "assets", "hero")   # drop your hero images here
HOLD = 6.0   # seconds each image stays on screen
FADE = 1.5   # seconds for the crossfade between images

st.set_page_config(page_title="RoadInspector | Home", page_icon="🛣️",
                   layout="wide", initial_sidebar_state="collapsed")


# --- HERO IMAGES ------------------------------------------------------------
# Finds files named bg1, bg2, bg3, ... (jpg / jpeg / jfif / png / webp) anywhere in
# the project folder, so it does not matter which sub-folder they were saved in.
IMG_EXT = (".jpg", ".jpeg", ".jfif", ".png", ".webp")
SKIP_DIRS = {".venv", "venv", "__pycache__", "node_modules", "evidence", ".git", ".idea", ".streamlit"}


def _hero_files():
    found = {}
    for folder, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            m = re.match(r"bg(\d+)", name.lower())
            if m and name.lower().endswith(IMG_EXT):
                found.setdefault(int(m.group(1)), os.path.join(folder, name))
    if found:
        return [found[k] for k in sorted(found)]   # bg1, bg2, bg3, bg4 ...
    if os.path.isdir(HERO_DIR):                    # fallback: any image in assets/hero
        return sorted(os.path.join(HERO_DIR, f) for f in os.listdir(HERO_DIR) if f.lower().endswith(IMG_EXT))
    return []


@st.cache_data(show_spinner=False)
def load_hero_images(signature):
    """Resize each image once and embed it, so no static file server is needed."""
    out, failed = [], []
    for path, _mtime in signature:
        try:
            im = Image.open(path).convert("RGB")
            im.thumbnail((1600, 1000))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=78, optimize=True)
            out.append("data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode())
        except Exception:
            failed.append(os.path.basename(path))
    return out, failed


files = _hero_files()
imgs, failed = load_hero_images(tuple((f, os.path.getmtime(f)) for f in files))

# Crossfade keyframes depend on how many images there are
n = max(len(imgs), 1)
total = n * HOLD
k_in, k_hold, k_out = FADE / total * 100, HOLD / total * 100, (HOLD + FADE) / total * 100
slide_css = "".join(
    f".ri-s{i} {{ background-image: url({src}); animation-delay: {i * HOLD}s; }}\n"
    for i, src in enumerate(imgs)
)
st.markdown(f"""
<style>
@keyframes ri-fade {{
  0% {{opacity: 0}} {k_in:.2f}% {{opacity: 1}} {k_hold:.2f}% {{opacity: 1}}
  {k_out:.2f}% {{opacity: 0}} 100% {{opacity: 0}}
}}
.ri-slide {{ animation: ri-fade {total}s linear infinite both; }}
{slide_css}
</style>
""", unsafe_allow_html=True)

# --- STYLES -----------------------------------------------------------------
# Visual language: Philippine road markings (asphalt grey, yellow center line).
# Only the hero and nav pills are fixed-dark; the rest follows the Streamlit theme.
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Barlow:wght@400;500;600&display=swap');
.block-container { position: relative; padding: 4rem 2rem 3rem !important; max-width: 1280px; }

/* hero */
.ri-hero {
  position: relative; overflow: hidden; border-radius: 14px;
  min-height: 78vh; background: #1B1E23; font-family: 'Barlow', 'Segoe UI', sans-serif;
}
.ri-slides, .ri-slide, .ri-shade { position: absolute; inset: 0; }
.ri-slide { background-size: cover; background-position: center; opacity: 0; }
.ri-shade { background:
  linear-gradient(to bottom, rgba(14,16,19,0.5), transparent 24%),
  linear-gradient(to top, rgba(14,16,19,0.9) 0%, rgba(14,16,19,0.5) 40%, rgba(14,16,19,0.12) 75%); }
.ri-copy { position: absolute; left: 48px; bottom: 56px; right: 340px; color: #F5F5F2; text-shadow: 0 2px 18px rgba(0,0,0,0.45); }
.ri-title { font-family: 'Barlow Condensed', 'Arial Narrow', sans-serif; font-weight: 700;
  font-size: clamp(3.2rem, 8vw, 6.2rem); line-height: 0.92; }
.ri-sub { margin-top: 14px; font-size: 1.3rem; line-height: 1.4; max-width: 30ch; color: #E4E6E9; }
.ri-card { position: absolute; right: 28px; bottom: 44px; width: 260px; padding: 10px 10px 8px;
  background: rgba(20,23,27,0.72); backdrop-filter: blur(8px); border-radius: 10px; color: #F5F5F2; }
.ri-card svg { width: 100%; height: auto; display: block; }
.ri-card div { margin: 6px 4px 0; font-size: 0.85rem; color: #C9CDD3; }
.ri-line { position: absolute; left: 0; right: 0; bottom: 16px; border-top: 4px dashed #F2B705; }

@media (prefers-reduced-motion: reduce) {
  .ri-slide { animation: none !important; }
  .ri-slide:first-child { opacity: 1; }
}

/* content sections */
.ri-h { font-family: 'Barlow Condensed', 'Arial Narrow', sans-serif; font-weight: 700;
  font-size: 2rem; line-height: 1.1; margin: 36px 0 12px; }
.ri-body { font-family: 'Barlow', 'Segoe UI', sans-serif; font-size: 1.05rem; line-height: 1.6; max-width: 68ch; }
.ri-body p { margin: 0 0 12px; }
.ri-cap { border-top: 4px solid #F2B705; padding-top: 14px; font-family: 'Barlow', 'Segoe UI', sans-serif; }
.ri-cap h4 { margin: 0 0 6px; font-size: 1.15rem; }
.ri-cap p { margin: 0; font-size: 0.97rem; line-height: 1.55; opacity: 0.82; }
.ri-legend { font-family: 'Barlow', 'Segoe UI', sans-serif; border: 1px solid rgba(128,128,128,0.3);
  border-radius: 10px; padding: 16px 18px; }
.ri-legend h4 { margin: 0 0 10px; font-size: 1.05rem; }
.ri-row { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 10px; font-size: 0.95rem; line-height: 1.4; }
.ri-row:last-child { margin-bottom: 0; }
.ri-dot { flex: 0 0 12px; height: 12px; margin-top: 4px; border-radius: 50%; }
.ri-row span { opacity: 0.8; }
.ri-step { font-family: 'Barlow', 'Segoe UI', sans-serif; }
.ri-num { display: inline-flex; align-items: center; justify-content: center; width: 34px; height: 34px;
  border-radius: 6px; margin-bottom: 8px; background: #1B1E23; color: #F2B705;
  font-family: 'Barlow Condensed', sans-serif; font-weight: 700; font-size: 1.3rem; }
.ri-step h4 { margin: 0 0 4px; font-size: 1.05rem; }
.ri-step p { margin: 0; font-size: 0.93rem; line-height: 1.5; opacity: 0.8; }
.ri-foot { margin-top: 40px; padding-top: 16px; border-top: 1px solid rgba(128,128,128,0.3);
  font-size: 0.9rem; opacity: 0.7; font-family: 'Barlow', 'Segoe UI', sans-serif; }

@media (max-width: 800px) {
  .block-container { padding: 4rem 1rem 3rem !important; }
  .ri-hero { min-height: 70vh; }
  .ri-copy { left: 24px; right: 24px; bottom: 48px; }
  .ri-card { display: none; }
}
</style>
""", unsafe_allow_html=True)


# --- TOP-RIGHT NAV (shared with every page) ---
render_top_nav(overlay=True)


# --- HERO -------------------------------------------------------------------
slides = "".join(f'<div class="ri-slide ri-s{i}"></div>' for i in range(len(imgs)))
st.markdown(f"""
<div class="ri-hero">
<div class="ri-slides">{slides}</div>
<div class="ri-shade"></div>
<div class="ri-copy">
<div class="ri-title">RoadInspector</div>
<div class="ri-sub">Automated road infrastructure audits for Local Government Units.</div>
</div>
<div class="ri-card">
<svg viewBox="0 0 360 250" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Road view with the AI analysis zone and two detected hazards">
<rect width="360" height="250" rx="8" fill="#14171B"/>
<polygon points="68,96 292,96 352,240 8,240" fill="#2A2E35" stroke="#F2B705" stroke-width="2" stroke-dasharray="7 5"/>
<text x="180" y="88" text-anchor="middle" font-size="11" fill="#F2B705" font-family="Barlow, sans-serif">AI Analysis Zone</text>
<g stroke="#F5F5F2" stroke-width="3" stroke-linecap="round"><line x1="180" y1="102" x2="180" y2="112"/><line x1="180" y1="124" x2="180" y2="140"/><line x1="180" y1="154" x2="180" y2="178"/><line x1="180" y1="196" x2="180" y2="236"/></g>
<ellipse cx="128" cy="190" rx="26" ry="11" fill="#14171B"/>
<rect x="98" y="172" width="60" height="38" fill="none" stroke="#D64045" stroke-width="2"/>
<rect x="98" y="158" width="86" height="14" fill="#D64045"/>
<text x="102" y="169" font-size="10" fill="#fff" font-family="Barlow, sans-serif">Pothole 0.87</text>
<rect x="226" y="128" width="50" height="22" fill="none" stroke="#F0A030" stroke-width="2"/>
<rect x="226" y="115" width="78" height="13" fill="#F0A030"/>
<text x="230" y="125" font-size="10" fill="#14171B" font-family="Barlow, sans-serif">Crack 0.71</text>
</svg>
<div>What the AI sees on every frame</div>
</div>
<div class="ri-line"></div>
</div>
""", unsafe_allow_html=True)

if len(imgs) < 4:
    st.caption(f"Found {len(imgs)} hero image(s). Save images named bg1, bg2, bg3, bg4 (.jpg, .png, or .webp) anywhere in the project, for example in assets/hero.")

if failed:
    st.caption("Could not read these images: " + ", ".join(failed))

# --- LIVE NUMBERS -----------------------------------------------------------
@st.cache_data(ttl=30)
def load_stats():
    """Counts from the local SQLite DB. Returns zeros if the DB is empty or missing."""
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            return conn.execute("""
                SELECT COUNT(*),
                       COALESCE(SUM(UPPER(Severity) = 'CRITICAL'), 0),
                       COALESCE(SUM(Latitude IS NOT NULL AND Longitude IS NOT NULL), 0),
                       COUNT(DISTINCT Hazard_Class)
                FROM Reports
            """).fetchone()
    except Exception:
        return (0, 0, 0, 0)


total_r, critical, mapped, types = load_stats()
m1, m2, m3, m4 = st.columns(4)
m1.metric("Hazards logged", f"{total_r:,}")
m2.metric("Critical hazards", f"{critical:,}")
m3.metric("Mapped to a location", f"{mapped:,}")
m4.metric("Hazard types found", f"{types}")

# --- ABOUT ------------------------------------------------------------------
st.markdown('<div class="ri-h">About the system</div>', unsafe_allow_html=True)
about, legend = st.columns([3, 2], gap="large")
with about:
    st.markdown("""
<div class="ri-body">
<p><b>RoadInspector</b> is an AI-driven infrastructure auditing platform designed for Local Government Units (LGUs).</p>
<p>Traditional road maintenance relies on manual, labor-intensive surveys that are slow and prone to human error. By combining custom YOLOv8 computer vision models with geospatial mapping, this system detects, classifies, and logs road hazards so city engineers can prioritize critical repairs.</p>
<p>The project supports <b>Sustainable Development Goal 9 (Industry, Innovation, and Infrastructure)</b>. It was developed as a third-year computer science capstone at the Technological Institute of the Philippines to show how edge AI can be applied in civic engineering.</p>
</div>
""", unsafe_allow_html=True)
with legend:
    st.markdown("""
<div class="ri-legend">
<h4>How hazards are rated</h4>
<div class="ri-row"><div class="ri-dot" style="background:#D64045"></div><div><b>Critical</b><br><span>Potholes and alligator cracking</span></div></div>
<div class="ri-row"><div class="ri-dot" style="background:#F0A030"></div><div><b>Medium</b><br><span>Longitudinal, transverse, and block cracks; road obstacles</span></div></div>
<div class="ri-row"><div class="ri-dot" style="background:#3FA34D"></div><div><b>Low</b><br><span>Previously repaired surfaces</span></div></div>
</div>
""", unsafe_allow_html=True)

# --- CAPABILITIES -----------------------------------------------------------
st.markdown('<div class="ri-h">What it can do</div>', unsafe_allow_html=True)
c1, c2, c3 = st.columns(3, gap="large")
caps = [
    (c1, "Two ways to capture", "Process forward-facing dashcam MP4 files you upload, or pull street-level imagery from Mapillary's network."),
    (c2, "Two models, one verdict", "Two YOLOv8 models run on every frame: one for obstacles and potholes, one for standard structural road damage."),
    (c3, "Reports you can act on", "Each hazard is saved to a local database with its location, severity, and visual evidence, ready to review or export."),
]
for col, title, text in caps:
    with col:
        st.markdown(f'<div class="ri-cap"><h4>{title}</h4><p>{text}</p></div>', unsafe_allow_html=True)

# --- HOW IT WORKS -----------------------------------------------------------
st.markdown('<div class="ri-h">How an audit runs</div>', unsafe_allow_html=True)
s1, s2, s3, s4 = st.columns(4, gap="large")
steps = [
    (s1, "1", "Load footage", "Upload dashcam video or choose a Mapillary area to scan."),
    (s2, "2", "Focus on the road", "Everything outside the drivable lane is blacked out, so sidewalks and sky are ignored."),
    (s3, "3", "Detect and filter", "Both models scan the road. Tall, narrow shapes such as poles and pedestrians are rejected."),
    (s4, "4", "Log once", "Repeat sightings of the same hazard nearby are merged into a single report."),
]
for col, num, title, text in steps:
    with col:
        st.markdown(f'<div class="ri-step"><div class="ri-num">{num}</div><h4>{title}</h4><p>{text}</p></div>',
                    unsafe_allow_html=True)

# --- FOOTER -----------------------------------------------------------------
st.markdown("""
<div class="ri-foot">RoadInspector: Detections are decision support and should be verified by an engineer before work orders are issued.</div>
""", unsafe_allow_html=True)