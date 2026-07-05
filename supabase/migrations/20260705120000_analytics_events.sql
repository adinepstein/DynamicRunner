-- Analytics events table for product metrics
CREATE TABLE IF NOT EXISTS public.analytics_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    event text NOT NULL,
    properties jsonb DEFAULT '{}',
    event_date date NOT NULL DEFAULT CURRENT_DATE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_analytics_events_user_date
    ON public.analytics_events(user_id, event_date);
CREATE INDEX IF NOT EXISTS idx_analytics_events_event
    ON public.analytics_events(event, event_date);

ALTER TABLE public.analytics_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY analytics_events_user_policy ON public.analytics_events
    FOR ALL USING (auth.uid() = user_id);

-- Service role can insert for any user (backend tracking)
CREATE POLICY analytics_events_service_insert ON public.analytics_events
    FOR INSERT WITH CHECK (true);
