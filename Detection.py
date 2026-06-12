import cv2
import time
import os
import shutil
import numpy as np
import threading
import json
import random
import paho.mqtt.client as mqtt

from ultralytics import YOLO
from PIL import ImageFont, ImageDraw, Image

# Lane drawing module (Bilal's file)
from lane_drawing import draw_lanes_mode, load_lanes
import lane_drawing

# -------------------------------------------------------
# Arabic names and plate generator (used for violations)
# -------------------------------------------------------
ARABIC_NAMES = [
    "احمد الزوي", "محمد الشريف", "عمر بالقاسم", "يوسف المبروك",
    "خالد الفيتوري", "ابراهيم البوسيفي", "علي الطاهر", "سالم الورفلي",
    "عبدالله الهروني", "مصطفى الغرياني", "حسين الدرسي", "طارق العجيلي",
    "نور الدين الكيلاني", "رمضان الزنتاني", "صالح المحجوب",
]

def generate_plate():
    """Generate a Libyan-style random licence plate: 3 digits + 3 letters."""
    letters = "ABCDEFGHJKLMNPRSTUVWXYZ"
    nums = str(random.randint(100, 999))
    lets = "".join(random.choices(letters, k=3))
    return f"{nums}-{lets}"

# -------------------------------------------------------
# Violation queue — Detection fills it, Ticket GUI reads it
# -------------------------------------------------------
# Each item is a dict:
# {
#   "timestamp": str,
#   "lane": str,
#   "plate": str,
#   "driver": str,
#   "vehicle_image_path": str,   # path to the saved PNG crop
#   "snapshot_path": str,        # path to the full-frame screenshot
# }
violation_queue = []
violation_lock = threading.Lock()

VIOLATIONS_DIR = "violations"
os.makedirs(VIOLATIONS_DIR, exist_ok=True)

# -------------------------------------------------------
# Model / font helpers
# -------------------------------------------------------
def load_model():
    return YOLO("yolov8n.pt")

def load_font():
    try:
        return ImageFont.truetype("arial.ttf", 18)
    except OSError:
        return ImageFont.load_default()

def open_video(path):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {path}")
    return cap

# -------------------------------------------------------
# MQTT setup
# -------------------------------------------------------
BROKER_ADDRESS = "broker.hivemq.com"
MQTT_TOPIC     = "iot/traffic/lights/faraj123"

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
try:
    mqtt_client.connect(BROKER_ADDRESS, 1883, 60)
    mqtt_client.loop_start()
    print("Connected to MQTT broker.")
except Exception as exc:
    print(f"MQTT connection failed: {exc}")

# -------------------------------------------------------
# Traffic light state
# -------------------------------------------------------
LANES          = ["North", "East", "South", "West"]
BASE_GREEN     = 5      # seconds
TIME_PER_CAR   = 2      # extra seconds per waiting car

current_lane_idx    = 0
last_switch_time    = time.time()
current_green_dur   = BASE_GREEN
cars_in_lanes_global = {lane: 0 for lane in LANES}

def publish_state(states, duration, lane):
    payload = {**{l: states[l] for l in LANES}, "Duration": duration, "Lane": lane}
    mqtt_client.publish(MQTT_TOPIC, json.dumps(payload))

# -------------------------------------------------------
# Snapshot cleanup (clears 'breaks' folder every 60 s)
# -------------------------------------------------------
BREAKS_DIR = r"C:\ProgramData\SmartTraffic\breaks"
os.makedirs(BREAKS_DIR, exist_ok=True)

def _cleanup_worker():
    while True:
        time.sleep(60)
        if os.path.exists(BREAKS_DIR):
            shutil.rmtree(BREAKS_DIR)
        os.makedirs(BREAKS_DIR)

threading.Thread(target=_cleanup_worker, daemon=True).start()

# -------------------------------------------------------
# Line-intersection math
# -------------------------------------------------------
def _ccw(a, b, c):
    return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])

def lines_intersect(p1, p2, q1, q2):
    return (_ccw(p1, q1, q2) != _ccw(p2, q1, q2) and
            _ccw(p1, p2, q1) != _ccw(p1, p2, q2))

def crossed_always_green(prev_pos, curr_pos, lane_name):
    for (p1, p2) in lane_drawing.always_green_lines.get(lane_name, []):
        if lines_intersect(prev_pos, curr_pos, p1, p2):
            return True
    return False

# -------------------------------------------------------
# Car tracking state (reset per lane run)
# -------------------------------------------------------
prev_cars   = {}
next_car_id = 0
MAX_MATCH   = 50   # px

snapshot_count = 0

# -------------------------------------------------------
# Core detection function
# -------------------------------------------------------
def detect_cars(frame, model, states, active_lane=None):
    global snapshot_count, prev_cars, next_car_id, cars_in_lanes_global

    results = model(frame, classes=[2], verbose=False)

    current_cars_in_lanes = {lane: 0 for lane in LANES}
    polys  = lane_drawing.lanes_polygons
    glines = lane_drawing.always_green_lines

    # Draw lane polygons
    for lane_name, poly in polys.items():
        if poly is None:
            continue
        if active_lane is not None and lane_name != active_lane:
            continue
        color = (0, 255, 0) if states[lane_name] == "GREEN" else (0, 0, 255)
        cv2.polylines(frame, [poly], True, color, 2)

    # Draw always-green lines
    for lane_name, line_list in glines.items():
        if active_lane is not None and lane_name != active_lane:
            continue
        for (p1, p2) in line_list:
            cv2.line(frame, p1, p2, (255, 255, 255), 2)

    # Parse detections
    dets = []
    for r in results:
        for box in r.boxes:
            if float(box.conf[0]) > 0.3:
                x1, y1, x2, y2 = box.xyxy[0].int().tolist()
                if x2 > x1 and y2 > y1:
                    dets.append((x1, y1, x2, y2))

    centers = [((x1 + x2) // 2, (y1 + y2) // 2) for (x1, y1, x2, y2) in dets]

    # Hungarian-lite: nearest-centroid matching
    matched_ids = {}
    used_prev   = set()
    for idx, (cx, cy) in enumerate(centers):
        best_id, best_dist = None, MAX_MATCH
        for car_id, data in prev_cars.items():
            if car_id in used_prev:
                continue
            px, py = data["pos"]
            d = ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5
            if d < best_dist:
                best_dist, best_id = d, car_id
        if best_id is not None:
            matched_ids[idx] = best_id
            used_prev.add(best_id)
        else:
            matched_ids[idx] = next_car_id
            next_car_id += 1

    new_prev = {}
    for idx, (x1, y1, x2, y2) in enumerate(dets):
        cx, cy   = centers[idx]
        car_id   = matched_ids[idx]

        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(frame, "car", (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

        inside_lane = None
        for lane_name, poly in polys.items():
            if poly is not None and cv2.pointPolygonTest(poly, (cx, cy), False) >= 0:
                inside_lane = lane_name
                current_cars_in_lanes[lane_name] += 1
                break

        prev_state = prev_cars.get(car_id, {"lane": None, "inside": False, "pos": (cx, cy)})
        new_prev[car_id] = {"lane": inside_lane, "inside": inside_lane is not None, "pos": (cx, cy)}

        # Violation: car was inside lane, now outside
        if prev_state["inside"] and not new_prev[car_id]["inside"]:
            lane_name = prev_state["lane"]
            if lane_name:
                if active_lane is not None and lane_name != active_lane:
                    continue
                if crossed_always_green(prev_state["pos"], (cx, cy), lane_name):
                    continue
                if states[lane_name] == "RED":
                    _save_violation(frame, x1, y1, x2, y2, lane_name)

    prev_cars = new_prev
    cars_in_lanes_global = current_cars_in_lanes
    return frame, len(dets)


def _save_violation(frame, x1, y1, x2, y2, lane_name):
    global snapshot_count
    snapshot_count += 1

    ts        = time.strftime("%Y%m%d_%H%M%S")
    plate     = generate_plate()
    driver    = random.choice(ARABIC_NAMES)
    ts_human  = time.strftime("%Y-%m-%d %H:%M:%S")

    # Crop of the offending car
    car_crop  = frame[max(0, y1):y2, max(0, x1):x2]
    crop_name = f"{VIOLATIONS_DIR}/{lane_name}_{ts}_{snapshot_count}_crop.png"
    cv2.imwrite(crop_name, car_crop)

    # Full-frame screenshot
    snap_name = f"{VIOLATIONS_DIR}/{lane_name}_{ts}_{snapshot_count}_scene.png"
    cv2.imwrite(snap_name, frame)

    # Also save to legacy 'breaks' folder
    cv2.imwrite(f"{BREAKS_DIR}/{lane_name}_snapshot_{snapshot_count}.jpg", car_crop)

    record = {
        "timestamp":          ts_human,
        "lane":               lane_name,
        "plate":              plate,
        "driver":             driver,
        "vehicle_image_path": crop_name,
        "snapshot_path":      snap_name,
    }

    with violation_lock:
        violation_queue.append(record)

    # Persist to JSON log
    log_path = r"C:\\ProgramData\\SmartTraffic\\violations_log.json"
    log = []
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                log = json.load(f)
        except Exception:
            log = []
    log.append(record)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    print(f"[VIOLATION] {lane_name} | {plate} | {driver} | {ts_human}")

# -------------------------------------------------------
# HUD overlay
# -------------------------------------------------------
def overlay_info(frame, fps, cars_in_frame, cars_per_second, font):
    pil   = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("RGBA")
    layer = Image.new("RGBA", pil.size, (0, 0, 0, 0))
    d     = ImageDraw.Draw(layer)
    d.rectangle([(5, 5), (200, 100)], fill=(0, 0, 0, 70), outline=(200, 200, 200), width=1)
    pil = Image.alpha_composite(pil, layer)
    d   = ImageDraw.Draw(pil)
    d.text((15, 12), f"FPS: {fps:.1f}",               font=font, fill=(255, 255, 255))
    d.text((15, 38), f"Cars in frame: {cars_in_frame}", font=font, fill=(255, 255, 0))
    d.text((15, 62), f"Cars/sec: {cars_per_second}",    font=font, fill=(255, 165, 0))
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGBA2BGR)

# -------------------------------------------------------
# Per-lane video runner
# -------------------------------------------------------
def run_lane_video(lane_name, video_path, model, font, duration, states, frame_rate=5):
    """Process one video for the given lane for 'duration' seconds.
    Returns max car count, or -1 if user pressed Q."""
    global prev_cars, next_car_id
    prev_cars   = {}
    next_car_id = 0

    cap        = open_video(video_path)
    start      = time.time()
    prev_tick  = 0
    max_cars   = 0
    cars_sec   = 0
    last_sec   = time.time()
    cps_disp   = 0

    while True:
        elapsed   = time.time() - start
        remaining = duration - elapsed
        if remaining <= 0:
            break

        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue

        tick_delta = time.time() - prev_tick
        if tick_delta < 1.0 / frame_rate:
            if cv2.waitKey(1) & 0xFF == ord('q'):
                cap.release()
                return -1
            continue

        prev_tick = time.time()
        frame     = cv2.resize(frame, (640, 384))
        frame, n  = detect_cars(frame, model, states, active_lane=lane_name)

        max_cars  = max(max_cars, cars_in_lanes_global.get(lane_name, 0))
        cars_sec += n
        if time.time() - last_sec >= 1.0:
            cps_disp = cars_sec
            cars_sec = 0
            last_sec = time.time()

        fps   = 1.0 / max(tick_delta, 1e-6)
        frame = overlay_info(frame, fps, n, cps_disp, font)

        green_lane = next((l for l, s in states.items() if s == "GREEN"), "?")
        cv2.putText(frame, f"GREEN: {green_lane}  |  Detecting: {lane_name}",
                    (10, 370), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
        cv2.putText(frame, f"Switch in: {int(remaining)}s",
                    (460, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2)

        cv2.imshow("Smart Traffic - YOLOv8", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            cap.release()
            return -1
        elif key == ord('l'):
            draw_lanes_mode(frame)
            load_lanes()

    cap.release()
    print(f"Lane {lane_name} done — max cars seen: {max_cars}")
    return max_cars

# -------------------------------------------------------
# Video paths (one per lane — swap in real feeds later)
# -------------------------------------------------------
LANE_VIDEOS = {
    "North": "Test_Traffic_4.mp4",
    "East":  "Test_Traffic_4.mp4",
    "South": "Test_Traffic_4.mp4",
    "West":  "Test_Traffic_4.mp4",
}

# -------------------------------------------------------
# Entry point
# -------------------------------------------------------
if __name__ == "__main__":
    load_lanes()
    model = load_model()
    font  = load_font()

    idx       = 0
    green_dur = BASE_GREEN

    while True:
        green_lane  = LANES[idx]
        next_idx    = (idx + 1) % len(LANES)
        detect_lane = LANES[next_idx]

        states = {lane: "RED" for lane in LANES}
        states[green_lane] = "GREEN"

        publish_state(states, green_dur, green_lane)
        print(f"\n{'='*42}")
        print(f"  GREEN: {green_lane}  ({green_dur}s)   Detecting: {detect_lane}")
        print(f"{'='*42}")

        result = run_lane_video(
            detect_lane, LANE_VIDEOS[detect_lane],
            model, font, duration=green_dur, states=states
        )

        if result == -1:
            break

        cars_in_lanes_global[detect_lane] = result
        idx       = next_idx
        green_dur = BASE_GREEN + result * TIME_PER_CAR

        print(f"Cars per lane: {cars_in_lanes_global}")

    cv2.destroyAllWindows()

