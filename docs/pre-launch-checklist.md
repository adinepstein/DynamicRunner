# Pre-Launch Checklist

## Play Store Requirements

- [ ] App name: "DynamicRunner" (check trademark availability)
- [ ] Package name: `app.dynamicrunner.dynamicrunner`
- [ ] Signed release APK/AAB built with upload key
- [ ] App icon (512x512 hi-res, 1024x500 feature graphic)
- [ ] Short description (80 chars max)
- [ ] Full description (4000 chars max)
- [ ] Screenshots: phone (2+), 7" tablet (optional), 10" tablet (optional)
- [ ] Content rating questionnaire completed
- [ ] Target audience and content: 13+ (fitness/health)
- [ ] App category: Health & Fitness
- [ ] Contact email configured
- [ ] Privacy policy URL set (see below)

## Legal

- [ ] Privacy Policy published (hosted URL)
  - Data collected: email, Garmin activity data, health metrics
  - Third parties: Supabase (data storage), Google Cloud (AI), Garmin (data source)
  - Data retention: until account deletion + 30 day grace
  - User rights: export, delete (GDPR Article 17)
- [ ] Terms of Service published
  - Limitation of liability (not medical advice)
  - Account termination conditions
  - Intellectual property

## Security

- [ ] All secrets in environment variables (never in code)
- [ ] APP_ENCRYPTION_KEY rotated from development value
- [ ] Supabase RLS policies verified for all tables
- [ ] Service role key only accessible by backend
- [ ] HTTPS enforced on all endpoints
- [ ] Rate limiting configured on auth endpoints

## Infrastructure

- [ ] Render/Fly production service deployed
- [ ] Environment variables set on production host
- [ ] Supabase project on paid plan (for production limits)
- [ ] Custom domain configured (optional for MVP)
- [ ] Sentry DSN configured for production
- [ ] GitHub Actions secrets configured (RENDER_DEPLOY_HOOK, CRON_SECRET, API_URL)

## Monitoring

- [ ] Sentry alerts configured for error spikes
- [ ] Sync failure rate monitoring (>10% alert)
- [ ] Gemini cost tracking (alert if >$1/user/month)
- [ ] GDPR cleanup cron verified working

## Staged Rollout Plan

1. **Internal testing** (1-3 users) — verify end-to-end flow
2. **Closed beta** (10-20 runners) — 4 weeks, weekly feedback surveys
3. **Open beta** (100 users) — fix remaining issues
4. **Production** — staged rollout: 1% → 10% → 100%

## Release Build Commands

```bash
# Generate signed AAB
cd app
flutter build appbundle --release \
  --dart-define-from-file=dart_defines.prod.json

# Verify the bundle
bundletool build-apks --bundle=build/app/outputs/bundle/release/app-release.aab \
  --output=build/app.apks --mode=universal
```
