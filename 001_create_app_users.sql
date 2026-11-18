-- =====================================================================
-- Unified accounts: merge  users (Stock Mgmt)  +  supply_users (Supply/Forecasting)
-- into ONE table, app_users.  The two old tables are NOT modified or dropped.
--
-- HOW TO RUN (Supabase SQL editor), in order:
--   STEP 1  create the table + preview view
--   STEP 2  look at the PREVIEW query output and sanity-check it
--   STEP 3  run the INSERT
--   STEP 4  run the verification queries
-- Safe to re-run: the INSERT skips emails that already exist in app_users.
-- =====================================================================

-- ---------------------------------------------------------------- STEP 1
create table if not exists public.app_users (
  id                          bigint generated always as identity primary key,
  email                       text        not null,
  full_name                   text,
  password_hash               text        not null,
  legacy_password_hash        text,        -- 2nd password for merged accounts whose old passwords differed
  role                        text        not null default 'viewer'
                              check (role in ('viewer','editor','admin')),
  is_approved                 boolean     not null default false,
  is_active                   boolean     not null default true,
  module_access               text        not null default '',      -- e.g. 'stock,supply,forecasting'
  stock_program_access        text        not null default 'All',   -- Stock: empty/All = all programs
  stock_tab_access            text        not null default 'All',   -- was users.main_tab_access
  supply_program_access       text        not null default '',      -- Supply: empty = NO programs
  supply_tab_access           text        not null default 'All',   -- was supply_users.tab_access
  password_reset_requested    boolean     not null default false,
  password_reset_approved     boolean     not null default false,
  password_reset_requested_at timestamptz,
  password_reset_approved_at  timestamptz,
  last_active                 timestamptz,
  last_login                  timestamptz,
  created_at                  timestamptz not null default now(),
  updated_at                  timestamptz,
  migrated_from               text         -- 'both' | 'stock_only' | 'supply_only' | null (new signup)
);

create unique index if not exists app_users_email_key on public.app_users (lower(email));

-- Match the access settings of your existing users / supply_users tables.
-- (The apps talk to Supabase with the same key as before; if RLS were left ON with no
--  policy, nobody could log in.)  Review this against how users/supply_users are set up.
alter table public.app_users disable row level security;

create or replace view public.v_app_users_merge as
with
s as (
  select lower(trim(email))                                   as email,
         full_name,
         password_hash,
         case when role in ('admin','editor','viewer') then role else 'viewer' end as role,
         coalesce(is_approved::int,0) <> 0                    as approved,
         coalesce(is_active::int,1)   <> 0                    as active,
         coalesce(program_access,'')                          as program_access,
         coalesce(nullif(trim(tab_access),''),'All')          as tab_access,
         coalesce(password_reset_requested::int,0) <> 0       as reset_req,
         coalesce(password_reset_approved::int,0)  <> 0       as reset_appr,
         nullif(password_reset_requested_at::text,'')::timestamptz as reset_req_at,
         nullif(password_reset_approved_at::text,'')::timestamptz  as reset_appr_at,
         nullif(created_at::text,'')::timestamptz             as created_at,
         nullif(last_login::text,'')::timestamptz             as last_seen
  from public.supply_users
),
d as (
  select lower(trim(email))                                   as email,
         full_name,
         password                                             as password_hash,
         case role when 'admin'  then 'admin'
                   when 'editor' then 'editor'
                   else 'viewer' end                          as role,      -- legacy 'user' -> viewer
         coalesce(is_approved::int,0) <> 0                    as approved,
         coalesce(nullif(trim(program_access),''),'All')      as program_access,
         coalesce(nullif(trim(main_tab_access),''),'All')     as tab_access,
         nullif(created_at::text,'')::timestamptz             as created_at,
         nullif(last_active::text,'')::timestamptz            as last_seen
  from public.users
)
select
  coalesce(s.email, d.email)                                                  as email,
  coalesce(nullif(s.full_name,''), nullif(d.full_name,''), split_part(coalesce(s.email,d.email),'@',1)) as full_name,

  -- password: keep the one from the account used most recently ...
  case when s.email is null then d.password_hash
       when d.email is null then s.password_hash
       when coalesce(d.last_seen,'-infinity') > coalesce(s.last_seen,'-infinity') then d.password_hash
       else s.password_hash end                                               as password_hash,
  -- ... and keep the other one as a fallback so NOBODY gets locked out
  case when s.email is not null and d.email is not null
        and s.password_hash is distinct from d.password_hash then
         case when coalesce(d.last_seen,'-infinity') > coalesce(s.last_seen,'-infinity')
              then s.password_hash else d.password_hash end
       end                                                                    as legacy_password_hash,

  -- highest role wins
  (array['viewer','editor','admin'])[greatest(
      coalesce(array_position(array['viewer','editor','admin'], s.role),1),
      coalesce(array_position(array['viewer','editor','admin'], d.role),1))] as role,

  (coalesce(s.approved,false) or coalesce(d.approved,false))                  as is_approved,
  (coalesce(s.active,false) or d.email is not null)                           as is_active,

  -- a module is granted only where the person was ALREADY approved
  coalesce(concat_ws(',',
      case when d.email is not null and d.approved                    then 'stock' end,
      case when s.email is not null and s.approved and s.active       then 'supply' end,
      case when s.email is not null and s.approved and s.active       then 'forecasting' end
  ),'')                                                                       as module_access,

  coalesce(d.program_access,'All')                                            as stock_program_access,
  coalesce(d.tab_access,'All')                                                as stock_tab_access,
  coalesce(s.program_access,'')                                               as supply_program_access,
  coalesce(s.tab_access,'All')                                                as supply_tab_access,

  coalesce(s.reset_req,false)                                                 as password_reset_requested,
  coalesce(s.reset_appr,false)                                                as password_reset_approved,
  s.reset_req_at                                                              as password_reset_requested_at,
  s.reset_appr_at                                                             as password_reset_approved_at,

  greatest(s.last_seen, d.last_seen)                                          as last_active,
  s.last_seen                                                                 as last_login,
  least(s.created_at, d.created_at)                                           as created_at,
  case when s.email is not null and d.email is not null then 'both'
       when d.email is not null then 'stock_only' else 'supply_only' end      as migrated_from
from s
full outer join d on s.email = d.email;

-- ---------------------------------------------------------------- STEP 2  (PREVIEW - read-only)
-- Check: one row per person, modules look right, 'both' rows have the union of access.
--   select email, role, is_approved, module_access, migrated_from,
--          legacy_password_hash is not null as has_alt_password
--   from public.v_app_users_merge order by migrated_from, email;
--
-- Duplicate emails INSIDE one old table (e.g. 'A@x.org' and 'a@x.org') would be merged
-- into one person; this should return no rows, or rows you are happy to merge:
--   select lower(trim(email)), count(*) from public.users        group by 1 having count(*)>1;
--   select lower(trim(email)), count(*) from public.supply_users group by 1 having count(*)>1;
--
-- Accounts that exist in BOTH apps but had DIFFERENT passwords (both will keep working):
--   select email from public.v_app_users_merge where legacy_password_hash is not null;

-- ---------------------------------------------------------------- STEP 3  (the actual copy)
insert into public.app_users
  (email, full_name, password_hash, legacy_password_hash, role, is_approved, is_active,
   module_access, stock_program_access, stock_tab_access, supply_program_access, supply_tab_access,
   password_reset_requested, password_reset_approved, password_reset_requested_at,
   password_reset_approved_at, last_active, last_login, created_at, migrated_from)
select email, full_name, password_hash, legacy_password_hash, role, is_approved, is_active,
       module_access, stock_program_access, stock_tab_access, supply_program_access, supply_tab_access,
       password_reset_requested, password_reset_approved, password_reset_requested_at,
       password_reset_approved_at, last_active, last_login, coalesce(created_at, now()), migrated_from
from public.v_app_users_merge
where password_hash is not null
on conflict ((lower(email))) do nothing;

-- ---------------------------------------------------------------- STEP 4  (verify)
--   -- should equal the number of DISTINCT emails across both old tables:
--   select count(*) from public.app_users;
--   select count(distinct e) from (select lower(trim(email)) e from public.users
--                                  union select lower(trim(email)) from public.supply_users) x;
--   -- nobody approved should end up with zero modules (admins excepted):
--   select email from public.app_users where is_approved and role <> 'admin' and module_access = '';

-- Optional cleanup once everything is confirmed:
--   drop view public.v_app_users_merge;
