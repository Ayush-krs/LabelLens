"""Generic, evidence-backed inspection rules for LabelLens.

This module does not make a legal determination. It evaluates whether
structured declarations were detected well enough to continue inspection.
"""

from typing import Any


STATUS_PASS = "PASS"
STATUS_REVIEW = "REVIEW_REQUIRED"
STATUS_POTENTIAL = "POTENTIAL_VIOLATION"


def _field_value(field: Any):
    """Return the extracted value from a declaration field."""
    if isinstance(field, dict):
        return field.get("value")
    return field


def _field_confidence(field: Any):
    """Return a numeric confidence when the extractor provides one."""
    if isinstance(field, dict):
        value = field.get("confidence", 0)
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _field_status(field: Any):
    """Return extractor status, if available."""
    if isinstance(field, dict):
        return field.get("status")
    return None


def _field_evidence(field: Any):
    """Return evidence object, if available."""
    if isinstance(field, dict):
        return field.get("evidence")
    return None


def _check_field(
    *,
    check_id: str,
    field_name: str,
    label: str,
    field: Any,
    missing_reason: str,
    low_confidence_reason: str,
    confidence_threshold: float = 60.0,
    category_dependent: bool = False,
):
    value = _field_value(field)
    confidence = _field_confidence(field)
    extractor_status = _field_status(field)
    evidence = _field_evidence(field)

    if value not in (None, "", []):
        if confidence and confidence < confidence_threshold:
            status = STATUS_REVIEW
            reason = low_confidence_reason
        else:
            status = STATUS_PASS
            reason = "A declaration was detected and retained as inspection evidence."
    elif extractor_status == "not_visible":
        status = STATUS_REVIEW
        reason = "Related declaration text was detected, but the value was not captured clearly. Inspect the package image manually."
    else:
        status = STATUS_REVIEW
        reason = missing_reason

    if category_dependent:
        reason += " Applicability depends on the commodity category and should be confirmed by an authorised inspector."

    return {
        "check_id": check_id,
        "field": field_name,
        "label": label,
        "status": status,
        "reason": reason,
        "confidence": round(confidence, 2),
        "value": value,
        "evidence": evidence,
    }


def run_compliance_checks(declarations: dict, category: str = "general_packaged_commodity") -> dict:
    """Run conservative, generic inspection checks.

    The default category intentionally avoids declaring that every field is
    universally mandatory. Missing or unclear fields become REVIEW_REQUIRED.
    """

    declarations = declarations or {}

    checks = [
        _check_field(
            check_id="product_name_present",
            field_name="product_name",
            label="Product identity detected",
            field=declarations.get("product_name"),
            missing_reason="A clear product identity was not detected. Review the package visually.",
            low_confidence_reason="A product identity was detected, but OCR confidence is low. Confirm it visually.",
        ),
        _check_field(
            check_id="net_quantity_present",
            field_name="net_quantity",
            label="Net quantity detected",
            field=declarations.get("net_quantity"),
            missing_reason="A net quantity declaration was not detected. Review the package visually.",
            low_confidence_reason="A net quantity was detected, but OCR confidence is low. Confirm the printed declaration.",
        ),
        _check_field(
            check_id="mrp_visible",
            field_name="mrp",
            label="MRP visibility check",
            field=declarations.get("mrp"),
            missing_reason="An MRP value was not clearly captured. Inspect the printed MRP on the package.",
            low_confidence_reason="An MRP value was detected with low OCR confidence. Confirm the printed value manually.",
        ),
        _check_field(
            check_id="manufacturer_details_present",
            field_name="manufacturer",
            label="Manufacturer / responsible-entity details detected",
            field=declarations.get("manufacturer"),
            missing_reason="Manufacturer or related responsible-entity details were not clearly detected. Review the package.",
            low_confidence_reason="Manufacturer or related responsible-entity details were detected with low OCR confidence. Confirm visually.",
        ),
        _check_field(
            check_id="consumer_care_present",
            field_name="consumer_care",
            label="Consumer-care information detected",
            field=declarations.get("consumer_care"),
            missing_reason="Consumer-care information was not clearly detected. Review the package and commodity category.",
            low_confidence_reason="Consumer-care information was detected with low OCR confidence. Confirm visually.",
            category_dependent=True,
        ),
        _check_field(
            check_id="licence_number_detected",
            field_name="license_number",
            label="Licence / registration number detected",
            field=declarations.get("license_number"),
            missing_reason="A licence or registration number was not detected. Check whether the commodity category requires one.",
            low_confidence_reason="A licence or registration number was detected with low OCR confidence. Confirm visually.",
            category_dependent=True,
        ),
        _check_field(
            check_id="batch_or_lot_detected",
            field_name="batch_number",
            label="Batch / lot identifier detected",
            field=declarations.get("batch_number"),
            missing_reason="A batch or lot identifier was not clearly detected. Check the package and commodity category.",
            low_confidence_reason="A batch or lot identifier was detected with low OCR confidence. Confirm visually.",
            category_dependent=True,
        ),
        _check_field(
            check_id="date_information_detected",
            field_name="packing_date",
            label="Packing / date information detected",
            field=declarations.get("packing_date"),
            missing_reason="Packing or related date information was not clearly detected. Check the package and commodity category.",
            low_confidence_reason="Packing or related date information was detected with low OCR confidence. Confirm visually.",
            category_dependent=True,
        ),
    ]

    summary = {
        "pass": sum(check["status"] == STATUS_PASS for check in checks),
        "review_required": sum(check["status"] == STATUS_REVIEW for check in checks),
        "potential_violation": sum(check["status"] == STATUS_POTENTIAL for check in checks),
        "total": len(checks),
    }

    return {
        "category": category,
        "disclaimer": "Automated inspection assistance only. A final legal determination requires authorised human review.",
        "checks": checks,
        "summary": summary,
    }