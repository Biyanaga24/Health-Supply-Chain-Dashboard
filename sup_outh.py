"""
sup_outh.py - compatibility shim.

Supply Planning / Forecasting used to have their own login system (table supply_users).
Everything now lives in core_auth.py (table app_users); this file only re-exports the
old function names so planning.py needs no import changes.
"""
import streamlit as st

import core_auth as _core
from core_auth import (  # noqa: F401  (re-exported)
    get_current_user, get_user_role, is_admin, is_editor, logout,
    get_user_program_access, check_program_access, get_user_tab_access,
    approve_user, reject_user, update_user_role, toggle_user_active,
    change_password, update_user_profile, refresh_current_user,
    request_password_reset, get_password_reset_requests, approve_password_reset,
    reject_password_reset, has_approved_password_reset, complete_password_reset,
    delete_user, authenticate_user, create_user, hash_password,
    get_current_time, format_time_for_display,
)

# These two returned lists in the old module (core_auth's DataFrame variants are used by outh.py)
get_all_users = _core.get_all_users_list
get_pending_users = _core.get_pending_users_list


def update_user_program_access(user_id, programs):
    return _core.update_module_access(user_id, "supply", "program", programs)


def update_user_tab_access(user_id, tabs):
    if isinstance(tabs, str):
        tabs = [t.strip() for t in tabs.split(",") if t.strip()]
    return _core.update_module_access(user_id, "supply", "tab", tabs)


def show_login_page():
    from outh import show_login_page as _login      # the one shared login screen
    _login()


def require_auth():
    """True when logged in; otherwise shows the shared login page."""
    if not st.session_state.get("auth"):
        show_login_page()
        return False
    _core.check_session_validity()
    return bool(st.session_state.get("auth"))
