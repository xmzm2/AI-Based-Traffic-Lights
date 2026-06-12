"""
Ticket.py — Traffic Violation Ticket Printer
=============================================
This file does 3 things:
  1. Reads violations saved by Detection.py from a JSON file
  2. Shows them in a simple GUI table with images
  3. Prints a receipt to a thermal USB printer

The JSON file acts as our database — no SQL needed.
Location: C:\\ProgramData\\SmartTraffic\\violations_log.json
"""

import sys
import os
import json
import io
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QLabel, QPushButton, QLineEdit,
    QSplitter, QHeaderView, QMessageBox, QScrollArea, QGroupBox,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui  import QPixmap, QFont

# Try to import the Windows printer library
# If it's not installed, printing will be disabled but everything else works
try:
    import win32print
    import win32ui
    from PIL import ImageWin
    CAN_PRINT = True
except ImportError:
    CAN_PRINT = False


# =============================================================================
# SETTINGS — change these if you move files around
# =============================================================================

DATA_FOLDER  = r"C:\ProgramData\SmartTraffic"
LOG_FILE     = os.path.join(DATA_FOLDER, "violations_log.json")
RECEIPTS_DIR = os.path.join(DATA_FOLDER, "receipts")
FINE_AMOUNT  = "200 LYD"

# Make sure the folders exist when the program starts
os.makedirs(DATA_FOLDER,  exist_ok=True)
os.makedirs(RECEIPTS_DIR, exist_ok=True)


# =============================================================================
# DRIVER NAMES
# These are randomly assigned to violations in Detection.py
# Written in English transliteration — no special Arabic library needed
# =============================================================================

DRIVER_NAMES = [
    "Ahmed Al-Zawawi",     "Mohamed Al-Sharif",   "Omar Belqasem",
    "Youssef Al-Mabrouk",  "Khaled Al-Fituri",    "Ibrahim Al-Busaifi",
    "Ali Al-Taher",        "Salem Al-Warfalli",   "Abdullah Al-Harouni",
    "Mustafa Al-Ghiryani", "Hussein Al-Darsi",    "Tarek Al-Ojaili",
    "Noureddine Al-Kilani","Ramadan Al-Zintani",  "Saleh Al-Mahjoub",
]


# =============================================================================
# STEP 1 — JSON DATABASE
# Two simple functions: read the file, write the file. That's our database.
# =============================================================================

def read_violations() -> list:
    """Load all violations from the JSON file. Returns empty list if file missing."""
    if not os.path.exists(LOG_FILE):
        return []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def write_violations(records: list):
    """Save the violations list back to the JSON file."""
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


# =============================================================================
# STEP 2 — RECEIPT IMAGE (PIL)
# We draw the receipt as an image using PIL (Pillow).
# Why an image? Because sending an image to the printer is way simpler
# than dealing with raw thermal printer commands (ESC/POS).
# =============================================================================

def load_font(size, bold=False):
    """Try to load Arial, fall back to the default PIL font."""
    font_name = "arialbd.ttf" if bold else "arial.ttf"
    try:
        return ImageFont.truetype(font_name, size)
    except OSError:
        return ImageFont.load_default()

def build_receipt_image(record: dict) -> Image.Image:
    """
    Draw a receipt for one violation and return it as a PIL Image.
    The receipt is 576px wide — that matches an 80mm thermal printer at 203dpi.
    """
    WIDTH   = 576
    PADDING = 20

    # Load fonts at different sizes
    font_big    = load_font(24, bold=True)
    font_bold   = load_font(15, bold=True)
    font_normal = load_font(15)
    font_small  = load_font(13)

    # Define every line on the receipt as (style, text)
    lines = [
        ("big",    "TRAFFIC VIOLATION NOTICE"),
        ("big",    "Libya Traffic Authority"),
        ("line",   None),
        ("bold",   "Ticket No."),
        ("normal", "TKT-" + record.get("timestamp", "").replace(" ","").replace("-","").replace(":","")),
        ("bold",   "Date & Time"),
        ("normal", record.get("timestamp", "N/A")),
        ("line",   None),
        ("bold",   "Driver Name"),
        ("normal", record.get("driver",    "N/A")),
        ("bold",   "Licence Plate"),
        ("normal", record.get("plate",     "N/A")),
        ("bold",   "Lane"),
        ("normal", record.get("lane",      "N/A")),
        ("bold",   "Violation"),
        ("normal", "Running a Red Light"),
        ("bold",   "Fine"),
        ("normal", FINE_AMOUNT),
        ("line",   None),
        ("small",  "Pay within 15 days at any"),
        ("small",  "approved traffic authority office."),
        ("line",   None),
        ("small",  "Printed: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ("small",  "Smart Traffic System v1.0"),
    ]

    # Calculate total height so the image fits perfectly
    height = PADDING * 2
    for style, _ in lines:
        height += 10 if style == "line" else (34 if style == "big" else 28)

    # Create a white image and draw on it
    img  = Image.new("RGB", (WIDTH, height), "white")
    draw = ImageDraw.Draw(img)
    y    = PADDING

    for style, text in lines:
        if style == "line":
            # Draw a horizontal separator line
            draw.line([(PADDING, y + 5), (WIDTH - PADDING, y + 5)], fill="black", width=1)
            y += 10
        elif style == "big":
            # Center the title text
            font = font_big
            text_width = draw.textbbox((0, 0), text, font=font)[2]
            draw.text(((WIDTH - text_width) // 2, y), text, font=font, fill="black")
            y += 34
        elif style == "bold":
            draw.text((PADDING, y), text, font=font_bold, fill=(80, 80, 80))
            y += 28
        elif style == "normal":
            draw.text((PADDING + 10, y), text, font=font_normal, fill="black")
            y += 28
        elif style == "small":
            draw.text((PADDING, y), text, font=font_small, fill=(120, 120, 120))
            y += 28

    # Dashed lines at top and bottom (looks like a real receipt)
    for x in range(0, WIDTH, 8):
        draw.line([(x, 1),        (x + 4, 1)],        fill="black", width=2)
        draw.line([(x, height-2), (x + 4, height-2)], fill="black", width=2)

    return img


# =============================================================================
# STEP 3 — SAVE RECEIPT AS PNG
# Every receipt is saved as a PNG file so you have a copy.
# =============================================================================

def save_receipt_png(record: dict) -> str:
    """Build the receipt image and save it as a PNG. Returns the saved file path."""
    img       = build_receipt_image(record)
    timestamp = record.get("timestamp", "").replace(" ", "_").replace(":", "-")
    plate     = record.get("plate", "UNKNOWN").replace("-", "")
    filepath  = os.path.join(RECEIPTS_DIR, f"receipt_{timestamp}_{plate}.png")
    img.save(filepath)
    return filepath


# =============================================================================
# STEP 4 — SEND TO THERMAL PRINTER (win32print)
# We convert the PIL image and send it directly to the printer.
# win32print handles all the low-level Windows printer communication.
# =============================================================================

def print_receipt(record: dict) -> tuple[bool, str]:
    """
    Print the receipt to the connected USB thermal printer.
    Returns (True, success_message) or (False, error_message).
    """
    if not CAN_PRINT:
        return False, "pywin32 is not installed.\nRun: pip install pywin32"

    img = build_receipt_image(record)

    try:
        # Start with the Windows default printer
        printer_name = win32print.GetDefaultPrinter()

        # If a thermal/USB printer is connected, prefer it
        all_printers = [p[2] for p in win32print.EnumPrinters(2)]
        thermal_keywords = ["thermal", "usb", "pos", "receipt", "epson", "star", "xprinter"]
        for p in all_printers:
            if any(keyword in p.lower() for keyword in thermal_keywords):
                printer_name = p
                break

        # Create a Windows device context (DC) for the printer
        hdc = win32ui.CreateDC()
        hdc.CreatePrinterDC(printer_name)
        hdc.StartDoc("Traffic Violation Receipt")
        hdc.StartPage()

        # Scale image to fit the printer's page width
        page_width  = hdc.GetDeviceCaps(8)   # physical page width in pixels
        scale       = page_width / img.width
        draw_height = int(img.height * scale)

        # Send image to printer
        ImageWin.Dib(img).draw(hdc.GetHandleOutput(), (0, 0, page_width, draw_height))

        hdc.EndPage()
        hdc.EndDoc()
        hdc.DeleteDC()

        return True, f"Printed successfully on: {printer_name}"

    except Exception as error:
        return False, f"Print failed: {error}"


# =============================================================================
# STEP 5 — THE GUI (PyQt6)
# One window with:
#   Left  → table of violations + action buttons
#   Right → vehicle image, scene photo, receipt preview
# =============================================================================

class ViolationApp(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Traffic Violation System")
        self.resize(1200, 740)

        # Our in-memory list of violations (mirrors the JSON file)
        self.violations: list[dict] = read_violations()
        self.selected:   dict | None = None

        self._setup_ui()

        # Check the JSON file every 2 seconds for new violations from Detection.py
        timer = QTimer(self)
        timer.timeout.connect(self._check_for_new_violations)
        timer.start(2000)

    # -------------------------------------------------------------------------
    # UI SETUP
    # -------------------------------------------------------------------------
    def _setup_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # -- Title --
        title = QLabel("Smart Traffic Violation System")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Georgia", 17, QFont.Weight.Bold))
        title.setStyleSheet("color: #c0392b; padding: 4px 0;")
        main_layout.addWidget(title)

        # -- Search bar --
        search_row = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search by plate, driver, lane, or date...")
        self.search_box.setFixedHeight(32)
        self.search_box.textChanged.connect(self._refresh_table)
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(60)
        clear_btn.setFixedHeight(32)
        clear_btn.clicked.connect(lambda: self.search_box.clear())
        search_row.addWidget(QLabel("Search:"))
        search_row.addWidget(self.search_box)
        search_row.addWidget(clear_btn)
        main_layout.addLayout(search_row)

        # -- Split view: left = table, right = detail --
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # ---- LEFT PANEL ----
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 4, 0)

        # The violations table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Time", "Lane", "Plate", "Driver", "Fine"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.selectionModel().selectionChanged.connect(self._on_row_click)
        self.table.setStyleSheet("""
            QTableWidget { font-size: 13px; }
            QHeaderView::section { background: #2c3e50; color: white; font-weight: bold; padding: 4px; }
            QTableWidget::item:selected { background: #2980b9; color: white; }
        """)
        left_layout.addWidget(self.table)

        # Action buttons below the table
        buttons_layout = QHBoxLayout()
        btn_specs = [
            ("Print Receipt", "#27ae60", self._on_print),
            ("Save PNG",      "#2980b9", self._on_save_png),
            ("Delete Record", "#c0392b", self._on_delete),
        ]
        for label, color, handler in btn_specs:
            btn = QPushButton(label)
            btn.setFixedHeight(30)
            btn.setStyleSheet(f"background: {color}; color: white; font-weight: bold; border-radius: 4px;")
            btn.clicked.connect(handler)
            buttons_layout.addWidget(btn)
        left_layout.addLayout(buttons_layout)

        splitter.addWidget(left_panel)

        # ---- RIGHT PANEL ----
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 0, 0, 0)

        # Vehicle crop image
        crop_box = QGroupBox("Vehicle Image")
        crop_layout = QVBoxLayout(crop_box)
        self.vehicle_img = QLabel("Select a record to view.")
        self.vehicle_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vehicle_img.setFixedHeight(155)
        self.vehicle_img.setStyleSheet("background: #12192a; color: #888;")
        crop_layout.addWidget(self.vehicle_img)
        right_layout.addWidget(crop_box)

        # Full scene screenshot
        scene_box = QGroupBox("Scene Screenshot")
        scene_layout = QVBoxLayout(scene_box)
        self.scene_img = QLabel("Select a record to view.")
        self.scene_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scene_img.setFixedHeight(195)
        self.scene_img.setStyleSheet("background: #12192a; color: #888;")
        scene_layout.addWidget(self.scene_img)
        right_layout.addWidget(scene_box)

        # Receipt preview (scrollable in case it's tall)
        receipt_box = QGroupBox("Receipt Preview")
        receipt_layout = QVBoxLayout(receipt_box)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.receipt_preview = QLabel("Select a record to preview.")
        self.receipt_preview.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.receipt_preview.setStyleSheet("background: white; padding: 4px;")
        scroll.setWidget(self.receipt_preview)
        scroll.setFixedHeight(255)
        receipt_layout.addWidget(scroll)
        right_layout.addWidget(receipt_box)

        splitter.addWidget(right_panel)
        splitter.setSizes([600, 460])

        # Dark theme for the whole window
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background: #1e2a38;
                color: #ecf0f1;
                font-family: Segoe UI, Arial;
            }
            QGroupBox {
                border: 1px solid #34495e;
                border-radius: 5px;
                margin-top: 8px;
                padding-top: 6px;
                color: #bdc3c7;
                font-weight: bold;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QLineEdit {
                background: #2c3e50; border: 1px solid #34495e;
                border-radius: 4px; padding: 3px 8px; color: #ecf0f1;
            }
            QPushButton {
                background: #2c3e50; border: 1px solid #34495e;
                border-radius: 4px; padding: 3px 10px; color: #ecf0f1;
            }
            QPushButton:hover { background: #34495e; }
            QTableWidget {
                background: #243342;
                alternate-background-color: #1e2a38;
                gridline-color: #34495e;
            }
            QScrollArea { border: none; }
            QStatusBar  { color: #95a5a6; }
        """)

        self.statusBar().showMessage("Ready — watching for new violations every 2 seconds...")
        self._refresh_table()

    # -------------------------------------------------------------------------
    # LOGIC
    # -------------------------------------------------------------------------

    def _check_for_new_violations(self):
        """Called every 2 seconds. If the JSON file grew, reload and refresh."""
        fresh = read_violations()
        if len(fresh) != len(self.violations):
            self.violations = fresh
            self._refresh_table()
            self.statusBar().showMessage(
                f"Total violations: {len(self.violations)}  |  "
                f"Updated: {datetime.now().strftime('%H:%M:%S')}"
            )

    def _refresh_table(self):
        """Rebuild the table rows, applying any active search filter."""
        query = self.search_box.text().strip().lower()

        # Filter: keep records where the query appears in any field
        visible = [
            r for r in self.violations
            if not query or any(
                query in r.get(field, "").lower()
                for field in ("plate", "driver", "lane", "timestamp")
            )
        ]

        self.table.setRowCount(0)
        for record in visible:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(record.get("timestamp", "")))
            self.table.setItem(row, 1, QTableWidgetItem(record.get("lane",      "")))
            self.table.setItem(row, 2, QTableWidgetItem(record.get("plate",     "")))
            self.table.setItem(row, 3, QTableWidgetItem(record.get("driver",    "")))
            self.table.setItem(row, 4, QTableWidgetItem(FINE_AMOUNT))
            # Store the full record object in the first cell so we can retrieve it on click
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, record)

        self.statusBar().showMessage(f"Total: {len(self.violations)}  |  Shown: {len(visible)}")

    def _on_row_click(self):
        """When user clicks a row, show the images and receipt preview on the right."""
        row = self.table.currentRow()
        if row < 0:
            return

        # Pull the stored record object out of the first cell
        record = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if not record:
            return
        self.selected = record

        # Show vehicle crop
        crop_path = record.get("vehicle_image_path", "")
        if crop_path and os.path.exists(crop_path):
            pixmap = QPixmap(crop_path).scaledToHeight(145, Qt.TransformationMode.SmoothTransformation)
            self.vehicle_img.setPixmap(pixmap)
        else:
            self.vehicle_img.setText("Vehicle image not found.")

        # Show scene screenshot
        scene_path = record.get("snapshot_path", "")
        if scene_path and os.path.exists(scene_path):
            pixmap = QPixmap(scene_path).scaledToWidth(440, Qt.TransformationMode.SmoothTransformation)
            self.scene_img.setPixmap(pixmap)
        else:
            self.scene_img.setText("Scene screenshot not found.")

        # Build receipt and show as preview image
        try:
            receipt_img = build_receipt_image(record)
            # Convert PIL image → bytes → QPixmap (no temp file needed)
            buffer = io.BytesIO()
            receipt_img.save(buffer, "PNG")
            buffer.seek(0)
            pixmap = QPixmap()
            pixmap.loadFromData(buffer.read())
            pixmap = pixmap.scaledToWidth(440, Qt.TransformationMode.SmoothTransformation)
            self.receipt_preview.setPixmap(pixmap)
        except Exception as e:
            self.receipt_preview.setText(f"Preview error: {e}")

    def _require_selection(self) -> bool:
        """Show a warning and return True if nothing is selected."""
        if not self.selected:
            QMessageBox.warning(self, "Nothing Selected", "Please click a violation row first.")
            return True
        return False

    def _on_print(self):
        if self._require_selection():
            return
        success, message = print_receipt(self.selected)
        if success:
            QMessageBox.information(self, "Printed", message)
        else:
            QMessageBox.critical(self, "Print Error", message)

    def _on_save_png(self):
        if self._require_selection():
            return
        try:
            path = save_receipt_png(self.selected)
            QMessageBox.information(self, "Saved", f"Receipt saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))

    def _on_delete(self):
        if self._require_selection():
            return
        plate = self.selected.get("plate", "?")
        answer = QMessageBox.question(
            self, "Confirm Delete",
            f"Remove the violation record for plate {plate}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        # Remove from list and save back to JSON
        self.violations = [
            r for r in self.violations
            if not (r.get("plate") == self.selected.get("plate") and
                    r.get("timestamp") == self.selected.get("timestamp"))
        ]
        write_violations(self.violations)
        self.selected = None

        # Reset the right panel
        self.vehicle_img.setText("Select a record to view.")
        self.scene_img.setText("Select a record to view.")
        self.receipt_preview.setText("Select a record to preview.")

        self._refresh_table()


# =============================================================================
# RUN
# =============================================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = ViolationApp()
    window.show()
    sys.exit(app.exec())

# run: python Ticket.py
