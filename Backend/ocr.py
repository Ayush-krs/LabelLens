import cv2
import pytesseract
from pytesseract import Output

TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


def preprocess_image(image_path):
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError("Could not read the image.")

    # Make small package text easier for OCR to read
    image = cv2.resize(
        image,
        None,
        fx=2,
        fy=2,
        interpolation=cv2.INTER_CUBIC,
    )

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Improve contrast
    gray = cv2.convertScaleAbs(
        gray,
        alpha=1.4,
        beta=0,
    )

    # Reduce small image noise
    gray = cv2.GaussianBlur(
        gray,
        (3, 3),
        0,
    )

    return gray


def group_words_into_lines(words):
    """
    Group OCR words into readable text lines.
    Tesseract gives every word its own coordinates.
    We group words using block, paragraph and line numbers.
    """
    grouped = {}

    for word in words:
        key = (
            word["block_num"],
            word["par_num"],
            word["line_num"],
        )

        if key not in grouped:
            grouped[key] = []

        grouped[key].append(word)

    lines = []

    for group in grouped.values():
        if not group:
            continue

        # Put words in left-to-right order
        group.sort(key=lambda item: item["x"])

        text = " ".join(
            item["text"]
            for item in group
            if item["text"].strip()
        ).strip()

        if not text:
            continue

        x1 = min(item["x"] for item in group)
        y1 = min(item["y"] for item in group)
        x2 = max(
            item["x"] + item["width"]
            for item in group
        )
        y2 = max(
            item["y"] + item["height"]
            for item in group
        )

        confidences = [
            item["confidence"]
            for item in group
            if item["confidence"] >= 0
        ]

        confidence = (
            sum(confidences) / len(confidences)
            if confidences
            else 0
        )

        lines.append({
            "text": text,
            "confidence": round(confidence, 2),
            "x": x1,
            "y": y1,
            "width": x2 - x1,
            "height": y2 - y1,
        })

    # Sort roughly from top to bottom
    lines.sort(
        key=lambda item: (
            item["y"],
            item["x"],
        )
    )

    return lines


def run_tesseract(image, psm):
    config = f"--oem 3 --psm {psm}"

    text = pytesseract.image_to_string(
        image,
        config=config,
    ).strip()

    data = pytesseract.image_to_data(
        image,
        config=config,
        output_type=Output.DICT,
    )

    words = []

    for i, word in enumerate(data["text"]):
        word = word.strip()
        if not word:
            continue

        try:
            confidence = float(data["conf"][i])
        except (ValueError, TypeError):
            continue

        if confidence < 0:
            continue

        words.append({
            "text": word,
            "confidence": round(confidence, 2),
            "x": data["left"][i],
            "y": data["top"][i],
            "width": data["width"][i],
            "height": data["height"][i],
            # Used to group words into lines
            "block_num": data["block_num"][i],
            "par_num": data["par_num"][i],
            "line_num": data["line_num"][i],
        })

    confidences = [
        word["confidence"]
        for word in words
        if word["confidence"] >= 0
    ]

    average_confidence = (
        sum(confidences) / len(confidences)
        if confidences
        else 0
    )

    lines = group_words_into_lines(words)

    return {
        "text": text,
        "confidence": round(average_confidence, 2),
        "words": words,
        "lines": lines,
        "psm": psm,
    }


def _box(line):
    return (
        line["x"],
        line["y"],
        line["x"] + line["width"],
        line["y"] + line["height"],
    )


def _overlap_ratio(a, b):
    """Return intersection-over-union-like overlap for two OCR line boxes."""
    ax1, ay1, ax2, ay2 = _box(a)
    bx1, by1, bx2, by2 = _box(b)

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0

    intersection = (ix2 - ix1) * (iy2 - iy1)
    area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1, (bx2 - bx1) * (by2 - by1))
    union = area_a + area_b - intersection

    return intersection / union


def _line_similarity(a, b):
    """Return a conservative spatial similarity score for two OCR lines."""
    overlap = _overlap_ratio(a, b)
    if overlap >= 0.25:
        return overlap

    acx = a["x"] + a["width"] / 2
    bcx = b["x"] + b["width"] / 2
    acy = a["y"] + a["height"] / 2
    bcy = b["y"] + b["height"] / 2

    max_height = max(a["height"], b["height"], 1)
    max_width = max(a["width"], b["width"], 1)

    # Only use a proximity fallback when the two regions are very close.
    # This avoids collapsing two legitimate lines that happen to sit in the
    # same column.
    vertical_close = abs(acy - bcy) <= max_height * 0.45
    horizontal_close = abs(acx - bcx) <= max_width * 0.5

    if vertical_close and horizontal_close:
        return 0.25

    return 0.0


def merge_ocr_lines(pass_results):
    """
    Combine useful lines from multiple OCR passes while suppressing
    obvious spatial duplicates.

    For overlapping lines, retain the higher-confidence interpretation.
    Distinct lines from either pass are preserved.
    """
    merged = []

    # Process the more confident pass first so its lines become the
    # initial candidates when two passes identify the same region.
    ordered_passes = sorted(
        pass_results,
        key=lambda result: result["confidence"],
        reverse=True,
    )

    for result in ordered_passes:
        for candidate in result["lines"]:
            duplicate_index = None
            best_similarity = 0.0

            for index, existing in enumerate(merged):
                similarity = _line_similarity(candidate, existing)
                if similarity > best_similarity:
                    best_similarity = similarity
                    duplicate_index = index

            if duplicate_index is None or best_similarity == 0.0:
                merged.append(dict(candidate))
                continue

            existing = merged[duplicate_index]

            # Keep the stronger OCR interpretation for the same region.
            if candidate["confidence"] > existing["confidence"]:
                merged[duplicate_index] = dict(candidate)

    merged.sort(
        key=lambda item: (
            item["y"],
            item["x"],
        )
    )

    return merged


def _lines_to_text(lines):
    return "\n".join(
        line["text"]
        for line in lines
        if line.get("text")
    ).strip()


def run_ocr(image_path):
    image = preprocess_image(image_path)

    # Different page segmentation modes work better for different package layouts.
    passes = [
        run_tesseract(image, 6),
        run_tesseract(image, 11),
    ]

    merged_lines = merge_ocr_lines(passes)

    # Keep words from the same lines used by the merged result. For now,
    # retain the word list from the strongest pass to avoid creating a large
    # duplicate word collection that could confuse downstream debugging.
    best = max(
        passes,
        key=lambda result: result["confidence"],
    )

    return {
        # Downstream extraction continues to receive the same fields.
        "text": _lines_to_text(merged_lines) or best["text"],
        "confidence": round(
            sum(line["confidence"] for line in merged_lines) / len(merged_lines),
            2,
        ) if merged_lines else best["confidence"],
        "words": best["words"],
        "lines": merged_lines,
        # Preserve the strongest pass as the representative PSM.
        "psm": best["psm"],
        "passes": [
            {
                "psm": result["psm"],
                "confidence": result["confidence"],
            }
            for result in passes
        ],
    }
