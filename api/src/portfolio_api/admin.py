"""Admin JSON API. Spec section 9.2.

`admin_auth.admin_gate` checks every request under `/api/admin` before it reaches a route here.
Plan T16 adds the project, image, lead, and publish endpoints.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/admin", tags=["admin"])


class Me(BaseModel):
    email: str


@router.get("/me")
def me(request: Request) -> Me:
    """The logged-in admin. The SPA shows it in the header."""
    return Me(email=request.state.admin_email)
