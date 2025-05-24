import sys
import json
import unittest
from unittest.mock import patch
from io import StringIO
import solution

class TestQuoteScraper(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.expected_keys = {'author', 'text', 'tags'}

    def capture_output(self, func):
        captured = StringIO()
        sys.stdout = captured
        func()
        sys.stdout = sys.__stdout__
        return captured.getvalue()

    def test_normal_case(self):
        output = self.capture_output(solution.main)
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            self.fail("Output is not valid JSON")

        self.assertGreaterEqual(len(data), 1, "Should return at least one quote")

        for quote in data:
            self.assertEqual(set(quote.keys()), self.expected_keys, 
                            "Each quote should have required fields")
            self.assertIsInstance(quote['tags'], list, 
                                "Tags should be a list")
            self.assertTrue(quote['text'].startswith('“') and quote['text'].endswith('”'),
                          "Quote text should be properly quoted")

        # Check sorting
        authors = [q['author'] for q in data]
        self.assertEqual(authors, sorted(authors), "Quotes should be sorted by author")

    @patch('solution.requests.get')
    def test_network_failure(self, mock_get):
        mock_get.side_effect = solution.requests.exceptions.RequestException("Mocked network error")

        captured_err = StringIO()
        sys.stderr = captured_err
        with self.assertRaises(SystemExit) as cm:
            solution.fetch_quotes()
        sys.stderr = sys.__stderr__

        self.assertEqual(cm.exception.code, 1, "Should exit with code 1 on network error")
        self.assertIn("Error fetching data", captured_err.getvalue())

    @patch('solution.requests.get')
    def test_html_parsing_failure(self, mock_get):
        mock_response = type('MockResponse', (), {
            'text': '<html><body><div class="quote">Invalid structure</div></body></html>',
            'raise_for_status': lambda self: None
        })
        mock_get.return_value = mock_response()

        captured_err = StringIO()
        sys.stderr = captured_err
        result = solution.fetch_quotes()
        sys.stderr = sys.__stderr__

        self.assertEqual(len(result), 0, "Should return empty list for invalid HTML")
        self.assertIn("Warning: Failed to parse a quote", captured_err.getvalue())

def main():
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestQuoteScraper)
    runner = unittest.TextTestRunner(stream=sys.stdout, verbosity=2)
    result = runner.run(suite)
    sys.exit(not result.wasSuccessful())

if __name__ == "__main__":
    main()