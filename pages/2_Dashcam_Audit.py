import os
import tempfile
import folium
import requests
import streamlit as st
from streamlit_folium import st_folium
from utils.db_manager import init_db
from utils.video_processor import process_uploaded_video

st.set_page_config(page_title="Batch Processing", layout="wide")
from utils.nav import render_top_nav
render_top_nav()
init_db()

st.title("Batch Dashcam Video Analysis")
st.markdown("Upload forward-facing dashcam footage and lock the capture location for LGU mapping.")

OSM_HEADERS = {"User-Agent": "RoadInspector-LGU-Audit/1.0"}

@st.cache_data(ttl=600)
def geocode_location(query):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": query, "format": "json", "limit": 1, "countrycodes": "ph"}
    resp = requests.get(url, params=params, headers=OSM_HEADERS, timeout=6)
    if resp.status_code == 200 and resp.json():
        hit = resp.json()[0]
        return float(hit["lat"]), float(hit["lon"]), hit.get("display_name", query)
    return None

if "vid_lat" not in st.session_state:
    st.session_state.vid_lat = None
if "vid_lon" not in st.session_state:
    st.session_state.vid_lon = None
if "vid_map_center" not in st.session_state:
    st.session_state.vid_map_center = [14.6600, 121.0730]

st.subheader("1. Set Documentation Location")
st.markdown("Search for the footage location, or click directly on the map to set the exact coordinates.")

search_col1, search_col2 = st.columns([4, 1])
with search_col1:
    search_query = st.text_input(
        "Search Location",
        placeholder="e.g., Commonwealth Avenue, Quezon City",
        label_visibility="collapsed",
    )
with search_col2:
    search_clicked = st.button("Search Map", use_container_width=True)

if search_clicked and search_query.strip():
    geo = geocode_location(search_query.strip())
    if geo:
        s_lat, s_lon, disp = geo
        st.session_state.vid_map_center = [s_lat, s_lon]
        st.session_state.vid_lat = s_lat
        st.session_state.vid_lon = s_lon
        st.success(f"📍 Location Locked: {disp}")
    else:
        st.warning("Location not found. Try adding the city name (e.g., 'Quezon City').")

m = folium.Map(location=st.session_state.vid_map_center, zoom_start=16)
if st.session_state.vid_lat and st.session_state.vid_lon:
    folium.Marker(
        location=[st.session_state.vid_lat, st.session_state.vid_lon],
        tooltip="Dashcam Footage Location",
        icon=folium.Icon(color="blue", icon="camera", prefix="fa")
    ).add_to(m)

map_data = st_folium(m, height=350, use_container_width=True)
if map_data and map_data.get("last_clicked"):
    st.session_state.vid_lat = map_data["last_clicked"]["lat"]
    st.session_state.vid_lon = map_data["last_clicked"]["lng"]
    st.session_state.vid_map_center = [st.session_state.vid_lat, st.session_state.vid_lon]
    st.rerun()

if st.session_state.vid_lat and not search_clicked:
    st.success(f"📍 Location Locked: {st.session_state.vid_lat:.5f}, {st.session_state.vid_lon:.5f}")
elif not st.session_state.vid_lat:
    st.info("Please search or click the map above to set a location before uploading footage.")

st.subheader("2. Upload and Analyze")
uploaded_file = st.file_uploader(
    "Upload Dashcam Footage",
    type=["mp4", "avi", "mov"],
    disabled=(st.session_state.vid_lat is None)
)

if uploaded_file is not None and st.session_state.vid_lat is not None:
    col1, col2 = st.columns(2)
    with col1:
        st.video(uploaded_file)

    with col2:
        live_feed = st.empty()
        live_feed.info("Click 'Run Hazard Detection' to start rapid frame analysis.")

    if st.button("Run Hazard Detection", type="primary"):
        progress_bar = st.progress(0.0)
        with st.spinner("Scanning optimal dashcam frames with Dual-Model ROI pipeline..."):
            temp_in = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            temp_in.write(uploaded_file.read())
            input_path = temp_in.name
            temp_in.close()

            try:
                hazards_count, snapshots = process_uploaded_video(
                    input_path, live_feed, progress_bar,
                    lat=st.session_state.vid_lat, lon=st.session_state.vid_lon
                )
            finally:
                if os.path.exists(input_path):
                    os.remove(input_path)

        st.success(f"Analysis Complete! {hazards_count} hazards logged to SQLite at the selected location.")

        if snapshots:
            st.subheader("Captured Hazard Snapshots")
            snap_cols = st.columns(3)
            for idx, img in enumerate(snapshots):
                snap_cols[idx % 3].image(img, use_container_width=True)