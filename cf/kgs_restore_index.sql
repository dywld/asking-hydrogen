-- 전체 docs_fts 재생성 후 보관된 KGS 조각을 색인에 다시 넣는다.
INSERT INTO docs_fts(rowid, bg)
SELECT -k.id, k.bg FROM kgs_docs k
WHERE NOT EXISTS (SELECT 1 FROM docs_fts f WHERE f.rowid = -k.id);
