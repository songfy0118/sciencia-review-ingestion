from pathlib import Path
import unittest

from review_ingestion.amazon import (
    classify_page,
    extract_asin,
    parse_reviews,
    product_url,
    review_url,
)


FIXTURE = Path(__file__).parent / "fixtures" / "reviews.html"


class AmazonCollectorTests(unittest.TestCase):
    def test_extract_asin_from_id_and_urls(self) -> None:
        self.assertEqual(extract_asin("B09XS7JWHH"), "B09XS7JWHH")
        self.assertEqual(extract_asin(product_url("B09XS7JWHH")), "B09XS7JWHH")
        self.assertEqual(extract_asin(review_url("B09XS7JWHH")), "B09XS7JWHH")

    def test_classifies_sign_in_and_review_pages(self) -> None:
        self.assertEqual(classify_page("<title>Sign in</title>", "Sign in"), "sign_in")
        product_html = '<title>Example product</title><a href="/ap/signin">Account</a>'
        self.assertEqual(
            classify_page(product_html, "Example product"), "accessible_no_reviews"
        )
        html = FIXTURE.read_text(encoding="utf-8")
        self.assertEqual(classify_page(html, "Sample reviews"), "reviews_present")

    def test_parses_review_fields(self) -> None:
        html = FIXTURE.read_text(encoding="utf-8")
        reviews = parse_reviews(
            html,
            asin="B09XS7JWHH",
            source_url=review_url("B09XS7JWHH"),
            collected_at="2026-09-21T00:00:00+00:00",
        )
        self.assertEqual(len(reviews), 2)
        self.assertEqual(reviews[0].review_id, "RTEST00001")
        self.assertEqual(reviews[0].rating, 4.0)
        self.assertTrue(reviews[0].verified_purchase)
        self.assertIn("comfortable", reviews[0].body.lower())
        self.assertEqual(reviews[0].variation, "Color: Black")
        self.assertFalse(reviews[1].verified_purchase)


if __name__ == "__main__":
    unittest.main()
