import streamlit as st
import pandas as pd
import sqlite3
import requests
import os
import time
from contextlib import closing

st.set_page_config(page_title="Reports & Logs", layout="wide")
from utils.nav import render_top_nav
render_top_nav()

DB_FILE = "inspections.db"  # same relative path the rest of the app uses

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .pill { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 700; text-transform: uppercase; border: 1px solid; }
    .pill-critical { color: #d32f2f; border-color: #d32f2f; background-color: #ffebee; }
    .pill-medium { color: #f57c00; border-color: #f57c00; background-color: #fff3e0; }
    .pill-low { color: #388e3c; border-color: #388e3c; background-color: #e8f5e9; }
    .styled-table { width: 100%; border-collapse: collapse; font-family: sans-serif; font-size: 14px; }
    .styled-table th { background-color: #f9f9f9; color: #777; font-weight: 600; text-align: left; padding: 12px 16px; border-bottom: 1px solid #eee; }
    .styled-table td { padding: 16px; border-bottom: 1px solid #eee; color: #333; }
    </style>
""", unsafe_allow_html=True)


def render_pill(severity):
    sev = str(severity).upper()
    if sev == "CRITICAL":
        return '<span class="pill pill-critical">● CRITICAL</span>'
    elif sev == "MEDIUM":
        return '<span class="pill pill-medium">● MEDIUM</span>'
    else:
        return '<span class="pill pill-low">● LOW</span>'


@st.cache_data(ttl=3600)
def reverse_geocode(lat, lon):
    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {"lat": lat, "lon": lon, "format": "json", "zoom": 16}
        headers = {"User-Agent": "RoadInspector-LGU-Audit/1.0"}
        resp = requests.get(url, params=params, headers=headers, timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            address = data.get("address", {})
            parts = [p for p in [address.get("road", ""), address.get("suburb", address.get("village", "")),
                                 address.get("city", "")] if p]
            if parts: return ", ".join(parts[:2])
    except:
        pass
    return f"{lat:.4f}, {lon:.4f}"


# --- LOCATION LOOKUP FOR THE CSV EXPORT ---------------------------------------
# Results are saved in a Geo_Cache table inside inspections.db, so each spot is
# looked up from OpenStreetMap only once, even across app restarts.
def _geo_key(lat, lon):
    return f"{float(lat):.4f},{float(lon):.4f}"  # 4 decimals is roughly 11 m


def _geo_load():
    with closing(sqlite3.connect(DB_FILE)) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS Geo_Cache (
            Geo_Key TEXT PRIMARY KEY, Street TEXT, Barangay TEXT, City TEXT, Province TEXT)""")
        rows = conn.execute("SELECT Geo_Key, Street, Barangay, City, Province FROM Geo_Cache").fetchall()
    return {r[0]: tuple(r[1:]) for r in rows}


def _geo_save(key, addr):
    with closing(sqlite3.connect(DB_FILE)) as conn:
        conn.execute("INSERT OR REPLACE INTO Geo_Cache VALUES (?, ?, ?, ?, ?)", (key, *addr))
        conn.commit()


def _fetch_address(lat, lon):
    """Returns (street, barangay, city, province) or None if the lookup failed."""
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 18, "addressdetails": 1},
            headers={"User-Agent": "RoadInspector-LGU-Audit/1.0"},
            timeout=6,
        )
        if resp.status_code != 200:
            return None
        a = resp.json().get("address", {})
    except Exception:
        return None
    if not a:
        return None
    street = a.get("road") or a.get("pedestrian") or a.get("footway") or ""
    barangay = a.get("suburb") or a.get("village") or a.get("neighbourhood") or a.get("quarter") or ""
    city = a.get("city") or a.get("town") or a.get("municipality") or a.get("city_district") or a.get("county") or ""
    province = a.get("state") or a.get("province") or a.get("region") or ""
    return (street, barangay, city, province)


def build_export(frame):
    """Adds Location, Street, Barangay, City_Municipality, Province_Region after Longitude."""
    out = frame.copy()
    keys = [
        _geo_key(la, lo) if pd.notnull(la) and pd.notnull(lo) else None
        for la, lo in zip(out["Latitude"], out["Longitude"])
    ]
    cache = _geo_load()
    todo = [k for k in dict.fromkeys(k for k in keys if k) if k not in cache]

    if todo:
        bar = st.progress(0.0, text="Looking up locations...")
        for i, k in enumerate(todo, start=1):
            lat, lon = k.split(",")
            addr = _fetch_address(lat, lon)
            if addr:  # failed lookups are not saved, so they are retried next time
                cache[k] = addr
                _geo_save(k, addr)
            bar.progress(i / len(todo), text=f"Looking up locations ({i}/{len(todo)})")
            time.sleep(1.1)  # OpenStreetMap's public server allows about 1 request per second
        bar.empty()

    def part(k, i):
        return cache.get(k, ("", "", "", ""))[i] if k else ""

    def label(k):
        if not k:
            return "Batch Video Upload (no GPS)"
        text = ", ".join(p for p in (part(k, 0), part(k, 1), part(k, 2)) if p)
        return text or k  # fall back to raw coordinates if the lookup failed

    out["Location"] = [label(k) for k in keys]
    out["Street"] = [part(k, 0) for k in keys]
    out["Barangay"] = [part(k, 1) for k in keys]
    out["City_Municipality"] = [part(k, 2) for k in keys]
    out["Province_Region"] = [part(k, 3) for k in keys]

    new = ["Location", "Street", "Barangay", "City_Municipality", "Province_Region"]
    base = [c for c in out.columns if c not in new]
    pos = base.index("Longitude") + 1 if "Longitude" in base else len(base)
    return out[base[:pos] + new + base[pos:]]


# --- FETCH DATA ---
try:
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM Reports ORDER BY Date_Captured DESC", conn)
    conn.close()
except Exception:
    df = pd.DataFrame()

st.title("System Reports & Inspection Logs")
st.markdown("Download official LGU infrastructure CSV reports and review automated visual evidence.")

if not df.empty:
    col_title, col_btn = st.columns([4, 1])
    with col_title:
        st.subheader("Official Database Export")
        st.caption("The CSV includes the street, barangay, and city of every geotagged report.")

    # Throw away a stale export whenever reports are added
    sig = (len(df), int(df["Report_ID"].max()))
    if st.session_state.get("export_sig") != sig:
        st.session_state.pop("export_csv", None)

    with col_btn:
        prepare = st.button("📍 Prepare CSV with locations", use_container_width=True)
        if "export_csv" in st.session_state:
            st.download_button("📥 Download LGU CSV", data=st.session_state["export_csv"],
                               file_name="lgu_infrastructure_audit.csv", mime="text/csv",
                               use_container_width=True)

    if prepare:
        export_df = build_export(df)
        # utf-8-sig keeps names like Parañaque and Las Piñas intact when opened in Excel
        st.session_state["export_csv"] = export_df.to_csv(index=False).encode("utf-8-sig")
        st.session_state["export_sig"] = sig
        st.rerun()

    st.divider()

    # VISUAL EVIDENCE LOGS
    st.subheader("Visual Evidence Gallery")

    # Filter functionality
    filter_val = st.selectbox("Filter by Severity:", ["All", "CRITICAL", "MEDIUM", "LOW"])
    if filter_val != "All":
        display_df = df[df['Severity'] == filter_val]
    else:
        display_df = df

    for _, row in display_df.iterrows():
        col_img, col_details = st.columns([1, 4])
        with col_img:
            if 'Image_Path' in df.columns and pd.notnull(row['Image_Path']) and os.path.exists(row['Image_Path']):
                st.image(row['Image_Path'], use_container_width=True)
            else:
                st.info("No image captured")

        with col_details:
            loc_str = reverse_geocode(row['Latitude'], row['Longitude']) if pd.notnull(
                row['Latitude']) else "Batch Video Upload"
            st.markdown(render_pill(row['Severity']), unsafe_allow_html=True)
            st.markdown(f"**Hazard Detected:** {row['Hazard_Class']}")
            st.caption(
                f"📍 **Location:** {loc_str} &nbsp; | &nbsp; 🕒 **Date:** {str(row['Date_Captured']).split('.')[0]}")
        st.divider()
else:
    st.info("System database is empty. No reports to download.")