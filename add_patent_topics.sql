-- One-off: add the three patent-only topics (run once on the existing database).
-- "Targeted protein degradation" already exists (shared with articles).
USE asap_chem_hub;
INSERT IGNORE INTO patent_topics (name) VALUES
  ('Antibody-drug conjugates'),
  ('Antibodies'),
  ('OLED materials and devices');
SELECT topic_id, name FROM patent_topics ORDER BY topic_id;
