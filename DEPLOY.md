# Unified app – deployment guide

## What's in this folder
| File | Role |
|---|---|
| `app.py` | **New single entry point.** One login, hand-built sidebar (EPSS, Welcome, Modules, module sidebar, Refresh, account links). |
| `core_auth.py` | **New.** The one account system (table `app_users`). |
| `outh.py` | Shared login / profile / admin screens (rewritten on top of `core_auth`). |
| `sup_outh.py` | Compatibility shim – re-exports the old names from `core_auth`. |
| `stock.py` | Stock Management. 2 small guarded edits (page config, sidebar Users Control). |
| `planning.py` | Supply Planning + Forecasting. ~37 changed lines (guarded; see below). |
| `migration/001_create_app_users.sql` | Creates `app_users` and merges `users` + `supply_users`. Old tables untouched. |

## Steps
1. **Database** – in the Supabase SQL editor run `migration/001_create_app_users.sql` step by step
   (STEP 1 create → STEP 2 run the commented preview queries and check them → STEP 3 insert → STEP 4 verify).
   Check the `alter table ... disable row level security` line matches how your existing user tables are set up.
2. **Code** – deploy this folder; start with `streamlit run app.py` (**Streamlit >= 1.46** - the sidebar uses `st.navigation(position="hidden")`).
   Same `st.secrets` as before. Keep your other modules (`forecast_core`, etc.) next to these files.
3. **Smoke test** with 4 accounts: an admin, a Stock-only user, a Supply-only user, a user with all three.
4. Once happy, retire the old entry points. The old `users` / `supply_users` tables can stay as a backup.

**Rollback:** run the old apps against the old tables (use your original files). Nothing in the old tables was modified.

## How access works now
* `role`: viewer / editor / admin (admins always see every module).
* `module_access`: which of Stock Management / Supply Planning / Forecasting a user can open.
* Restrictions are **per module**: Stock has its own programs + tabs; Supply and Forecasting share theirs.
  (The apps treated an empty program list oppositely – Stock: all programs, Supply: none – so each keeps its own rule.)
* Admin Panel (one for everything): approve users **and choose their modules**, change role, deactivate, edit
  modules and per-module restrictions, add users, approve/reject password resets.
* Existing passwords keep working. They are silently upgraded from unsalted SHA-256 to salted PBKDF2 at next login.
  If someone had different passwords in the two old apps, **both** work on first login, then it collapses to the one used.

## What the migration decides (review these)
* Same email in both tables -> one account; **highest role wins**; modules are the union.
* A module is granted only where the person was **already approved** there. Pending in both -> stays pending.
* Dashboard role `user` becomes `viewer` (Stock never enforced editor/viewer differences).
* People who were inactive in Supply lose Supply/Forecasting; they keep Stock if they had it.

## NOT yet verified (no Streamlit/Supabase in the build sandbox)
* The SQL has not been executed – use the preview step on your real data first.
* The Streamlit UI flow (login, navigation, admin screens) and both apps running inside `st.navigation` have not been run.
  What *was* tested: all account logic against an in-memory fake DB (50 checks), plus compile + undefined-name checks.
* Both modules now share one browser session. Only `user` and `action_plan_tab` are keys used by both (same default), but
  watch for odd state when switching modules in the first week.

## Phase 2 (not done): shared calculations
`calculate_dos`, `categorize_stock`, `calculate_risk` and 7 more functions exist in both files with **different logic**.
Notably the dashboard classifies stock with global min/max months-of-stock thresholds while Supply Planning uses
per-material limits (`get_stock_limits`), so the same material can show a different status in different modules.
Decide which rule is correct, then move one version into a shared `core/` module.

## Sidebar layout (latest change)
Sidebar, top to bottom: **EPSS -> Welcome, <name>! -> Modules -> the open module's own sidebar -> Refresh (once) -> Admin Panel / Profile / Logout (once)**.
* `app.py` creates a `module_slot` and a `footer_slot` container; the open module draws its sidebar into the slot
  (`stock.py`: `_SB`, `planning.py`: `st.session_state["_sb_slot"]`). The footer is therefore always below it, even when a page calls `st.stop()`.
* Forecasting has no controls: it shows only the title **Demand Forecasting Tool** and works on all programs the user may access.
* Stock / Supply no longer draw their own EPSS, Welcome, Refresh, Admin, Profile or Logout when embedded (standalone behaviour is unchanged).
* No Overview page: the first module a user may open is the landing page.
* Not run here (no Streamlit in the sandbox): files compile, but the sidebar order still needs a visual check.

## Extra package
* PowerPoint export of the Action Plan Follow Up table needs `python-pptx`. It is now listed in `requirements.txt`: run `pip install -r requirements.txt` (or redeploy so the host installs it), then restart Streamlit. The app also tries a one-off `pip install python-pptx` itself, but that does not work on most hosted platforms.
* `requirements.txt` was built from the imports in these files; `forecast_core` (not in this folder) may need more, e.g. statsmodels/scipy/scikit-learn are included as a precaution - trim what you don't need.
