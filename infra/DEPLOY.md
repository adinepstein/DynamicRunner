# Deploy FastAPI to Render (Phase 1.5)

## 1. Create the Render web service

1. [Render Dashboard](https://dashboard.render.com/) → **New +** → **Web Service**.
2. Connect the **DynamicRunner** GitHub repo.
3. Settings:
   - **Root Directory:** `backend`
   - **Runtime:** Docker (uses [`backend/Dockerfile`](../backend/Dockerfile))
   - **Health Check Path:** `/healthz`
4. **Environment** (from Supabase dashboard):
   - `SUPABASE_URL`
   - `SUPABASE_JWT_AUDIENCE` = `authenticated`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `LOG_LEVEL` = `INFO`
   - `LOG_JSON` = `true`

Or apply the blueprint: [`render.yaml`](render.yaml) (adjust plan/region as needed).

## 2. GitHub Actions deploy hook (optional)

After the service exists:

1. Render → your service → **Settings** → **Deploy Hook** → copy URL.
2. GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:
   - Name: `RENDER_DEPLOY_HOOK`
   - Value: paste deploy hook URL

Pushes to `main` run [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) and trigger a new deploy (~few minutes).

If the secret is unset, CI still runs; deploy job is skipped.

## 3. Verify

```bash
curl https://YOUR-SERVICE.onrender.com/healthz
# {"status":"ok"}
```

## CI (every PR and push to main)

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml):

- **backend:** ruff, pytest, mypy (app code), Docker build
- **app:** `flutter analyze`, `flutter test`, debug APK with `dart_defines.ci.json`

## Fly.io (alternative)

Use the same `backend/Dockerfile`. Example:

```bash
fly launch --dockerfile backend/Dockerfile --path backend
fly secrets set SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=...
fly deploy
```

No Fly workflow is checked in yet; add `FLY_API_TOKEN` + `fly deploy` when you choose Fly over Render.
