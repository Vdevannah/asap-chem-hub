-- Switch the 8 RSC journals to Crossref (old feeds.rsc.org RSS froze in June 2026)
USE asap_chem_hub;
UPDATE journals SET source_type = 'crossref', feed_url = 'crossref:issn:2041-6539', last_error = NULL WHERE name = 'Chemical Science';
UPDATE journals SET source_type = 'crossref', feed_url = 'crossref:issn:1364-548X', last_error = NULL WHERE name = 'Chem. Commun.';
UPDATE journals SET source_type = 'crossref', feed_url = 'crossref:issn:1477-0539', last_error = NULL WHERE name = 'Org. Biomol. Chem.';
UPDATE journals SET source_type = 'crossref', feed_url = 'crossref:issn:2052-4129', last_error = NULL WHERE name = 'Org. Chem. Front.';
UPDATE journals SET source_type = 'crossref', feed_url = 'crossref:issn:2632-8682', last_error = NULL WHERE name = 'RSC Med. Chem.';
UPDATE journals SET source_type = 'crossref', feed_url = 'crossref:issn:2633-0679', last_error = NULL WHERE name = 'RSC Chem. Biol.';
UPDATE journals SET source_type = 'crossref', feed_url = 'crossref:issn:1460-4744', last_error = NULL WHERE name = 'Chem. Soc. Rev.';
UPDATE journals SET source_type = 'crossref', feed_url = 'crossref:issn:1460-4752', last_error = NULL WHERE name = 'Nat. Prod. Rep.';
SELECT name, source_type, feed_url FROM journals WHERE publisher = 'RSC';
