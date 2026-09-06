import re
from typing import Any, Dict, List


COMPARABLE_FIELDS = [
    "product_name",
    "manufacturer",
    "net_quantity",
    "mrp",
    "packing_date",
    "best_before",
    "use_by",
    "consumer_care",
]

# Below this confidence, conflicting OCR values are treated as uncertain
# rather than reported as a potential discrepancy.
MIN_COMPARISON_CONFIDENCE = 60.0


def normalize_value(value: Any) -> str:
    """Normalize values so harmless formatting differences do not matter."""
    if value is None:
        return ""

    value = str(value).lower().strip()

    # Normalize currency wording.
    value = value.replace("₹", "rs")
    value = re.sub(r"\brs\.?\b", "rs", value)

    # Remove formatting differences such as spaces and punctuation.
    # Examples:
    # "₹199"   -> "rs199"
    # "Rs 199" -> "rs199"
    # "120 g"  -> "120g"
    # "120g"   -> "120g"
    value = re.sub(r"[^a-z0-9]+", "", value)

    return value


def _get_confidence(field: Dict[str, Any]) -> float:
    """Return a safe numeric confidence value."""
    value = field.get("confidence", 0)

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _is_reliable(field: Dict[str, Any]) -> bool:
    """Return True when the extracted field is reliable enough to compare."""
    return _get_confidence(field) >= MIN_COMPARISON_CONFIDENCE


def compare_declarations(
    results: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Compare declarations across uploaded package panels.

    Only clearly detected values are compared. Missing or not-visible
    values are ignored. When conflicting values are detected but OCR
    confidence is too low, the result is marked REVIEW_REQUIRED instead
    of being reported as a potential discrepancy.
    """
    comparisons = []

    if len(results) < 2:
        return comparisons

    for field_name in COMPARABLE_FIELDS:
        values = []

        for result in results:
            # Ignore image-processing failures.
            if result.get("error"):
                continue

            declarations = result.get("declarations", {})
            field = declarations.get(field_name, {})

            if not isinstance(field, dict):
                continue

            value = field.get("value")
            status = field.get("status")

            # Only actual detected values should participate in comparison.
            # Missing/not-visible fields are simply insufficient evidence.
            if value in (None, "", []):
                continue

            if status != "detected":
                continue

            values.append(
                {
                    "filename": result.get("filename"),
                    "value": value,
                    "confidence": _get_confidence(field),
                    "evidence": field.get("evidence"),
                }
            )

        # Nothing meaningful to compare.
        if len(values) < 2:
            continue

        normalized = {
            normalize_value(item["value"])
            for item in values
        }

        if len(normalized) == 1:
            comparisons.append(
                {
                    "field": field_name,
                    "status": "MATCH",
                    "message": (
                        "The detected values match across the supplied panels."
                    ),
                    "sources": values,
                }
            )
            continue

        # Values are different. Before calling this a discrepancy,
        # make sure every compared value has sufficient OCR confidence.
        all_reliable = all(
            item["confidence"] >= MIN_COMPARISON_CONFIDENCE
            for item in values
        )

        if all_reliable:
            status = "POTENTIAL_DISCREPANCY"
            message = (
                "Different values were detected across the supplied panels. "
                "Manual verification is required."
            )
        else:
            status = "REVIEW_REQUIRED"
            message = (
                "Different values were detected, but one or more OCR results "
                "have low confidence. Manual verification is required before "
                "treating this as a discrepancy."
            )

        comparisons.append(
            {
                "field": field_name,
                "status": status,
                "message": message,
                "sources": values,
            }
        )

    return comparisons