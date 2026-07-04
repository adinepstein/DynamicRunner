-- Phase 3: Add onboarding_completed flag to profiles
alter table public.profiles
  add column if not exists onboarding_completed boolean not null default false;
