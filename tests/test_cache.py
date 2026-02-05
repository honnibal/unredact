"""Tests for PDF cache with GCS storage."""

from unittest.mock import MagicMock, patch

import pytest

from unredact.cache import CacheResult, check_cache, ensure_in_cache, url_to_blob_path, validate_url
from unredact.settings import Settings


class TestUrlToBlobPath:
    """Test URL to GCS object path conversion."""

    def test_basic_url(self):
        url = "https://www.justice.gov/epstein/files/EFTA00156482.pdf"
        assert url_to_blob_path(url) == "www.justice.gov/epstein/files/EFTA00156482.pdf"

    def test_url_decoding(self):
        url = "https://www.justice.gov/epstein/files/DataSet%209/EFTA00156482.pdf"
        assert url_to_blob_path(url) == "www.justice.gov/epstein/files/DataSet 9/EFTA00156482.pdf"

    def test_strips_scheme(self):
        url = "http://example.com/file.pdf"
        assert url_to_blob_path(url) == "example.com/file.pdf"

    def test_preserves_nested_path(self):
        url = "https://example.com/a/b/c/d.pdf"
        assert url_to_blob_path(url) == "example.com/a/b/c/d.pdf"

    def test_no_double_slash(self):
        url = "https://example.com//file.pdf"
        assert url_to_blob_path(url) == "example.com/file.pdf"

    def test_rejects_no_scheme(self):
        with pytest.raises(ValueError, match="http or https"):
            url_to_blob_path("www.justice.gov/file.pdf")

    def test_rejects_ftp(self):
        with pytest.raises(ValueError, match="http or https"):
            url_to_blob_path("ftp://example.com/file.pdf")

    def test_rejects_no_host(self):
        with pytest.raises(ValueError, match="no hostname"):
            url_to_blob_path("https:///file.pdf")

    def test_rejects_no_path(self):
        with pytest.raises(ValueError, match="no path"):
            url_to_blob_path("https://example.com")

    def test_rejects_bare_slash(self):
        with pytest.raises(ValueError, match="no path"):
            url_to_blob_path("https://example.com/")


class TestValidateUrlDomains:
    """Test domain whitelisting in validate_url."""

    def test_no_whitelist_allows_any_domain(self):
        validate_url("https://example.com/file.pdf")  # no error

    def test_allows_exact_domain(self):
        validate_url(
            "https://justice.gov/file.pdf",
            allowed_domains=["justice.gov"],
        )

    def test_allows_subdomain(self):
        validate_url(
            "https://www.justice.gov/file.pdf",
            allowed_domains=["justice.gov"],
        )

    def test_rejects_unlisted_domain(self):
        with pytest.raises(ValueError, match="not in the allowed list"):
            validate_url(
                "https://evil.com/file.pdf",
                allowed_domains=["justice.gov"],
            )

    def test_rejects_partial_match(self):
        """notjustice.gov should not match justice.gov."""
        with pytest.raises(ValueError, match="not in the allowed list"):
            validate_url(
                "https://notjustice.gov/file.pdf",
                allowed_domains=["justice.gov"],
            )


class TestCheckCache:
    """Test check_cache with mocked GCS."""

    def _settings(self, bucket: str = "test-bucket") -> Settings:
        return Settings(storage_bucket=bucket)

    @patch("unredact.cache.storage.Client")
    def test_returns_cache_result(self, mock_client_cls):
        mock_blob = MagicMock()
        mock_blob.exists.return_value = False
        mock_client_cls.return_value.bucket.return_value.blob.return_value = mock_blob

        result = check_cache("https://example.com/file.pdf", self._settings())
        assert isinstance(result, CacheResult)
        assert result.source_url == "https://example.com/file.pdf"
        assert result.storage_url == "gs://test-bucket/example.com/file.pdf"
        assert result.present is False

    @patch("unredact.cache.storage.Client")
    def test_present_when_exists(self, mock_client_cls):
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_client_cls.return_value.bucket.return_value.blob.return_value = mock_blob

        result = check_cache("https://example.com/file.pdf", self._settings())
        assert result.present is True

    @patch("unredact.cache.storage.Client")
    def test_strips_gs_prefix(self, mock_client_cls):
        mock_blob = MagicMock()
        mock_blob.exists.return_value = False
        mock_client_cls.return_value.bucket.return_value.blob.return_value = mock_blob

        result = check_cache("https://example.com/file.pdf", self._settings("gs://my-bucket"))
        assert result.storage_url == "gs://my-bucket/example.com/file.pdf"
        mock_client_cls.return_value.bucket.assert_called_with("my-bucket")

    @patch("unredact.cache.storage.Client")
    def test_does_not_download(self, mock_client_cls):
        """check_cache must never fetch from the source URL."""
        mock_blob = MagicMock()
        mock_blob.exists.return_value = False
        mock_client_cls.return_value.bucket.return_value.blob.return_value = mock_blob

        with patch("unredact.cache.httpx.Client") as mock_httpx:
            check_cache("https://example.com/file.pdf", self._settings())
            mock_httpx.assert_not_called()


class TestEnsureInCache:
    """Test ensure_in_cache with mocked GCS and HTTP."""

    def _settings(self) -> Settings:
        return Settings(storage_bucket="test-bucket")

    @patch("unredact.cache.storage.Client")
    def test_skips_download_when_present(self, mock_client_cls):
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_client_cls.return_value.bucket.return_value.blob.return_value = mock_blob

        with patch("unredact.cache.httpx.Client") as mock_httpx:
            result = ensure_in_cache("https://example.com/file.pdf", self._settings())
            mock_httpx.assert_not_called()

        assert result.present is True

    @patch("unredact.cache.storage.Client")
    @patch("unredact.cache.httpx.Client")
    def test_downloads_when_absent(self, mock_httpx_cls, mock_client_cls):
        mock_blob = MagicMock()
        mock_blob.exists.return_value = False
        mock_client_cls.return_value.bucket.return_value.blob.return_value = mock_blob

        mock_response = MagicMock()
        mock_response.content = b"%PDF-fake-content"
        mock_httpx = MagicMock()
        mock_httpx.get.return_value = mock_response
        mock_httpx_cls.return_value.__enter__ = lambda s: mock_httpx
        mock_httpx_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = ensure_in_cache("https://example.com/file.pdf", self._settings())

        mock_httpx.get.assert_called_once_with("https://example.com/file.pdf")
        mock_blob.upload_from_string.assert_called_once_with(
            b"%PDF-fake-content", content_type="application/pdf"
        )
        assert result.present is True

    @patch("unredact.cache.storage.Client")
    @patch("unredact.cache.httpx.Client")
    def test_returns_correct_storage_url(self, mock_httpx_cls, mock_client_cls):
        mock_blob = MagicMock()
        mock_blob.exists.return_value = False
        mock_client_cls.return_value.bucket.return_value.blob.return_value = mock_blob

        mock_response = MagicMock()
        mock_response.content = b"data"
        mock_httpx = MagicMock()
        mock_httpx.get.return_value = mock_response
        mock_httpx_cls.return_value.__enter__ = lambda s: mock_httpx
        mock_httpx_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = ensure_in_cache(
            "https://www.justice.gov/epstein/files/DataSet%209/EFTA00156482.pdf",
            self._settings(),
        )
        assert result.storage_url == (
            "gs://test-bucket/www.justice.gov/epstein/files/DataSet 9/EFTA00156482.pdf"
        )


class TestSettings:
    """Test settings loading."""

    def test_default_empty(self):
        s = Settings(storage_bucket="")
        assert s.storage_bucket == ""

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("UNREDACT_STORAGE_BUCKET", "gs://my-bucket")
        s = Settings()
        assert s.storage_bucket == "gs://my-bucket"
