create table enterprise_orders (
    id varchar(36) primary key,
    request_id varchar(80) not null unique,
    amount_cents bigint not null check (amount_cents > 0),
    status varchar(24) not null
);

create table enterprise_inventory (
    sku varchar(80) primary key,
    available bigint not null check (available >= 0)
);

create table enterprise_outbox (
    id varchar(36) primary key,
    aggregate_id varchar(36) not null,
    event_type varchar(80) not null,
    payload text not null,
    published boolean not null default false,
    created_at timestamp with time zone not null
);

create index enterprise_outbox_pending_idx
    on enterprise_outbox (published, created_at);

create table enterprise_consumed_events (
    message_id varchar(36) primary key,
    payload text not null,
    handled_count integer not null check (handled_count = 1),
    consumed_at timestamp with time zone not null
);
