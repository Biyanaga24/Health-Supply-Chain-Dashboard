"""
core_auth.py - ONE account system for Stock Management, Supply Planning and Forecasting.

All users live in a single Supabase table (``app_users``).  Each user has:
  * a global role            : viewer / editor / admin
  * module_access            : which of the three modules they may open
  * per-module restrictions  : program access + tab access for Stock and for Supply
                               (Forecasting follows the Supply settings)

The two legacy login modules (outh.py, sup_outh.py) now just re-export from here,
so stock.py and planning.py keep working with almost no edits.
"""
import hashlib
import hmac
import os
import time
from datetime import datetime, timedelta

import pandas as pd
import pytz
import streamlit as st
from supabase import create_client

USERS_TABLE = "app_users"
ADDIS_ABABA_TZ = pytz.timezone("Africa/Addis_Ababa")

# ------------------------------------------------------------------ modules
MODULES = {                       # key -> display name
    "stock": "Stock Management",
    "supply": "Supply Planning",
    "forecasting": "Forecasting",
}
MODULE_ICONS = {"stock": "📦", "supply": "🗂️", "forecasting": "📈"}
ROLES = ["viewer", "editor", "admin"]

# ------------------------------------------------------------------ helpers
def get_current_time():
    return datetime.now(ADDIS_ABABA_TZ)


def _iso():
    return get_current_time().isoformat()


def format_time_for_display(dt):
    if dt is None or (not isinstance(dt, str) and pd.isna(dt)):
        return "Never"
    if isinstance(dt, str):
        if dt in ("None", ""):
            return "Never"
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return dt
    if hasattr(dt, "tzinfo"):
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt).astimezone(ADDIS_ABABA_TZ)
        else:
            dt = dt.astimezone(ADDIS_ABABA_TZ)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return str(dt)


@st.cache_resource
def init_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


def get_supabase():
    try:
        return init_supabase()
    except Exception as e:  # pragma: no cover
        st.error(f"Database connection error: {e}")
        return None


def normalize_email(email):
    return (email or "").strip().lower()


def _split(csv):
    return [p.strip() for p in (csv or "").split(",") if p.strip()]


# ---------------------------------------------------------------- passwords
# New passwords use salted PBKDF2.  Old unsalted SHA-256 hashes (both legacy
# apps used them) still verify, and are upgraded silently on the next login.
_ITERS = 200_000


def hash_password(password):
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERS).hex()
    return f"pbkdf2${_ITERS}${salt}${dk}"


def verify_password(password, stored):
    if not stored:
        return False
    if stored.startswith("pbkdf2$"):
        try:
            _, iters, salt, dk = stored.split("$")
            calc = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters)).hex()
            return hmac.compare_digest(calc, dk)
        except Exception:
            return False
    return hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), stored)


def _is_legacy_hash(stored):
    return bool(stored) and not stored.startswith("pbkdf2$")


# -------------------------------------------------------------- module logic
def user_modules(user):
    """List of module keys the user may open (admins: all)."""
    if not user:
        return []
    if user.get("role") == "admin":
        return list(MODULES)
    return [m for m in _split(user.get("module_access")) if m in MODULES]


def has_module(user, module):
    return module in user_modules(user)


def apply_module_context(user, module):
    """
    Copy the per-module restrictions into the keys each legacy app reads:
      Stock Management -> program_access, main_tab_access
      Supply/Forecasting -> program_access, tab_access
    The two apps treat an EMPTY program_access differently (Stock: = all programs,
    Supply: = none), so each module keeps its own column and its own default.
    """
    if not user:
        return user
    if module == "stock":
        user["program_access"] = user.get("stock_program_access") or "All"
        user["main_tab_access"] = user.get("stock_tab_access") or "All"
    else:
        user["program_access"] = user.get("supply_program_access") or ""
        user["tab_access"] = user.get("supply_tab_access") or "All"
    return user


def set_active_module(module):
    st.session_state["active_module"] = module
    if st.session_state.get("user"):
        apply_module_context(st.session_state["user"], module)


_HIDDEN = ("password_hash", "legacy_password_hash")


def build_user(row, module=None):
    user = {k: v for k, v in row.items() if k not in _HIDDEN}
    user["email"] = normalize_email(user.get("email"))
    user["full_name"] = user.get("full_name") or user["email"].split("@")[0]
    user["modules"] = user_modules(user)
    apply_module_context(user, module or st.session_state.get("active_module") or "stock")
    return user


# ------------------------------------------------------------------ queries
def _get_row_by_email(email):
    sb = get_supabase()
    if sb is None:
        return None
    r = sb.table(USERS_TABLE).select("*").eq("email", normalize_email(email)).execute()
    return r.data[0] if r.data else None


def get_user_row(user_id):
    sb = get_supabase()
    if sb is None:
        return None
    r = sb.table(USERS_TABLE).select("*").eq("id", user_id).execute()
    return r.data[0] if r.data else None


def _update(user_id, fields):
    sb = get_supabase()
    if sb is None:
        return False
    try:
        fields = dict(fields, updated_at=_iso())
        sb.table(USERS_TABLE).update(fields).eq("id", user_id).execute()
        return True
    except Exception as e:
        st.error(f"Update failed: {e}")
        return False


# --------------------------------------------------------------- login/signup
def authenticate_user(email, password):
    """Returns user dict, None (bad credentials) or {'error': code}.
    codes: not_approved | inactive | reset_pending | no_modules"""
    try:
        row = _get_row_by_email(email)
        if not row:
            return None
        ok = verify_password(password, row.get("password_hash"))
        used_alt = False
        if not ok and row.get("legacy_password_hash"):
            ok = used_alt = verify_password(password, row["legacy_password_hash"])
        if not ok:
            return None
        if not row.get("is_approved"):
            return {"error": "not_approved"}
        if row.get("is_active") is False:
            return {"error": "inactive"}
        if row.get("password_reset_requested") and not row.get("password_reset_approved"):
            return {"error": "reset_pending"}
        if not user_modules(row):
            return {"error": "no_modules"}
        fields = {"last_login": _iso(), "last_active": _iso()}
        if _is_legacy_hash(row.get("password_hash")) or used_alt:
            fields.update(password_hash=hash_password(password), legacy_password_hash=None)
        _update(row["id"], fields)
        return build_user(row)
    except Exception as e:
        st.error(f"Authentication error: {e}")
        return None


def create_user(email, password, full_name, role="viewer", approved=False, modules=None):
    sb = get_supabase()
    if sb is None:
        return False, "Database connection error"
    try:
        email = normalize_email(email)
        if _get_row_by_email(email):
            return False, "Email already exists. Please use a different email."
        now = _iso()
        sb.table(USERS_TABLE).insert({
            "email": email, "full_name": full_name, "password_hash": hash_password(password),
            "role": role if role in ROLES else "viewer",
            "is_approved": bool(approved), "is_active": True,
            "module_access": ",".join(m for m in (modules or []) if m in MODULES),
            "created_at": now, "last_active": now, "updated_at": now,
        }).execute()
        if approved:
            return True, "User created."
        return True, "Registration successful! Your account is pending admin approval."
    except Exception as e:
        return False, f"Registration failed: {e}"


def change_password(user_id, old_password, new_password):
    try:
        row = get_user_row(user_id)
        if not row or not (verify_password(old_password, row.get("password_hash"))
                           or verify_password(old_password, row.get("legacy_password_hash"))):
            return False, "Current password is incorrect"
        if not _update(user_id, {"password_hash": hash_password(new_password), "legacy_password_hash": None}):
            return False, "Failed to change password"
        return True, "Password changed successfully! Please login again."
    except Exception as e:
        return False, f"Failed to change password: {e}"


def update_user_profile(user_id, full_name=None):
    if not full_name or not full_name.strip():
        return False, "Name cannot be empty."
    if _update(user_id, {"full_name": full_name.strip()}):
        return True, "Profile updated successfully."
    return False, "Failed to update profile."


# ------------------------------------------------------------ password reset
def request_password_reset(email):
    try:
        row = _get_row_by_email(email)
        generic = "If your email exists, a reset request has been submitted to the admin."
        if not row:
            return True, generic
        if row.get("password_reset_requested") and not row.get("password_reset_approved"):
            return True, "You already have a pending reset request. Please wait for admin approval."
        _update(row["id"], {"password_reset_requested": True, "password_reset_approved": False,
                            "password_reset_requested_at": _iso(), "password_reset_approved_at": None})
        return True, "Your password reset request has been submitted. Please wait for admin approval."
    except Exception as e:
        return False, f"Failed to submit request: {e}"


def get_password_reset_requests():
    sb = get_supabase()
    if sb is None:
        return []
    try:
        r = sb.table(USERS_TABLE).select(
            "id, email, full_name, password_reset_requested, password_reset_approved, "
            "password_reset_requested_at, password_reset_approved_at"
        ).eq("password_reset_requested", True).order("password_reset_requested_at", desc=False).execute()
        return r.data or []
    except Exception as e:
        st.error(f"Error getting password reset requests: {e}")
        return []


def approve_password_reset(user_id):
    return _update(user_id, {"password_reset_approved": True, "password_reset_approved_at": _iso()})


def reject_password_reset(user_id):
    return _update(user_id, {"password_reset_requested": False, "password_reset_approved": False,
                             "password_reset_requested_at": None, "password_reset_approved_at": None})


def has_approved_password_reset(user_id):
    row = get_user_row(user_id)
    return bool(row) and bool(row.get("password_reset_requested")) and bool(row.get("password_reset_approved"))


def complete_password_reset(user_id, new_password):
    ok = _update(user_id, {"password_hash": hash_password(new_password), "legacy_password_hash": None,
                           "password_reset_requested": False, "password_reset_approved": False,
                           "password_reset_requested_at": None, "password_reset_approved_at": None})
    if ok:
        return True, "Password reset successfully! Please login with your new password."
    return False, "Failed to reset password."


# ------------------------------------------------------------- admin queries
def get_all_users_list():
    sb = get_supabase()
    if sb is None:
        return []
    try:
        r = sb.table(USERS_TABLE).select("*").order("created_at", desc=True).execute()
        return [{k: v for k, v in u.items() if k not in _HIDDEN} for u in (r.data or [])]
    except Exception as e:
        st.error(f"Error loading users: {e}")
        return []


def get_all_users_df():
    users = get_all_users_list()
    return pd.DataFrame(users) if users else pd.DataFrame()


def get_pending_users():
    """DataFrame of users awaiting approval (dashboard admin UI expects a DataFrame)."""
    df = get_all_users_df()
    if df.empty:
        return df
    return df[~df["is_approved"].astype(bool)].sort_values("created_at").reset_index(drop=True)


def get_pending_users_list():
    return [u for u in get_all_users_list() if not u.get("is_approved")]


def approve_user(user_id, modules=None, role=None):
    fields = {"is_approved": True, "is_active": True}
    if modules is not None:
        fields["module_access"] = ",".join(m for m in modules if m in MODULES)
    if role in ROLES:
        fields["role"] = role
    return _update(user_id, fields)


def reject_user(user_id):
    sb = get_supabase()
    try:
        sb.table(USERS_TABLE).delete().eq("id", user_id).execute()
        return True
    except Exception:
        return False


def delete_user(user_id):
    try:
        row = get_user_row(user_id)
        if not row:
            return False, f"User with ID {user_id} not found"
        get_supabase().table(USERS_TABLE).delete().eq("id", user_id).execute()
        return True, f"User {row.get('full_name') or row.get('email')} deleted successfully"
    except Exception as e:
        return False, str(e)


def update_user_role(user_id, role):
    return role in ROLES and _update(user_id, {"role": role})


def toggle_user_active(user_id, is_active):
    return _update(user_id, {"is_active": bool(is_active)})


def get_user_modules(user_id):
    row = get_user_row(user_id)
    return [m for m in _split(row.get("module_access")) if m in MODULES] if row else []


def update_user_modules(user_id, modules):
    return _update(user_id, {"module_access": ",".join(m for m in modules if m in MODULES)})


def _col(module, kind):  # kind: program | tab
    return f"{'stock' if module == 'stock' else 'supply'}_{kind}_access"


def get_module_access(user_id, module, kind):
    row = get_user_row(user_id)
    raw = (row or {}).get(_col(module, kind)) or ""
    return [] if raw.strip() == "" else _split(raw)


def update_module_access(user_id, module, kind, values):
    values = [str(v).strip() for v in (values or []) if str(v).strip()]
    if kind == "tab" and (not values or "All" in values):
        text = "All"
    elif kind == "program" and module == "stock" and (not values or "All" in values):
        text = "All"
    else:
        text = ", ".join(values)
    return _update(user_id, {_col(module, kind): text})


def add_user_by_admin(email, full_name, password, role, modules, approved=True):
    return create_user(email, password, full_name, role=role, approved=approved, modules=modules)


# ---------------------------------------------------------- activity/sessions
def update_user_session(user_id, session_id=""):
    try:
        get_supabase().table(USERS_TABLE).update({"last_active": _iso()}).eq("id", user_id).execute()
        return True
    except Exception:
        return False


def get_online_users():
    try:
        cutoff = (get_current_time() - timedelta(minutes=5)).isoformat()
        r = get_supabase().table(USERS_TABLE) \
            .select("id, email, full_name, role, last_active, created_at") \
            .eq("is_approved", True).gt("last_active", cutoff).execute()
        users = sorted(r.data or [], key=lambda x: x.get("last_active") or "", reverse=True)
        for u in users:
            u["last_active_display"] = format_time_for_display(u.get("last_active")) if u.get("last_active") else "Unknown"
        return users
    except Exception as e:
        print(f"Error getting online users: {e}")
        return []


# ---------------------------------------------------------------- session mgmt
def logout():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()


def refresh_user_access(user_id=None):
    """Re-read the user's row so admin changes apply live. Logs out revoked users."""
    user = st.session_state.get("user")
    if not user:
        return
    try:
        row = get_user_row(user_id or user["id"])
    except Exception:
        return                                  # DB hiccup: keep the session as is
    if (row is None or not row.get("is_approved") or row.get("is_active") is False
            or not user_modules(row)):
        st.session_state["auth"] = False
        st.session_state["user"] = None
        st.session_state["access_revoked"] = True
        return
    st.session_state["user"] = build_user(row, st.session_state.get("active_module"))


def refresh_current_user():
    refresh_user_access()
    return st.session_state.get("user")


def check_session_validity():
    """Heartbeat every 30s: last_active + re-sync access."""
    if st.session_state.get("auth") and st.session_state.get("user"):
        now = get_current_time()
        if (now - st.session_state.get("last_activity", now)).seconds >= 30:
            update_user_session(st.session_state["user"]["id"], st.session_state.get("session_id", ""))
            refresh_user_access()
            st.session_state["last_activity"] = now


# ----------------------------------------- legacy sup_outh-style session helpers
def get_current_user():
    return st.session_state.get("user")


def get_user_role():
    u = get_current_user()
    return u.get("role", "viewer") if u else None


def is_admin():
    return get_user_role() == "admin"


def is_editor():
    return get_user_role() in ("editor", "admin")


def get_user_program_access():
    u = get_current_user()
    return _split(u.get("program_access")) if u else []


def check_program_access(program_name):
    if is_admin():
        return True
    progs = get_user_program_access()
    return bool(progs) and ("All" in progs or program_name in progs)


def get_user_tab_access():
    u = get_current_user()
    if not u:
        return ["All"]
    access = u.get("tab_access", "All")
    return ["All"] if (access == "All" or not access) else _split(access)
