# Detection.py - Line by Line Explanation

This document provides a detailed, line-by-line breakdown of how the `Detection.py` script works.

## 1. Imports
```python
1: import cv2
2: import time
3: import os
4: import shutil
5: import numpy as np
6: import threading
7: import json
8: import random
9: import paho.mqtt.client as mqtt
10: 
11: from ultralytics import YOLO
12: from PIL import ImageFont, ImageDraw, Image
13: 
14: # Lane drawing module (Bilal's file)
15: from lane_drawing import draw_lanes_mode, load_lanes
16: import lane_drawing
```
* **Lines 1-9:** Standard Python libraries. `cv2` (OpenCV) handles video processing. `time` tracks durations. `os` and `shutil` handle file/folder operations. `numpy` handles math/arrays. `threading` runs background tasks. `json` parses data. `random` generates fake ticket info. `mqtt` connects to the ESP32.
* **Lines 11-12:** Imports `YOLO` (AI car detection model) and `PIL` (Pillow library) for drawing nice text on the screen.
* **Lines 14-16:** Imports functions from your custom `lane_drawing.py` script to handle drawing and loading the lane polygons.

## 2. Mock Data Generator (Violations)
```python
21: ARABIC_NAMES = [ ... ]
28: def generate_plate():
29:     """Generate a Libyan-style random licence plate: 3 digits + 3 letters."""
30:     letters = "ABCDEFGHJKLMNPRSTUVWXYZ"
31:     nums = str(random.randint(100, 999))
32:     lets = "".join(random.choices(letters, k=3))
33:     return f"{nums}-{lets}"
```
* **Lines 21-26:** A list of random Arabic names to assign to drivers who run a red light.
* **Lines 28-33:** A function that generates a fake, random license plate string (e.g., "123-ABC") for the violation ticket.

## 3. Violation Queue and Folders
```python
47: violation_queue = []
48: violation_lock = threading.Lock()
49: 
50: VIOLATIONS_DIR = "violations"
51: os.makedirs(VIOLATIONS_DIR, exist_ok=True)
```
* **Line 47:** An empty list that will temporarily hold new violations so the GUI (`Ticket.py`) can read them.
* **Line 48:** A thread lock to ensure that multiple parts of the program don't write to the queue at the exact same time and corrupt the data.
* **Lines 50-51:** Defines the folder where high-quality violation images are saved and creates it if it doesn't exist.

## 4. Helper Functions (Model, Font, Video)
```python
56: def load_model():
57:     return YOLO("yolov8n.pt")
58: 
59: def load_font(): ...
65: def open_video(path): ...
```
* **Lines 56-57:** Loads the YOLOv8 Nano model (the fastest, smallest AI model for object detection).
* **Lines 59-63:** Tries to load the Arial font for the on-screen display. If it fails, it uses a default font.
* **Lines 65-69:** Opens a video file using OpenCV. If the file is missing, it crashes on purpose to let you know immediately.

## 5. MQTT Setup (Communicating with ESP32)
```python
74: BROKER_ADDRESS = "broker.hivemq.com"
75: MQTT_TOPIC     = "iot/traffic/lights/faraj123"
76: 
77: mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
78: try:
79:     mqtt_client.connect(BROKER_ADDRESS, 1883, 60)
80:     mqtt_client.loop_start()
81:     print("Connected to MQTT broker.")
82: except Exception as exc: ...
```
* **Lines 74-75:** Defines the public server (`broker.hivemq.com`) and the specific "channel" (`iot/traffic/lights/faraj123`) to send messages to the ESP32.
* **Lines 77-83:** Creates the MQTT client, attempts to connect, and starts a background thread (`loop_start()`) to handle the connection.

## 6. Traffic Light State Variables
```python
88: LANES          = ["North", "East", "South", "West"]
89: BASE_GREEN     = 5      # seconds
90: TIME_PER_CAR   = 2      # extra seconds per waiting car
91: 
92: current_lane_idx    = 0
93: last_switch_time    = time.time()
94: current_green_dur   = BASE_GREEN
95: cars_in_lanes_global = {lane: 0 for lane in LANES}
96: 
97: def publish_state(states, duration, lane):
98:     payload = {**{l: states[l] for l in LANES}, "Duration": duration, "Lane": lane}
99:     mqtt_client.publish(MQTT_TOPIC, json.dumps(payload))
```
* **Lines 88-90:** Constants for how the system cycles: base green time is 5 seconds, and every waiting car adds 2 extra seconds.
* **Lines 92-95:** Tracks which lane is currently green, when the light last changed, how long it should stay green, and a dictionary storing how many cars are waiting in each lane.
* **Lines 97-99:** A helper function that packages the current light colors into a JSON string and publishes it to the ESP32 over MQTT.

## 7. Cleanup Worker (Legacy Breaks Folder)
```python
104: BREAKS_DIR = r"C:\ProgramData\SmartTraffic\breaks"
105: os.makedirs(BREAKS_DIR, exist_ok=True)
106: 
107: def _cleanup_worker():
108:     while True:
109:         time.sleep(60)
110:         if os.path.exists(BREAKS_DIR):
111:             shutil.rmtree(BREAKS_DIR)
112:         os.makedirs(BREAKS_DIR)
113: 
114: threading.Thread(target=_cleanup_worker, daemon=True).start()
```
* **Lines 104-114:** Creates a background thread that wakes up every 60 seconds and completely deletes and recreates the `breaks` folder to prevent the hard drive from filling up with old images.

## 8. Intersection Math
```python
119: def _ccw(a, b, c): ...
122: def lines_intersect(p1, p2, q1, q2): ...
126: def crossed_always_green(prev_pos, curr_pos, lane_name): ...
```
* **Lines 119-124:** Mathematical functions to check if two line segments cross each other.
* **Lines 126-130:** Checks if the path a car traveled (from its previous position to its current position) crossed over an "always green" line (like a right-turn lane).

## 9. Tracking Variables
```python
135: prev_cars   = {}
136: next_car_id = 0
137: MAX_MATCH   = 50   # px
139: snapshot_count = 0
```
* **Line 135:** A dictionary that remembers where cars were in the previous frame.
* **Line 136-137:** A counter for assigning IDs to new cars, and the maximum pixel distance a car can move between frames to still be considered the "same" car.

## 10. Core AI Function (`detect_cars`)
```python
144: def detect_cars(frame, model, states, active_lane=None):
145:     global snapshot_count, prev_cars, next_car_id, cars_in_lanes_global
147:     results = model(frame, classes=[2], verbose=False)
```
* **Line 144:** The function that processes a single image frame.
* **Line 147:** Runs YOLO on the frame, asking it to only look for `class 2` (cars) and keeping the console output quiet (`verbose=False`).

### Drawing Polygons
```python
154:     for lane_name, poly in polys.items():
157:         if active_lane is not None and lane_name != active_lane:
158:             continue
159:         color = (0, 255, 0) if states[lane_name] == "GREEN" else (0, 0, 255)
160:         cv2.polylines(frame, [poly], True, color, 2)
```
* **Lines 154-160:** Loops through the saved lane polygons. It skips any polygons that don't belong to the video currently playing (`active_lane`). It draws the polygon green if the light is green, otherwise red. (Lines 163-167 do the same for the white always-green lines).

### Filtering AI Detections
```python
169:     dets = []
170:     for r in results:
171:         for box in r.boxes:
172:             if float(box.conf[0]) > 0.3:
173:                 x1, y1, x2, y2 = box.xyxy[0].int().tolist()
174:                 if x2 > x1 and y2 > y1:
175:                     dets.append((x1, y1, x2, y2))
```
* **Lines 169-176:** Extracts the bounding boxes from YOLO's results, throwing away anything with less than 30% confidence to avoid false positives.

### Centroid Matching (Car Tracking)
```python
178:     centers = [((x1 + x2) // 2, (y1 + y2) // 2) for (x1, y1, x2, y2) in dets]
181:     matched_ids = {}
...
188:             d = ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5
189:             if d < best_dist: ...
```
* **Line 178:** Calculates the exact center point (cx, cy) of every detected car.
* **Lines 181-197:** Compares every car's current center point to the center points from the *previous* frame. It uses the Pythagorean theorem (Line 188) to find the closest match. If a match is found, the car keeps its old ID. If no match is found, it gets a new ID.

### Checking for Violations
```python
208:         inside_lane = None
209:         for lane_name, poly in polys.items():
210:             if poly is not None and cv2.pointPolygonTest(poly, (cx, cy), False) >= 0:
...
218:         if prev_state["inside"] and not new_prev[car_id]["inside"]:
...
226:                 if states[lane_name] == "RED":
227:                     _save_violation(frame, x1, y1, x2, y2, lane_name)
```
* **Lines 208-213:** Uses a math function (`pointPolygonTest`) to see if the car's center point is physically inside the lane polygon on the screen.
* **Line 218:** The core violation logic: "Was the car inside the lane in the last frame, but outside the lane in this frame?" (meaning it crossed the line).
* **Line 226:** If it crossed the line AND the light is RED, call `_save_violation` to record the ticket.

## 11. Saving Violations
```python
234: def _save_violation(frame, x1, y1, x2, y2, lane_name):
238:     ts        = time.strftime("%Y%m%d_%H%M%S")
239:     plate     = generate_plate()
240:     driver    = random.choice(ARABIC_NAMES)
...
244:     car_crop  = frame[max(0, y1):y2, max(0, x1):x2]
245:     crop_name = f"{VIOLATIONS_DIR}/{lane_name}_{ts}_{snapshot_count}_crop.png"
246:     cv2.imwrite(crop_name, car_crop)
...
255:     record = {
256:         "timestamp":          ts_human,
257:         "lane":               lane_name, ...
264:     with violation_lock:
265:         violation_queue.append(record)
...
277:     with open(log_path, "w", encoding="utf-8") as f:
278:         json.dump(log, f, ensure_ascii=False, indent=2)
```
* **Lines 238-240:** Generates the timestamp and fake driver data.
* **Lines 244-250:** Crops the image to just the car, and saves both the crop and the full screenshot to the hard drive.
* **Lines 255-262:** Packages all the data into a Python dictionary.
* **Lines 264-265:** Adds the dictionary to the queue so the GUI can see it.
* **Lines 268-278:** Opens `violations_log.json`, adds the new ticket to the list, and saves the file back to the hard drive.

## 12. Processing a Video (`run_lane_video`)
```python
300: def run_lane_video(lane_name, video_path, model, font, duration, states, frame_rate=5):
307:     cap        = open_video(video_path)
308:     start      = time.time()
...
315:     while True:
316:         elapsed   = time.time() - start
317:         remaining = duration - elapsed
318:         if remaining <= 0:
319:             break
```
* **Line 300:** This function processes a video for one specific lane for a limited amount of time (`duration`).
* **Line 315-319:** A loop that constantly checks if the assigned "green time" (`duration`) has expired. If it has, the loop `break`s (ends), moving the system on to the next lane.
* **Line 321-324:** Reads the next frame. If the video ended, it loops back to the start (`POS_FRAMES, 0`).
* **Line 327-331:** Skips frames so that the AI only processes e.g. 5 frames per second (to save CPU power).
* **Line 335:** Calls the AI function `detect_cars()` to do the heavy lifting.
* **Line 353:** Shows the final annotated frame on your screen using `cv2.imshow()`.

## 13. The Main Loop (Entry Point)
```python
380: if __name__ == "__main__":
381:     load_lanes()
382:     model = load_model()
...
388:     while True:
389:         green_lane  = LANES[idx]
390:         next_idx    = (idx + 1) % len(LANES)
391:         detect_lane = LANES[next_idx]
...
396:         publish_state(states, green_dur, green_lane)
...
401:         result = run_lane_video(
402:             detect_lane, LANE_VIDEOS[detect_lane],
403:             model, font, duration=green_dur, states=states
404:         )
...
409:         cars_in_lanes_global[detect_lane] = result
410:         idx       = next_idx
411:         green_dur = BASE_GREEN + result * TIME_PER_CAR
```
* **Line 380:** This means "if you run this script directly, start here."
* **Lines 381-382:** Loads the lanes from the JSON file and spins up the AI model.
* **Line 388:** An infinite loop that cycles through the traffic lights forever.
* **Lines 389-391:** Figures out which lane is currently green, and which lane is *next* (the one we need to detect cars in right now).
* **Line 396:** Tells the ESP32 via MQTT that the lights have changed.
* **Lines 401-404:** Starts playing the video for the next lane, letting the AI count the cars for the duration of the current green light.
* **Lines 409-411:** The video finished (green light expired). It saves how many cars were waiting, updates the index to move to the next lane, and calculates how long the *next* green light should be based on the cars it just counted (`BASE_GREEN + result * TIME_PER_CAR`).
