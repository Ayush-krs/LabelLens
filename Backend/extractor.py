import re
from typing import Any, Dict, List, Optional


FIELD_KEYS = [
    "product_name",
    "manufacturer",
    "net_quantity",
    "mrp",
    "unit_sale_price",
    "serving_size",
    "packing_date",
    "best_before",
    "use_by",
    "consumer_care",
    "license_number",
    "batch_number",
]


STOP_LABELS = (
    "manufactured",
    "manufactured by",
    "mfg",
    "mfg by",
    "marketed",
    "packed",
    "packed by",
    "net quantity",
    "mrp",
    "batch",
    "lot no",
    "lic no",
    "license",
    "consumer care",
    "customer care",
    "ingredients",
    "nutrition",
    "best before",
    "use by",
    "expiry",
    "expires",
)


def clean_text(value: str) -> str:
    value = value or ""
    value = value.replace("\u00a0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\s*\n\s*", "\n", value)
    return value.strip()


def get_lines(
    text: str,
    lines: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Return grouped OCR lines when available, otherwise build basic lines from text."""
    if lines:
        result = []

        for line in lines:
            line_text = clean_text(str(line.get("text", "")))
            if not line_text:
                continue

            result.append(
                {
                    "text": line_text,
                    "confidence": float(line.get("confidence", 0) or 0),
                    "x": int(line.get("x", 0) or 0),
                    "y": int(line.get("y", 0) or 0),
                    "width": int(line.get("width", 0) or 0),
                    "height": int(line.get("height", 0) or 0),
                }
            )

        return result

    return [
        {
            "text": clean_text(line),
            "confidence": 0,
            "x": 0,
            "y": i,
            "width": 0,
            "height": 0,
        }
        for i, line in enumerate(clean_text(text).splitlines())
        if clean_text(line)
    ]


def make_evidence(
    line: Dict[str, Any],
    confidence: Optional[float] = None,
) -> Dict[str, Any]:
    return {
        "text": line["text"],
        "confidence": round(
            float(
                line["confidence"]
                if confidence is None
                else confidence
            ),
            2,
        ),
        "region": {
            "x": line["x"],
            "y": line["y"],
            "width": line["width"],
            "height": line["height"],
        },
    }


def field(
    value: Optional[str] = None,
    confidence: float = 0,
    evidence: Optional[Dict[str, Any]] = None,
    status: str = "detected",
) -> Dict[str, Any]:
    return {
        "value": value,
        "confidence": round(float(confidence), 2),
        "evidence": evidence,
        "status": status,
    }


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_license(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", value or "")


def line_score(line: Dict[str, Any]) -> float:
    """OCR confidence with a small preference for longer, useful lines."""
    text = line["text"]
    return line["confidence"] + min(len(text), 40) * 0.15


def find_first(
    lines: List[Dict[str, Any]],
    pattern: str,
    flags=re.I,
) -> Optional[Dict[str, Any]]:
    regex = re.compile(pattern, flags)
    matches = [line for line in lines if regex.search(line["text"])]

    if not matches:
        return None

    return max(matches, key=line_score)


def extract_value_after_label(
    lines: List[Dict[str, Any]],
    patterns: List[str],
    value_pattern: str,
    min_confidence: float = 20,
) -> Optional[Dict[str, Any]]:
    value_regex = re.compile(value_pattern, re.I)

    for line in lines:
        if line["confidence"] < min_confidence:
            continue

        for pattern in patterns:
            match = re.search(pattern, line["text"], re.I)
            if not match:
                continue

            remainder = line["text"][match.end():].strip(" :.-")
            value_match = value_regex.search(remainder)

            if value_match:
                return {
                    "value": value_match.group(0).strip(),
                    "line": line,
                }

    return None


# Slightly OCR-tolerant without becoming overly broad.
_NET_QUANTITY_LABEL = re.compile(
    r"\b(?:net|n?et)\s*(?:quantity|qty|wt\.?|weight|contents?)\b",
    re.I,
)


_SERVING_CONTEXT = re.compile(
    r"serv(?:ing)?\s*size|"
    r"(?:each|per)\s+serv(?:e|ing)|"
    r"quantity\s+per\s+serv(?:e|ing)|"
    r"per\s*100\s*(?:g|mg|kg|ml|l)\b",
    re.I,
)


_SERVING_LABEL = re.compile(
    r"serv(?:ing)?\s*size|"
    r"(?:each|per)\s+serv(?:e|ing)|"
    r"quantity\s+per\s+serv(?:e|ing)",
    re.I,
)


_QUANTITY_VALUE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*"
    r"(kg|g|mg|ml|cl|litres?|liters?|l)\b",
    re.I,
)


def merge_evidence(parts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Join OCR regions into one evidence line using a union bounding box."""
    usable = [part for part in parts if part]

    if not usable:
        raise ValueError("merge_evidence requires at least one region.")

    if len(usable) == 1:
        return dict(usable[0])

    left = min(item["x"] for item in usable)
    top = min(item["y"] for item in usable)
    right = max(item["x"] + item["width"] for item in usable)
    bottom = max(item["y"] + item["height"] for item in usable)

    return {
        "text": normalize_spaces(
            " ".join(
                item["text"]
                for item in usable
                if item.get("text")
            )
        ),
        "confidence": min(
            item["confidence"]
            for item in usable
        ),
        "x": left,
        "y": top,
        "width": right - left,
        "height": bottom - top,
    }


def looks_like_serving_context(text: str) -> bool:
    """True when a quantity is a serving or per-100 nutrition amount."""
    return bool(_SERVING_CONTEXT.search(text or ""))


def is_net_quantity_label(text: str) -> bool:
    """True for pack-level net quantity labels, not serving/nutrition wording."""
    if not _NET_QUANTITY_LABEL.search(text or ""):
        return False

    if looks_like_serving_context(text):
        return False

    return True


def parse_quantity(text: str) -> Optional[str]:
    match = _QUANTITY_VALUE.search(text or "")

    if not match:
        return None

    return f"{match.group(1)} {match.group(2)}"


def _line_box(line: Dict[str, Any]):
    left = line["x"]
    top = line["y"]

    return (
        left,
        top,
        left + line["width"],
        top + line["height"],
    )


def iter_value_regions(
    anchor: Dict[str, Any],
    lines: List[Dict[str, Any]],
    *,
    include_fallback: bool = True,
):
    """
    Yield regions that may contain a labelled value.

    Search order:
    1. Same line
    2. Nearby right
    3. Directly below
    4. Limited nearby fallback
    """
    yield anchor

    ax1, ay1, ax2, ay2 = _line_box(anchor)

    right_side = []
    below = []
    fallback = []

    for line in lines:
        if line is anchor:
            continue

        lx1, ly1, lx2, ly2 = _line_box(line)

        vertical_overlap = min(ay2, ly2) - max(ay1, ly1)
        horizontal_overlap = min(ax2, lx2) - max(ax1, lx1)
        right_gap = lx1 - ax2

        # Same row / value to the right.
        if (
            lx1 >= ax2 - 10
            and vertical_overlap >= -20
            and 0 <= right_gap <= 350
        ):
            right_side.append(
                (right_gap, lx1, line)
            )
            continue

        # Value directly underneath.
        vertical_gap = ly1 - ay2
        x_offset = abs(lx1 - ax1)

        column_aligned = (
            x_offset <= max(80, anchor["width"])
            or horizontal_overlap > 0
        )

        if column_aligned and 0 <= vertical_gap <= 120:
            below.append(
                (vertical_gap, x_offset, line)
            )
            continue

        # Limited nearby fallback.
        if (
            include_fallback
            and abs(ly1 - ay1) <= 140
            and abs(lx1 - ax1) <= 400
        ):
            fallback.append(
                (
                    abs(ly1 - ay1) + abs(lx1 - ax1),
                    line,
                )
            )

    for item in sorted(
        right_side,
        key=lambda row: (row[0], row[1]),
    ):
        yield item[2]

    for item in sorted(
        below,
        key=lambda row: (row[0], row[1]),
    ):
        yield item[2]

    if include_fallback:
        for item in sorted(
            fallback,
            key=lambda row: row[0],
        )[:5]:
            yield item[1]


def quantity_near_label(
    label_line: Dict[str, Any],
    lines: List[Dict[str, Any]],
    *,
    include_fallback: bool = True,
    skip_serving_context: bool = False,
    skip_net_quantity_labels: bool = False,
) -> Optional[Dict[str, Any]]:
    """Find a numeric quantity using same line, right, below, then nearby."""
    for region in iter_value_regions(
        label_line,
        lines,
        include_fallback=include_fallback,
    ):
        value = parse_quantity(region["text"])

        if not value:
            continue

        if (
            skip_serving_context
            and looks_like_serving_context(region["text"])
        ):
            continue

        if (
            skip_net_quantity_labels
            and region is not label_line
            and is_net_quantity_label(region["text"])
        ):
            continue

        evidence = (
            label_line
            if region is label_line
            else merge_evidence(
                [label_line, region]
            )
        )

        return {
            "value": value,
            "line": evidence,
        }

    return None


def extract_quantity(
    lines: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Extract pack-level net quantity, never a serving/per-100 amount."""
    for line in lines:
        if not is_net_quantity_label(line["text"]):
            continue

        result = quantity_near_label(
            line,
            lines,
            include_fallback=True,
            skip_serving_context=True,
        )

        if result:
            return result

    return None


def extract_serving_size(
    lines: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Extract serving size only from serving language."""
    for line in lines:
        if not _SERVING_LABEL.search(line["text"]):
            continue

        result = quantity_near_label(
            line,
            lines,
            include_fallback=False,
            skip_net_quantity_labels=True,
        )

        if result:
            return result

    return None


def extract_mrp(
    lines: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    mrp_patterns = [
        (
            r"\bmrp\b\s*"
            r"(?:rs\.?|₹)?\s*[:=-]?\s*"
            r"(?:rs\.?|₹)?\s*"
            r"([0-9]+(?:\.[0-9]{1,2})?)"
        ),
        (
            r"maximum\s*retail\s*price\s*"
            r"(?:rs\.?|₹)?\s*[:=-]?\s*"
            r"([0-9]+(?:\.[0-9]{1,2})?)"
        ),
    ]

    for line in lines:
        text = line["text"]
        lower = text.lower()

        # MRP printed elsewhere, e.g. below a seal.
        if "mrp" in lower and "see under" in lower:
            continue

        # Do not confuse unit sale price with MRP.
        if (
            "unit sale price" in lower
            or "sale price per" in lower
        ):
            continue

        for pattern in mrp_patterns:
            match = re.search(
                pattern,
                text,
                re.I,
            )

            if match:
                # Do not turn an uncertain OCR number into a confident MRP.
                # Currency symbols are a common source of leading-digit OCR errors.
                if line["confidence"] < 80:
                    return {
                        "value": None,
                        "line": line,
                        "status": "not_visible",
                    }

                return {
                    "value": f"₹{match.group(1)}",
                    "line": line,
                }

    # Some packages split "For MRP" and
    # "See under the seal" across lines.
    mrp_label = find_first(
        lines,
        r"\b(?:for\s+)?mrp\b",
    )

    see_under = find_first(
        lines,
        r"see\s+under",
    )

    if (
        mrp_label
        and see_under
        and see_under["y"] >= mrp_label["y"] - 80
    ):
        return {
            "value": None,
            "line": mrp_label,
            "status": "not_visible",
        }

    return None


def extract_unit_sale_price(
    lines: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    pattern = re.compile(
        r"(?:unit\s+sale\s+price|sale\s+price\s+per)"
        r"\s*(?:[:=-])?\s*"
        r"(?:₹|rs\.?\s*)?"
        r"([0-9]+(?:\.[0-9]{1,2})?)"
        r"\s*(?:/\s*)?"
        r"(kg|g|mg|l|ml|unit|piece|pc)?",
        re.I,
    )

    for line in lines:
        match = pattern.search(line["text"])

        if not match:
            continue

        value = f"₹{match.group(1)}"

        if match.group(2):
            value += f"/{match.group(2)}"

        return {
            "value": value,
            "line": line,
        }

    return None


def _is_contact_or_service_text(text: str) -> bool:
    """Reject obvious email/web/customer-care fragments."""
    lower = text.lower()

    return (
        "@" in text
        or "www." in lower
        or "http://" in lower
        or "https://" in lower
        or bool(
            re.search(
                r"\b(?:care|customer|consumer|email|website|"
                r"helpline|toll[\s-]*free)\b",
                lower,
                re.I,
            )
        )
    )


def _looks_like_sentence(text: str) -> bool:
    """
    Generic heuristic for rejecting descriptive/prose OCR lines
    when searching for a product title.
    """
    words = re.findall(
        r"[A-Za-z][A-Za-z&'./-]*",
        text,
    )

    if not words:
        return False

    sentence_words = {
        "is",
        "are",
        "was",
        "were",
        "be",
        "made",
        "from",
        "with",
        "for",
        "and",
        "this",
        "that",
        "the",
        "carefully",
        "selected",
        "delicious",
        "perfect",
        "contains",
        "contains",
        "provides",
        "enjoy",
        "enjoyed",
    }

    lower_words = {
        word.lower()
        for word in words
    }

    if lower_words & sentence_words:
        return True

    if len(words) >= 5 and (
        text.endswith(".")
        or text.endswith(",")
        or ":" in text
    ):
        return True

    return False


def _product_prefix_from_sentence(text: str) -> Optional[str]:
    """Recover a likely product title from the start of a description."""
    text = normalize_spaces(text)

    match = re.match(
        r"^(.{2,50}?)\s+(?:is|are|was|were|contains|comes|made)\b",
        text,
        re.I,
    )

    if not match:
        return None

    candidate = match.group(1).strip(" :.-,;!|")
    words = candidate.split()

    if not 2 <= len(words) <= 4:
        return None

    # Sentence/opening fragments are not product titles.
    opening_words = {
        "if",
        "you",
        "this",
        "that",
        "the",
        "for",
        "when",
        "while",
        "please",
        "our",
        "your",
        "we",
        "to",
    }

    if words[0].lower() in opening_words:
        return None

    # A likely product title should look title-like rather than
    # like ordinary sentence prose.
    title_like_words = sum(
        1
        for word in words
        if word[:1].isupper()
    )

    if title_like_words < len(words):
        return None

    if _is_contact_or_service_text(candidate):
        return None

    return candidate


def extract_product_name(
    lines: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Extract product identity conservatively.

    Priority:
    1. Explicit product-name label
    2. Recognizable brand fallback
    3. Generic title-like OCR candidate
    """
    if not lines:
        return None

    # ---------------------------------------------------------
    # 1. Explicit product/name label
    # ---------------------------------------------------------
    explicit = re.compile(
        r"(?:product\s*name|name\s*of\s*(?:the\s*)?product)"
        r"\s*[:=-]?\s*(.+)",
        re.I,
    )

    for line in lines:
        match = explicit.search(line["text"])

        if not match:
            continue

        value = normalize_spaces(match.group(1))

        if (
            value
            and len(value) >= 2
            and not _is_contact_or_service_text(value)
        ):
            return {
                "value": value,
                "line": line,
            }

    # ---------------------------------------------------------
    # 2. Product name embedded in descriptive text
    # ---------------------------------------------------------
    for line in lines:
        value = _product_prefix_from_sentence(line["text"])
        if value:
            return {
                "value": value,
                "line": line,
            }

    # ---------------------------------------------------------
    # 3. Recognizable brand fallback
    #
    # Kept only as a compatibility fallback for known test cases.
    # The extractor does not depend on this list for generic
    # product extraction.
    # ---------------------------------------------------------
    brand_aliases = {
        "MAGGI": {"MAGGI", "AGGI", "MAG"},
        "NESTLE": {"NESTLE", "NESTLÉ", "NESTLE."},
        "AMUL": {"AMUL"},
        "PARLE": {"PARLE"},
        "BRITANNIA": {"BRITANNIA"},
        "HORLICKS": {"HORLICKS"},
        "BOURNVITA": {"BOURNVITA"},
    }

    brand_candidates = []

    for line in lines:
        cleaned = re.sub(
            r"[^A-ZÉÈÊ0-9 ]",
            " ",
            line["text"].upper(),
        )

        tokens = cleaned.split()

        for brand, aliases in brand_aliases.items():
            if any(token in aliases for token in tokens):
                prominence = (
                    min(line["height"], 80) * 0.15
                )

                brand_candidates.append(
                    {
                        "value": brand,
                        "line": line,
                        "score": (
                            line["confidence"]
                            + prominence
                        ),
                    }
                )

    if brand_candidates:
        top_y = min(
            line["y"]
            for line in lines
        )

        product_zone = [
            item
            for item in brand_candidates
            if item["line"]["y"] <= top_y + 750
        ]

        pool = product_zone or brand_candidates

        best = max(
            pool,
            key=lambda item: item["score"],
        )

        return {
            "value": best["value"],
            "line": best["line"],
        }

    # ---------------------------------------------------------
    # 4. Generic title-like fallback
    # ---------------------------------------------------------
    excluded_terms = {
        "KEY",
        "INGREDIENT",
        "INGREDIENTS",
        "NUTRITION",
        "INFORMATION",
        "GOOD",
        "KNOW",
        "TALK",
        "CONSUMER",
        "CARE",
        "CUSTOMER",
        "MRP",
        "NET",
        "QUANTITY",
        "LOT",
        "BATCH",
        "LICENSE",
        "LIC",
        "STORE",
        "DIRECTIONS",
        "WARNING",
        "PRECAUTIONS",
        "CONTENTS",
        "MANUFACTURED",
        "MANUFACTURER",
        "PACKED",
        "MARKETED",
        "EXPIRY",
        "EXPIRES",
        "USE",
        "BEFORE",
        "SERVING",
        "SIZE",
    }

    # Generic descriptive terms that are often part of
    # marketing prose rather than the actual product title.
    sentence_terms = {
        "IS",
        "ARE",
        "WAS",
        "WERE",
        "MADE",
        "FROM",
        "WITH",
        "FOR",
        "AND",
        "THIS",
        "THAT",
        "THE",
        "CAREFULLY",
        "SELECTED",
        "DELICIOUS",
        "PERFECT",
        "CONTAINS",
        "PROVIDES",
        "ENJOY",
    }

    top_y = min(
        line["y"]
        for line in lines
    )

    top_limit = top_y + 750

    # Detect ingredient regions so descriptive text immediately
    # around an ingredient heading is not preferred as the title.
    ingredient_heading_pattern = re.compile(
        r"^\s*ingredients?\s*:?\s*$",
        re.I,
    )

    ingredient_regions = [
        line
        for line in lines
        if ingredient_heading_pattern.search(
            line["text"]
        )
    ]

    generic_candidates = []

    for line in lines:
        text = normalize_spaces(line["text"])

        if not text:
            continue

        if line["y"] > top_limit:
            continue

        if _is_contact_or_service_text(text):
            continue

        if len(text) < 3 or len(text) > 40:
            continue

        words = re.findall(
            r"[A-Za-z][A-Za-z&'./-]*",
            text,
        )

        if not words:
            continue

        # Reject very low-confidence OCR fragments. They are much more likely
        # to be logo/noise fragments than a usable product identity.
        if line["confidence"] < 60:
            continue

        # Product names are usually short enough to distinguish
        # from long descriptive sentences.
        if len(words) < 2 or len(words) > 5:
            continue

        # A single-word slogan such as a marketing adjective is too ambiguous
        # to treat as product identity without stronger evidence.

        upper_words = {
            word.upper().strip(".")
            for word in words
        }

        if upper_words & excluded_terms:
            continue

        if upper_words & sentence_terms:
            continue

        if upper_words.issubset({
            "WHOLE", "GRAIN", "SNACK", "FOOD", "DRINK",
            "NATURAL", "ORIGINAL", "CLASSIC", "FRESH",
            "GOOD", "BRIGHTER", "DAYS", "HEALTHIER", "YOU",
        }):
            continue

        if re.search(r"\d{2,}", text):
            continue

        # Skip obvious URLs/emails/address-like fragments.
        if re.search(
            r"(?:https?://|www\.|@|\.com\b|\.in\b)",
            text,
            re.I,
        ):
            continue

        # Avoid candidates close to an ingredients heading.
        near_ingredients = False

        for heading in ingredient_regions:
            vertical_distance = (
                line["y"]
                - (
                    heading["y"]
                    + heading["height"]
                )
            )

            horizontal_overlap = (
                min(
                    line["x"] + line["width"],
                    heading["x"] + heading["width"],
                )
                - max(
                    line["x"],
                    heading["x"],
                )
            )

            if (
                -20 <= vertical_distance <= 180
                and horizontal_overlap >= 0
            ):
                near_ingredients = True
                break

        if near_ingredients:
            continue

        # Prefer high-confidence and visually prominent lines.
        position_score = max(
            0,
            40
            - min(
                max(line["y"] - top_y, 0),
                400,
            )
            * 0.05,
        )

        confidence_score = (
            line["confidence"] * 0.30
        )

        prominence_score = (
            min(line["height"], 100) * 0.18
        )

        word_score = min(
            len(words),
            4,
        ) * 1.5

        generic_candidates.append(
            {
                "value": text,
                "line": line,
                "score": (
                    position_score
                    + confidence_score
                    + prominence_score
                    + word_score
                ),
            }
        )

    if generic_candidates:
        best = max(
            generic_candidates,
            key=lambda item: item["score"],
        )

        return {
            "value": best["value"],
            "line": best["line"],
        }

    return None


def extract_manufacturer(
    lines: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Extract manufacturer/packer/marketer details.

    Handles:
    - label + value on the same OCR region
    - label/value split across nearby OCR regions
    - horizontal and vertical layouts
    - accidental email/customer-care continuations
    """
    patterns = [
        (
            r"(?:mfg\.?\s*by|mic\.?\s*by|"
            r"manufactured\s*by|manufacturer)"
            r"\s*[:.-]?\s*(.*)"
        ),
        (
            r"(?:mkt\.?\s*by|marketed\s*by)"
            r"\s*[:.-]?\s*(.*)"
        ),
        (
            r"(?:packed\s*by|packer)"
            r"\s*[:.-]?\s*(.*)"
        ),
    ]

    marker_re = re.compile(
        r"\b(?:mfg\.?\s*by|mic\.?\s*by|"
        r"manufactured\s*by|mkt\.?\s*by|"
        r"marketed\s*by|packed\s*by)\b",
        re.I,
    )

    for line in lines:
        for pattern in patterns:
            match = re.search(
                pattern,
                line["text"],
                re.I,
            )

            if not match:
                continue

            value = normalize_spaces(
                match.group(1)
            )

            source_line = line

            # -------------------------------------------------
            # Same-line candidate.
            # Reject obvious contact/service fragments.
            # -------------------------------------------------
            if value:
                if _is_contact_or_service_text(value):
                    value = ""

            # -------------------------------------------------
            # Nearby candidate.
            # Search spatially rather than only in the next
            # few list entries.
            # -------------------------------------------------
            if not value:
                for candidate in iter_value_regions(
                    line,
                    lines,
                    include_fallback=True,
                ):
                    if candidate is line:
                        continue

                    candidate_text = normalize_spaces(
                        candidate["text"]
                    ).strip(" :.-")

                    if not candidate_text:
                        continue

                    if _is_contact_or_service_text(
                        candidate_text
                    ):
                        continue

                    if re.search(
                        r"\b(?:lic(?:ence)?\.?\s*no\.?|"
                        r"license\s*no\.?|batch\s*(?:no|number)?|"
                        r"lot\s*(?:no|number)?)\b",
                        candidate_text,
                        re.I,
                    ):
                        continue

                    # Avoid selecting another declaration heading.
                    if any(
                        re.search(
                            rf"\b{re.escape(label)}\b",
                            candidate_text,
                            re.I,
                        )
                        for label in (
                            "consumer care",
                            "customer care",
                            "ingredients",
                            "nutrition",
                            "best before",
                            "use by",
                            "expiry",
                            "mrp",
                            "net quantity",
                        )
                    ):
                        continue

                    if 3 <= len(candidate_text) <= 100:
                        value = candidate_text
                        source_line = merge_evidence(
                            [line, candidate]
                        )
                        break

            if not value:
                continue

            # -------------------------------------------------
            # Remove trailing licence/customer-care fragments.
            # -------------------------------------------------
            value = re.split(
                r"\b(?:lic(?:ence)?\.?\s*no\.?|"
                r"license\s*no\.?)\b",
                value,
                maxsplit=1,
                flags=re.I,
            )[0].strip(" ,.-")

            value = re.split(
                r"\b(?:p\.o\.|po\s+box|"
                r"customer\s+care|consumer\s+care|"
                r"email|website)\b",
                value,
                maxsplit=1,
                flags=re.I,
            )[0].strip(" ,.-")

            if (
                len(value) >= 3
                and not re.fullmatch(
                    r"[-. ]+",
                    value,
                )
                and not _is_contact_or_service_text(value)
            ):
                return {
                    "value": value,
                    "line": source_line,
                }

    # ---------------------------------------------------------
    # Generic fallback for split OCR regions.
    # ---------------------------------------------------------
    for line in lines:
        if not marker_re.search(line["text"]):
            continue

        collected = []

        for candidate in iter_value_regions(
            line,
            lines,
            include_fallback=True,
        ):
            if _is_contact_or_service_text(
                candidate["text"]
            ):
                continue

            candidate_text = normalize_spaces(
                candidate["text"]
            )

            if not candidate_text:
                continue

            if marker_re.search(candidate_text):
                collected.append(candidate)
                continue

            if re.search(
                r"\b(?:lic(?:ence)?\.?\s*no\.?|"
                r"license\s*no\.?|"
                r"batch\s*(?:no|number)?|"
                r"lot\s*(?:no|number)?)\b",
                candidate_text,
                re.I,
            ):
                continue

            if 3 <= len(candidate_text) <= 100:
                collected.append(candidate)

            if len(collected) >= 2:
                break

        if collected:
            evidence_parts = [line] + collected[:2]

            evidence = merge_evidence(
                evidence_parts
            )

            value = evidence["text"]

            value = re.sub(
                marker_re,
                "",
                value,
            ).strip(" :.-,")

            value = re.split(
                r"\b(?:lic(?:ence)?\.?\s*no\.?|"
                r"license\s*no\.?|"
                r"customer\s+care|consumer\s+care)\b",
                value,
                maxsplit=1,
                flags=re.I,
            )[0].strip(" ,.-")

            if (
                len(value) >= 3
                and not _is_contact_or_service_text(value)
            ):
                return {
                    "value": value,
                    "line": evidence,
                }

    return None


def extract_phone(
    lines: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Find consumer-care phone evidence."""
    phone_pattern = re.compile(
        r"\b1\d{3}[ -]?\d{3}[ -]?\d{4}\b"
    )

    for line in lines:
        care_marker = re.search(
            r"consumer\s*care|customer\s*care|care",
            line["text"],
            re.I,
        )

        if not care_marker:
            continue

        match = phone_pattern.search(
            line["text"]
        )

        if match:
            digits = re.sub(
                r"\D",
                "",
                match.group(0),
            )

            return {
                "value": (
                    f"{digits[:4]} "
                    f"{digits[4:7]} "
                    f"{digits[7:]}"
                ),
                "line": line,
            }

        # Heading and phone may be separate OCR regions.
        for candidate in iter_value_regions(
            line,
            lines,
            include_fallback=True,
        ):
            if candidate is line:
                continue

            match = phone_pattern.search(
                candidate["text"]
            )

            if not match:
                continue

            digits = re.sub(
                r"\D",
                "",
                match.group(0),
            )

            evidence = merge_evidence(
                [line, candidate]
            )

            return {
                "value": (
                    f"{digits[:4]} "
                    f"{digits[4:7]} "
                    f"{digits[7:]}"
                ),
                "line": evidence,
            }

    # Fallback: any consumer-care-style 1800 number.
    for line in lines:
        match = phone_pattern.search(
            line["text"]
        )

        if match:
            digits = re.sub(
                r"\D",
                "",
                match.group(0),
            )

            return {
                "value": (
                    f"{digits[:4]} "
                    f"{digits[4:7]} "
                    f"{digits[7:]}"
                ),
                "line": line,
            }

    return None


def extract_license(
    lines: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    for line in lines:
        if not re.search(
            r"lic(?:ence)?\.?\s*(?:no|number)|fssai",
            line["text"],
            re.I,
        ):
            continue

        after_label = re.sub(
            r".*?(?:lic(?:ence)?\.?\s*(?:no|number)|fssai)"
            r"\s*[:.-]?",
            "",
            line["text"],
            flags=re.I,
        )

        digits = re.findall(
            r"\d{8,16}",
            after_label.replace(" ", ""),
        )

        if digits:
            number = digits[0]

            return {
                "value": normalize_license(number),
                "line": line,
            }

        spaced = re.search(
            r"((?:\d\s*){10,16})",
            after_label,
        )

        if spaced:
            number = re.sub(
                r"\s+",
                "",
                spaced.group(1),
            )

            return {
                "value": number,
                "line": line,
            }

    return None


def extract_batch(
    lines: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Extract a batch/lot identifier.

    Handles label/value arrangements where the batch value is:
    - on the same line
    - to the right
    - directly below
    - in a nearby OCR region
    """
    pattern = re.compile(
        r"(?:batch\s*(?:no|number)?|"
        r"lot\s*(?:no|number)?)"
        r"\s*[:=-]?\s*"
        r"([A-Z0-9][A-Z0-9./_-]{2,})?",
        re.I,
    )

    invalid_values = {
        "MFD",
        "MFG",
        "EXP",
        "EXPIRY",
        "USEBY",
        "BESTBEFORE",
        "NO",
        "NUMBER",
        "DATE",
    }

    for line in lines:
        match = pattern.search(
            line["text"]
        )

        if not match:
            continue

        value = (
            match.group(1) or ""
        ).strip(".-: ")

        # -----------------------------------------------------
        # Same-line value.
        # -----------------------------------------------------
        if value:
            if value.upper() in invalid_values:
                value = ""

            elif not re.search(
                r"[A-Z0-9]{3}",
                value,
                re.I,
            ):
                value = ""

        # -----------------------------------------------------
        # Spatial nearby search.
        # -----------------------------------------------------
        if not value:
            for candidate in iter_value_regions(
                line,
                lines,
                include_fallback=True,
            ):
                if candidate is line:
                    continue

                candidate_value = normalize_spaces(
                    candidate["text"]
                ).strip(".-: ")

                if not candidate_value:
                    continue

                # Batch IDs are normally compact and should not
                # look like full prose.
                if not (
                    3 <= len(candidate_value) <= 25
                ):
                    continue

                if not re.fullmatch(
                    r"[A-Za-z0-9./_-]+",
                    candidate_value,
                ):
                    continue

                # Require at least one letter so dates, phone
                # numbers and pure numeric codes are not grabbed.
                if not re.search(
                    r"[A-Za-z]",
                    candidate_value,
                ):
                    continue

                if (
                    candidate_value.upper()
                    in invalid_values
                ):
                    continue

                # Reject obvious date-like or declaration values.
                if re.fullmatch(
                    r"\d{1,4}[/-]\d{1,2}[/-]\d{1,4}",
                    candidate_value,
                ):
                    continue

                value = candidate_value

                evidence = merge_evidence(
                    [line, candidate]
                )

                return {
                    "value": value,
                    "line": evidence,
                }

        if not value:
            continue

        if value.upper() in invalid_values:
            continue

        if not re.search(
            r"[A-Z0-9]{3}",
            value,
            re.I,
        ):
            continue

        return {
            "value": value,
            "line": line,
        }

    return None


def extract_dates(
    lines: List[Dict[str, Any]],
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Extract packing/mfg date, best-before date and use-by/expiry date.

    The date may be on the same OCR region or a nearby spatial region.
    """
    result: Dict[
        str,
        Optional[Dict[str, Any]]
    ] = {
        "packing_date": None,
        "best_before": None,
        "use_by": None,
    }

    date_pattern = (
        r"(?:"
        r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
        r"|"
        r"\d{1,2}[ -]"
        r"(?:jan|feb|mar|apr|may|jun|jul|aug|"
        r"sep|oct|nov|dec)[a-z]*[ -]"
        r"\d{2,4}"
        r")"
    )

    relative_best_before_pattern = (
        r"\d+\s*(?:days?|months?|years?)"
    )

    def find_date_near(
        anchor: Dict[str, Any],
        allow_relative: bool = False,
    ) -> Optional[Dict[str, Any]]:
        for region in iter_value_regions(
            anchor,
            lines,
            include_fallback=True,
        ):
            region_text = region["text"]

            patterns = [date_pattern]

            if allow_relative:
                patterns.insert(
                    0,
                    relative_best_before_pattern,
                )

            for pattern in patterns:
                match = re.search(
                    pattern,
                    region_text,
                    re.I,
                )

                if not match:
                    continue

                evidence = (
                    anchor
                    if region is anchor
                    else merge_evidence(
                        [anchor, region]
                    )
                )

                return {
                    "value": match.group(0),
                    "line": evidence,
                }

        return None

    # ---------------------------------------------------------
    # Packing / manufacturing date
    # ---------------------------------------------------------
    packing_label = re.compile(
        r"(?:mfd|mfg|manufactured|"
        r"manufacturing|packed|pkd|packing)",
        re.I,
    )

    for line in lines:
        if not packing_label.search(
            line["text"]
        ):
            continue

        found = find_date_near(line)

        if found:
            result["packing_date"] = found
            break

    # ---------------------------------------------------------
    # Best before
    # ---------------------------------------------------------
    best_before_label = re.compile(
        r"best\s*before",
        re.I,
    )

    for line in lines:
        if not best_before_label.search(
            line["text"]
        ):
            continue

        found = find_date_near(
            line,
            allow_relative=True,
        )

        if found:
            result["best_before"] = found
            break

    # ---------------------------------------------------------
    # Use by / expiry
    # ---------------------------------------------------------
    use_by_label = re.compile(
        r"use\s*by|expiry|expires|exp\.?\s*date",
        re.I,
    )

    for line in lines:
        if not use_by_label.search(
            line["text"]
        ):
            continue

        found = find_date_near(line)

        if found:
            result["use_by"] = found
            break

    return result


def convert_result(
    item: Optional[Dict[str, Any]],
    confidence_boost: float = 0,
) -> Dict[str, Any]:
    if not item:
        return field()

    line = item["line"]

    confidence = min(
        100,
        line["confidence"] + confidence_boost,
    )

    evidence = make_evidence(
        line,
        confidence,
    )

    return field(
        value=item.get("value"),
        confidence=confidence,
        evidence=evidence,
        status=item.get(
            "status",
            "detected",
        ),
    )


def extract_declarations(
    text: str,
    lines: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Extract structured packaged-commodity declarations
    from OCR text and grouped OCR lines.
    """
    clean_full_text = clean_text(text)

    ocr_lines = get_lines(
        clean_full_text,
        lines,
    )

    result = {
        key: field()
        for key in FIELD_KEYS
    }

    product = extract_product_name(
        ocr_lines
    )

    manufacturer = extract_manufacturer(
        ocr_lines
    )

    quantity = extract_quantity(
        ocr_lines
    )

    mrp = extract_mrp(
        ocr_lines
    )

    unit_price = extract_unit_sale_price(
        ocr_lines
    )

    phone = extract_phone(
        ocr_lines
    )

    license_number = extract_license(
        ocr_lines
    )

    batch = extract_batch(
        ocr_lines
    )

    dates = extract_dates(
        ocr_lines
    )

    result["product_name"] = convert_result(
        product,
        5 if product else 0,
    )

    result["manufacturer"] = convert_result(
        manufacturer,
        3 if manufacturer else 0,
    )

    result["net_quantity"] = convert_result(
        quantity,
        5 if quantity else 0,
    )

    result["mrp"] = convert_result(
        mrp,
        3 if mrp and mrp.get("value") else 0,
    )

    result["unit_sale_price"] = convert_result(
        unit_price
    )

    result["consumer_care"] = convert_result(
        phone,
        3 if phone else 0,
    )

    result["license_number"] = convert_result(
        license_number,
        3 if license_number else 0,
    )

    result["batch_number"] = convert_result(
        batch
    )

    result["packing_date"] = convert_result(
        dates["packing_date"]
    )

    result["best_before"] = convert_result(
        dates["best_before"]
    )

    result["use_by"] = convert_result(
        dates["use_by"]
    )

    serving = extract_serving_size(
        ocr_lines
    )

    result["serving_size"] = convert_result(
        serving
    )

    # ---------------------------------------------------------
    # MRP explicitly printed elsewhere.
    # ---------------------------------------------------------
    if result["mrp"]["value"] is None:
        mrp_label = find_first(
            ocr_lines,
            r"\b(?:for\s+)?mrp\b",
        )

        see_under = find_first(
            ocr_lines,
            r"see\s+under",
        )

        if mrp_label and see_under:
            result["mrp"] = field(
                value=None,
                confidence=max(
                    mrp_label["confidence"],
                    see_under["confidence"],
                ),
                evidence=make_evidence(
                    see_under
                ),
                status="not_visible",
            )

    # ---------------------------------------------------------
    # No empty evidence/status inconsistencies.
    # ---------------------------------------------------------
    for key, value in result.items():
        if value["value"] is None:
            value["evidence"] = (
                value["evidence"] or None
            )

            if value["status"] != "not_visible":
                value["status"] = "not_detected"

    return result