-- Technology pillar: labels for the extra technology_metric keys that prompts/tech_rollups.py writes (staging_ui only; Approve copies to serving).
INSERT INTO staging_ui.code_label (table_name, column_name, code, label, tag_class, tooltip, display_order, is_active, is_default) VALUES
 ('technology_metric', 'metric_key', 'rival',       'Competitor advances',            'rival', 'cards where a tracked competitor gains a capability', 1, true, false),
 ('technology_metric', 'metric_key', 'adopt',       'Adoptable advances',             'adopt', 'cards KSSL could adopt, license or team on', 2, true, false),
 ('technology_metric', 'metric_key', 'trend',       'Trends and threats',             'trend', 'threats to KSSL''s position and industry trends', 3, true, false),
 ('technology_metric', 'metric_key', 'all',         'Domains tracked',                NULL,    'categories with at least one card or innovation', 4, true, false),
 ('technology_metric', 'metric_key', 'threat',      'Cards labelled threat',          'threat','direction computed by code', 5, true, false),
 ('technology_metric', 'metric_key', 'watch',       'Cards labelled watch',           'watch', 'direction computed by code', 6, true, false),
 ('technology_metric', 'metric_key', 'fav',         'Cards labelled favourable',      'fav',   'direction computed by code', 7, true, false),
 ('technology_metric', 'metric_key', 'innovations', 'Innovations in the pipeline',    NULL,    'active innovations', 8, true, false),
 ('technology_metric', 'metric_key', 'patents',     'Competitor patent filings',      NULL,    'filings on record', 9, true, false)
ON CONFLICT (table_name, column_name, code) DO UPDATE SET label = EXCLUDED.label, tag_class = EXCLUDED.tag_class, tooltip = EXCLUDED.tooltip,
  display_order = EXCLUDED.display_order, is_active = true;
