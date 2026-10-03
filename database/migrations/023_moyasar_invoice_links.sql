create table if not exists moyasar_invoice_links(
  invoice_id text primary key,
  order_id bigint not null,
  amount_halalas bigint not null,
  webhook_url text not null,
  checkout_url text,
  provider_status text not null default 'initiated',
  last_event_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(order_id)
);
create index if not exists idx_moyasar_invoice_links_order on moyasar_invoice_links(order_id);
