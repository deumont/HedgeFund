-- Private remote console. The existing local ledger remains the only execution authority.
begin;
create table if not exists public.atlas_members (
 user_id uuid primary key references auth.users(id) on delete cascade
);
create table if not exists public.atlas_snapshots (
 path text primary key, payload jsonb not null, etag text not null,
 captured_at timestamptz not null default now(),
 check (octet_length(payload::text) <= 1000000)
);
create table if not exists public.atlas_engine (
 id boolean primary key default true check(id), engine_id text not null,
 connected_at timestamptz not null default now()
);
create table if not exists public.atlas_commands (
 id uuid primary key, created_by uuid not null references auth.users(id),
 method text not null check(method in ('GET','POST')), path text not null,
 body jsonb not null default '{}'::jsonb,
 status text not null default 'pending' check(status in ('pending','processing','completed','failed','uncertain','expired')),
 created_at timestamptz not null default now(), expires_at timestamptz not null default now()+interval '2 minutes',
 result jsonb, error text, engine_id text,
 check (octet_length(body::text)<=100000)
);
create index if not exists atlas_commands_pending on public.atlas_commands(status,created_at);
alter table public.atlas_members enable row level security;
alter table public.atlas_snapshots enable row level security;
alter table public.atlas_engine enable row level security;
alter table public.atlas_commands enable row level security;
revoke all on public.atlas_members,public.atlas_snapshots,public.atlas_engine,public.atlas_commands from anon,authenticated;
grant all on public.atlas_members,public.atlas_snapshots,public.atlas_engine,public.atlas_commands to service_role;
grant select on public.atlas_members to authenticated;
drop policy if exists atlas_members_self on public.atlas_members;
create policy atlas_members_self on public.atlas_members for select to authenticated using(user_id=(select auth.uid()));

create or replace function public.atlas_read_snapshot(p_path text,p_etag text default '')
returns jsonb language plpgsql security definer set search_path='' as $$
declare s public.atlas_snapshots; heartbeat timestamptz;
begin
 if not exists(select 1 from public.atlas_members where user_id=auth.uid()) then
  raise exception 'ATLAS access denied' using errcode='42501';
 end if;
 select * into s from public.atlas_snapshots where path=p_path;
 select connected_at into heartbeat from public.atlas_engine where id=true;
 if s.path is null then return jsonb_build_object('missing',true,'heartbeat',heartbeat); end if;
 return jsonb_build_object('etag',s.etag,'captured_at',s.captured_at,'heartbeat',heartbeat,
   'payload',case when s.etag=p_etag then null else s.payload end);
end $$;

create or replace function public.atlas_submit_command(p_id uuid,p_method text,p_path text,p_body jsonb default '{}'::jsonb)
returns uuid language plpgsql security definer set search_path='' as $$
declare target_engine text;
begin
 if not exists(select 1 from public.atlas_members where user_id=auth.uid()) then
  raise exception 'ATLAS access denied' using errcode='42501';
 end if;
 if p_method not in ('GET','POST') or length(p_path)>200 or octet_length(p_body::text)>100000
    or p_path ~ '(^/|\.\.|://)' or p_path ~ '^(login|logout|session|live|health)(/|$)' then
  raise exception 'Unsupported ATLAS command';
 end if;
 if (select count(*) from public.atlas_commands where created_by=auth.uid() and created_at>now()-interval '1 minute')>=30 then
  raise exception 'ATLAS command rate limit';
 end if;
 select engine_id into target_engine from public.atlas_engine where id=true and connected_at>now()-interval '90 seconds';
 if target_engine is null then raise exception 'Handelsengine offline; keine Aktion ausgeführt'; end if;
 if exists(select 1 from public.atlas_commands where id=p_id and created_by<>auth.uid()) then
  raise exception 'Command identity conflict';
 end if;
 insert into public.atlas_commands(id,created_by,method,path,body,engine_id)
 values(p_id,auth.uid(),p_method,p_path,p_body,target_engine) on conflict(id) do nothing;
 return p_id;
end $$;

create or replace function public.atlas_command_result(p_id uuid)
returns jsonb language plpgsql security definer set search_path='' as $$
declare c public.atlas_commands;
begin
 if not exists(select 1 from public.atlas_members where user_id=auth.uid()) then
  raise exception 'ATLAS access denied' using errcode='42501';
 end if;
 select * into c from public.atlas_commands where id=p_id and created_by=auth.uid();
 if c.id is null then raise exception 'Command missing'; end if;
 return jsonb_build_object('status',c.status,'result',c.result,'error',c.error);
end $$;

create or replace function public.atlas_claim_commands(p_engine text)
returns setof public.atlas_commands language plpgsql security definer set search_path='' as $$
begin
 if auth.role()<>'service_role' then raise exception 'Worker access denied' using errcode='42501'; end if;
 -- Commands left in processing after a disconnect are never replayed automatically.
 update public.atlas_commands set status='uncertain',error='Ausführung nach Verbindungsabbruch unklar; nicht automatisch wiederholt'
 where status='processing' and expires_at<now();
 update public.atlas_commands set status='expired',error='Auftrag abgelaufen; keine Ausführung'
 where status='pending' and (expires_at<now() or engine_id<>p_engine);
 return query with pending as (
  select id from public.atlas_commands where status='pending' and engine_id=p_engine
  order by created_at for update skip locked limit 5
 ) update public.atlas_commands c set status='processing' from pending p where c.id=p.id returning c.*;
 -- Keep the free project bounded. No trading ledger is deleted here.
 delete from public.atlas_commands where created_at<now()-interval '7 days' and status not in ('pending','processing');
end $$;

revoke all on function public.atlas_read_snapshot(text,text),public.atlas_submit_command(uuid,text,text,jsonb),public.atlas_command_result(uuid),public.atlas_claim_commands(text) from public,anon,authenticated;
grant execute on function public.atlas_read_snapshot(text,text),public.atlas_submit_command(uuid,text,text,jsonb),public.atlas_command_result(uuid) to authenticated;
grant execute on function public.atlas_claim_commands(text) to service_role;
commit;
