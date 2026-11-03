from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Values come from env vars or `.env`. See `/.env.example`."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_path: Path = Path("data/portfolio.db")
    cors_origin: str = "http://localhost:4321"
    # Public base URL of the R2 images bucket. Image and diagram keys are appended to it.
    images_base_url: str = "https://img.fatihiazmi.dev"

    # Contact form, spec section 6. Empty values turn the endpoint off with a 503.
    ip_hash_salt: str = ""
    turnstile_secret: str = ""
    # Lead email. Empty values store the lead and skip the email.
    resend_api_key: str = ""
    lead_notify_email: str = ""
    # Sender on the domain verified in Resend: `fatihiazmi.dev`. A sender on any other
    # domain, including a subdomain, gets 403 from Resend.
    lead_from_email: str = "fatihiazmi.dev <leads@fatihiazmi.dev>"

    @property
    def contact_ready(self) -> bool:
        return bool(self.ip_hash_salt and self.turnstile_secret)

    @property
    def email_ready(self) -> bool:
        return bool(self.resend_api_key and self.lead_notify_email)


@lru_cache
def get_settings() -> Settings:
    return Settings()
