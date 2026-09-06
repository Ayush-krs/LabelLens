import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from extractor import extract_declarations
from compliance import run_compliance_checks
from comparator import compare_declarations


class ComparisonTests(unittest.TestCase):

    def test_matching_values_across_panels(self):
        results = [
            {
                "filename": "front.jpg",
                "declarations": {
                    "mrp": {
                        "value": "₹199",
                        "confidence": 90,
                        "status": "detected",
                        "evidence": None,
                    }
                },
            },
            {
                "filename": "back.jpg",
                "declarations": {
                    "mrp": {
                        "value": "Rs 199",
                        "confidence": 85,
                        "status": "detected",
                        "evidence": None,
                    }
                },
            },
        ]

        comparisons = compare_declarations(results)

        self.assertEqual(len(comparisons), 1)
        self.assertEqual(comparisons[0]["field"], "mrp")
        self.assertEqual(comparisons[0]["status"], "MATCH")

    def test_different_values_create_potential_discrepancy(self):
        results = [
            {
                "filename": "front.jpg",
                "declarations": {
                    "mrp": {
                        "value": "₹199",
                        "confidence": 90,
                        "status": "detected",
                        "evidence": None,
                    }
                },
            },
            {
                "filename": "side.jpg",
                "declarations": {
                    "mrp": {
                        "value": "₹249",
                        "confidence": 85,
                        "status": "detected",
                        "evidence": None,
                    }
                },
            },
        ]

        comparisons = compare_declarations(results)

        self.assertEqual(len(comparisons), 1)
        self.assertEqual(
            comparisons[0]["status"],
            "POTENTIAL_DISCREPANCY",
        )

    def test_missing_field_on_one_panel_is_not_violation(self):
        results = [
            {
                "filename": "front.jpg",
                "declarations": {
                    "mrp": {
                        "value": "₹199",
                        "confidence": 90,
                        "status": "detected",
                        "evidence": None,
                    }
                },
            },
            {
                "filename": "back.jpg",
                "declarations": {
                    "mrp": {
                        "value": None,
                        "confidence": 0,
                        "status": "not_detected",
                        "evidence": None,
                    }
                },
            },
        ]

        comparisons = compare_declarations(results)

        self.assertEqual(comparisons, [])

    def test_quantity_formatting_differences_still_match(self):
        results = [
            {
                "filename": "front.jpg",
                "declarations": {
                    "net_quantity": {
                        "value": "120 g",
                        "confidence": 90,
                        "status": "detected",
                        "evidence": None,
                    }
                },
            },
            {
                "filename": "back.jpg",
                "declarations": {
                    "net_quantity": {
                        "value": "120g",
                        "confidence": 85,
                        "status": "detected",
                        "evidence": None,
                    }
                },
            },
        ]

        comparisons = compare_declarations(results)

        self.assertEqual(comparisons[0]["status"], "MATCH")

    def test_single_image_has_no_comparison(self):
        results = [
            {
                "filename": "front.jpg",
                "declarations": {
                    "mrp": {
                        "value": "₹199",
                        "confidence": 90,
                        "status": "detected",
                        "evidence": None,
                    }
                },
            }
        ]

        comparisons = compare_declarations(results)

        self.assertEqual(comparisons, [])


def line(text, x=10, y=10, width=220, height=24, confidence=90):
    return {
        "text": text,
        "confidence": confidence,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
    }


def extract(lines, text=""):
    return extract_declarations(text, lines)


class NetQuantityAndServingSizeTests(unittest.TestCase):
    def test_net_quantity_and_each_serve_are_separate(self):
        result = extract([
            line("NET QUANTITY: 280 g", y=20),
            line("Each serve (70 g)", y=220),
        ])
        self.assertEqual(result["net_quantity"]["value"], "280 g")
        self.assertEqual(result["net_quantity"]["status"], "detected")
        self.assertEqual(result["serving_size"]["value"], "70 g")
        self.assertEqual(result["serving_size"]["status"], "detected")

    def test_quantity_per_serve_is_not_net_quantity(self):
        result = extract([line("Quantity per serve: 30 g", y=40)])
        self.assertIsNone(result["net_quantity"]["value"])
        self.assertEqual(result["net_quantity"]["status"], "not_detected")
        self.assertEqual(result["serving_size"]["value"], "30 g")
        self.assertEqual(result["serving_size"]["status"], "detected")

    def test_net_wt_is_net_quantity(self):
        result = extract([line("Net Wt 500 ml", y=30)])
        self.assertEqual(result["net_quantity"]["value"], "500 ml")
        self.assertEqual(result["net_quantity"]["status"], "detected")
        self.assertIsNone(result["serving_size"]["value"])
        self.assertEqual(result["serving_size"]["status"], "not_detected")

    def test_fragmented_net_quantity_label_and_value(self):
        result = extract([
            line("NET QUANTITY:", x=12, y=40, width=180, height=22),
            line("280 g", x=12, y=70, width=80, height=22),
        ])
        self.assertEqual(result["net_quantity"]["value"], "280 g")
        self.assertEqual(result["net_quantity"]["status"], "detected")

    def test_per_100_g_nutrition_is_not_net_quantity(self):
        result = extract([
            line("Energy per 100 g 350 kcal", y=80),
            line("Protein 12 g per 100 g", y=110),
        ])
        self.assertIsNone(result["net_quantity"]["value"])
        self.assertEqual(result["net_quantity"]["status"], "not_detected")
        self.assertIsNone(result["serving_size"]["value"])
        self.assertEqual(result["serving_size"]["status"], "not_detected")


class PriceExtractionTests(unittest.TestCase):
    def test_mrp_and_unit_sale_price_are_separate(self):
        result = extract([
            line("MRP ₹100", y=20),
            line("Unit Sale Price ₹1/ml", y=60),
        ])
        self.assertEqual(result["mrp"]["value"], "₹100")
        self.assertEqual(result["mrp"]["status"], "detected")
        self.assertEqual(result["unit_sale_price"]["value"], "₹1/ml")
        self.assertEqual(result["unit_sale_price"]["status"], "detected")

    def test_mrp_with_rs_format(self):
        result = extract([line("MRP Rs. 250", y=20)])
        self.assertEqual(result["mrp"]["value"], "₹250")
        self.assertEqual(result["mrp"]["status"], "detected")

    def test_maximum_retail_price_format(self):
        result = extract([line("Maximum Retail Price ₹199", y=20)])
        self.assertEqual(result["mrp"]["value"], "₹199")
        self.assertEqual(result["mrp"]["status"], "detected")

    def test_unit_sale_price_is_not_mrp(self):
        result = extract([line("Unit Sale Price ₹1/ml", y=20)])
        self.assertIsNone(result["mrp"]["value"])
        self.assertEqual(result["mrp"]["status"], "not_detected")
        self.assertEqual(result["unit_sale_price"]["value"], "₹1/ml")

    def test_sale_price_per_is_not_mrp(self):
        result = extract([line("Sale Price Per 2/kg", y=20)])
        self.assertIsNone(result["mrp"]["value"])
        self.assertEqual(result["mrp"]["status"], "not_detected")
        self.assertEqual(result["unit_sale_price"]["value"], "₹2/kg")

    def test_unrelated_offer_price_is_not_mrp(self):
        result = extract([line("Special offer price ₹80", y=20)])
        self.assertIsNone(result["mrp"]["value"])
        self.assertIsNone(result["unit_sale_price"]["value"])


class SpatialExtractionTests(unittest.TestCase):
    def test_net_quantity_value_on_same_line(self):
        result = extract([line("NET QUANTITY: 500 g", x=20, y=20, width=250)])
        self.assertEqual(result["net_quantity"]["value"], "500 g")

    def test_net_quantity_value_to_the_right(self):
        result = extract([
            line("NET QUANTITY:", x=20, y=20, width=150),
            line("500 g", x=190, y=20, width=80),
        ])
        self.assertEqual(result["net_quantity"]["value"], "500 g")

    def test_net_quantity_value_directly_below(self):
        result = extract([
            line("NET QUANTITY:", x=20, y=20, width=150),
            line("500 g", x=25, y=60, width=80),
        ])
        self.assertEqual(result["net_quantity"]["value"], "500 g")

    def test_serving_value_nearby_is_not_selected_as_net_quantity(self):
        result = extract([
            line("NET QUANTITY:", x=20, y=20, width=150),
            line("Each serve: 70 g", x=200, y=30, width=160),
            line("280 g", x=25, y=90, width=80),
        ])
        self.assertEqual(result["net_quantity"]["value"], "280 g")
        self.assertEqual(result["serving_size"]["value"], "70 g")

    def test_closest_logical_quantity_is_selected(self):
        result = extract([
            line("NET QUANTITY:", x=20, y=20, width=150),
            line("120 g", x=40, y=70, width=80),
            line("999 g", x=450, y=70, width=80),
        ])
        self.assertEqual(result["net_quantity"]["value"], "120 g")

    def test_unrelated_nutrition_quantity_is_not_selected(self):
        result = extract([
            line("NET QUANTITY:", x=20, y=20, width=150),
            line("Protein 20 g per 100 g", x=40, y=70, width=200),
            line("300 g", x=40, y=110, width=80),
        ])
        self.assertEqual(result["net_quantity"]["value"], "300 g")


class ProductIdentityTests(unittest.TestCase):
    def test_explicit_product_name_unknown_brand(self):
        result = extract([line("Product Name: Sunbeam Herbal Shampoo", y=20)])
        self.assertEqual(result["product_name"]["value"], "Sunbeam Herbal Shampoo")
        self.assertEqual(result["product_name"]["status"], "detected")

    def test_generic_product_name_without_known_brand(self):
        result = extract([line("Organic Whole Wheat Flour", y=20, height=45)])
        self.assertEqual(result["product_name"]["value"], "Organic Whole Wheat Flour")

    def test_nutrition_text_is_not_product_identity(self):
        result = extract([
            line("Nutrition Information", y=20, height=40),
            line("Protein 12 g", y=60),
            line("Energy 350 kcal", y=90),
        ])
        self.assertNotEqual(result["product_name"]["value"], "Nutrition Information")

    def test_no_reasonable_identity_returns_not_detected(self):
        result = extract([
            line("Ingredients", y=20),
            line("Salt Sugar Spices", y=60),
            line("Net Quantity 100 g", y=100),
        ])

        self.assertIsNone(result["product_name"]["value"])
        self.assertEqual(
            result["product_name"]["status"],
            "not_detected",
        )

    def test_explicit_identity_does_not_require_brand_dictionary(self):
        result = extract([line("Name of Product: Unlisted Brand Coconut Cookies", y=20)])
        self.assertEqual(
            result["product_name"]["value"],
            "Unlisted Brand Coconut Cookies",
        )

    def test_product_identity_prefers_actual_product_over_quality_message(self):
        result = extract([
            line(
                "Milk Chocolate",
                x=20,
                y=20,
                width=180,
                height=32,
                confidence=82,
            ),
            line(
                "PRODUCT QUALITY",
                x=20,
                y=400,
                width=220,
                height=40,
                confidence=96,
            ),
            line(
                "If you are not satisfied with the product quality, retain the package",
                x=20,
                y=450,
                width=500,
                height=35,
                confidence=96,
            ),
        ])

        self.assertEqual(
            result["product_name"]["value"],
            "Milk Chocolate",
        )

    def test_quality_message_is_not_selected_as_product_identity(self):
        result = extract([
            line(
                "Milk Chocolate",
                y=30,
                confidence=80,
            ),
            line(
                "product quality, retain the package",
                y=450,
                confidence=100,
            ),
        ])

        self.assertEqual(
            result["product_name"]["value"],
            "Milk Chocolate",
        )


class ComplianceTests(unittest.TestCase):
    @staticmethod
    def make_field(value=None, confidence=0, status="not_detected", evidence=None):
        return {
            "value": value,
            "confidence": confidence,
            "status": status,
            "evidence": evidence,
        }

    @staticmethod
    def get_check(result, check_id):
        return next(check for check in result["checks"] if check["check_id"] == check_id)

    def test_high_confidence_detected_field_passes(self):
        result = run_compliance_checks({
            "net_quantity": self.make_field(
                value="500 g", confidence=90, status="detected"
            )
        })
        check = self.get_check(result, "net_quantity_present")
        self.assertEqual(check["status"], "PASS")

    def test_low_confidence_field_requires_review(self):
        result = run_compliance_checks({
            "net_quantity": self.make_field(
                value="500 g", confidence=45, status="detected"
            )
        })
        check = self.get_check(result, "net_quantity_present")
        self.assertEqual(check["status"], "REVIEW_REQUIRED")

    def test_missing_field_requires_review_not_violation(self):
        result = run_compliance_checks({
            "net_quantity": self.make_field(
                value=None, confidence=0, status="not_detected"
            )
        })
        check = self.get_check(result, "net_quantity_present")
        self.assertEqual(check["status"], "REVIEW_REQUIRED")
        self.assertNotEqual(check["status"], "POTENTIAL_VIOLATION")

    def test_not_visible_field_requires_review(self):
        result = run_compliance_checks({
            "mrp": self.make_field(
                value=None, confidence=40, status="not_visible"
            )
        })
        check = self.get_check(result, "mrp_visible")
        self.assertEqual(check["status"], "REVIEW_REQUIRED")

    def test_missing_fields_do_not_create_potential_violations(self):
        result = run_compliance_checks({})
        self.assertEqual(result["summary"]["potential_violation"], 0)
        self.assertEqual(
            result["summary"]["review_required"],
            result["summary"]["total"],
        )


if __name__ == "__main__":
    unittest.main()
