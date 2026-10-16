-- Page configuration the prompts need (not data): applied to kssl_staging, idempotent (a row is inserted only if missing).
--   staging_ui.ui_project_stage_step   the four stages of a defence project (prompt `project` writes a stage per project)
--   staging_ui.ui_project_filter       Domestic / Export filter of the Projects page
--   staging.technology_pillar          the one pillar row of the Technology page
-- Local: applied by db/make_databases.sh.  VPS: python -m prompts.batch sql db/setup/07_page_setup.sql --db vps  (tunnel open)
INSERT INTO staging_ui.ui_project_stage_step (stage_step_id, stage_name, stage_order)
SELECT v.id, v.name, v.ord
FROM (VALUES (1, 'Concept', 1), (2, 'Trials', 2), (3, 'Contract', 3), (4, 'Production', 4)) AS v(id, name, ord)
WHERE NOT EXISTS (SELECT 1 FROM staging_ui.ui_project_stage_step s WHERE s.stage_name = v.name);

INSERT INTO staging_ui.ui_project_filter (filter_id, filter_code, filter_label, display_order, is_default)
SELECT v.id, v.code, v.code, v.ord, false
FROM (VALUES (1, 'Domestic', 1), (2, 'Export', 2)) AS v(id, code, ord)
WHERE NOT EXISTS (SELECT 1 FROM staging_ui.ui_project_filter f WHERE f.filter_code = v.code);

INSERT INTO staging.technology_pillar (pillar_id, pillar_code, pillar_name, client_name, is_active, created_at, updated_at)
SELECT 1, 'technology', 'Technology', 'KSSL', true, now(), now()
WHERE NOT EXISTS (SELECT 1 FROM staging.technology_pillar p WHERE p.pillar_code = 'technology');
