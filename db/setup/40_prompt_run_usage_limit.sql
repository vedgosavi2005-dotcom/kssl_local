-- prompt_run status 'usage_limit' (owner 2026-10-24: "processing must produce no errors"). A run stopped because the model account
-- hit its usage limit is not a failure of the pipeline: the runners stop cleanly and log nothing for it (prompts/run.py exit 3,
-- scripts/flood_run.py). Before those guards (17 Oct 02:55-03:12) 994 such runs were logged as 'failed', $0 each; they are relabelled
-- here, keeping the record. prompts/run.pending() counts only loaded / skipped / rejected / failed, so these subjects stay pending.
-- Staging DB only (prompt_run is never synced). Safe to re-run.
ALTER TABLE staging.prompt_run DROP CONSTRAINT IF EXISTS prompt_run_status_check;
ALTER TABLE staging.prompt_run ADD CONSTRAINT prompt_run_status_check
    CHECK (status IN ('loaded', 'skipped', 'rejected', 'failed', 'dry_run', 'usage_limit'));
UPDATE staging.prompt_run SET status = 'usage_limit'
WHERE status = 'failed' AND coalesce(error, '') ~* '(hit your .*limit|usage limit|credit balance)' AND coalesce(cost_usd, 0) = 0;

-- A source page that cannot be read (paywall, block, removed, empty) is skipped before the model call from 24 Oct (prompts/run.py);
-- the earlier rows that logged it as 'failed' ($0, no model call) are relabelled the same way, keeping the reason.
UPDATE staging.prompt_run SET status = 'skipped', skip_reason = left('unreadable source: ' || substr(error, 16), 300)
WHERE status = 'failed' AND error LIKE 'DocumentError: %' AND coalesce(cost_usd, 0) = 0;
