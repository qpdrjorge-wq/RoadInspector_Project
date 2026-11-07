import os
import streamlit as st
import pandas as pd
import sqlite3
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Executive Dashboard", layout="wide", initial_sidebar_state="expanded")
from utils.nav import render_top_nav
render_top_nav()

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
    if sev == "CRITICAL": return '<span class="pill pill-critical">● CRITICAL</span>'
    elif sev == "MEDIUM": return '<span class="pill pill-medium">● MEDIUM</span>'
    else: return '<span class="pill pill-low">● LOW</span>'

# FORCED ABSOLUTE PATH: Ensures the Dashboard reads the exact same file the Scanners write to
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "inspections.db")

try:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM Reports ORDER BY Date_Captured DESC", conn)
    conn.close()
except Exception as e:
    st.error(f"Database Connection Error: {e}") # This will now visibly warn you if the path is still wrong
    df = pd.DataFrame()

st.title("RoadInspector Command Center")
st.markdown("### Philippine Road & Sidewalk Condition Overview")
st.markdown("<p style='color: #666;'>Real-time automated LGU auditing for safer communities.</p>", unsafe_allow_html=True)

if not df.empty:
    map_df = df.dropna(subset=['Latitude', 'Longitude'])

    total = len(df)
    crit_count = len(df[df['Severity'] == 'CRITICAL'])
    med_count = len(df[df['Severity'] == 'MEDIUM'])
    low_count = len(df[df['Severity'] == 'LOW'])

    st.markdown("#### Overall Infrastructure Health")
    st.markdown(f"""
        <div style="display: flex; height: 12px; border-radius: 6px; overflow: hidden; margin-bottom: 24px; background-color: #eee;">
            <div style="width: {(crit_count / total) * 100 if total else 0}%; background-color: #d32f2f;"></div>
            <div style="width: {(med_count / total) * 100 if total else 0}%; background-color: #fba834;"></div>
            <div style="width: {(low_count / total) * 100 if total else 0}%; background-color: #388e3c;"></div>
        </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(render_pill("CRITICAL"), unsafe_allow_html=True)
        st.markdown(f"<h1 style='margin: 10px 0 0 0;'>{crit_count}</h1><p style='color: #666;'>Immediate LGU action required</p>", unsafe_allow_html=True)
    with col2:
        st.markdown(render_pill("MEDIUM"), unsafe_allow_html=True)
        st.markdown(f"<h1 style='margin: 10px 0 0 0;'>{med_count}</h1><p style='color: #666;'>Maintenance queue</p>", unsafe_allow_html=True)
    with col3:
        st.markdown(render_pill("LOW"), unsafe_allow_html=True)
        st.markdown(f"<h1 style='margin: 10px 0 0 0;'>{low_count}</h1><p style='color: #666;'>Minor fissures & fading</p>", unsafe_allow_html=True)

    st.divider()

    st.subheader("Master Geospatial Hazard Map")
    if not map_df.empty:
        center_lat = map_df['Latitude'].mean()
        center_lon = map_df['Longitude'].mean()
        m = folium.Map(location=[center_lat, center_lon], zoom_start=13)

        for _, row in map_df.iterrows():
            color = "red" if row['Severity'] == 'CRITICAL' else "orange" if row['Severity'] == 'MEDIUM' else "green"
            folium.CircleMarker(
                location=[row['Latitude'], row['Longitude']],
                radius=6,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.7,
                tooltip=f"{row['Hazard_Class']} ({row['Severity']})"
            ).add_to(m)

        st_folium(m, height=450, use_container_width=True)
    else:
        st.info("No spatial data available to map yet.")

else:
    st.info("System database is empty. Please run an audit using the sidebar tools to populate the dashboard.")