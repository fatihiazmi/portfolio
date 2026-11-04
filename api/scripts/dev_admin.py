"""Local admin dev server. Plan T17.

Starts the API on 127.0.0.1:8000 with a throwaway Access key pair. Writes a JWT signed by
that key to `admin/.env.development.local`. `pnpm dev` in `admin/` sends the JWT on every
`/api` request, so the real admin gate runs and passes.

Rules:

- Dev only. The image never holds this file: the Dockerfile copies `src/` only.
- The key pair lives in memory. A restart makes a new one and a new JWT.
- Access certs requests go to the in-memory key. R2 and the deploy hook go out for real,
  with the keys from `api/.env`.

Run from `api/`: uv run python scripts/dev_admin.py
Port 8000 taken: add `--port 8001`, and set `ADMIN_DEV_API=http://127.0.0.1:8001` in
`admin/.env.development.local` after the script writes it.
"""

import argparse
import json
import time

import httpx
import jwt
import uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa

from portfolio_api.config import API_ROOT, Settings
from portfolio_api.main import create_app

TEAM = "dev.cloudflareaccess.invalid"
AUD = "dev-aud"
EMAIL = "dev@localhost"
KID = "dev-key"
TOKEN_HOURS = 12
ENV_FILE = API_ROOT.parent / "admin" / ".env.development.local"


class DevCerts(httpx.BaseTransport):
    """Answers the Access certs URL from memory. Every other request goes out."""

    def __init__(self, key: rsa.RSAPrivateKey) -> None:
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        self._body = {"keys": [{**jwk, "kid": KID, "alg": "RS256", "use": "sig"}]}
        self._real = httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == TEAM:
            return httpx.Response(200, json=self._body)
        return self._real.handle_request(request)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8000)
    port = parser.parse_args().port
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    claims = {
        "aud": [AUD],
        "iss": f"https://{TEAM}",
        "email": EMAIL,
        "iat": now,
        "exp": now + TOKEN_HOURS * 3600,
    }
    token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": KID})
    ENV_FILE.write_text(f"ADMIN_DEV_JWT={token}\n")
    ENV_FILE.chmod(0o600)
    print(f"JWT for {EMAIL} written to {ENV_FILE}. Valid {TOKEN_HOURS} h.")
    print("Next: cd admin && pnpm dev, then open http://localhost:5173/admin/")

    settings = Settings(cf_access_team_domain=TEAM, cf_access_aud=AUD, admin_email=EMAIL)
    http = httpx.Client(transport=DevCerts(key), timeout=httpx.Timeout(10.0))
    app = create_app(settings, http=http)
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
