-- Run once in your dedicated Supabase project's SQL editor.
create table if not exists public.family_shop_backups (
  owner uuid primary key references auth.users(id) on delete cascade,
  version bigint not null check (version > 0),
  payload text not null check (octet_length(payload) <= 16000000),
  updated_at timestamptz not null default now()
);
alter table public.family_shop_backups enable row level security;
revoke all on public.family_shop_backups from anon;
grant select, insert, update on public.family_shop_backups to authenticated;
drop policy if exists family_shop_owner on public.family_shop_backups;
create policy family_shop_owner on public.family_shop_backups for all to authenticated
using ((select auth.uid()) = owner) with check ((select auth.uid()) = owner);

create or replace function public.family_shop_upload(expected_version bigint, snapshot text)
returns bigint language plpgsql security invoker set search_path = '' as $$
declare next_version bigint;
begin
  if auth.uid() is null then raise exception 'Sign in required'; end if;
  if expected_version < 0 or octet_length(snapshot)>16000000 then raise exception 'Invalid snapshot'; end if;
  if expected_version = 0 then
    insert into public.family_shop_backups(owner,version,payload)
      values(auth.uid(),1,snapshot) on conflict do nothing returning version into next_version;
  else
    update public.family_shop_backups set version=version+1,payload=snapshot,updated_at=now()
      where owner=auth.uid() and version=expected_version returning version into next_version;
  end if;
  if next_version is null then raise exception 'CLOUD_CONFLICT: Download the newer cloud copy before uploading'; end if;
  return next_version;
end $$;
revoke execute on function public.family_shop_upload(bigint,text) from public, anon;
grant execute on function public.family_shop_upload(bigint,text) to authenticated;

-- Multi-shop upgrade: preserve the earlier single-shop backup table.
create table if not exists public.family_shop_shop_backups (
  owner uuid not null references auth.users(id) on delete cascade,
  shop text not null check (shop in ('mutowei-bottle-store','bizzy-tuckshop','chikofa-tuckshop')),
  version bigint not null check (version > 0),
  payload text not null check (octet_length(payload) <= 16000000),
  updated_at timestamptz not null default now(),
  primary key(owner,shop)
);
alter table public.family_shop_shop_backups enable row level security;
revoke all on public.family_shop_shop_backups from anon;
grant select,insert,update on public.family_shop_shop_backups to authenticated;
drop policy if exists family_shop_shop_owner on public.family_shop_shop_backups;
create policy family_shop_shop_owner on public.family_shop_shop_backups for all to authenticated
using ((select auth.uid())=owner) with check ((select auth.uid())=owner);
create or replace function public.family_shop_upload_shop(expected_version bigint,snapshot text,target_shop text)
returns bigint language plpgsql security invoker set search_path='' as $$
declare next_version bigint;
begin
  if auth.uid() is null then raise exception 'Sign in required'; end if;
  if expected_version<0 or octet_length(snapshot)>16000000 or target_shop not in ('mutowei-bottle-store','bizzy-tuckshop','chikofa-tuckshop') then raise exception 'Invalid snapshot or shop'; end if;
  if expected_version=0 then
    insert into public.family_shop_shop_backups(owner,shop,version,payload)
    values(auth.uid(),target_shop,1,snapshot) on conflict do nothing returning version into next_version;
  else
    update public.family_shop_shop_backups set version=version+1,payload=snapshot,updated_at=now()
    where owner=auth.uid() and shop=target_shop and version=expected_version returning version into next_version;
  end if;
  if next_version is null then raise exception 'CLOUD_CONFLICT: Download the newer cloud copy before uploading'; end if;
  return next_version;
end $$;
revoke execute on function public.family_shop_upload_shop(bigint,text,text) from public,anon;
grant execute on function public.family_shop_upload_shop(bigint,text,text) to authenticated;
