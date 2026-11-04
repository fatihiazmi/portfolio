"""Serve the admin SPA build at `/admin`. Spec section 9.2, plan T17.

`admin/` builds into `ADMIN_UI_DIR` (default `api/static/admin`). `admin_auth.admin_gate`
checks every request here before it reaches a route.

Rules:

- `/admin` redirects to `/admin/`.
- A path that names a file in the build returns that file.
- Files under `assets/` carry a content hash in the name, so they are cached for a year.
- Any other path returns `index.html`, so the Vue router can handle it. A missing path
  that looks like a file (it has an extension) returns 404 instead.
- No build: 503 with the build command.
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

router = APIRouter(include_in_schema=False)

NO_CACHE = {"Cache-Control": "no-cache"}
IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}


def _root(request: Request) -> Path:
    return Path(request.app.state.settings.admin_ui_dir).resolve()


@router.get("/admin")
def admin_root() -> RedirectResponse:
    return RedirectResponse("/admin/", status_code=307)


@router.get("/admin/{path:path}")
def admin_file(path: str, request: Request) -> Response:
    root = _root(request)
    index = root / "index.html"
    if not index.is_file():
        return JSONResponse(
            {"detail": "Admin UI is not built. Run `pnpm build` in admin/."}, status_code=503
        )
    if path:
        target = (root / path).resolve()
        if target.is_relative_to(root) and target.is_file():
            headers = IMMUTABLE if path.startswith("assets/") else NO_CACHE
            return FileResponse(target, headers=headers)
        if "." in path.rsplit("/", 1)[-1]:
            return JSONResponse({"detail": f"{path} not found"}, status_code=404)
    return FileResponse(index, headers=NO_CACHE)
