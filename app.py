"""
app.py - the ONE entry point.   Run with:   streamlit run app.py   (Streamlit >= 1.46)

  * one page config, one login, one account per person
  * the first module the person may open is the landing page
  * sidebar, top to bottom:
        EPSS
        Welcome, <name>!
        Modules            (only the modules that person may open)
        <the open module's own sidebar>
              Stock Management -> its filters + Navigation
              Supply Planning  -> Selection + Main Tabs
              Forecasting      -> no controls, just the title "Demand Forecasting Tool"
        ✅ Connected to Supabase (admins)
        Refresh            (once, clears every module's caches)
        Admin Panel (admins), Profile, Logout   (once)
"""
import streamlit as st

st.set_page_config(
    page_title="HPC Supply Chain Management Tool",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.session_state["_unified_shell"] = True      # tells stock.py / planning.py they are embedded

import core_auth as ca
from outh import (
    init_session_state, show_login_page, show_profile_page,
    show_admin_panel, show_forced_password_reset,
)

init_session_state()

# ------------------------------------------------------------------ login gate
if not st.session_state.get("auth"):
    if st.session_state.pop("access_revoked", False):
        st.warning("Your access was changed or removed by an administrator. Please sign in again.")
    show_login_page()
    st.stop()

ca.check_session_validity()                    # heartbeat + live access refresh
if not st.session_state.get("auth"):           # access revoked while signed in
    st.rerun()

if st.session_state.get("force_password_reset"):
    if show_forced_password_reset():
        st.stop()

user = st.session_state["user"]
allowed = ca.user_modules(user)

# ---------------------------------------------------------------------- pages
def no_access_page():
    st.warning("No modules are assigned to your account yet. Please contact your administrator.")


def supply_page():
    st.session_state["active_section"] = "supply_planning"
    import planning
    planning.main()


def forecasting_page():
    st.session_state["active_section"] = "forecasting"
    import planning
    planning.main()


MODULE_PAGES = {   # module key -> st.Page (the first allowed module is the landing page)
    "stock": lambda first: st.Page("stock.py", title=ca.MODULES["stock"], icon=ca.MODULE_ICONS["stock"],
                                   url_path="stock-management", default=first),
    "supply": lambda first: st.Page(supply_page, title=ca.MODULES["supply"], icon=ca.MODULE_ICONS["supply"],
                                    url_path="supply-planning", default=first),
    "forecasting": lambda first: st.Page(forecasting_page, title=ca.MODULES["forecasting"],
                                         icon=ca.MODULE_ICONS["forecasting"], url_path="forecasting",
                                         default=first),
}
TITLE_TO_MODULE = {title: key for key, title in ca.MODULES.items()}

MODULE_PAGE_OBJS = {m: MODULE_PAGES[m](i == 0) for i, m in enumerate(allowed)}
no_access = None if allowed else st.Page(no_access_page, title="No access", icon="🚫", url_path="no-access", default=True)
profile_pg = st.Page(show_profile_page, title="Profile", icon="👤", url_path="profile")
admin_pg = (st.Page(show_admin_panel, title="Admin Panel", icon="👑", url_path="admin")
            if user.get("role") == "admin" else None)

# The built-in navigation is hidden: the sidebar is drawn by hand (below) so that it reads, top to bottom:
#   EPSS / Welcome / Modules / the open module's own sidebar / Refresh / Admin Panel, Profile, Logout
pg = st.navigation(
    [*MODULE_PAGE_OBJS.values(), *([no_access] if no_access else []), profile_pg, *([admin_pg] if admin_pg else [])],
    position="hidden",
)

# per-module restrictions (program/tab access) follow whichever module is open
if pg.title in TITLE_TO_MODULE:
    ca.set_active_module(TITLE_TO_MODULE[pg.title])


def refresh_everything():
    """The one Refresh: clears the caches and the memos of every module."""
    try:
        st.cache_data.clear()
    except Exception:
        pass
    for k in ("_main_frames_memo", "_kpi_lead_memo"):
        st.session_state.pop(k, None)
    st.session_state["proc_cache_bust"] = st.session_state.get("proc_cache_bust", 0) + 1
    st.session_state["data_loaded"] = False          # supply planning / forecasting reload


# ---------------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown(
        "<div style='background:#1a5276;border-radius:15px;padding:10px;text-align:center;width:60px'>"
        "<p style='color:white;font-weight:bold;margin:0'>EPSS</p></div>", unsafe_allow_html=True)
    st.markdown(f"### Welcome, {user.get('full_name')}!")

    st.markdown("#### Modules")
    for _m, _page in MODULE_PAGE_OBJS.items():
        st.page_link(_page, label=ca.MODULES[_m], icon=ca.MODULE_ICONS[_m])

    st.divider()
    module_slot = st.container()     # the open module draws its own sidebar here
    footer_slot = st.container()     # Refresh + account links: always below the module's sidebar

st.session_state["_sb_slot"] = module_slot

with footer_slot:
    st.divider()
    if user.get("role") == "admin" and st.session_state.get("supabase_client"):
        st.success("✅ Connected to Supabase")
    if st.button("🔄 Refresh", key="shell_refresh", use_container_width=True,
                 help="Reload the latest data from Supabase / Google Sheets"):
        refresh_everything()
        st.rerun()
    if admin_pg:
        st.page_link(admin_pg, label="Admin Panel", icon="👑")
    st.page_link(profile_pg, label="Profile", icon="👤")
    if st.button("🚪 Logout", key="shell_logout", use_container_width=True):
        ca.logout()

pg.run()
