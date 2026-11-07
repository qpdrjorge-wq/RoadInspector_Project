from datetime import datetime, timezone
import urllib.request
import cv2
import folium
import numpy as np
import requests
import streamlit as st
from streamlit_folium import st_folium
import os
import uuid

from utils.db_manager import init_db, insert_report
from utils.detector import analyze_road_frame, get_mapillary_token, haversine_meters

st.set_page_config(page_title="Mapillary Scanner", layout="wide")
from utils.nav import render_top_nav

render_top_nav()
init_db()

OSM_HEADERS = {"User-Agent": "RoadInspector-LGU-Audit/1.0"}

st.title("Automated LGU Road Infrastructure Audit")
st.markdown("Search a street or click directly on a drivable road to run an automated sequence audit.")

ACCESS_TOKEN = get_mapillary_token()
if not ACCESS_TOKEN:
    st.error("Mapillary token missing. Add MAPILLARY_TOKEN to .streamlit/secrets.toml.")
    st.stop()


@st.cache_data(ttl=600)
def geocode_location(query):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": query, "format": "json", "limit": 1, "countrycodes": "ph"}
    resp = requests.get(url, params=params, headers=OSM_HEADERS, timeout=6)
    if resp.status_code == 200 and resp.json():
        hit = resp.json()[0]
        return float(hit["lat"]), float(hit["lon"]), hit.get("display_name", query)
    return None


@st.cache_data(ttl=600)
def verify_road_click(lat, lon):
    overpass_query = f"""
    [out:json][timeout:4];
    way(around:22,{lat},{lon})["highway"]["highway"!~"footway|steps|pedestrian|path|cycleway|corridor"];
    out tags 1;
    """
    try:
        resp = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": overpass_query},
            headers=OSM_HEADERS,
            timeout=5,
        )
        if resp.status_code == 200:
            elements = resp.json().get("elements", [])
            if elements:
                tags = elements[0].get("tags", {})
                road_name = tags.get("name", f"Unnamed {tags.get('highway', 'Road').title()}")
                return True, road_name
            return False, None
    except Exception:
        pass

    try:
        rev = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 18},
            headers=OSM_HEADERS,
            timeout=5,
        )
        if rev.status_code == 200:
            data = rev.json()
            road = data.get("address", {}).get("road")
            if data.get("category") == "highway" or road:
                return True, road or "Verified Road"
    except Exception:
        pass
    return False, None


def _parse_capture_dt(raw_ts):
    if isinstance(raw_ts, (int, float)):
        sec = raw_ts / 1000.0 if raw_ts > 1e11 else float(raw_ts)
        return datetime.fromtimestamp(sec, tz=timezone.utc)
    return datetime(1970, 1, 1, tzinfo=timezone.utc)


@st.cache_data(ttl=300)
def fetch_latest_road_sequence(token, lat, lon):
    offset = 0.002
    bbox = f"{lon - offset},{lat - offset},{lon + offset},{lat + offset}"

    url = (
        f"https://graph.mapillary.com/images?access_token={token}"
        f"&fields=id,geometry,thumb_1024_url,sequence,captured_at&bbox={bbox}&limit=200"
    )

    try:
        resp = requests.get(url, timeout=30)
    except requests.exceptions.Timeout:
        return {"error": "Mapillary servers timed out. Please try searching again."}
    except requests.exceptions.RequestException as e:
        return {"error": f"Connection Error: {str(e)}"}

    if resp.status_code != 200:
        return {"error": f"Mapillary API Error {resp.status_code}"}

    raw_data = resp.json().get("data", [])
    if not raw_data:
        return {"frames": [], "newest_dt": None}

    sequences = {}
    for item in raw_data:
        seq_id = item.get("sequence") or "default"
        sequences.setdefault(seq_id, []).append(item)

    rich_sequences = {k: v for k, v in sequences.items() if len(v) >= 10}
    pool = rich_sequences if rich_sequences else sequences

    best_seq_frames = max(pool.values(), key=lambda imgs: len(imgs))

    best_seq_frames.sort(key=lambda x: x.get("captured_at", 0))
    newest_ts = max(i.get("captured_at", 0) for i in best_seq_frames)

    return {
        "frames": best_seq_frames,
        "newest_dt": _parse_capture_dt(newest_ts),
    }


if "map_center" not in st.session_state:
    st.session_state.map_center = [14.6600, 121.0730]
if "target_coords" not in st.session_state:
    st.session_state.target_coords = None
if "last_click_key" not in st.session_state:
    st.session_state.last_click_key = None

search_col1, search_col2 = st.columns([4, 1])
with search_col1:
    search_query = st.text_input(
        "Search Road or Barangay",
        placeholder="e.g., Commonwealth Avenue, Quezon City",
        label_visibility="collapsed",
    )
with search_col2:
    search_clicked = st.button("Search Location", use_container_width=True)

if search_clicked and search_query.strip():
    geo = geocode_location(search_query.strip())
    if geo:
        s_lat, s_lon, disp = geo
        st.session_state.map_center = [s_lat, s_lon]
        st.session_state.target_coords = (s_lat, s_lon)
        st.success(f"Located: {disp}")
    else:
        st.warning("Location not found. Try adding 'Quezon City' or 'Metro Manila'.")

m = folium.Map(location=st.session_state.map_center, zoom_start=16)
if st.session_state.target_coords:
    folium.Marker(
        location=list(st.session_state.target_coords),
        tooltip="Selected Audit Point",
        icon=folium.Icon(color="red", icon="road", prefix="fa"),
    ).add_to(m)

map_data = st_folium(m, height=400, use_container_width=True)

if map_data and map_data.get("last_clicked"):
    c_lat = map_data["last_clicked"]["lat"]
    c_lon = map_data["last_clicked"]["lng"]
    click_key = f"{c_lat:.6f},{c_lon:.6f}"
    if click_key != st.session_state.last_click_key:
        st.session_state.last_click_key = click_key
        st.session_state.target_coords = (c_lat, c_lon)
        st.session_state.map_center = [c_lat, c_lon]
        st.rerun()

if st.session_state.target_coords:
    t_lat, t_lon = st.session_state.target_coords
    on_road, road_name = verify_road_click(t_lat, t_lon)

    if not on_road:
        st.error(
            f"Off-Road Selection ({t_lat:.5f}, {t_lon:.5f}): You clicked on a building, park, "
            "or footpath. Please click directly on a drivable street."
        )
    else:
        st.info(f"Target Road Locked: **{road_name}** ({t_lat:.5f}, {t_lon:.5f})")
        seq_meta = fetch_latest_road_sequence(ACCESS_TOKEN, t_lat, t_lon)

        if "error" in seq_meta:
            st.error(seq_meta["error"])
        elif not seq_meta["frames"]:
            st.error("No Mapillary street imagery exists on this road segment yet. Audit prevented.")
        else:
            frames = seq_meta["frames"]

            st.success(f"Mapillary Sequence Stream Locked: {len(frames)} continuous frames ready for analysis.")

            if st.button("Run Live Sequence Audit", type="primary"):
                st.subheader("Live AI Inspection Feed (Cropped Road Surface)")
                video_feed = st.empty()
                progress = st.progress(0.0)

                hazards_found = 0
                logged_points = []

                # NEW: Array to collect the images for the final gallery
                evidence_snapshots = []

                # ALGORITHM: Sequence Subsampling - Analyze every 4th frame to speed up by 75%
                optimized_frames = frames[::4]

                for idx, item in enumerate(optimized_frames):
                    img_url = item.get("thumb_1024_url")
                    if not img_url:
                        continue

                    lon, lat = item["geometry"]["coordinates"]
                    req = urllib.request.urlopen(img_url)
                    arr = np.asarray(bytearray(req.read()), dtype=np.uint8)
                    img = cv2.imdecode(arr, -1)
                    if img is None:
                        continue

                    # ALGORITHM: imgsz matrix reduction for faster Mapillary processing
                    annotated_bgr, detections = analyze_road_frame(img, conf=0.40)

                    # NEW: Track if we actually saved a hazard this frame
                    logged_this_frame = False

                    for det in detections:
                        h_name = det["name"]
                        is_dup = any(
                            prev_name == h_name and haversine_meters(lat, lon, p_lat, p_lon) < 15.0
                            for prev_name, p_lat, p_lon in logged_points
                        )
                        if not is_dup:
                            os.makedirs("evidence", exist_ok=True)
                            img_path = f"evidence/mapillary_{uuid.uuid4().hex[:6]}.jpg"
                            cv2.imwrite(img_path, annotated_bgr)

                            insert_report(h_name, det["severity"], lat=lat, lon=lon, image_path=img_path)
                            logged_points.append((h_name, lat, lon))
                            hazards_found += 1
                            logged_this_frame = True  # Flag triggered for gallery inclusion

                    annotated_rgb = cv2.cvtColor(annotated_bgr, cv2.COLOR_BGR2RGB)
                    video_feed.image(annotated_rgb, use_container_width=True)

                    # NEW: If the flag triggered, save this RGB frame for the end
                    if logged_this_frame:
                        evidence_snapshots.append(annotated_rgb)

                    progress.progress((idx + 1) / len(optimized_frames))

                st.success(
                    f"Sequence Complete! {hazards_found} unique road hazards logged to the LGU database."
                )

                # NEW: Render the gallery at the end of the Mapillary scan
                if evidence_snapshots:
                    st.subheader("Captured Mapillary Hazards")
                    cols = st.columns(3)
                    for idx, snap in enumerate(evidence_snapshots):
                        cols[idx % 3].image(snap, use_container_width=True)
else:
    st.info("Search a street above or click directly on a road line on the map to begin.")