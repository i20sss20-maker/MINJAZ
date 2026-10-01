create table if not exists operational_events(
  id bigserial primary key,
  request_id text,
  level text not null default 'error' check(level in ('info','warning','error','critical')),
  area text not null,
  code text not null,
  message text,
  user_id bigint references users(id) on delete set null,
  entity_type text,
  entity_id text,
  meta jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_operational_events_created on operational_events(created_at desc);
create index if not exists idx_operational_events_area on operational_events(area,created_at desc);
create index if not exists idx_operational_events_request on operational_events(request_id) where request_id is not null;