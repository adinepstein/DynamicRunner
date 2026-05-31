# Supabase migrations

SQL migrations for the DynamicRunner POC Postgres schema (Phase 1.6).

## Apply to your dev project

### Option A — SQL Editor (no CLI)

1. Open [Supabase Dashboard](https://supabase.com/dashboard) → your project → **SQL Editor**.
2. Run **`migrations/20260526120000_initial_schema.sql`** (entire file).
3. Run **`migrations/20260526120100_rls.sql`** (entire file).

### Option B — Supabase CLI

```bash
brew install supabase/tap/supabase
cd /path/to/DynamicRunner
supabase login
supabase link --project-ref YOUR_PROJECT_REF
supabase db push
```

## RLS smoke test

After migrations, with two test users A and B:

1. Sign in as user A in the app (or via Auth API) and note `access_token`.
2. In SQL Editor, as service role, insert a row for user B:

```sql
insert into public.profiles (user_id, email)
select id, email from auth.users where email = 'other-user@example.com'
on conflict do nothing;
```

3. From a REST client, `GET` your project's PostgREST URL for `profiles` with user A's JWT — you should only see A's row, never B's.

Or run this policy check in SQL Editor (uses `auth.uid()` only when called with a user JWT via RPC — manual check is easier via Flutter in Phase 1.7).

## Table access summary

| Table | Client (anon + user JWT) | FastAPI (service role) |
|-------|--------------------------|-------------------------|
| `profiles` | select, update own | full |
| `garmin_profiles` | select own | full |
| `garmin_credentials` | **no access** | full |
| `activities`, `daily_metrics`, `plans`, `workouts`, `agent_runs` | select own | full (sync/agents) |
| `checkins`, `week_overrides` | select/insert/update own | full |

See [docs/access-control.md](../docs/access-control.md).

## Auth trigger

`handle_new_user` creates a `profiles` row when a user signs up (email or Google). Default timezone `UTC`; override in onboarding (Phase 1.7).
