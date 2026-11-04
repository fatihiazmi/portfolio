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

    # Admin gate, spec 9.2. Any empty value turns `/admin*` and `/api/admin*` off with a 503.
    # Team domain, for example `fatihiazmi.cloudflareaccess.com`.
    cf_access_team_domain: str = ""
    # Application Audience (AUD) tag of the Access application.
    cf_access_aud: str = ""
    # The one email allowed in. The Access policy allows the same email.
    admin_email: str = ""

    # R2 images bucket, spec 9.2. Any empty value turns image and diagram uploads off with a 503.
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_images_bucket: str = ""
    # Cloudflare Pages deploy hook. Empty: `POST /api/admin/publish` returns 503.
    pages_deploy_hook_url: str = ""

    @property
    def images_ready(self) -> bool:
        return bool(
            self.r2_account_id
            and self.r2_access_key_id
            and self.r2_secret_access_key
            and self.r2_images_bucket
        )

    @property
    def admin_ready(self) -> bool:
        return bool(self.cf_access_team_domain and self.cf_access_aud and self.admin_email)

    @property
    def contact_ready(self) -> bool:
        return bool(self.ip_hash_salt and self.turnstile_secret)

    @property
    def email_ready(self) -> bool:
        return bool(self.resend_api_key and self.lead_notify_email)


@lru_cache
def get_settings() -> Settings:
    return Settings()
