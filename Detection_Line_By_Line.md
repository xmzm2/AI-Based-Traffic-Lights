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
11: from ultralytics import YOLO
12: from PIL import ImageFont, ImageDraw, Image
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
77: mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
78: try:
79:     mqtt_client.connect(BROKER_ADDRESS, 1883, 60)
80:     mqtt_client.loop_start()
81:     print("Connected to MQTT broker.")
```
* **Lines 74-75:** Defines the public server (`broker.hivemq.com`) and the specific "channel" (`iot/traffic/lights/faraj123`) to send messages to the ESP32.
* **Lines 77-83:** Creates the MQTT client, attempts to connect, and starts a background thread (`loop_start()`) to handle the connection.

## 6. Traffic Light State Variables
```python
88: LANES          = ["North", "East", "South", "West"]
89: BASE_GREEN     = 5      # seconds
90: TIME_PER_CAR   = 2      # extra seconds per waiting car
92: current_lane_idx    = 0
94: current_green_dur   = BASE_GREEN
95: cars_in_lanes_global = {lane: 0 for lane in LANES}
97: def publish_state(states, duration, lane):
98:     payload = {**{l: states[l] for l in LANES}, "Duration": duration, "Lane": lane}
99:     mqtt_client.publish(MQTT_TOPIC, json.dumps(payload))
```
* **Lines 88-90:** Constants for how the system cycles: base green time is 5 seconds, and every waiting car adds 2 extra seconds.
* **Lines 92-95:** Tracks which lane is currently green, how long it should stay green, and a dictionary storing how many cars are waiting in each lane.
* **Lines 97-99:** A helper function that packages the current light colors into a JSON string and publishes it to the ESP32 over MQTT.

## 7. Cleanup Worker (Legacy Breaks Folder)
```python
104: BREAKS_DIR = r"C:\ProgramData\SmartTraffic\breaks"
107: def _cleanup_worker():
108:     while True:
109:         time.sleep(60)
110:         if os.path.exists(BREAKS_DIR):
111:             shutil.rmtree(BREAKS_DIR)
112:         os.makedirs(BREAKS_DIR)
114: threading.Thread(target=_cleanup_worker, daemon=True).start()
```
* **Lines 104-114:** Creates a background thread that wakes up every 60 seconds and completely deletes and recreates the `breaks` folder to prevent the hard drive from filling up with old images.

## 8. Core AI Function (`detect_cars`)
```python
144: def detect_cars(frame, model, states, active_lane=None):
147:     results = model(frame, classes=[2], verbose=False)
```
* **Line 144:** The function that processes a single image frame.
* **Line 147:** Runs YOLO on the frame, asking it to only look for `class 2` (cars) and keeping the console output quiet (`verbose=False`).

### Drawing Polygons and Colors
```python
154:     for lane_name, poly in polys.items():
157:         if active_lane is not None and lane_name != active_lane:
158:             continue
159:         if states[lane_name] == "GREEN":
160:             color = (0, 255, 0)
161:         elif states[lane_name] == "YELLOW":
162:             color = (0, 255, 255)
163:         else:
164:             color = (0, 0, 255)
165:         cv2.polylines(frame, [poly], True, color, 2)
```
* **Lines 154-165:** Loops through the saved lane polygons. It skips polygons that don't belong to the active video. It draws the polygon **Green** if the light is GREEN, **Yellow** if the light is YELLOW, and **Red** otherwise.

### Filtering Detections and Car Tracking
```python
178:     centers = [((x1 + x2) // 2, (y1 + y2) // 2) for (x1, y1, x2, y2) in dets]
181:     matched_ids = {}
...
188:             d = ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5
```
* **Line 178:** Calculates the exact center point (cx, cy) of every detected car.
* **Lines 181-197:** Compares every car's current center point to the center points from the *previous* frame using the Pythagorean theorem. If a match is found, the car keeps its old ID.

### Checking for Violations
```python
218:         if prev_state["inside"] and not new_prev[car_id]["inside"]:
...
226:                 if states[lane_name] == "RED":
227:                     _save_violation(frame, x1, y1, x2, y2, lane_name)
```
* **Line 218:** The core violation logic: "Was the car inside the lane in the last frame, but outside the lane in this frame?" (meaning it crossed the line).
* **Line 226:** If it crossed the line **AND** the light is strictly RED, call `_save_violation` to record the ticket. (It ignores YELLOW and GREEN lights).

## 9. Processing a Video (`run_lane_video`)
```python
300: def run_lane_video(lane_name, video_path, model, font, duration, states, frame_rate=5):
320:     while True:
321:         elapsed   = time.time() - start
322:         remaining = duration - elapsed
323:         if remaining <= 0:
324:             break
```
* **Line 300:** Processes a video for a limited amount of time (`duration`).
* **Line 320-324:** Constantly checks if the assigned duration has expired. If it has, the loop ends.

### Yellow Light Transition Logic
```python
326:         # In the last 1 second, transition the GREEN light to YELLOW seamlessly
327:         if remaining <= 1.0 and "GREEN" in states.values():
328:             gl = next(l for l, s in states.items() if s == "GREEN")
329:             states[gl] = "YELLOW"
330:             states[lane_name] = "YELLOW"
331:             publish_state(states, 1, f"{gl} & {lane_name}")
```
* **Lines 326-331:** **This is the synchronized yellow light logic.** When there is only 1.0 second left on the timer, it finds the currently `"GREEN"` lane (`gl`) and the upcoming lane (`lane_name`). It sets BOTH of their states to `"YELLOW"`, and blasts an MQTT message to the ESP32. The ESP32 instantly turns on the Yellow LEDs for both lanes. Because this happens *inside* the video loop, the video playback never freezes.

### Dynamic HUD Display
```python
359:         active_lights = [l for l, s in states.items() if s in ("GREEN", "YELLOW")]
360:         active_str = " & ".join(active_lights) if active_lights else "?"
361:         state_str = "GREEN" if "GREEN" in states.values() else ("YELLOW" if "YELLOW" in states.values() else "RED")
362:         cv2.putText(frame, f"{state_str}: {active_str}  |  Detecting: {lane_name}",
363:                     (10, 370), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
```
* **Lines 359-363:** This builds the text in the bottom left of the video. It looks for any active lights (Green or Yellow) and displays them. If multiple lights are active (like during the synchronized yellow phase), it joins them with `&` (e.g. `YELLOW: North & East`).

## 10. The Main Loop (Entry Point)
```python
380: if __name__ == "__main__":
388:     while True:
389:         green_lane  = LANES[idx]
390:         next_idx    = (idx + 1) % len(LANES)
391:         detect_lane = LANES[next_idx]
```
* **Line 388:** An infinite loop that cycles through the traffic lights forever.
* **Lines 389-391:** Figures out which lane is currently green (`green_lane`), and which lane is *next* (`detect_lane`).

```python
393:         states = {lane: "RED" for lane in LANES}
394:         states[green_lane] = "GREEN"
396:         publish_state(states, green_dur, green_lane)
```
* **Lines 393-396:** Sets all lanes to RED, except the `green_lane` which is set to GREEN. Publishes this initial green state to the ESP32.

```python
403:         # We pass duration = green_dur + 1. The last second will automatically transition to YELLOW.
404:         result = run_lane_video(
405:             detect_lane, LANE_VIDEOS[detect_lane],
406:             model, font, duration=green_dur + 1, states=states
407:         )
```
* **Lines 403-407:** Starts playing the video for the next lane (`detect_lane`). The AI will count cars on that lane. Notice we give it `duration = green_dur + 1`. This total time accounts for the regular green phase PLUS the 1-second yellow phase that triggers at the very end of `run_lane_video()`.

```python
412:         cars_in_lanes_global[detect_lane] = result
413:         idx       = next_idx
414:         green_dur = BASE_GREEN + result * TIME_PER_CAR
```
* **Lines 412-414:** The video finished. It saves how many cars were waiting, moves the index to the next lane, and calculates how long the *next* green light should be based on the cars it just counted (`BASE_GREEN + result * TIME_PER_CAR`).
