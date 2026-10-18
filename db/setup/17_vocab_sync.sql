-- code_label rows for codes the prompts actually write (red-team audit 2026-10-18). The prompt enums are the source of truth:
--   competitive_partnership.partner_type        prompts/partnership.yml (the code_label list had drifted: JV, Licence / ToT, ...)
--   competitive_geo_company_presence.activity_type   prompts/geo.yml (code_label had Manufactures / Sells / Sources)
--   story_step.label_after / step_type          prompts/story.py (opportunity stages, project stages, planned / production steps)
-- Labels that no stored row and no prompt uses any more are set inactive (kept for history). Idempotent; staging_ui only
-- (serving ui.code_label is copied by Approve).
DO $vocab$
BEGIN
  IF to_regclass('staging_ui.code_label') IS NULL THEN
    RETURN;
  END IF;
  INSERT INTO staging_ui.code_label (table_name, column_name, code, label, tag_class, tooltip, display_order, is_active, value_from, value_to, is_default)
  SELECT v.t, v.c, v.code, v.label, NULL, NULL, v.o, true, NULL::numeric, NULL::numeric, false
  FROM (VALUES
    ('competitive_partnership', 'partner_type', 'Joint venture', 'Joint venture', 1),
    ('competitive_partnership', 'partner_type', 'Acquisition', 'Acquisition', 2),
    ('competitive_partnership', 'partner_type', 'Technology / ToT', 'Technology / ToT', 3),
    ('competitive_partnership', 'partner_type', 'Teaming', 'Teaming', 4),
    ('competitive_partnership', 'partner_type', 'Supplier', 'Supplier', 5),
    ('competitive_partnership', 'partner_type', 'Supply / customer', 'Supply / customer', 6),
    ('competitive_partnership', 'partner_type', 'MoU / strategic', 'MoU / strategic', 7),
    ('competitive_partnership', 'partner_type', 'Other', 'Other', 8),
    ('competitive_geo_company_presence', 'activity_type', 'Local production', 'Local production', 1),
    ('competitive_geo_company_presence', 'activity_type', 'Licensed production', 'Licensed production', 2),
    ('competitive_geo_company_presence', 'activity_type', 'Export', 'Export', 3),
    ('competitive_geo_company_presence', 'activity_type', 'Sales and service', 'Sales and service', 4),
    ('competitive_geo_company_presence', 'activity_type', 'Sourcing', 'Sourcing', 5),
    ('story_step', 'step_type', 'planned', 'Planned', 11),
    ('story_step', 'step_type', 'production', 'Production', 12),
    ('story_step', 'label_after', 'need_stated', 'Need stated', 20),
    ('story_step', 'label_after', 'approved_funded', 'Approved and funded', 21),
    ('story_step', 'label_after', 'rfi', 'RFI', 22),
    ('story_step', 'label_after', 'rfp_tender', 'RFP / tender', 23),
    ('story_step', 'label_after', 'downselect_prototype', 'Down-select / prototype', 24),
    ('story_step', 'label_after', 'production_award', 'Production award', 25),
    ('story_step', 'label_after', 'delivered', 'Delivered', 26),
    ('story_step', 'label_after', 'cancelled', 'Cancelled', 27),
    ('story_step', 'label_after', 'Concept', 'Concept', 30),
    ('story_step', 'label_after', 'Trials', 'Trials', 31),
    ('story_step', 'label_after', 'Contract', 'Contract', 32),
    ('story_step', 'label_after', 'Production', 'Production', 33),
    ('story_step', 'label_after', 'Deliveries', 'Deliveries', 34),
    ('story_step', 'label_after', 'In service', 'In service', 35),
    ('story_step', 'label_after', 'none', 'Not shown', 36)
  ) AS v(t, c, code, label, o)
  WHERE NOT EXISTS (SELECT 1 FROM staging_ui.code_label l WHERE l.table_name = v.t AND l.column_name = v.c AND l.code = v.code);

  -- labels no prompt writes any more
  UPDATE staging_ui.code_label SET is_active = false
   WHERE (table_name, column_name) IN (('competitive_partnership', 'partner_type'), ('competitive_geo_company_presence', 'activity_type'))
     AND code NOT IN ('Joint venture', 'Acquisition', 'Technology / ToT', 'Teaming', 'Supplier', 'Supply / customer', 'MoU / strategic', 'Other',
                      'Local production', 'Licensed production', 'Export', 'Sales and service', 'Sourcing');
END $vocab$;
