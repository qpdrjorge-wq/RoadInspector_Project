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

# FORCED ABSOLUTE PATH
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(BASE_DIR, "inspections.db")

st.markdown("""
    <style>
    .pill { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 700; text-transform: uppercase; border: 1px solid; }
    .pill-critical { color: #d32f2f; border-color: #d32f2f; background-color: #ffebee; }
    .pill-medium { color: #f57c00; border-color: #f57c00; background-color: #fff3e0; }
    .pill-low { color: #388e3c; border-color: #388e3c; background-color: #e8f5e9; }
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


def _geo_key(lat, lon):
    return f"{float(lat):.4f},{float(lon):.4f}"


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
            if addr:
                cache[k] = addr
                _geo_save(k, addr)
            bar.progress(i / len(todo), text=f"Looking up locations ({i}/{len(todo)})")
            time.sleep(1.1)
        bar.empty()

    def part(k, i):
        return cache.get(k, ("", "", "", ""))[i] if k else ""

    def label(k):
        if not k:
            return "Dashcam Audit (No GPS)"
        text = ", ".join(p for p in (part(k, 0), part(k, 1), part(k, 2)) if p)
        return text or k

    out["Location"] = [label(k) for k in keys]
    out["Street"] = [part(k, 0) for k in keys]
    out["Barangay"] = [part(k, 1) for k in keys]
    out["City_Municipality"] = [part(k, 2) for k in keys]
    out["Province_Region"] = [part(k, 3) for k in keys]

    new = ["Location", "Street", "Barangay", "City_Municipality", "Province_Region"]
    base = [c for c in out.columns if c not in new]
    pos = base.index("Longitude") + 1 if "Longitude" in base else len(base)
    return out[base[:pos] + new + base[pos:]]


try:
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM Reports ORDER BY Date_Captured DESC", conn)
    conn.close()
except Exception:
    df = pd.DataFrame()

st.title("System Reports & Inspection Logs")
st.markdown("Review grouped audit sessions and export selective LGU infrastructure reports.")

if not df.empty:

    # --- MASTER EXPORT: Download EVERYTHING ---
    st.divider()
    col_title, col_btn = st.columns([4, 1])
    with col_title:
        st.subheader("Official Database Export")
        st.caption("Download the complete Master CSV containing every report in the database across all locations.")

    sig = (len(df), int(df["Report_ID"].max()))
    if st.session_state.get("export_sig") != sig:
        st.session_state.pop("export_csv", None)

    with col_btn:
        prepare_all = st.button("📍 Prepare Master CSV", use_container_width=True, key="prep_all")
        if "export_csv" in st.session_state:
            st.download_button("📥 Download Master CSV", data=st.session_state["export_csv"],
                               file_name="master_lgu_audit.csv", mime="text/csv",
                               use_container_width=True, key="dl_all")

    if prepare_all:
        export_df_all = build_export(df)
        st.session_state["export_csv"] = export_df_all.to_csv(index=False).encode("utf-8-sig")
        st.session_state["export_sig"] = sig
        st.rerun()
    st.divider()

    # --- GROUPED AUDIT SESSIONS ---
    df['Date_Only'] = pd.to_datetime(df['Date_Captured']).dt.date
    df['Group_Lat'] = df['Latitude'].round(3).fillna("Dashcam")
    df['Group_Lon'] = df['Longitude'].round(3).fillna("Upload")
    grouped_audits = df.groupby(['Date_Only', 'Group_Lat', 'Group_Lon'])

    st.subheader("Recent Audit Sessions")
    st.caption(
        "Expand an audit session below to view visual evidence or download a targeted report for that specific street.")

    for (date, g_lat, g_lon), group_df in grouped_audits:

        if g_lat == "Dashcam":
            session_name = f"Dashcam Video Upload - {date}"
            loc_str = "Batch Video Upload (No GPS)"
            icon = "🎥"
        else:
            loc_str = reverse_geocode(group_df.iloc[0]['Latitude'], group_df.iloc[0]['Longitude'])
            session_name = f"Mapillary Scan: {loc_str} - {date}"
            icon = "📍"

        total_hazards = len(group_df)
        crit = len(group_df[group_df['Severity'] == 'CRITICAL'])

        # Find the first valid image path to use as the Cover Image for this group
        cover_image = None
        for img in group_df['Image_Path'].dropna():
            if os.path.exists(img):
                cover_image = img
                break

        with st.expander(f"{icon} {session_name} | {total_hazards} Hazards ({crit} Critical)"):

            # Top layout: Cover image on the left, session details and download on the right
            c_cover, c_info = st.columns([1, 4])
            with c_cover:
                if cover_image:
                    st.image(cover_image, caption="Session Cover", use_container_width=True)
                else:
                    st.info("No visual evidence")

            with c_info:
                st.markdown(f"**Audit Location:** {loc_str}")
                st.markdown(f"**Date Logged:** {date}")
                st.markdown(f"**Total Critical Hazards:** {crit}")

                # Selective Download Button for JUST this specific Audit Session
                export_group_df = build_export(group_df.copy())
                csv_data = export_group_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    label="📥 Download CSV For This Location Only",
                    data=csv_data,
                    file_name=f"audit_{date}_{g_lat}.csv",
                    mime="text/csv",
                    key=f"dl_{date}_{g_lat}_{g_lon}"
                )

            st.markdown("#### Individual Detections")

            # Display the visual evidence gallery specifically for this group
            for _, row in group_df.iterrows():
                col_img, col_details = st.columns([1, 4])
                with col_img:
                    if 'Image_Path' in group_df.columns and pd.notnull(row['Image_Path']) and os.path.exists(
                            row['Image_Path']):
                        st.image(row['Image_Path'], use_container_width=True)
                    else:
                        st.info("No image")

                with col_details:
                    st.markdown(render_pill(row['Severity']), unsafe_allow_html=True)
                    st.markdown(f"**Hazard Detected:** {row['Hazard_Class']}")
                    st.caption(
                        f" **Coordinates:** {row['Latitude']}, {row['Longitude']} &nbsp; | &nbsp; 🕒 **Time:** {str(row['Date_Captured']).split('.')[0]}")
                st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)
else:
    st.info("System database is empty. No reports to download.")