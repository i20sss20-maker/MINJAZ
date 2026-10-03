alter table users add column if not exists deleted_at timestamptz;
create index if not exists idx_users_deleted_at on users(deleted_at) where deleted_at is not null;
alter table privacy_requests add column if not exists deletion_executed_at timestamptz;
