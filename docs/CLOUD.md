# Private Supabase console

The existing Python worker and SQLite ledger remain the sole trading authority.
Supabase stores private UI snapshots and an authenticated command queue; it does
not run a second fund or trade when the local PC is off. Vercel hosts the frontend.

1. Apply `supabase/migrations/202610200001_atlas_remote.sql` to a new Supabase project.
2. Set local server-only `SUPABASE_URL`, `SUPABASE_SECRET_KEY`,
   `CLOUD_SYNC_ENABLED=true`. Never expose the server secret in a frontend variable.
3. Set Vercel Production `VITE_SUPABASE_URL` and
   `VITE_SUPABASE_PUBLISHABLE_KEY`, then deploy the frontend.
4. The CEO creates an Auth user with their own password in Supabase. Grant only
   that verified user's UUID access via `atlas_members`; an arbitrary Auth account
   has no ATLAS data access. No default cloud password exists.
5. Test member login, nonmember rejection, anonymous rejection and engine-offline
   behavior before treating remote access as fully verified.

All app tables use RLS. Clients read snapshots through membership-checked RPCs.
Only the server can update snapshots or claim commands. Local API authentication
and validation apply again to each forwarded command. Expired commands are denied;
ambiguous execution is never automatically replayed. Manager replies persist in
SQLite and synchronize independently of the browser window.

Free Supabase has quotas and may pause inactive projects; this is not a guaranteed
always-on service. Local execution still requires the existing PC to remain on.
Official references: https://supabase.com/docs/guides/database/postgres/row-level-security
and https://supabase.com/docs/guides/platform/free-project-pausing.

20 October 2026: schema applied, private snapshots synchronized, anonymous table
and RPC access rejected. CEO Auth-user creation and membership are still pending;
remote password login cannot be claimed as tested until that step is completed.
