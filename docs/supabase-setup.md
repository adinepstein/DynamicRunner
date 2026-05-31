# Supabase setup (Phase 1.4)

Step-by-step for the **DynamicRunner POC** dev project. Database tables and RLS policies come in **Phase 1.6**; this doc gets Auth + API keys wired so Flutter and FastAPI can share the same Supabase project.

## What you need at the end

| Secret | Where it goes | Safe in Flutter app? |
|--------|---------------|----------------------|
| **Project URL** | Flutter + backend | Yes |
| **anon (public) key** | Flutter + backend (JWKS only needs URL) | Yes — RLS protects data |
| **service_role key** | Backend only (Phase 2+ cron, Garmin, agents) | **Never** |
| JWT audience | Backend (`authenticated`) | N/A |

---

## 1. Create the Supabase project

1. Sign in at [supabase.com/dashboard](https://supabase.com/dashboard).
2. **New project**
   - **Name:** `dynamicrunner-dev` (or similar)
   - **Database password:** generate and save in your password manager
   - **Region:** pick closest to you (e.g. **Europe (Frankfurt)** for Israel/EU)
3. Wait until the project status is **Active** (~2 minutes).

---

## 2. Copy API credentials

### Where to find them (Supabase dashboard)

1. Open your project in [supabase.com/dashboard](https://supabase.com/dashboard).
2. In the **left sidebar**, scroll to the bottom and click the **gear icon** → **Project Settings**.
3. In the settings submenu, click **API** (not “Database” or “Auth”).

On the **API** page you will see a **Project URL** section and a **Project API keys** section with two long JWT strings.

| What you see on screen | Label in dashboard | Looks like |
|------------------------|-------------------|------------|
| Base URL for your project | **Project URL** | `https://abcdefghijklmnop.supabase.co` |
| Public client key | **anon** `public` | Long string starting with `eyJ...` — there is a **Copy** button |
| Server-only key | **service_role** `secret` | Another long `eyJ...` string — **Reveal** then **Copy** |

Tips:

- The middle part of the URL (`abcdefghijklmnop`) is your **project ref** — you will see it in several places.
- Use **anon public** for the mobile app. It is designed to be embedded in clients; Postgres **RLS** (Phase 1.6) limits what it can read/write.
- **service_role** bypasses RLS — treat it like a root password. **Never** put it in Flutter, commit it to git, or paste it in chat.

You do **not** need the **JWT Secret** on this page for our FastAPI setup; the backend validates tokens via **JWKS** using only `SUPABASE_URL`.

### Where to paste them (this repo)

You need **two local files** (both gitignored — never commit real values):

#### A. Backend — `backend/.env`

Create from the template if you have not already:

```bash
cd /Users/adin/Documents/DynamicRunner/backend
cp .env.example .env
```

Open **`backend/.env`** in your editor and fill in:

```env
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co          ← paste Project URL
SUPABASE_JWT_AUDIENCE=authenticated                        ← leave as-is
SUPABASE_SERVICE_ROLE_KEY=eyJ...                           ← paste service_role key
LOG_LEVEL=INFO
LOG_JSON=false
```

| Dashboard value | Paste into `backend/.env` as |
|-----------------|------------------------------|
| **Project URL** | `SUPABASE_URL=...` |
| **service_role** key | `SUPABASE_SERVICE_ROLE_KEY=...` |

The anon key is **not** required in `backend/.env` today (JWT verification uses JWKS + URL only). The service role will be used in later phases for server-side DB work.

Restart uvicorn after saving:

```bash
# Ctrl+C the running server, then:
uvicorn dynamicrunner.api.app:create_app --factory --reload --port 8000
```

#### B. Flutter app — `app/dart_defines.json`

Create from the template:

```bash
cd /Users/adin/Documents/DynamicRunner/app
cp dart_defines.json.example dart_defines.json
```

Open **`app/dart_defines.json`** and fill in:

```json
{
  "SUPABASE_URL": "https://YOUR_PROJECT_REF.supabase.co",
  "SUPABASE_ANON_KEY": "eyJ...",
  "SENTRY_DSN": ""
}
```

| Dashboard value | Paste into `app/dart_defines.json` as |
|-----------------|---------------------------------------|
| **Project URL** | `"SUPABASE_URL": "..."` |
| **anon public** key | `"SUPABASE_ANON_KEY": "..."` |
| (optional) Sentry | `"SENTRY_DSN": "..."` or leave `""` |

Run the app with that file (hot reload does **not** pick up new defines — restart `flutter run`):

```bash
flutter run --dart-define-from-file=dart_defines.json
```

**Do not** put `SUPABASE_SERVICE_ROLE_KEY` in `dart_defines.json` or anywhere under `app/`.

### Quick checklist

- [ ] **Project URL** → `backend/.env` (`SUPABASE_URL`) **and** `app/dart_defines.json` (`SUPABASE_URL`)
- [ ] **anon public** → `app/dart_defines.json` only (`SUPABASE_ANON_KEY`)
- [ ] **service_role** → `backend/.env` only (`SUPABASE_SERVICE_ROLE_KEY`)
- [ ] Neither `.env` nor `dart_defines.json` is staged in git

---

## 3. Configure Auth providers

### Email / password (do this now)

1. **Authentication** → **Providers** → **Email**
2. For local dev, turn **off** “Confirm email” (you can re-enable before beta).
3. Leave **Enable Email provider** on.

### Google (optional until Phase 1.7)

Defer full Google sign-in until **1.7** unless you want it early:

1. [Google Cloud Console](https://console.cloud.google.com/) → create/select a project → **APIs & Services** → **OAuth consent screen** (External, test users).
2. **Credentials** → `/` **Create OAuth client ID** → **Web application**
   - Authorized redirect URI: `https://<YOUR_PROJECT_REF>.supabase.co/auth/v1/callback`  
     (copy exact URL from Supabase **Authentication** → **Providers** → **Google**)
3. Paste **Client ID** and **Client secret** into Supabase Google provider and enable it.
4. For **Android native** Google sign-in later, add an Android OAuth client with your debug **SHA-1** (`keytool -list -v -keystore ~/.android/debug.keystore -alias androiddebugkey -storepass android -keypass android`).

---

## 4. Wire the backend

```bash
cd backend
cp .env.example .env
```

Edit `backend/.env`:

```env
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_JWT_AUDIENCE=authenticated
SUPABASE_SERVICE_ROLE_KEY=eyJ...   # backend only — never commit
LOG_LEVEL=INFO
LOG_JSON=false
```

Restart the API if it is already running:

```bash
source .venv/bin/activate
uvicorn dynamicrunner.api.app:create_app --factory --reload --port 8000
```

Check:

```bash
curl -s http://localhost:8000/healthz
# {"status":"ok"}
```

---

## 5. Wire the Flutter app

Create a local defines file (gitignored):

```bash
cd app
cp dart_defines.json.example dart_defines.json
```

Edit `app/dart_defines.json` with your URL and anon key, then run:

```bash
flutter run --dart-define-from-file=dart_defines.json
```

Or pass defines inline:

```bash
flutter run \
  --dart-define=SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co \
  --dart-define=SUPABASE_ANON_KEY=eyJ...
```

The app already calls `Supabase.initialize()` in `lib/main.dart` on startup.

---

## 6. Verify Auth + FastAPI JWT (smoke test)

### A. Create a test user (curl)

Replace `YOUR_PROJECT_REF` and `YOUR_ANON_KEY`:

```bash
curl -s -X POST 'https://YOUR_PROJECT_REF.supabase.co/auth/v1/signup' \
  -H "apikey: YOUR_ANON_KEY" \
  -H "Content-Type: application/json" \
  -d '{"email":"dev-test@example.com","password":"DevTestPassword123!"}' \
  | python3 -m json.tool
```

From the JSON response, copy **`access_token`** (or sign in via **Authentication** → **Users** → add user in the dashboard).

If email confirmation is enabled, use the dashboard to confirm the user or disable confirmation (step 3).

### B. Sign in (if signup did not return a session)

```bash
curl -s -X POST 'https://YOUR_PROJECT_REF.supabase.co/auth/v1/token?grant_type=password' \
  -H "apikey: YOUR_ANON_KEY" \
  -H "Content-Type: application/json" \
  -d '{"email":"dev-test@example.com","password":"DevTestPassword123!"}' \
  | python3 -m json.tool
```

Use the **`access_token`** from the response.

### C. Call protected FastAPI route

```bash
export TOKEN="paste_access_token_here"
curl -s http://localhost:8000/me -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Expected:

```json
{ "uid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" }
```

That `uid` is the JWT **`sub`** claim — same ID you will use as `user_id` in Postgres (Phase 1.6–1.7).

### D. Confirm rejection without token

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/me
# 401
```

---

## 7. Realtime (optional for now)

**Database** → **Publications**: default `supabase_realtime` exists. You will add tables to the publication in **Phase 1.6** when `garmin_profiles`, `workouts`, etc. exist. No action required for 1.4.

---

## 8. Security checklist

- [ ] `backend/.env` and `app/dart_defines.json` are **not** committed (root `.gitignore` covers `.env`; add `dart_defines.json` locally).
- [ ] **service_role** key is only in `backend/.env` (and future host secrets on Render/Fly).
- [ ] Anon key in the mobile app is expected — data access is gated by **RLS** (Phase 1.6).
- [ ] Use a **separate** Supabase project for production later; keep `dynamicrunner-dev` for POC.

---

## 9. Phase 1.4 acceptance checklist

- [ ] Supabase project created; email auth enabled
- [ ] `SUPABASE_URL` + anon key in Flutter (`dart_defines.json` or `--dart-define`)
- [ ] `SUPABASE_URL` + service role in `backend/.env`
- [ ] `GET /healthz` → 200
- [ ] `GET /me` with user access token → 200 + correct `uid`
- [ ] Firebase / FCM — separate step in [app/README.md](../app/README.md) (minimal Firebase project, `google-services.json`)

When the checklist is done, mark **TODO 1.4** complete and apply **Phase 1.6** migrations ([`supabase/README.md`](../supabase/README.md)), then test sign-in in the Flutter app (Phase 1.7).

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `/me` → 503 “SUPABASE_URL is not configured” | Set `SUPABASE_URL` in `backend/.env` and restart uvicorn |
| `/me` → 401 “Invalid or expired token” | Token expired (default 1h); sign in again. Check `iss`/`aud` — must be Supabase user JWT with `aud: authenticated` |
| Signup returns user but no `access_token` | Email confirmation required — disable in Auth settings or confirm via email |
| Flutter still shows placeholder URL | Rebuild with `--dart-define-from-file`; hot reload does not apply new defines |
| pip install fails (401 CodeArtifact) | `PIP_INDEX_URL=https://pypi.org/simple pip install -e ".[dev]"` |
