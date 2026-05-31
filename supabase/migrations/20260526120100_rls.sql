-- Row Level Security — user_id = auth.uid() for client paths (see docs/access-control.md).

alter table public.profiles enable row level security;
alter table public.garmin_profiles enable row level security;
alter table public.garmin_credentials enable row level security;
alter table public.activities enable row level security;
alter table public.daily_metrics enable row level security;
alter table public.plans enable row level security;
alter table public.workouts enable row level security;
alter table public.week_overrides enable row level security;
alter table public.checkins enable row level security;
alter table public.agent_runs enable row level security;

-- profiles
create policy profiles_select_own on public.profiles
  for select to authenticated
  using (user_id = auth.uid());

create policy profiles_update_own on public.profiles
  for update to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

-- garmin_profiles (read-only for client; writes via FastAPI service role)
create policy garmin_profiles_select_own on public.garmin_profiles
  for select to authenticated
  using (user_id = auth.uid());

-- garmin_credentials: RLS enabled, no authenticated policies → service role only

-- activities, daily_metrics, plans, workouts, agent_runs — read own rows
create policy activities_select_own on public.activities
  for select to authenticated
  using (user_id = auth.uid());

create policy daily_metrics_select_own on public.daily_metrics
  for select to authenticated
  using (user_id = auth.uid());

create policy plans_select_own on public.plans
  for select to authenticated
  using (user_id = auth.uid());

create policy workouts_select_own on public.workouts
  for select to authenticated
  using (user_id = auth.uid());

create policy agent_runs_select_own on public.agent_runs
  for select to authenticated
  using (user_id = auth.uid());

-- checkins — read/insert/update own
create policy checkins_select_own on public.checkins
  for select to authenticated
  using (user_id = auth.uid());

create policy checkins_insert_own on public.checkins
  for insert to authenticated
  with check (user_id = auth.uid());

create policy checkins_update_own on public.checkins
  for update to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

-- week_overrides — read/insert/update/delete own
create policy week_overrides_select_own on public.week_overrides
  for select to authenticated
  using (user_id = auth.uid());

create policy week_overrides_insert_own on public.week_overrides
  for insert to authenticated
  with check (user_id = auth.uid());

create policy week_overrides_update_own on public.week_overrides
  for update to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

create policy week_overrides_delete_own on public.week_overrides
  for delete to authenticated
  using (user_id = auth.uid());

-- Realtime (POC): add tables to supabase_realtime publication (ignore if already added)
do $$
begin
  alter publication supabase_realtime add table public.garmin_profiles;
exception when duplicate_object then null;
end $$;
do $$
begin
  alter publication supabase_realtime add table public.plans;
exception when duplicate_object then null;
end $$;
do $$
begin
  alter publication supabase_realtime add table public.workouts;
exception when duplicate_object then null;
end $$;
do $$
begin
  alter publication supabase_realtime add table public.agent_runs;
exception when duplicate_object then null;
end $$;
