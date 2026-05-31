-- DynamicRunner initial schema (POC) — PRD §8, shared/schemas payloads in jsonb.
-- Apply via Supabase SQL Editor or `supabase db push` (see supabase/README.md).

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- profiles (client-readable; created on auth signup via trigger)
-- ---------------------------------------------------------------------------
create table public.profiles (
  user_id uuid primary key references auth.users (id) on delete cascade,
  email text,
  display_name text,
  timezone text not null default 'UTC',
  units text not null default 'metric' check (units in ('metric', 'imperial')),
  preferences jsonb not null default '{}'::jsonb,
  athlete_profile jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.profiles is 'Per-user settings; athlete_profile jsonb aligns with athlete-profile.schema.json when populated.';

-- ---------------------------------------------------------------------------
-- garmin_profiles — sync status visible to client; tokens live elsewhere
-- ---------------------------------------------------------------------------
create table public.garmin_profiles (
  user_id uuid primary key references public.profiles (user_id) on delete cascade,
  garmin_user_id text,
  sync_status text not null default 'disconnected'
    check (sync_status in ('disconnected', 'syncing', 'ok', 'error', 'reauth_required')),
  reauth_required boolean not null default false,
  mfa_enabled boolean not null default false,
  last_sync_at timestamptz,
  backfill_progress jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.garmin_profiles is 'Garmin connection state for UI/Realtime; no secrets.';

-- ---------------------------------------------------------------------------
-- garmin_credentials — server-only (RLS on, no policies for authenticated)
-- ---------------------------------------------------------------------------
create table public.garmin_credentials (
  user_id uuid primary key references public.profiles (user_id) on delete cascade,
  token_ciphertext bytea not null,
  updated_at timestamptz not null default now()
);

comment on table public.garmin_credentials is 'Encrypted OAuth token blob; FastAPI service role only.';

-- ---------------------------------------------------------------------------
-- activities, daily_metrics
-- ---------------------------------------------------------------------------
create table public.activities (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (user_id) on delete cascade,
  garmin_activity_id text not null,
  activity_date date not null,
  payload jsonb not null,
  synced_at timestamptz not null default now(),
  unique (user_id, garmin_activity_id)
);

create index activities_user_date_idx on public.activities (user_id, activity_date desc);

create table public.daily_metrics (
  user_id uuid not null references public.profiles (user_id) on delete cascade,
  metric_date date not null,
  payload jsonb not null,
  synced_at timestamptz not null default now(),
  primary key (user_id, metric_date)
);

-- ---------------------------------------------------------------------------
-- plans, workouts, week_overrides, checkins, agent_runs
-- ---------------------------------------------------------------------------
create table public.plans (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (user_id) on delete cascade,
  status text not null default 'draft'
    check (status in ('draft', 'active', 'completed', 'abandoned')),
  payload jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index plans_one_active_per_user_idx
  on public.plans (user_id)
  where status = 'active';

create index plans_user_created_idx on public.plans (user_id, created_at desc);

create table public.workouts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (user_id) on delete cascade,
  plan_id uuid not null references public.plans (id) on delete cascade,
  scheduled_date date not null,
  payload jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index workouts_user_scheduled_idx on public.workouts (user_id, scheduled_date);
create index workouts_plan_scheduled_idx on public.workouts (plan_id, scheduled_date);

create table public.week_overrides (
  user_id uuid not null references public.profiles (user_id) on delete cascade,
  plan_id uuid not null references public.plans (id) on delete cascade,
  iso_week text not null,
  payload jsonb not null,
  updated_at timestamptz not null default now(),
  primary key (user_id, plan_id, iso_week)
);

create table public.checkins (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (user_id) on delete cascade,
  workout_id uuid not null references public.workouts (id) on delete cascade,
  payload jsonb not null,
  created_at timestamptz not null default now(),
  unique (user_id, workout_id)
);

create table public.agent_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (user_id) on delete cascade,
  payload jsonb not null,
  created_at timestamptz not null default now()
);

create index agent_runs_user_created_idx on public.agent_runs (user_id, created_at desc);

-- ---------------------------------------------------------------------------
-- updated_at helper
-- ---------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger profiles_set_updated_at
  before update on public.profiles
  for each row execute function public.set_updated_at();

create trigger garmin_profiles_set_updated_at
  before update on public.garmin_profiles
  for each row execute function public.set_updated_at();

create trigger plans_set_updated_at
  before update on public.plans
  for each row execute function public.set_updated_at();

create trigger workouts_set_updated_at
  before update on public.workouts
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- New auth user → profile row (Phase 1.7)
-- ---------------------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (user_id, email, timezone, units)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data ->> 'timezone', 'UTC'),
    'metric'
  );
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
