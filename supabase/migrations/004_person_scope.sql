-- Allow person-scoped digest_scope values (e.g. "person:susan.zuzic@company.com")
-- The old CHECK constraint only permitted the three named scopes.

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_digest_scope_check;

ALTER TABLE users ADD CONSTRAINT users_digest_scope_check
  CHECK (
    digest_scope IS NULL
    OR digest_scope IN ('my_deals', 'team_deals', 'top_pipeline')
    OR digest_scope LIKE 'person:%'
  );
