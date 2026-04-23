"""
permit_splitter.py
==================
UT Austin Events Team — Parking Permit PDF Splitter
----------------------------------------------------
Takes a multi-permit PDF from Parking and Transportation Services (PTS),
detects individual permits via contour detection, extracts key text fields
via OCR, and rebuilds one mobile-optimized PDF per permit.

Dependencies (install via pip):
    pip install pdf2image pillow opencv-python pytesseract reportlab

External requirement:
    - Tesseract OCR must be installed on your system.
      macOS:   brew install tesseract
      Windows: https://github.com/UB-Mannheim/tesseract/wiki
      Linux:   sudo apt install tesseract-ocr

    - Poppler must be installed for pdf2image.
      macOS:   brew install poppler
      Windows: https://github.com/oschwartz10612/poppler-windows/releases
      Linux:   sudo apt install poppler-utils

Usage:
    python permit_splitter.py --input permits.pdf --output ./output_permits
    python permit_splitter.py --input permits.pdf  # output defaults to ./output_permits
"""

import argparse
import os
import re
import sys

import cv2
import numpy as np
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────

# If Tesseract is not on your PATH, set the full path to the executable here.
# Examples:
#   Windows: r"C:\Program Files\Tesseract-OCR\tesseract.exe"
#   macOS/Linux: "/usr/local/bin/tesseract"  (usually not needed if installed via brew/apt)
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"  # use system PATH

# DPI for rasterizing PDF pages. Higher = more accurate OCR and contour detection.
PDF_RENDER_DPI = 300

# Mobile portrait page size in points (ReportLab uses points: 1 pt = 1/72 inch)
# This matches a standard phone screen ratio (roughly 9:16)
MOBILE_WIDTH_MM = 90
MOBILE_HEIGHT_MM = 160
MOBILE_PAGE_SIZE = (MOBILE_WIDTH_MM * mm, MOBILE_HEIGHT_MM * mm)

# Minimum area (in pixels²) for a contour to be considered a permit border.
# Filters out small noise rectangles. Tune if permits are not detected correctly.
MIN_PERMIT_AREA_FRACTION = 0.10  # Must be at least 10% of page area

# How much of the permit height (from the bottom) to search for the QR code.
QR_SEARCH_ZONE_FRACTION = 0.45

# ──────────────────────────────────────────────────────────────────────────────
# STEP 1: Load PDF pages as images
# ──────────────────────────────────────────────────────────────────────────────

def load_pdf_as_images(pdf_path: str) -> list[Image.Image]:
    """
    Convert each page of a PDF into a high-resolution PIL Image.

    Args:
        pdf_path: Path to the input PDF file.

    Returns:
        List of PIL Images, one per page.
    """
    print(f"[load] Reading PDF: {pdf_path}")
    pages = convert_from_path(pdf_path, dpi=PDF_RENDER_DPI, poppler_path=r"C:\Program Files\poppler\poppler-25.12.0\Library\bin")
    print(f"[load] Found {len(pages)} page(s).")
    return pages


# ──────────────────────────────────────────────────────────────────────────────
# STEP 2: Detect permit bounding boxes on a page via contour detection
# ──────────────────────────────────────────────────────────────────────────────

def detect_permit_regions(page_img: Image.Image) -> list[tuple[int, int, int, int]]:
    """
    Use OpenCV contour detection to find the black rectangular borders
    that enclose each permit on a page.

    Each PTS permit is surrounded by a solid black rectangular border.
    We look for large, nearly-rectangular contours that take up a significant
    fraction of the page.

    Args:
        page_img: PIL Image of a single PDF page.

    Returns:
        List of bounding boxes (x, y, w, h) sorted top-to-bottom,
        one per detected permit. Typically 1 or 2 per page.
    """
    # Convert PIL → OpenCV grayscale array
    img_np = np.array(page_img.convert("L"))
    page_area = img_np.shape[0] * img_np.shape[1]
    min_area = page_area * MIN_PERMIT_AREA_FRACTION

    # Threshold: permit borders are near-black on a white background
    _, thresh = cv2.threshold(img_np, 50, 255, cv2.THRESH_BINARY_INV)

    # Find external contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    permit_boxes = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue  # Too small — skip noise

        # Approximate the contour to a polygon
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

        # Accept quadrilaterals (4 corners) or nearly-rectangular larger shapes
        if len(approx) >= 4:
            x, y, w, h = cv2.boundingRect(cnt)
            permit_boxes.append((x, y, w, h))

    # Sort top-to-bottom by y coordinate (first permit is above second)
    permit_boxes.sort(key=lambda b: b[1])

    # Deduplicate highly overlapping boxes (keep the largest)
    permit_boxes = _deduplicate_boxes(permit_boxes)

    print(f"[detect] Found {len(permit_boxes)} permit region(s) on page.")
    return permit_boxes


def _deduplicate_boxes(boxes: list[tuple]) -> list[tuple]:
    """
    Remove duplicate or heavily overlapping bounding boxes.
    When multiple contours nest inside each other, keep the outermost (largest).
    """
    if len(boxes) <= 1:
        return boxes

    def overlap_ratio(a, b):
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
        iy = max(0, min(ay + ah, by + bh) - max(ay, by))
        inter = ix * iy
        smaller = min(aw * ah, bw * bh)
        return inter / smaller if smaller > 0 else 0

    kept = []
    for box in boxes:
        dominated = False
        for k in kept:
            if overlap_ratio(box, k) > 0.7:
                # Keep the larger one
                if box[2] * box[3] <= k[2] * k[3]:
                    dominated = True
                    break
                else:
                    kept.remove(k)
                    break
        if not dominated:
            kept.append(box)

    kept.sort(key=lambda b: b[1])
    return kept


# ──────────────────────────────────────────────────────────────────────────────
# STEP 3: Crop a single permit image from the page
# ──────────────────────────────────────────────────────────────────────────────

def crop_permit(page_img: Image.Image, bbox: tuple[int, int, int, int]) -> Image.Image:
    """
    Crop a permit region from the full page image.

    Args:
        page_img: PIL Image of the full page.
        bbox: (x, y, w, h) bounding box from contour detection.

    Returns:
        Cropped PIL Image of just the permit, with a small margin.
    """
    x, y, w, h = bbox
    margin = 10  # pixels — small buffer so we don't clip the border
    left   = max(0, x - margin)
    top    = max(0, y - margin)
    right  = min(page_img.width,  x + w + margin)
    bottom = min(page_img.height, y + h + margin)
    return page_img.crop((left, top, right, bottom))


# ──────────────────────────────────────────────────────────────────────────────
# STEP 4: Extract text fields from a permit image via OCR
# ──────────────────────────────────────────────────────────────────────────────

# These regex patterns match the five fields we care about.
# They are intentionally flexible to handle OCR noise.
_PATTERNS = {
    "event_name":   r"(?:Honors\s+Day|[A-Z][A-Za-z\s]+(?:Day|Event|Ceremony|Festival|Fair|Conference|Summit))\s*\d{4}",
    "valid_dates":  r"Valid\s+Dates?[:\s]+([^\n]+)",
    "permit_id":    r"\b([A-Z0-9]{2}[A-Z]{2}\d{7})\b",
}

def extract_text_fields(permit_img: Image.Image) -> dict[str, str]:
    """
    Run Tesseract OCR on the permit image and parse out the five key fields.

    We only OCR the upper ~55% of the permit (above the QR code zone)
    to avoid garbled output from the QR pattern itself.

    Args:
        permit_img: Cropped PIL Image of a single permit.

    Returns:
        Dict with keys: event_name, valid_garage, valid_dates, permit_id.
        Missing fields are empty strings.
    """
    # OCR only the upper portion — QR codes produce garbage text
    upper_cutoff = int(permit_img.height * (1 - QR_SEARCH_ZONE_FRACTION))
    upper_region = permit_img.crop((0, 0, permit_img.width, upper_cutoff))

    # Enhance contrast for OCR
    gray = upper_region.convert("L")
    raw_text = pytesseract.image_to_string(gray, config="--psm 6")
    print(f"[ocr] Raw text (first 300 chars):\n{raw_text[:300]}\n")

    fields = {
        "event_name":   "",
        "valid_garage": "",
        "valid_dates":  "",
        "permit_id":    "",
    }

    # Event name: first non-empty line that looks like a title
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    for line in lines:
        # Skip header lines from PTS letterhead
        if "university" in line.lower() or "parking" in line.lower() or "transportation" in line.lower():
            continue
        # First substantial line is likely the event name
        if len(line) > 5:
            fields["event_name"] = line
            break

    # Valid garage / lot
    # Pattern handles:
    #   "Valid: San Jacinto Garage"
    #   "Valid Area: SJG"
    #   "Valid: SJG, SWG, SAG"
    #   "Valid: Any Garage"
    #   "Valid: All Garages"
    m = re.search(
        r"Valid(?:\s+(?:Area|Dates?|For))?[:\s]+([^\n]+)",
        raw_text, re.IGNORECASE
    )
    if m:
        captured = m.group(1).strip()
        # Strip any leftover "Area:" or "Dates:" prefixes from OCR noise
        captured = re.sub(r"(?i)^area[:\s]+", "", captured).strip()
        captured = re.sub(r"(?i)^dates?[:\s]+", "", captured).strip()
        # Only accept if it doesn't look like a date (valid dates line can also match)
        if not re.search(r"\d{4}", captured):
            fields["valid_garage"] = captured

    # Valid dates
    m = re.search(_PATTERNS["valid_dates"], raw_text, re.IGNORECASE)
    if m:
        fields["valid_dates"] = m.group(1).strip()

    # Permit ID: 11-character alphanumeric code
    # Try exact pattern first, then fall back to any 11-char token
    m = re.search(_PATTERNS["permit_id"], raw_text)
    if m:
        fields["permit_id"] = m.group(1)
    else:
        # Fallback: find any 11-char alphanumeric token
        tokens = re.findall(r"\b[A-Z0-9]{11}\b", raw_text)
        if tokens:
            fields["permit_id"] = tokens[0]

    # Validate that the permit is for a garage, not a surface lot.
    # Accepted formats:
    #   - Full garage name:     "San Jacinto Garage"
    #   - Garage code(s):       "SJG" or "SJG, SWG, ECG"
    #   - Wildcard phrases:     "Any Garage" or "All Garages"
    # Rejected formats:
    #   - Surface lots:         "Lot 80", "Lot 38", etc.
    valid_area = fields.get("valid_garage", "").strip()
    valid_area_lower = valid_area.lower()

    GARAGE_CODES = {
        "BRG", "CCG", "HCG", "MAG", "SAG", "TRG",
        "SWG", "ECG", "GUG", "NUG", "RHG", "SJG", "TSG"
    }

    # Check each accepted format in order
    is_valid_garage = (
        # Full garage name contains the word "garage"
        "garage" in valid_area_lower
        # Wildcard phrases
        or "any garage" in valid_area_lower
        or "all garage" in valid_area_lower
        # One or more garage codes listed (e.g. "SJG" or "SJG, SWG")
        or any(
            code in [token.strip().upper() for token in valid_area.replace(",", " ").split()]
            for code in GARAGE_CODES
        )
    )

    if valid_area and not is_valid_garage:
        raise ValueError(
            f"This permit is valid for '{valid_area}', which is not a garage.\n\n"
            f"This tool only processes garage permits. "
            f"Surface lot permits (e.g. Lot 80) must be handled separately."
        )

    print(f"[ocr] Extracted fields: {fields}")
    return fields


# ──────────────────────────────────────────────────────────────────────────────
# STEP 5: Crop the QR code from the bottom of the permit
# ──────────────────────────────────────────────────────────────────────────────

def extract_qr_code(permit_img: Image.Image) -> Image.Image:
    """
    Use OpenCV's built-in QR code detector to find the exact QR code
    boundaries — no surrounding text, no borders, just the QR pattern.
    Falls back to contour-based square detection if detector fails.
    """
    img_np = np.array(permit_img.convert("RGB"))
    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # ── Attempt 1: OpenCV QR detector ──
    qr_detector = cv2.QRCodeDetector()
    retval, points = qr_detector.detect(gray)

    if retval and points is not None:
        pts = points[0]  # shape (4, 2)
        x_coords = pts[:, 0]
        y_coords = pts[:, 1]
        pad = 10
        left   = max(0, int(x_coords.min()) - pad)
        top    = max(0, int(y_coords.min()) - pad)
        right  = min(permit_img.width,  int(x_coords.max()) + pad)
        bottom = min(permit_img.height, int(y_coords.max()) + pad)
        print(f"[qr] QR detector found QR at ({left},{top}) → ({right},{bottom})")
        return permit_img.crop((left, top, right, bottom))

    print("[qr] QR detector failed, trying contour fallback...")

    # ── Attempt 2: Find the three finder squares unique to QR codes ──
    # QR codes have 3 large square finder patterns in corners.
    # We look for nested squares in the bottom half of the permit.
    h, w = permit_img.height, permit_img.width
    bottom_half = permit_img.crop((0, h // 2, w, h))
    img_np2 = np.array(bottom_half.convert("L"))
    _, thresh = cv2.threshold(img_np2, 128, 255, cv2.THRESH_BINARY_INV)
    contours, hierarchy = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    # Find contours that are squares and have a child contour (nested = finder pattern)
    finder_centers = []
    if hierarchy is not None:
        for i, cnt in enumerate(contours):
            x, y, cw, ch = cv2.boundingRect(cnt)
            area = cw * ch
            if area < 500:
                continue
            squareness = min(cw, ch) / max(cw, ch) if max(cw, ch) > 0 else 0
            has_child = hierarchy[0][i][2] != -1
            if squareness > 0.7 and has_child:
                cx = x + cw // 2
                cy = y + ch // 2
                finder_centers.append((cx, cy + h // 2))  # offset back to full image coords

    if len(finder_centers) >= 3:
        all_x = [c[0] for c in finder_centers]
        all_y = [c[1] for c in finder_centers]
        pad = 30
        left   = max(0, min(all_x) - pad)
        top    = max(0, min(all_y) - pad)
        right  = min(w, max(all_x) + pad)
        bottom = min(h, max(all_y) + pad)
        # Make it square
        side = max(right - left, bottom - top)
        right  = min(w, left + side)
        bottom = min(h, top + side)
        print(f"[qr] Finder pattern fallback found QR at ({left},{top}) → ({right},{bottom})")
        return permit_img.crop((left, top, right, bottom))

    # ── Attempt 3: Last resort — bottom 30% only ──
    print("[qr] All detection failed, using bottom 30% crop.")
    return permit_img.crop((0, int(h * 0.70), w, h))



# Crop and add the UT Austin PTS logo/header text from the top of the permit.
def extract_logo(permit_img: Image.Image) -> Image.Image | None:
    """
    Crop the UT Austin PTS logo from the top of the permit using contour
    detection — finds the actual logo content and excludes surrounding
    black border lines and any signature/stamp on the right side.
    """
    h, w = permit_img.height, permit_img.width

    # Logo lives in the top 15% of the permit
    header_region = permit_img.crop((0, 0, w, int(h * 0.15)))
    img_np = np.array(header_region.convert("L"))

    # Check if region is blank
    if img_np.mean() > 245:
        print("[logo] Header region appears blank, skipping.")
        return None

    # Threshold to find dark content (logo text/seal is dark on white)
    _, thresh = cv2.threshold(img_np, 200, 255, cv2.THRESH_BINARY_INV)

    # Find all contours of dark content
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        print("[logo] No contours found in header, using raw crop.")
        return header_region

    # Get bounding box of all dark content combined
    all_x, all_y, all_x2, all_y2 = [], [], [], []
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        # Ignore very small noise specks
        if cw * ch < 50:
            continue
        all_x.append(x)
        all_y.append(y)
        all_x2.append(x + cw)
        all_y2.append(y + ch)

    if not all_x:
        return header_region

    # Tight crop around all logo content
    pad = 5
    left   = max(0, min(all_x) - pad)
    top    = max(0, min(all_y) - pad)
    right  = min(header_region.width, max(all_x2) + pad)
    bottom = min(header_region.height, max(all_y2) + pad)

    # Only keep the left 70% — excludes signature/stamp on the right
    right = min(right, int(header_region.width * 0.70))
    # Trim more from left and top to exclude border lines
    left = left + int((right - left) * 0.01)
    top  = top  + int((bottom - top) * 0.18)

    print(f"[logo] Logo cropped to ({left},{top}) → ({right},{bottom})")
    return header_region.crop((left, top, right, bottom))

    print(f"[logo] Logo cropped to ({left},{top}) → ({right},{bottom})")
    return header_region.crop((left, top, right, bottom))


# ──────────────────────────────────────────────────────────────────────────────
# STEP 6: Build a mobile-optimized PDF from extracted fields + QR image
# ──────────────────────────────────────────────────────────────────────────────

def build_mobile_pdf(
    fields: dict[str, str],
    qr_img: Image.Image,
    output_path: str,
    logo_img: Image.Image | None = None
) -> None:
    """
    Construct a clean, mobile-portrait PDF for a single permit.

    Layout (top to bottom):
        - Event name          (small, centered)
        - "Valid:" label      (small, centered)
        - Garage/Lot name     (LARGE, bold, centered) ← most important
        - Valid Dates         (medium, centered)
        - Permit ID           (medium, monospace, centered)
        - QR Code image       (LARGE, centered)       ← most important

    Args:
        fields:      Dict from extract_text_fields().
        qr_img:      PIL Image of the QR code.
        output_path: Destination .pdf file path.
    """
    page_w, page_h = MOBILE_PAGE_SIZE
    margin = 6 * mm

    # Save QR image temporarily as PNG for ReportLab
    qr_tmp_path = output_path.replace(".pdf", "_qr_tmp.png")
    qr_img.save(qr_tmp_path, format="PNG")

    c = canvas.Canvas(output_path, pagesize=MOBILE_PAGE_SIZE)

    # ── Background: white ──
    c.setFillColor(colors.white)
    c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

    # ── Logo: UT Austin PTS header cropped from original permit ──
    import tempfile
    logo_tmp_path = None
    logo_h_pts = 0
    if logo_img is not None:
        # Write to a named temp file that we fully control and can delete after save
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        logo_tmp_path = tmp.name
        tmp.close()
        logo_img.save(logo_tmp_path, format="PNG")
        aspect = logo_img.height / logo_img.width
        logo_w_pts = page_w - 2 * margin
        logo_h_pts = logo_w_pts * aspect
        c.drawImage(
            logo_tmp_path,
            margin,
            page_h - logo_h_pts - margin,
            width=logo_w_pts,
            height=logo_h_pts,
            preserveAspectRatio=True,
            mask="auto"
        )

    # ── Draw text fields ──
    cursor_y = page_h - logo_h_pts - margin - 8 * mm

    def draw_centered_text(text, font_name, font_size, y, color=colors.black):
        c.setFillColor(color)
        c.setFont(font_name, font_size)
        c.drawCentredString(page_w / 2, y, text)

    # Event name
    event = fields.get("event_name", "Parking Permit") or "Parking Permit"
    draw_centered_text(event, "Helvetica-Bold", 16, cursor_y, color=colors.black)
    cursor_y -= 8 * mm

    # Valid + Garage name — one line, black
    garage = fields.get("valid_garage", "") or "See Permit"
    valid_label = f"Valid: {garage}"
    garage_font_size = 16 if len(valid_label) <= 24 else 13
    draw_centered_text(valid_label, "Helvetica-Bold", garage_font_size, cursor_y,
                       color=colors.black)
    cursor_y -= (garage_font_size / 72 * 25.4 + 2) * mm

    # Divider line
    c.setStrokeColor(colors.HexColor("#DDDDDD"))
    c.setLineWidth(0.5)
    c.line(margin, cursor_y, page_w - margin, cursor_y)
    cursor_y -= 4 * mm

    # Valid dates
    dates = fields.get("valid_dates", "") or ""
    if dates:
        draw_centered_text("Valid Dates:", "Helvetica", 8, cursor_y,
                           color=colors.black)
        cursor_y -= 5 * mm
        draw_centered_text(dates, "Helvetica", 10, cursor_y)
        cursor_y -= 6 * mm

    # Permit ID
    permit_id = fields.get("permit_id", "") or ""
    if permit_id:
        draw_centered_text(permit_id, "Helvetica", 10, cursor_y,
                           color=colors.HexColor("#222222"))
        cursor_y -= 4 * mm

    # Another divider
    c.setStrokeColor(colors.HexColor("#DDDDDD"))
    c.line(margin, cursor_y, page_w - margin, cursor_y)
    cursor_y -= 6 * mm

    instructions = [
        ("Scan the QR code at the small blue column", False),
        ("or the box attached to the grey column.", True),
        ("Turn your phone brightness up to scan the permit", False),
    ]
    for line, add_gap_after in instructions:
        words = line.split()
        current_line = ""
        for word in words:
            test_line = f"{current_line} {word}".strip()
            if c.stringWidth(test_line, "Helvetica-Bold", 7) <= (page_w - 2 * margin):
                current_line = test_line
            else:
                draw_centered_text(current_line, "Helvetica-Bold", 7, cursor_y)
                cursor_y -= 4 * mm
                current_line = word
        if current_line:
            draw_centered_text(current_line, "Helvetica-Bold", 7, cursor_y)
            cursor_y -= 4 * mm
        if add_gap_after:
            cursor_y -= 3 * mm

    cursor_y -= 3 * mm

    # ── QR Code — nearly full width ──
    qr_size = (page_w - (2 * margin)) * 0.8  # almost edge to edge

    qr_x = (page_w - qr_size) / 2
    qr_y = cursor_y - qr_size - 10 * mm

    c.drawImage(
        qr_tmp_path,
        qr_x, qr_y,
        width=qr_size, height=qr_size,
        preserveAspectRatio=True,
        mask="auto"
    )

    cursor_y = qr_y - 4 * mm

    # Clean up temporary image files — must be after c.save() releases file handles
    c.save()
    if os.path.exists(qr_tmp_path):
        try:
            os.remove(qr_tmp_path)
        except Exception:
            pass
    if logo_tmp_path and os.path.exists(logo_tmp_path):
        try:
            os.remove(logo_tmp_path)
        except Exception:
            pass

    print(f"[pdf] Saved: {output_path}")


# ──────────────────────────────────────────────────────────────────────────────
# MAIN ORCHESTRATOR
# ──────────────────────────────────────────────────────────────────────────────

def main(pdf_path: str, output_dir: str) -> None:
    """
    Orchestrates the full pipeline:
        1. Load PDF pages as images
        2. Detect permit regions per page
        3. Crop each permit
        4. OCR text fields
        5. Extract QR code
        6. Build mobile PDF

    Args:
        pdf_path:   Path to input PDF from PTS.
        output_dir: Directory to write individual permit PDFs.
    """
    # ── Setup ──
    if TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

    os.makedirs(output_dir, exist_ok=True)

    # ── Step 1: Load pages ──
    pages = load_pdf_as_images(pdf_path)

    permit_count = 0

    for page_num, page_img in enumerate(pages, start=1):
        print(f"\n{'='*60}")
        print(f"Processing page {page_num} of {len(pages)}...")
        print(f"{'='*60}")

        # ── Step 2: Detect permit bounding boxes ──
        boxes = detect_permit_regions(page_img)

        if not boxes:
            print(f"[warn] No permit regions detected on page {page_num}. Skipping.")
            continue

        for box_idx, bbox in enumerate(boxes):
            permit_count += 1
            print(f"\n  -- Permit #{permit_count} (page {page_num}, region {box_idx + 1}) --")

            # ── Step 3: Crop permit ──
            permit_img = crop_permit(page_img, bbox)

            # ── Step 3b: Extract logo from permit header ──
            logo_img = extract_logo(permit_img)

            # ── Step 4: OCR text ──
            fields = extract_text_fields(permit_img)

            # ── Step 5: Extract QR code ──
            qr_img = extract_qr_code(permit_img)

            # ── Step 6: Build output PDF ──
            # Name output file by permit ID if available, else by index
            safe_id = fields.get("permit_id") or f"permit_{permit_count:03d}"
            
            # Lookup table mapping keywords from OCR garage text to official 3-letter garage codes.
            # Keys are lowercase substrings to match against the detected garage name.
            # Values are the official UT Austin Parking and Transportation Services abbreviations.
            GARAGE_CODES = {
                "brazos":        "BRG",
                "conference":    "CCG",
                "health":        "HCG",
                "manor":         "MAG",
                "san antonio":   "SAG",
                "trinity":       "TRG",
                "speedway":      "SWG",
                "east campus":   "ECG",
                "guadalupe":     "GUG",
                "nueces":        "NUG",
                "rowling":       "RHG",
                "san jacinto":   "SJG",
                "27th":          "TSG",
            }
            
            garage_raw = fields.get("valid_garage", "").strip()
            garage_raw_lower = garage_raw.lower()

            # First try matching by full name keyword (e.g. "san jacinto" → SJG)
            garage_code = next(
                (code for keyword, code in GARAGE_CODES.items() if keyword in garage_raw_lower),
                None
            )

            # If no name match, check if the valid area IS a garage code directly
            # e.g. "SJG" or first code in "SJG, SWG, ECG"
            if not garage_code:
                tokens = [t.strip().upper() for t in garage_raw.replace(",", " ").split()]
                garage_code = next(
                    (t for t in tokens if t in GARAGE_CODES),
                    None
                )

            # If still no match (e.g. "Any Garage"), fall back to sanitized raw name
            if not garage_code:
                garage_code = re.sub(r"[^\w\s]", "", garage_raw).strip().replace(" ", "_") or "permit"
            out_filename = f"{garage_code}_{safe_id}.pdf"
            out_path = os.path.join(output_dir, out_filename)

            # Block only if this exact [GARAGE_CODE]_[PERMIT_ID] file already exists.
            # A different permit ID for the same garage will not be blocked.
            if os.path.exists(out_path):
                raise FileExistsError(
                    f"Conflict: {out_filename} already exists in the output folder. "
                    f"Delete existing files before reprocessing."
                )

            build_mobile_pdf(fields, qr_img, out_path, logo_img=logo_img)

    print(f"\n{'='*60}")
    print(f"Done! {permit_count} permit(s) written to: {output_dir}")
    print(f"{'='*60}")


# ──────────────────────────────────────────────────────────────────────────────
# CLI ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Split UT Austin PTS parking permit PDFs into individual mobile-optimized PDFs."
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Path to the input PDF file from PTS (e.g., permits.pdf)"
    )
    parser.add_argument(
        "--output", "-o",
        default="./output_permits",
        help="Directory to write individual permit PDFs (default: ./output_permits)"
    )
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"[error] Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    main(args.input, args.output)
