import os
import math
import cv2
import numpy as np
import streamlit as st
from ultralytics import YOLO

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OBSTACLE_MODEL_PATH = os.path.join(BASE_DIR, "best (1).pt")
DAMAGE_MODEL_PATH = os.path.join(BASE_DIR, "RDD.pt")
SEG_MODEL_PATH = os.path.join(BASE_DIR, "road_seg.pt")

LOCAL_FALLBACK_TOKEN = ""

CLASS_MAP = {
    "D00": ("Longitudinal Crack", "MEDIUM", (0, 165, 255)),
    "D10": ("Transverse Crack", "MEDIUM", (0, 165, 255)),
    "D20": ("Alligator Crack", "CRITICAL", (0, 0, 255)),
    "D40": ("Pothole", "CRITICAL", (0, 0, 255)),
    "Block crack": ("Block Crack", "MEDIUM", (0, 165, 255)),
    "Repair": ("Repaired Surface", "LOW", (0, 200, 0)),
    "Obstacle": ("Road Obstacle", "MEDIUM", (0, 165, 255)),
    "Pothole": ("Pothole", "CRITICAL", (0, 0, 255)),
}


def get_mapillary_token():
    try:
        token = st.secrets.get("MAPILLARY_TOKEN", "")
        if token and "paste_your" not in token:
            return token.strip()
    except Exception:
        pass
    return os.environ.get("MAPILLARY_TOKEN", LOCAL_FALLBACK_TOKEN).strip()


@st.cache_resource
def load_models():
    obs_model = YOLO(OBSTACLE_MODEL_PATH)
    dmg_model = YOLO(DAMAGE_MODEL_PATH)
    seg_model = YOLO(SEG_MODEL_PATH)
    return obs_model, dmg_model, seg_model


def _compute_iou(box_a, box_b):
    x_a = max(box_a[0], box_b[0])
    y_a = max(box_a[1], box_b[1])
    x_b = min(box_a[2], box_b[2])
    y_b = min(box_a[3], box_b[3])
    inter = max(0.0, x_b - x_a) * max(0.0, y_b - y_a)
    if inter <= 0:
        return 0.0
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    return inter / float(area_a + area_b - inter + 1e-6)


def analyze_road_frame(frame, conf=0.40):
    img_h, img_w = frame.shape[:2]
    annotated = frame.copy()
    mask = np.zeros((img_h, img_w), dtype=np.uint8)

    obs_model, dmg_model, seg_model = load_models()

    # DYNAMIC SEGMENTATION MASKING
    seg_res = seg_model.predict(frame, conf=0.25, verbose=False)[0]
    has_dynamic_mask = False

    if seg_res.masks is not None:
        for poly in seg_res.masks.xy:
            poly_pts = np.array(poly, dtype=np.int32)
            if len(poly_pts) > 2:
                cv2.fillPoly(mask, [poly_pts], 255)
                cv2.polylines(annotated, [poly_pts], isClosed=True, color=(0, 255, 255), thickness=2)
                has_dynamic_mask = True

        if has_dynamic_mask:
            cv2.putText(annotated, "Dynamic AI Zone", (int(img_w * 0.36), int(img_h * 0.53)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

    # STATIC FALLBACK (Triggers if the segmentation AI fails to find the road in a specific frame)
    if not has_dynamic_mask:
        pts = np.array([[
            [int(img_w * 0.05), int(img_h * 0.45)],
            [int(img_w * 0.95), int(img_h * 0.45)],
            [img_w, int(img_h * 0.75)],
            [0, int(img_h * 0.75)]
        ]], dtype=np.int32)
        cv2.fillPoly(mask, pts, 255)
        cv2.polylines(annotated, [pts], isClosed=True, color=(0, 255, 255), thickness=2)
        cv2.putText(annotated, "Static AI Zone (Fallback)", (int(img_w * 0.36), int(img_h * 0.53)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

    road_frame = cv2.bitwise_and(frame, frame, mask=mask)

    # RUN HAZARD MODELS ON MASKED ROAD
    obs_res = obs_model.predict(road_frame, conf=conf, classes=[2, 6, 8], verbose=False)[0]
    dmg_res = dmg_model.predict(road_frame, conf=conf, verbose=False)[0]

    # Extract Road-barrier coordinates first for suppression
    barrier_boxes = []
    for box in obs_res.boxes:
        cls_id = int(box.cls[0].item())
        if obs_res.names[cls_id] == 'Road-barrier':
            barrier_boxes.append(box.xyxy[0].cpu().numpy().tolist())

    candidates = []
    for res in (obs_res, dmg_res):
        for box in res.boxes:
            cls_id = int(box.cls[0].item())
            raw_name = res.names[cls_id]

            if raw_name == 'Road-barrier':
                continue
            if raw_name not in CLASS_MAP:
                continue

            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().tolist()
            box_w = x2 - x1
            box_h = y2 - y1
            box_area = box_w * box_h
            img_area = img_w * img_h

            # Barrier Suppression Filter
            is_on_barrier = False
            for b_box in barrier_boxes:
                inter_w = max(0.0, min(x2, b_box[2]) - max(x1, b_box[0]))
                inter_h = max(0.0, min(y2, b_box[3]) - max(y1, b_box[1]))
                inter_area = inter_w * inter_h
                if (inter_area / (box_area + 1e-6)) > 0.40:
                    is_on_barrier = True
                    break

            if is_on_barrier:
                continue

            if box_h > (box_w * 1.5):
                continue
            if box_w > (img_w * 0.85):
                continue

            score = float(box.conf[0].item())
            disp_name, severity, color = CLASS_MAP[raw_name]
            candidates.append({
                "bbox": [x1, y1, x2, y2],
                "conf": score,
                "name": disp_name,
                "severity": severity,
                "color": color,
            })

    candidates.sort(key=lambda d: d["conf"], reverse=True)
    kept = []
    for cand in candidates:
        if any(_compute_iou(cand["bbox"], prev["bbox"]) > 0.60 for prev in kept):
            continue
        kept.append(cand)

    for det in kept:
        x1, y1, x2, y2 = map(int, det["bbox"])
        color = det["color"]
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        label = f"{det['name']} {det['conf']:.2f}"
        cv2.putText(annotated, label, (x1, max(20, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

    return annotated, kept


def haversine_meters(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))