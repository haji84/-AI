-- Preserve existing credentials; Human schedules legacy expiry explicitly.
ALTER TABLE app_users ADD COLUMN password_changed_at timestamptz;
ALTER TABLE app_users ADD COLUMN password_expires_at timestamptz;
UPDATE app_users SET password_changed_at=COALESCE((SELECT MAX(h.changed_at) FROM account_password_history h WHERE h.user_id=app_users.user_id AND h.password_hash=app_users.password_hash),created_at) WHERE password_changed_at IS NULL;
ALTER TABLE app_users ALTER COLUMN password_changed_at SET NOT NULL;
