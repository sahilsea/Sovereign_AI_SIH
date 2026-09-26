"""Generate the demo inputs for the PS-26117 walkthrough into demo/.

    python scripts/make_demo_assets.py

Creates (all synthetic, no real MRPL data):
  demo/scanned_inspection_report.pdf  image-only (no text layer) inspection
                                      report with printed findings and
                                      handwritten inspector remarks
  demo/unit_inventory.xlsx            spare-parts inventory for spreadsheet work
  demo/pid_drawing.png                simplified P&ID sheet for vision
"""

from __future__ import annotations

import io
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).parent.parent / "demo"

_PRINT_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
]
_BOLD_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]
_HAND_FONTS = [
    "/System/Library/Fonts/Noteworthy.ttc",
    "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf",
    "/System/Library/Fonts/MarkerFelt.ttc",
    "C:/Windows/Fonts/segoepr.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
]


def _font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def scanned_inspection_report() -> Path:
    W, H = 1700, 2200  # ~200 dpi A4-ish
    img = Image.new("L", (W, H), 250)
    d = ImageDraw.Draw(img)
    f_title, f_bold, f_body = _font(_BOLD_FONTS, 46), _font(_BOLD_FONTS, 32), _font(_PRINT_FONTS, 30)
    f_hand = _font(_HAND_FONTS, 40)

    y = 110
    d.text((120, y), "MANGALORE REFINERY - INSPECTION DEPARTMENT", font=f_title, fill=20); y += 80
    d.text((120, y), "Pressure Vessel Inspection Report  No. INSP/PV/2025/0417", font=f_bold, fill=25); y += 70
    d.line((120, y, W - 120, y), fill=40, width=3); y += 30
    for line in [
        "Equipment Tag: V-2104 (Crude Unit Desalter Drum)      Unit: CDU-II",
        "Date of Inspection: 14-08-2025      Inspector: R. Shenoy, Sr. Engineer (Insp.)",
        "Design Pressure: 18.5 kg/cm2(g)    Design Temp: 150 C    MOC: SA-516 Gr.70",
        "Nominal Shell Thickness: 22.0 mm    Minimum Required Thickness: 18.4 mm",
    ]:
        d.text((120, y), line, font=f_body, fill=30); y += 50
    y += 30
    d.text((120, y), "FINDINGS", font=f_bold, fill=20); y += 60
    for line in [
        "1. Ultrasonic thickness at bottom shell CML-07 measured 19.1 mm, a loss of 2.9 mm.",
        "2. Corrosion rate at CML-07 is 0.48 mm per year; remaining life about 1.5 years.",
        "3. Pitting up to 1.2 mm depth observed near the brine outlet nozzle N4.",
        "4. External coating damaged over approximately 3 square metres on the south side.",
        "5. Pressure safety valve PSV-2104A test certificate expired on 30-06-2025.",
        "6. No leaks, bulging or cracks were observed on welds or nozzles.",
    ]:
        d.text((140, y), line, font=f_body, fill=30); y += 55
    y += 30
    d.text((120, y), "RECOMMENDATIONS", font=f_bold, fill=20); y += 60
    for line in [
        "a) Re-test and re-certify PSV-2104A before the unit restarts.",
        "b) Repair coating on the south side within 30 days.",
        "c) Monitor CML-07 every 6 months; plan shell repair in the next turnaround.",
    ]:
        d.text((140, y), line, font=f_body, fill=30); y += 55

    # Handwritten inspector remarks, slightly rotated, in "ink".
    hand = Image.new("L", (1400, 420), 255)
    hd = ImageDraw.Draw(hand)
    hd.text((10, 10), "Remarks: Vessel fit for continued service", font=f_hand, fill=40)
    hd.text((10, 80), "till next TA subject to PSV re-certification.", font=f_hand, fill=40)
    hd.text((10, 150), "Nozzle N4 pitting - recheck in Dec 2025.", font=f_hand, fill=40)
    hd.text((10, 260), "- R. Shenoy   14/8/25", font=f_hand, fill=40)
    hand = hand.rotate(-2.0, expand=True, fillcolor=255)
    img.paste(hand, (130, y + 50), mask=Image.eval(hand, lambda p: 255 - p))

    d.rectangle((W - 520, H - 300, W - 120, H - 150), outline=60, width=3)
    d.text((W - 500, H - 285), "Approved by: ____________", font=f_body, fill=40)
    d.text((W - 500, H - 225), "Head (Inspection)", font=f_body, fill=40)

    # Make it look scanned: slight skew, blur, speckle.
    random.seed(7)
    img = img.rotate(0.6, expand=False, fillcolor=245).filter(ImageFilter.GaussianBlur(0.7))
    px = img.load()
    for _ in range(9000):
        px[random.randrange(W), random.randrange(H)] = random.choice((120, 170, 210))

    path = OUT / "scanned_inspection_report.pdf"
    img.convert("RGB").save(path, "PDF", resolution=200.0)  # image only, no text layer
    return path


def unit_inventory() -> Path:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Inventory"
    ws.append(["Item Code", "Description", "Unit", "Qty On Hand", "Unit Cost (INR)", "Reorder Level"])
    random.seed(11)
    items = [
        ("GSK-150", "Spiral wound gasket 6in 150#"), ("GSK-300", "Spiral wound gasket 4in 300#"),
        ("BRG-6205", "Ball bearing 6205-2RS"), ("BRG-6310", "Ball bearing 6310 C3"),
        ("MS-P101", "Mechanical seal, pump P-101"), ("MS-P205", "Mechanical seal, pump P-205"),
        ("VLV-GT2", "Gate valve 2in CS"), ("VLV-GL1", "Globe valve 1in SS"),
        ("PSV-SPR", "PSV spring kit"), ("PT-TX", "Pressure transmitter 0-40 bar"),
        ("TT-PT100", "RTD PT100 element"), ("FLT-LO", "Lube oil filter element"),
        ("STUD-M20", "Stud bolt M20 x 150 B7"), ("CPL-GR", "Gear coupling insert"),
        ("IMP-P101", "Impeller, pump P-101"), ("OR-VITON", "O-ring kit Viton"),
    ]
    units = ["CDU-II", "HCU", "SRU", "Utilities"]
    for code, desc in items:
        ws.append([code, desc, random.choice(units), random.randint(0, 60),
                   random.choice([450, 1200, 3800, 8500, 15500, 42000, 96000]), random.randint(4, 20)])
    path = OUT / "unit_inventory.xlsx"
    wb.save(path)
    return path


def pid_drawing() -> Path:
    W, H = 1800, 1100
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f, fb = _font(_PRINT_FONTS, 26), _font(_BOLD_FONTS, 30)
    ink = (20, 20, 20)

    # Feed line -> V-2104 -> pump P-101 -> XV-201 -> to storage
    d.line((80, 400, 420, 400), fill=ink, width=5)
    d.polygon([(420, 400), (395, 385), (395, 415)], fill=ink)
    d.text((100, 350), 'FEED FROM CDU-II  6"-P-1201-A1', font=f, fill=ink)

    d.rounded_rectangle((440, 250, 700, 650), radius=120, outline=ink, width=5)  # vessel
    d.text((500, 430), "V-2104", font=fb, fill=ink)
    d.text((470, 470), "DESALTER", font=f, fill=ink)
    d.ellipse((560, 170, 640, 250), outline=ink, width=4)  # PT bubble
    d.text((572, 188), "PT", font=f, fill=ink)
    d.text((568, 216), "105", font=f, fill=ink)
    d.line((600, 250, 600, 250), fill=ink, width=3)

    # PSV on top
    d.line((520, 250, 520, 150), fill=ink, width=4)
    d.polygon([(495, 150), (545, 150), (520, 110)], outline=ink, width=4)
    d.text((440, 70), "PSV-2104A  SET 18.5 kg/cm2", font=f, fill=ink)

    # Outlet to pump
    d.line((570, 650, 570, 800, 900, 800), fill=ink, width=5)
    d.ellipse((900, 740, 1020, 860), outline=ink, width=5)  # pump
    d.polygon([(940, 760), (940, 840), (1005, 800)], outline=ink, width=4)
    d.text((910, 880), "P-101 A/B", font=fb, fill=ink)

    # Pump discharge with valve XV-201
    d.line((1020, 800, 1300, 800), fill=ink, width=5)
    d.polygon([(1300, 770), (1300, 830), (1360, 800)], outline=ink, width=4)  # bowtie valve
    d.polygon([(1420, 770), (1420, 830), (1360, 800)], outline=ink, width=4)
    d.text((1300, 700), "XV-201 (FC)", font=fb, fill=ink)
    d.line((1420, 800, 1720, 800), fill=ink, width=5)
    d.polygon([(1720, 800), (1695, 785), (1695, 815)], fill=ink)
    d.text((1450, 830), 'TO STORAGE  4"-P-1305-A1', font=f, fill=ink)

    # Level transmitter loop
    d.line((700, 450, 820, 450), fill=ink, width=3)
    d.ellipse((820, 410, 900, 490), outline=ink, width=4)
    d.text((838, 425), "LT", font=f, fill=ink)
    d.text((832, 453), "110", font=f, fill=ink)

    # Title block
    d.rectangle((1200, 950, 1760, 1080), outline=ink, width=3)
    d.text((1215, 960), "P&ID: CDU-II DESALTER SECTION", font=fb, fill=ink)
    d.text((1215, 1005), "DWG No. MRPL-CDU2-PID-014   REV 3", font=f, fill=ink)
    d.text((1215, 1040), "SYNTHETIC DEMO DRAWING", font=f, fill=(150, 0, 0))

    path = OUT / "pid_drawing.png"
    img.save(path)
    return path


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for fn in (scanned_inspection_report, unit_inventory, pid_drawing):
        print("Created", fn())
