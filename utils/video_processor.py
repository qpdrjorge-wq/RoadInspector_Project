import cv2
from utils.detector import analyze_road_frame
from utils.db_manager import init_db, insert_report
import os
import uuid


def process_uploaded_video(input_path, frame_placeholder, progress_bar, lat=None, lon=None):
    init_db()
    cap = cv2.VideoCapture(input_path)

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1

    stride = max(1, int(round(fps / 5.0)))

    frame_idx = 0
    hazards_logged = 0
    last_logged_sec = {}

    # NEW: Keep track of the highest confidence score we've seen recently
    last_logged_conf = {}
    evidence_snapshots = []

    while cap.isOpened():
        if frame_idx % stride != 0:
            if not cap.grab():
                break
            frame_idx += 1
            continue

        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1
        current_sec = frame_idx / fps

        annotated_bgr, detections = analyze_road_frame(frame, conf=0.40)
        annotated_rgb = cv2.cvtColor(annotated_bgr, cv2.COLOR_BGR2RGB)
        frame_placeholder.image(annotated_rgb, use_container_width=True)

        logged_this_frame = False
        for det in detections:
            h_name = det["name"]
            conf = det["conf"]

            # 1. Has a full second passed since we saw this type of hazard?
            time_passed = (current_sec - last_logged_sec.get(h_name, -999.0)) >= 1.0

            # 2. Or, are we getting a HIGHER confidence view of a hazard we just saw?
            better_view = conf > last_logged_conf.get(h_name, 0.0)

            # If either is true, snap the photo and log it to the database
            if time_passed or better_view:
                os.makedirs("evidence", exist_ok=True)
                img_path = f"evidence/dashcam_{uuid.uuid4().hex[:6]}.jpg"

                cv2.imwrite(img_path, annotated_bgr)
                insert_report(h_name, det["severity"], lat=lat, lon=lon, image_path=img_path)

                # Reset the timers and update the highest confidence score
                last_logged_sec[h_name] = current_sec
                last_logged_conf[h_name] = conf

                hazards_logged += 1
                logged_this_frame = True

        if logged_this_frame:
            evidence_snapshots.append(annotated_rgb)

        progress_bar.progress(min(frame_idx / total_frames, 1.0))

    cap.release()
    progress_bar.progress(1.0)
    return hazards_logged, evidence_snapshots