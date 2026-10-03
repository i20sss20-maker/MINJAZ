create table if not exists push_subscriptions(
  id bigserial primary key,
  user_id bigint not null references users(id) on delete cascade,
  endpoint text not null unique,
  p256dh text not null,
  auth_key text not null,
  expiration_time bigint,
  user_agent text,
  failure_count int not null default 0,
  last_success_at timestamptz,
  last_failure_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_push_subscriptions_user on push_subscriptions(user_id,updated_at desc);
