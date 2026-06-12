import cv2
import numpy as np
import json

lanes_polygons = {"North": None, "South": None, "East": None, "West": None}
always_green_lines = {"North": [], "South": [], "East": [], "West": []}

# -----------------------------

def draw_lanes_mode(frame):
    global lanes_polygons, always_green_lines
    base_frame  = frame.copy()              # clean copy from main screen
    draw_canvas = base_frame.copy()         # drawing canvas
    points = []
    current_lane = None

    def click_event(event, x, y, flags, param):
        nonlocal points, draw_canvas, current_lane
        if current_lane is None:
            return  # block drawing until a lane is selected
        if event == cv2.EVENT_LBUTTONDOWN:
            # polygon points
            points.append((x, y))
            cv2.circle(draw_canvas, (x, y), 5, (0, 255, 0), -1)
            if len(points) > 1:
                cv2.line(draw_canvas, points[-2], points[-1], (0, 255, 0), 2)
        elif event == cv2.EVENT_MBUTTONDOWN:
            # always-green line points
            if len(points) == 0:  # Clear old always-green lines b (was proplamatic so leave dont cahnge it)
                always_green_lines[current_lane] = []

            points.append((x, y))
            cv2.circle(draw_canvas, (x, y), 5, (255, 255, 255), -1)
            if len(points) > 1:
                p1, p2 = points[-2], points[-1]
                always_green_lines[current_lane].append((p1, p2))
                cv2.line(draw_canvas, p1, p2, (255, 255, 255), 2)
        elif event == cv2.EVENT_RBUTTONDOWN:
            if len(points) > 2:
                poly = np.array(points, np.int32)
                lanes_polygons[current_lane] = poly
                cv2.polylines(draw_canvas, [poly], True, (255, 0, 0), 2)
            points = []

    cv2.namedWindow("Draw Lanes")
    cv2.setMouseCallback("Draw Lanes", click_event)

    while True:
        # just copy the canvas each loop,
        display_frame = draw_canvas.copy()

        if current_lane is None:
            cv2.putText(display_frame, "Select lane: N/S/E/W", (20, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        else:
            cv2.putText(display_frame, f"Drawing {current_lane} lane...", (20, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

        cv2.imshow("Draw Lanes", display_frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('n'):
            current_lane = "North"
        elif key == ord('s'):   # i changed so i can use south now save is x
            current_lane = "South"
        elif key == ord('e'):
            current_lane = "East"
        elif key == ord('w'):
            current_lane = "West"
        elif key == ord('x'):  # save all
            save_lanes()
        elif key == ord('q'):  # quit drawing mode
            break

    cv2.destroyWindow("Draw Lanes")

# -----------------------------
def is_in_lane(x, y):
    global lanes_polygons
    for poly in lanes_polygons.values():
        if poly is not None and cv2.pointPolygonTest(poly, (x, y), False) >= 0:
            return True
    return False

# -----------------------------
def save_lanes(filename="lanes.json"):
    global lanes_polygons, always_green_lines

    data = {
        "lanes": {},
        "always_green": {}
    }

    for name in lanes_polygons.keys():
        # overwrite polygon: only keep the latest one
        poly = lanes_polygons[name]
        data["lanes"][name] = poly.tolist() if poly is not None else None

        #  Overwrite Always-Green Lines: only keep the latest ones (again avoid changes here)
        lines = always_green_lines.get(name, [])
        data["always_green"][name] = [[list(p1), list(p2)] for (p1, p2) in lines]

    with open(filename, "w") as f:
        json.dump(data, f)

# -----------------------------
def load_lanes(filename="lanes.json"):
    global lanes_polygons, always_green_lines
    try:
        with open(filename, "r") as f:
            data = json.load(f)
            # overwrite completely with file contents
            lanes_polygons = {
                name: (np.array(poly, np.int32) if poly is not None else None)
                for name, poly in data.get("lanes", {}).items()
            }
            always_green_lines = {
                name: [(tuple(p1), tuple(p2)) for (p1, p2) in data.get("always_green", {}).get(name, [])]
                for name in lanes_polygons.keys()
            }
    except FileNotFoundError:
        # add empty if the file was deletd exists
        lanes_polygons = {"North": None, "South": None, "East": None, "West": None}
        always_green_lines = {"North": [], "South": [], "East": [], "West": []}



#Left click: Draw point
#Right click: Finnish drawing
#Q: exit 
#S: Save