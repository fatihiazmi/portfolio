# admin

Admin SPA for `fatihiazmi.dev`: Vue 3, Vite, PrimeVue 4. Spec section 9.2, plan T17.

FastAPI serves the build at `api.fatihiazmi.dev/admin`. Cloudflare Access guards it, and the API checks the Access JWT again on every request.

## Screens

| Screen | Path | What it does |
|---|---|---|
| Dashboard | `/admin/` | New leads, published projects, blocking images, last publish, newest leads. |
| Projects | `/admin/projects` | List with drag reorder. **Save order** applies the new order. |
| Project edit | `/admin/projects/:id`, `/admin/projects/new` | All fields. Markdown sections with a Write / Preview toggle. One **Save** sends the whole form. |
| Map editor | `/admin/map`, `/admin/map?project=:id` | Top-down SVG of the 3D map. Drag a node to set `map_x` and `map_z`. Click two nodes to add or remove a road. **Save map** sends every change. |
| Images | `/admin/images?project=:id` | Upload, alt, caption, scrubbed, drag reorder. **Save changes** sends every edit. |
| Leads | `/admin/leads` | Filter by kind and status. A status change saves at once. |
| Publish | Header button, every screen | Starts a Pages build. A 409 lists the unscrubbed images. |

Rules:

- Uploads, image removals, diagram uploads, and lead status changes apply at once. Everything else waits for its Save button.
- Leaving a screen with unsaved edits asks first.
- The markdown preview uses the same rules as `web/src/lib/markdown.ts`. Change both files together.
- The map editor owns `map_x` and `map_z`. The project form shows them and links to the editor. Node ring sizes copy `SIZE` in `web/src/lib/map/scene.ts`. Change both files together.
- The map editor warns when two node rings overlap. The live map would draw them on top of each other.
- An expired Access session shows "Your admin login expired". Reload the page to log in again.

## Dev

Needs Node 24 and pnpm 11 (`packageManager` in `package.json`).

```bash
# Terminal 1, from api/: local API with a throwaway Access key
uv run python scripts/dev_admin.py            # add --port 8001 if 8000 is taken

# Terminal 2, from admin/
pnpm install
pnpm dev                                      # http://localhost:5173/admin/
```

`dev_admin.py` writes a 12-hour JWT to `admin/.env.development.local`. The Vite proxy adds it to every `/api` request. If the API runs on another port, add `ADMIN_DEV_API=http://127.0.0.1:8001` to that file.

R2 uploads and publish use the keys in `api/.env`. Without them, uploads and publish return 503. Point `DATABASE_PATH` at a scratch file to keep test edits out of `api/data/portfolio.db`.

## Build

```bash
pnpm build      # vue-tsc, then vite build into ../api/static/admin
pnpm typecheck  # vue-tsc only
```

The API image builds the SPA in its own stage from this directory. Compose passes it as the `admin-src` build context. `.dockerignore` keeps `node_modules` and `.env*` out of that context.

## Dependencies

- PrimeVue stays on 4.x. PrimeVue 5 ships under its own LICENSE.md, not MIT.
- `pnpm-workspace.yaml` blocks any version published in the last 7 days.
