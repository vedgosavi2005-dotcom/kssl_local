-- 41_change_proposal.sql -- CHANGES FOUND IN THE NEWS (owner 2026-10-24: "news can populate literally everything: a new product,
-- new product specs, the leadership change ... show it on review and mark it as a new thing, so the reviewer can say: should we
-- continue or not?").
-- STAGING DB. The signal and news prompts list what an article says that is NEW or DIFFERENT from our records; each such fact is
-- one proposal here. Nothing is written to the records until a reviewer clicks Accept on the review site (Changes from news):
-- Accept writes the change into the review data (staging), where it shows as a NEW / CHANGED card, and the usual Approve puts it
-- live. Reject keeps the row, so the same fact is not proposed again (fingerprint). Idempotent and DBeaver-safe.

CREATE TABLE IF NOT EXISTS staging.change_proposal (
    proposal_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind           text NOT NULL CHECK (kind IN ('new_product', 'spec', 'leadership', 'partner', 'location', 'company_fact')),
    competitor_id  uuid NOT NULL,
    subject        text NOT NULL,            -- the product / the person / the partner / the place / the company fact's name
    field          text,                     -- spec: its label ("Range"); leadership: the role ("Chief Executive Officer");
                                             -- company_fact: employee_count / annual_revenue / headquarters / starting_year ...
    proposed_value text NOT NULL,            -- what the article says
    unit           text,                     -- spec unit when separate ("km")
    target_table   text,                     -- the record it would change (staging table), NULL until resolved
    target_id      text,                     -- that record's id; NULL = a new record
    current_value  text,                     -- what we hold now, filled by code at load time (NULL = we hold nothing)
    effective_date date,                     -- when the change takes effect, if the article says
    article_url    text NOT NULL,
    quote          text NOT NULL,            -- the article's sentence that states it (the reviewer's evidence)
    article_date   date,
    source_prompt  text,                     -- signal / news
    source_row_id  text,                     -- the signal / news article it came with
    status         text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected', 'superseded')),
    decided_by     text,
    decided_at     timestamptz,
    decision_note  text,
    applied        jsonb,                    -- what Accept wrote: {"table": ..., "id": ..., "action": ...}
    fingerprint    text NOT NULL,            -- kind | competitor | subject | field | value, normalised: one proposal per fact
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS change_proposal_fp ON staging.change_proposal (fingerprint);
CREATE INDEX IF NOT EXISTS change_proposal_pending ON staging.change_proposal (status, created_at DESC);
CREATE INDEX IF NOT EXISTS change_proposal_competitor ON staging.change_proposal (competitor_id);
COMMENT ON TABLE staging.change_proposal IS 'facts an article states that are new or differ from our records; applied only by a reviewer''s Accept';
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kssl_app') THEN
    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON staging.change_proposal TO kssl_app';
  END IF;
END $$;
