"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Settings for the unredaction service.

    All settings are read from environment variables prefixed with UNREDACT_.
    For example, UNREDACT_STORAGE_BUCKET sets storage_bucket.
    """

    storage_bucket: str = ""
    allowed_domains: list[str] = ["justice.gov", "www.justice.gov"]

    model_config = {"env_prefix": "UNREDACT_"}
