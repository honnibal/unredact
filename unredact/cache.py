"""Cache PDF files from URLs to a GCS bucket."""

from dataclasses import dataclass
from urllib.parse import unquote, urlparse

import httpx
from google.cloud import storage

from .settings import Settings


@dataclass(frozen=True)
class CacheResult:
    """Result of a cache lookup.

    Attributes:
        source_url: The original URL
        storage_url: The GCS URI (gs://bucket/path)
        present: Whether the object exists in the bucket
    """

    source_url: str
    storage_url: str
    present: bool


def _to_archive_url(url: str) -> str:
    """Convert a URL to an archive.org Wayback Machine URL."""
    return f"https://web.archive.org/web/{url}"


def validate_url(url: str, *, allowed_domains: list[str] | None = None) -> None:
    """Raise ValueError if url is not a valid HTTP(S) URL with a host and path.

    Args:
        url: The URL to validate.
        allowed_domains: If provided, the URL's hostname must match one of
            these domains (exact match or subdomain).

    Raises:
        ValueError: If the URL is malformed or the domain is not allowed.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL must use http or https scheme, got {parsed.scheme!r}: {url}")
    if not parsed.hostname:
        raise ValueError(f"URL has no hostname: {url}")
    if not parsed.path or parsed.path == "/":
        raise ValueError(f"URL has no path: {url}")
    if allowed_domains is not None:
        hostname = parsed.hostname.lower()
        if not any(
            hostname == domain or hostname.endswith(f".{domain}")
            for domain in allowed_domains
        ):
            raise ValueError(
                f"Domain {hostname!r} is not in the allowed list: {allowed_domains}"
            )


def url_to_blob_path(url: str) -> str:
    """Convert a URL to a GCS object path.

    Strips the scheme, URL-decodes, and joins host + path.

    >>> url_to_blob_path("https://www.justice.gov/epstein/files/DataSet%209/EFTA00156482.pdf")
    'www.justice.gov/epstein/files/DataSet 9/EFTA00156482.pdf'

    Raises:
        ValueError: If the URL is not a valid HTTP(S) URL with a host and path.
    """
    validate_url(url)
    parsed = urlparse(url)
    path = unquote(parsed.path).lstrip("/")
    return f"{parsed.hostname}/{path}"


def _bucket_name(settings: Settings) -> str:
    """Extract the bare bucket name from settings (strip gs:// prefix)."""
    name = settings.storage_bucket
    if name.startswith("gs://"):
        name = name[len("gs://"):]
    return name.rstrip("/")


def check_cache(url: str, settings: Settings) -> CacheResult:
    """Check whether a URL's content is already cached in GCS.

    This never downloads from the source URL. It only checks whether
    the corresponding GCS object exists.

    Args:
        url: The source URL to look up
        settings: Application settings (must have storage_bucket set)

    Returns:
        CacheResult with the storage URL and whether the file is present.

    Raises:
        ValueError: If the URL is not a valid HTTP(S) URL with a host and path.
        google.auth.exceptions.DefaultCredentialsError: If GCP credentials
            are not configured (missing GOOGLE_APPLICATION_CREDENTIALS or
            Application Default Credentials).
        google.api_core.exceptions.Forbidden: If the service account lacks
            permission to access the bucket.
        google.api_core.exceptions.NotFound: If the bucket does not exist.
    """
    bucket_name = _bucket_name(settings)
    blob_path = url_to_blob_path(url)
    storage_url = f"gs://{bucket_name}/{blob_path}"

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)

    return CacheResult(
        source_url=url,
        storage_url=storage_url,
        present=blob.exists(),
    )


def ensure_in_cache(url: str, settings: Settings) -> CacheResult:
    """Download a URL's content to GCS if not already cached.

    Args:
        url: The source URL to cache
        settings: Application settings (must have storage_bucket set)

    Returns:
        CacheResult with present=True after ensuring the file is cached.

    Raises:
        ValueError: If the URL is not a valid HTTP(S) URL with a host and path.
        google.auth.exceptions.DefaultCredentialsError: If GCP credentials
            are not configured.
        google.api_core.exceptions.Forbidden: If the service account lacks
            permission to read/write the bucket.
        google.api_core.exceptions.NotFound: If the bucket does not exist.
        httpx.RequestError: If the source URL cannot be reached.
        httpx.HTTPStatusError: If the source server returns an error status.
    """
    result = check_cache(url, settings)
    if result.present:
        return result

    bucket_name = _bucket_name(settings)
    blob_path = url_to_blob_path(url)

    # Download from archive.org (justice.gov requires age verification)
    archive_url = _to_archive_url(url)
    with httpx.Client(follow_redirects=True) as http:
        response = http.get(archive_url)
        response.raise_for_status()
        data = response.content

    # Upload to GCS
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.upload_from_string(data, content_type="application/pdf")

    return CacheResult(
        source_url=url,
        storage_url=result.storage_url,
        present=True,
    )


def fetch_pdf(url: str, settings: Settings) -> bytes:
    """Fetch PDF bytes, reading from GCS cache when available.

    If storage_bucket is configured, checks the cache first and reads
    from GCS if present. On a cache miss, downloads from archive.org
    and stores in GCS for next time. If storage_bucket is not configured,
    downloads directly from archive.org (to bypass justice.gov age verification).

    Args:
        url: The source URL of the PDF.
        settings: Application settings.

    Returns:
        The raw PDF bytes.

    Raises:
        ValueError: If the URL is not a valid HTTP(S) URL with a host and path.
        httpx.RequestError: If the source URL cannot be reached.
        httpx.HTTPStatusError: If the source server returns an error status.
        google.auth.exceptions.DefaultCredentialsError: If GCS is configured
            but credentials are missing.
        google.api_core.exceptions.Forbidden: If the service account lacks
            permission to access the bucket.
    """
    validate_url(url)

    if not settings.storage_bucket:
        archive_url = _to_archive_url(url)
        with httpx.Client(follow_redirects=True) as http:
            response = http.get(archive_url)
            response.raise_for_status()
            return response.content

    bucket_name = _bucket_name(settings)
    blob_path = url_to_blob_path(url)

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)

    if blob.exists():
        return blob.download_as_bytes()

    # Cache miss: download from archive.org, store in GCS
    archive_url = _to_archive_url(url)
    with httpx.Client(follow_redirects=True) as http:
        response = http.get(archive_url)
        response.raise_for_status()
        data = response.content

    blob.upload_from_string(data, content_type="application/pdf")
    return data
