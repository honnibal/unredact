"""Tests for the API endpoints."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from unredact.api import app, lifespan


@pytest.fixture(scope="module")
def client():
    """Test client with lifespan initialized."""
    with TestClient(app) as c:
        yield c


class TestFontsByUrl:
    """Test the POST /fonts/by-url endpoint."""

    def test_rejects_disallowed_domain(self, client):
        resp = client.post("/fonts/by-url", json={"url": "https://evil.com/file.pdf"})
        assert resp.status_code == 400
        assert "not in the allowed list" in resp.json()["detail"]

    def test_rejects_invalid_url(self, client):
        resp = client.post("/fonts/by-url", json={"url": "not-a-url"})
        assert resp.status_code == 400

    def test_rejects_missing_url(self, client):
        resp = client.post("/fonts/by-url", json={})
        assert resp.status_code == 422

    @patch("unredact.api.fetch_pdf")
    def test_returns_font_info(self, mock_fetch, client):
        # Use a real small PDF with text
        import fitz

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Hello", fontname="helv", fontsize=12)
        pdf_bytes = doc.tobytes()
        doc.close()

        mock_fetch.return_value = pdf_bytes

        resp = client.post(
            "/fonts/by-url",
            json={"url": "https://www.justice.gov/epstein/files/test.pdf"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["url"] == "https://www.justice.gov/epstein/files/test.pdf"
        assert len(data["spans"]) >= 1

        span = data["spans"][0]
        assert "text" in span
        assert "font" in span
        assert "page" in span
        assert "bbox" in span
        assert span["font"]["size"] == 12

    @patch("unredact.api.fetch_pdf")
    def test_fetch_error_returns_502(self, mock_fetch, client):
        import httpx

        mock_fetch.side_effect = httpx.RequestError("connection refused")

        resp = client.post(
            "/fonts/by-url",
            json={"url": "https://www.justice.gov/epstein/files/missing.pdf"},
        )
        assert resp.status_code == 502
        assert "Failed to fetch PDF" in resp.json()["detail"]

    def test_allows_justice_gov(self, client):
        """justice.gov and www.justice.gov should both be allowed domains."""
        # We just check validation passes (will fail on fetch, not on domain)
        with patch("unredact.api.fetch_pdf", return_value=b"%PDF-1.0"):
            # Empty PDF will return empty spans, that's fine
            with patch("unredact.api.extract_font_info", return_value=[]):
                resp = client.post(
                    "/fonts/by-url",
                    json={"url": "https://justice.gov/epstein/files/test.pdf"},
                )
                assert resp.status_code == 200


class TestWidths:
    """Test the POST /widths endpoint."""

    def test_calculates_width(self, client):
        resp = client.post("/widths", json={"strings": ["Hello"]})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["text"] == "Hello"
        assert data["results"][0]["width"] > 0

    def test_strips_whitespace(self, client):
        """Strings with leading/trailing whitespace should be stripped."""
        resp = client.post("/widths", json={"strings": ["  Hello  ", "World  ", "  Test"]})
        assert resp.status_code == 200
        data = resp.json()
        texts = [r["text"] for r in data["results"]]
        assert texts == ["Hello", "World", "Test"]

    def test_multiple_strings(self, client):
        resp = client.post("/widths", json={"strings": ["A", "AB", "ABC"]})
        assert resp.status_code == 200
        data = resp.json()
        widths = [r["width"] for r in data["results"]]
        # Widths should increase with string length
        assert widths[0] < widths[1] < widths[2]

    def test_font_parameter(self, client):
        resp = client.post("/widths", json={"strings": ["Test"], "font": "arial"})
        assert resp.status_code == 200
        assert resp.json()["font"] == "arial"

    def test_size_parameter(self, client):
        resp_small = client.post("/widths", json={"strings": ["Test"], "size": 10})
        resp_large = client.post("/widths", json={"strings": ["Test"], "size": 20})
        assert resp_small.status_code == 200
        assert resp_large.status_code == 200
        # Larger size should produce larger width
        assert resp_large.json()["results"][0]["width"] > resp_small.json()["results"][0]["width"]
