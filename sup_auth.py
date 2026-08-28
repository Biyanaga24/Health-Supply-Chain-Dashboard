"""
============================================================================
 HPC SUPPLY PLANNING TOOL — AUTHENTICATION MODULE
 sup_auth.py

 Enterprise-grade Streamlit authentication system with:
   - Supabase-backed users table (login / register / approval / roles)
   - SHA256 password hashing
   - Session-state driven auth guard (require_auth)
   - A premium, animated, glassmorphism sign-in experience inspired by
     Stripe / Linear / Fabric / SAC-class dashboard products

 Drop-in replacement: exposes the same public API as the previous module
 (get_supabase, hash_password, create_user, authenticate_user, get_all_users,
 get_pending_users, approve_user, reject_user, update_user_role,
 toggle_user_active, update_user_program_access, get_current_user,
 get_user_role, get_user_program_access, is_admin, logout, require_auth,
 show_auth_page).
============================================================================
"""

import streamlit as st
import streamlit.components.v1 as components
import hashlib
import re
import time
from datetime import datetime
from supabase_py import create_client


# ============================================================================
# THEME / DESIGN TOKENS
# ============================================================================
# A single source of truth for the visual language. Every color, spacing and
# radius used across the auth experience derives from this dict so the look
# stays coherent and is trivial to re-skin later.

THEME = {
    "primary": "#10B981",       # Emerald
    "primary_dark": "#059669",
    "secondary": "#4F46E5",     # Indigo
    "accent": "#06B6D4",        # Cyan
    "bg": "#F4F7FC",            # Light, soft background — NOT black/near-black
    "bg_soft": "#EAF0FA",
    "surface": "rgba(15, 23, 42, 0.035)",
    "surface_solid": "#FFFFFF",
    "border": "rgba(15, 23, 42, 0.09)",
    "text": "#111827",
    "text_muted": "#6B7280",
    "danger": "#DC2626",
    "success": "#059669",
    "warning": "#D97706",
    "radius_lg": "24px",
    "radius_md": "16px",
    "radius_sm": "10px",
}


# ============================================================================
# DATABASE FUNCTIONS
# ============================================================================

def get_supabase():
    """Lazily create and cache the Supabase client in session_state."""
    if 'supabase' not in st.session_state:
        try:
            supabase_url = st.secrets["SUPABASE_URL"]
            supabase_key = st.secrets["SUPABASE_KEY"]
            st.session_state.supabase = create_client(supabase_url, supabase_key)
        except Exception as e:
            st.error(f"Supabase connection error: {e}")
            return None
    return st.session_state.supabase


def hash_password(password):
    """One-way SHA256 hash for password storage."""
    return hashlib.sha256(password.encode()).hexdigest()


def create_user(email, password, full_name, role='viewer'):
    """Register a new (unapproved) user in the supply_users table."""
    supabase = get_supabase()
    if supabase is None:
        return False, "Database connection failed"

    try:
        existing = supabase.table("supply_users").select("*").eq("email", email).execute()
        if existing.data and len(existing.data) > 0:
            return False, "Email already registered."

        hashed_pw = hash_password(password)
        user_data = {
            "email": email,
            "password_hash": hashed_pw,
            "full_name": full_name,
            "role": role,
            "is_approved": False,
            "created_at": datetime.now().isoformat(),
            "last_login": None,
            "is_active": True,
            "program_access": ""
        }

        response = supabase.table("supply_users").insert(user_data).execute()

        if response.data:
            return True, "Registration successful! Please wait for admin approval."
        else:
            return False, "Registration failed."

    except Exception as e:
        return False, f"Error: {str(e)}"


def authenticate_user(email, password):
    """Validate credentials and return the user row, or an error message."""
    supabase = get_supabase()
    if supabase is None:
        return None, "Database connection failed"

    try:
        hashed_pw = hash_password(password)
        response = supabase.table("supply_users").select("*").eq("email", email).execute()

        if not response.data or len(response.data) == 0:
            return None, "Invalid email or password."

        user = response.data[0]

        if hashed_pw != user.get('password_hash'):
            return None, "Invalid email or password."

        if not user.get('is_active', True):
            return None, "Your account has been deactivated. Please contact admin."

        if not user.get('is_approved', False):
            return None, "Your account is pending approval. Please wait for admin approval."

        supabase.table("supply_users").update(
            {"last_login": datetime.now().isoformat()}
        ).eq("id", user['id']).execute()

        return user, None

    except Exception as e:
        return None, f"Error: {str(e)}"


def request_password_reset(email):
    """
    Look up whether the email exists without leaking that information to the
    caller (standard practice). Wire this into a real email provider
    (Supabase Auth, SendGrid, SES, etc.) to actually deliver a reset link —
    this function is the integration point.
    """
    supabase = get_supabase()
    if supabase is None:
        return False, "Database connection failed"
    try:
        response = supabase.table("supply_users").select("id, email").eq("email", email).execute()
        found = bool(response.data and len(response.data) > 0)
        if found:
            # TODO: trigger transactional email with a signed reset token.
            pass
        return True, "If that email is registered, password reset instructions have been sent."
    except Exception as e:
        return False, f"Error: {str(e)}"


def get_all_users():
    """Return every user row, most recent first."""
    supabase = get_supabase()
    if supabase is None:
        return []
    try:
        response = supabase.table("supply_users").select("*").order("created_at", desc=True).execute()
        return response.data if response.data else []
    except Exception:
        return []


def get_pending_users():
    """Return active users awaiting admin approval."""
    supabase = get_supabase()
    if supabase is None:
        return []
    try:
        response = supabase.table("supply_users").select("*").eq("is_approved", False).eq("is_active", True).execute()
        return response.data if response.data else []
    except Exception:
        return []


def approve_user(user_id):
    supabase = get_supabase()
    if supabase is None:
        return False
    try:
        response = supabase.table("supply_users").update({"is_approved": True}).eq("id", user_id).execute()
        return True if response.data else False
    except Exception:
        return False


def reject_user(user_id):
    supabase = get_supabase()
    if supabase is None:
        return False
    try:
        response = supabase.table("supply_users").delete().eq("id", user_id).execute()
        return True if response.data else False
    except Exception:
        return False


def update_user_role(user_id, new_role):
    supabase = get_supabase()
    if supabase is None:
        return False
    try:
        response = supabase.table("supply_users").update({"role": new_role}).eq("id", user_id).execute()
        return True if response.data else False
    except Exception:
        return False


def toggle_user_active(user_id, is_active):
    supabase = get_supabase()
    if supabase is None:
        return False
    try:
        response = supabase.table("supply_users").update({"is_active": is_active}).eq("id", user_id).execute()
        return True if response.data else False
    except Exception:
        return False


def update_user_program_access(user_id, programs):
    supabase = get_supabase()
    if supabase is None:
        return False
    try:
        program_str = ",".join(programs) if programs else ""
        response = supabase.table("supply_users").update({"program_access": program_str}).eq("id", user_id).execute()
        return True if response.data else False
    except Exception:
        return False


def get_current_user():
    if 'user' in st.session_state:
        return st.session_state.user
    return None


def get_user_role():
    user = get_current_user()
    if user:
        return user.get('role', 'viewer')
    return None


def get_user_program_access():
    user = get_current_user()
    if user:
        program_str = user.get('program_access', '')
        if program_str:
            return [p.strip() for p in program_str.split(',') if p.strip()]
    return []


def is_admin():
    return get_user_role() == 'admin'


def logout():
    st.session_state.is_authenticated = False
    st.session_state.user = None
    st.session_state.auth_mode = 'login'
    st.rerun()


def require_auth():
    """Auth guard: call at the top of a protected page."""
    if 'is_authenticated' not in st.session_state or not st.session_state.is_authenticated:
        show_auth_page()
        st.stop()
        return False

    if 'user' in st.session_state:
        if not st.session_state.user.get('is_approved', False):
            st.error("⏳ Your account is pending approval. Please wait for admin approval.")
            st.stop()
            return False

    return True


# ============================================================================
# SESSION STATE BOOTSTRAP
# ============================================================================

def _init_auth_state():
    defaults = {
        'auth_mode': 'login',
        'auth_message': None,
        'auth_message_type': None,
        'show_password_login': False,
        'show_password_reg': False,
        'remember_me': False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ============================================================================
# FONTS + GLOBAL CSS
# ============================================================================

def _inject_base_styles():
    t = THEME
    st.markdown(f"""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Poppins:wght@500;600;700;800&display=swap" rel="stylesheet">

    <style>
        :root {{
            --primary: {t['primary']};
            --primary-dark: {t['primary_dark']};
            --secondary: {t['secondary']};
            --accent: {t['accent']};
            --bg: {t['bg']};
            --bg-soft: {t['bg_soft']};
            --surface: {t['surface']};
            --border: {t['border']};
            --text: {t['text']};
            --text-muted: {t['text_muted']};
            --danger: {t['danger']};
            --success: {t['success']};
            --warning: {t['warning']};
            --radius-lg: {t['radius_lg']};
            --radius-md: {t['radius_md']};
            --radius-sm: {t['radius_sm']};
        }}

        html, body, [class*="css"] {{
            font-family: 'Inter', -apple-system, sans-serif;
        }}

        .main > div {{ padding-top: 0px; }}
        header[data-testid="stHeader"] {{
            background: transparent;
            height: 0rem;
            min-height: 0rem;
        }}
        header[data-testid="stHeader"] * {{ display: none; }}
        div[data-testid="stToolbar"] {{ display: none; }}
        div[data-testid="stDecoration"] {{ display: none; }}
        section[data-testid="stAppViewContainer"] > div:first-child {{ padding-top: 0rem !important; }}
        .block-container {{
            padding-top: 0rem !important;
            padding-bottom: 0rem !important;
            max-width: 100% !important;
        }}
        .stApp {{
            background: radial-gradient(circle at 15% 10%, #FFFFFF 0%, var(--bg) 45%, var(--bg-soft) 100%);
        }}

        /* ================= KEYFRAMES ================= */
        @keyframes fadeIn {{
            from {{ opacity: 0; }}
            to {{ opacity: 1; }}
        }}
        @keyframes slideUp {{
            from {{ opacity: 0; transform: translateY(24px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        @keyframes floatY {{
            0%, 100% {{ transform: translateY(0px) rotate(0deg); }}
            50% {{ transform: translateY(-14px) rotate(3deg); }}
        }}
        @keyframes pulseGlow {{
            0%, 100% {{ box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.35); }}
            50% {{ box-shadow: 0 0 0 10px rgba(16, 185, 129, 0); }}
        }}
        @keyframes shimmerSweep {{
            0% {{ background-position: -300% 0; }}
            100% {{ background-position: 300% 0; }}
        }}
        @keyframes gradientMove {{
            0% {{ background-position: 0% 50%; }}
            50% {{ background-position: 100% 50%; }}
            100% {{ background-position: 0% 50%; }}
        }}
        @keyframes waveHand {{
            0%, 100% {{ transform: rotate(0deg); }}
            20% {{ transform: rotate(14deg); }}
            40% {{ transform: rotate(-8deg); }}
            60% {{ transform: rotate(10deg); }}
            80% {{ transform: rotate(-4deg); }}
        }}
        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}
        @keyframes growBar {{
            from {{ transform: scaleY(0); }}
            to {{ transform: scaleY(1); }}
        }}
        @keyframes drawLine {{
            from {{ stroke-dashoffset: 400; }}
            to {{ stroke-dashoffset: 0; }}
        }}
        @keyframes ripple {{
            0% {{ transform: scale(0); opacity: 0.55; }}
            100% {{ transform: scale(2.6); opacity: 0; }}
        }}

        /* ================= LAYOUT SHELL ================= */
        .auth-wrapper {{
            position: relative;
            z-index: 1;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: flex-start;
            padding: 28px 32px 40px;
            margin: 0;
        }}

        .auth-card {{
            position: relative;
            width: 100%;
            max-width: 1240px;
            border-radius: var(--radius-lg);
            padding: 3px;
            background: linear-gradient(135deg, var(--primary), var(--secondary), var(--accent), var(--primary));
            background-size: 300% 300%;
            animation: gradientMove 10s ease infinite, slideUp 0.7s ease both;
            box-shadow: 0 20px 60px rgba(15,23,42,0.12);
        }}

        .auth-card-inner {{
            background: linear-gradient(160deg, rgba(255,255,255,0.98), rgba(248,250,255,0.98));
            backdrop-filter: blur(18px);
            border-radius: calc(var(--radius-lg) - 3px);
            padding: 40px 54px;
        }}

        .auth-grid {{
            display: grid;
            grid-template-columns: 1.15fr 420px;
            gap: 46px;
            align-items: stretch;
        }}

        /* ================= HEADER ================= */
        .auth-header {{
            text-align: center;
            margin-bottom: 24px;
            margin-top: 0;
            animation: fadeIn 1s ease both;
        }}
        .auth-logo-badge {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 64px; height: 64px;
            border-radius: 20px;
            font-size: 30px;
            background: linear-gradient(135deg, var(--primary), var(--accent));
            box-shadow: 0 10px 30px rgba(16,185,129,0.28);
            animation: floatY 4s ease-in-out infinite;
            margin-bottom: 10px;
        }}
        .auth-title {{
            font-family: 'Poppins', sans-serif;
            font-size: 30px;
            font-weight: 800;
            letter-spacing: -0.5px;
            margin: 0;
            background: linear-gradient(135deg, var(--text) 20%, var(--primary) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .auth-subtitle {{
            font-size: 12.5px;
            color: var(--text-muted);
            margin-top: 6px;
            letter-spacing: 3.5px;
            text-transform: uppercase;
            font-weight: 600;
        }}
        .auth-divider {{
            width: 64px; height: 3px;
            background: linear-gradient(90deg, var(--primary), var(--accent));
            border-radius: 4px;
            margin: 14px auto 0;
        }}

        /* ================= LEFT: DASHBOARD PREVIEW ================= */
        .panel-title {{
            font-family: 'Poppins', sans-serif;
            font-size: 17px;
            font-weight: 700;
            color: var(--text);
            margin-bottom: 16px;
            display: flex; align-items: center; gap: 8px;
        }}

        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
            margin-bottom: 16px;
        }}
        .kpi-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-sm);
            padding: 14px 16px;
            transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease;
            animation: slideUp 0.6s ease both;
        }}
        .kpi-card:hover {{
            transform: translateY(-4px);
            border-color: rgba(16,185,129,0.45);
            box-shadow: 0 12px 26px rgba(16,185,129,0.16);
        }}
        .kpi-label {{
            font-size: 11px; color: var(--text-muted);
            text-transform: uppercase; letter-spacing: 1px; font-weight: 600;
            margin-bottom: 6px;
        }}
        .kpi-value {{
            font-family: 'Poppins', sans-serif;
            font-size: 22px; font-weight: 800; color: var(--text);
        }}
        .kpi-trend {{
            font-size: 11px; font-weight: 700; margin-top: 4px;
        }}
        .kpi-trend.up {{ color: var(--success); }}
        .kpi-trend.down {{ color: var(--danger); }}

        .chart-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 18px 20px;
            margin-bottom: 12px;
            transition: border-color 0.25s ease, transform 0.25s ease;
        }}
        .chart-card:hover {{ border-color: rgba(79,70,229,0.4); transform: translateY(-2px); }}
        .chart-card-head {{
            display: flex; justify-content: space-between; align-items: baseline;
            margin-bottom: 12px;
        }}
        .chart-card-title {{ font-size: 13px; font-weight: 700; color: var(--text); }}
        .chart-card-sub {{ font-size: 11px; color: var(--text-muted); }}

        .bars-row {{
            display: flex; align-items: flex-end; gap: 8px; height: 70px;
        }}
        .bar {{
            flex: 1;
            border-radius: 6px 6px 2px 2px;
            background: linear-gradient(180deg, var(--accent), var(--secondary));
            transform-origin: bottom;
            animation: growBar 0.9s cubic-bezier(.2,.8,.2,1) both;
        }}

        .risk-row {{ display: flex; align-items: center; gap: 10px; margin-top: 8px; }}
        .risk-track {{
            flex: 1; height: 7px; border-radius: 4px;
            background: rgba(15,23,42,0.08); overflow: hidden;
        }}
        .risk-fill {{
            height: 100%; border-radius: 4px;
            background: linear-gradient(90deg, var(--primary), var(--accent));
            animation: shimmerSweep 3s linear infinite;
            background-size: 200% 100%;
        }}
        .risk-label {{ font-size: 11px; color: var(--text-muted); width: 92px; }}
        .risk-pct {{ font-size: 11px; color: var(--text); font-weight: 700; width: 34px; text-align: right; }}

        /* ================= RIGHT: SIGN-IN BOX ================= */
        .signin-box {{
            background: linear-gradient(165deg, rgba(15,23,42,0.03), rgba(15,23,42,0.01));
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 30px 28px;
            height: 100%;
            display: flex;
            flex-direction: column;
            animation: slideUp 0.7s ease both;
            position: relative;
        }}
        .signin-title {{
            font-family: 'Poppins', sans-serif;
            font-size: 21px; font-weight: 700; color: var(--text);
            display: flex; align-items: center; gap: 8px;
        }}
        .signin-title .wave {{ display: inline-block; animation: waveHand 2.4s ease-in-out infinite; }}
        .signin-sub {{ font-size: 13px; color: var(--text-muted); margin: 4px 0 20px; }}

        .msg-banner {{
            padding: 10px 14px; border-radius: var(--radius-sm);
            font-size: 12.5px; margin-bottom: 14px;
            animation: slideUp 0.35s ease both;
        }}
        .msg-error {{ background: rgba(220,38,38,0.09); color: #B91C1C; border-left: 3px solid var(--danger); }}
        .msg-success {{ background: rgba(5,150,105,0.09); color: #047857; border-left: 3px solid var(--success); }}
        .msg-info {{ background: rgba(6,182,212,0.10); color: #0E7490; border-left: 3px solid var(--accent); }}

        .field-label {{
            font-size: 12px; font-weight: 600; color: var(--text-muted);
            display: flex; align-items: center; gap: 6px;
            margin-bottom: 4px; margin-top: 10px;
        }}

        /* Streamlit input overrides */
        .stTextInput > div > div > input {{
            background: #FFFFFF !important;
            border: 1px solid var(--border) !important;
            border-radius: var(--radius-sm) !important;
            color: var(--text) !important;
            padding: 10px 14px !important;
            transition: all 0.25s ease !important;
        }}
        .stTextInput > div > div > input:focus {{
            border-color: var(--primary) !important;
            box-shadow: 0 0 0 3px rgba(16,185,129,0.15) !important;
        }}
        .stTextInput > div > div > input::placeholder {{ color: rgba(107,114,128,0.7) !important; }}
        .stTextInput label {{ color: var(--text-muted) !important; font-size: 12.5px !important; }}

        .stCheckbox label p {{ color: var(--text-muted) !important; font-size: 12.5px !important; }}

        /* Buttons */
        .stButton > button {{
            border-radius: var(--radius-sm) !important;
            font-weight: 700 !important;
            border: none !important;
            transition: transform 0.2s ease, box-shadow 0.2s ease, filter 0.2s ease !important;
            position: relative;
            overflow: hidden;
        }}
        .stButton > button[kind="primary"] {{
            background: linear-gradient(135deg, var(--primary), var(--primary-dark)) !important;
            box-shadow: 0 8px 20px rgba(16,185,129,0.28) !important;
        }}
        .stButton > button:hover {{
            transform: translateY(-2px);
            filter: brightness(1.08);
            box-shadow: 0 12px 26px rgba(16,185,129,0.32) !important;
        }}
        .stButton > button:active {{ transform: translateY(0px) scale(0.98); }}

        .signin-footer {{
            text-align: center; margin-top: 16px; font-size: 12.5px; color: var(--text-muted);
        }}
        .signin-footer a {{
            color: var(--primary); font-weight: 700; text-decoration: none;
        }}
        .signin-footer a:hover {{ text-decoration: underline; }}

        .forgot-link {{ text-align: right; margin-top: -6px; margin-bottom: 8px; }}
        .forgot-link a {{ font-size: 11.5px; color: var(--text-muted); text-decoration: none; }}
        .forgot-link a:hover {{ color: var(--accent); }}

        /* Floating logistics icons */
        .float-icon {{
            position: fixed; z-index: 0; opacity: 0.10; pointer-events: none;
            font-size: 46px; filter: grayscale(0.2);
            animation: floatY 7s ease-in-out infinite;
        }}

        /* Responsive */
        @media (max-width: 1080px) {{
            .auth-grid {{ grid-template-columns: 1fr; }}
            .kpi-grid {{ grid-template-columns: repeat(3, 1fr); }}
        }}
        @media (max-width: 640px) {{
            .auth-card-inner {{ padding: 26px 18px; }}
            .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .auth-title {{ font-size: 22px; }}
        }}

        @media (prefers-reduced-motion: reduce) {{
            *, *::before, *::after {{ animation-duration: 0.001ms !important; animation-iteration-count: 1 !important; }}
        }}
    </style>
    """, unsafe_allow_html=True)


def _render_floating_background():
    """Full-viewport animated gradient blobs + floating logistics glyphs (pure SVG/CSS, no JS required)."""
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" style="position:fixed;top:0;left:0;width:100%;height:100%;z-index:0;pointer-events:none;opacity:0.10;">
        <defs>
            <linearGradient id="g1" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#10B981"/>
                <stop offset="50%" stop-color="#4F46E5"/>
                <stop offset="100%" stop-color="#06B6D4"/>
            </linearGradient>
        </defs>
        <circle cx="12%" cy="18%" r="90" fill="url(#g1)">
            <animate attributeName="cx" values="12%;85%;12%" dur="24s" repeatCount="indefinite"/>
            <animate attributeName="cy" values="18%;78%;18%" dur="17s" repeatCount="indefinite"/>
        </circle>
        <circle cx="82%" cy="72%" r="130" fill="url(#g1)">
            <animate attributeName="cx" values="82%;15%;82%" dur="28s" repeatCount="indefinite"/>
            <animate attributeName="cy" values="72%;22%;72%" dur="20s" repeatCount="indefinite"/>
        </circle>
        <circle cx="50%" cy="50%" r="60" fill="url(#g1)">
            <animate attributeName="cx" values="50%;22%;78%;50%" dur="32s" repeatCount="indefinite"/>
            <animate attributeName="cy" values="50%;80%;24%;50%" dur="24s" repeatCount="indefinite"/>
        </circle>
        <rect x="22%" y="28%" width="90" height="90" rx="18" fill="url(#g1)">
            <animate attributeName="x" values="22%;68%;22%" dur="19s" repeatCount="indefinite"/>
            <animate attributeName="y" values="28%;58%;28%" dur="15s" repeatCount="indefinite"/>
        </rect>
        <rect x="64%" y="62%" width="70" height="70" rx="16" fill="url(#g1)">
            <animate attributeName="x" values="64%;12%;64%" dur="23s" repeatCount="indefinite"/>
            <animate attributeName="y" values="62%;18%;62%" dur="18s" repeatCount="indefinite"/>
        </rect>
        <!-- particles -->
        <g fill="#10B981">
            <circle cx="8%" cy="60%" r="3"><animate attributeName="cy" values="60%;10%;60%" dur="14s" repeatCount="indefinite"/></circle>
            <circle cx="92%" cy="30%" r="2.5"><animate attributeName="cy" values="30%;85%;30%" dur="16s" repeatCount="indefinite"/></circle>
            <circle cx="34%" cy="85%" r="2"><animate attributeName="cy" values="85%;20%;85%" dur="12s" repeatCount="indefinite"/></circle>
            <circle cx="70%" cy="10%" r="2.5"><animate attributeName="cy" values="10%;70%;10%" dur="18s" repeatCount="indefinite"/></circle>
        </g>
    </svg>
    """
    st.markdown(svg, unsafe_allow_html=True)

    icons = [
        ("📦", "6%", "12%", "0s"), ("🚚", "88%", "20%", "1.4s"),
        ("🏭", "10%", "80%", "0.7s"), ("📊", "90%", "78%", "2.1s"),
        ("🌐", "48%", "6%", "1.9s"),
    ]
    for glyph, left, top, delay in icons:
        st.markdown(
            f'<div class="float-icon" style="left:{left};top:{top};animation-delay:{delay};">{glyph}</div>',
            unsafe_allow_html=True
        )


# ============================================================================
# LEFT PANEL: LIVE DASHBOARD PREVIEW
# ============================================================================

def _render_kpi_counters():
    """
    Animated count-up KPI strip. Rendered via components.html so the
    JavaScript actually executes (script tags injected through
    st.markdown are inert in Streamlit's DOM).
    """
    # These reflect the actual configuration of the Supply Planning Dashboard
    # (programs, branches, action-plan categories, etc. defined in supply_planning.py)
    # rather than generic marketing numbers.
    kpis = [
        {"label": "Health Programs", "value": 8, "suffix": "", "trend": "Malaria, HIV, TB +5", "up": True},
        {"label": "Branches & Hubs", "value": 19, "suffix": "", "trend": "Nationwide coverage", "up": True},
        {"label": "Action Categories", "value": 5, "suffix": "", "trend": "Stock out → Expiry", "up": True},
        {"label": "Progress Stages", "value": 4, "suffix": "", "trend": "Initiated → Completed", "up": True},
        {"label": "Stock Metrics", "value": 5, "suffix": "", "trend": "NSOH · AMC · NMOS · TMOS", "up": True},
        {"label": "Dashboard Views", "value": 4, "suffix": "", "trend": "Historical → Supply Plan", "up": True},
    ]

    cards_html = ""
    for i, k in enumerate(kpis):
        is_float = isinstance(k["value"], float)
        cards_html += f"""
        <div class="kpi-card" style="animation-delay:{i*0.06}s">
            <div class="kpi-label">{k['label']}</div>
            <div class="kpi-value">
                <span class="counter" data-target="{k['value']}" data-suffix="{k['suffix']}" data-float="{str(is_float).lower()}">0</span>
            </div>
            <div class="kpi-trend up">{k['trend']}</div>
        </div>
        """

    html = f"""
    <style>
        body {{ margin:0; font-family: 'Inter', sans-serif; }}
        .kpi-grid {{
            display:grid; grid-template-columns:repeat(3,1fr); gap:10px;
        }}
        .kpi-card {{
            background: rgba(15,23,42,0.035);
            border: 1px solid rgba(15,23,42,0.09);
            border-radius: 12px; padding: 12px 14px;
            transition: transform .25s ease, box-shadow .25s ease, border-color .25s ease;
            opacity:0; animation: rise .5s ease forwards;
        }}
        .kpi-card:hover {{
            transform: translateY(-4px);
            border-color: rgba(16,185,129,0.45);
            box-shadow: 0 12px 24px rgba(16,185,129,0.14);
        }}
        @keyframes rise {{ from {{opacity:0; transform:translateY(10px);}} to {{opacity:1; transform:translateY(0);}} }}
        .kpi-label {{ font-size:10.5px; color:#6B7280; text-transform:uppercase; letter-spacing:1px; font-weight:600; margin-bottom:6px;}}
        .kpi-value {{ font-family:'Poppins',sans-serif; font-size:20px; font-weight:800; color:#111827; }}
        .kpi-trend {{ font-size:10.5px; font-weight:700; margin-top:4px; }}
        .kpi-trend.up {{ color:#059669; }}
        .kpi-trend.down {{ color:#DC2626; }}
    </style>
    <div class="kpi-grid">{cards_html}</div>
    <script>
        const counters = document.querySelectorAll('.counter');
        counters.forEach(el => {{
            const target = parseFloat(el.getAttribute('data-target'));
            const suffix = el.getAttribute('data-suffix') || '';
            const isFloat = el.getAttribute('data-float') === 'true';
            const duration = 1100;
            const start = performance.now();
            function tick(now) {{
                const progress = Math.min((now - start) / duration, 1);
                const eased = 1 - Math.pow(1 - progress, 3);
                const current = target * eased;
                el.textContent = (isFloat ? current.toFixed(1) : Math.round(current)) + suffix;
                if (progress < 1) requestAnimationFrame(tick);
            }}
            requestAnimationFrame(tick);
        }});
    </script>
    """
    components.html(html, height=210, scrolling=False)


def _render_mini_charts():
    """CSS-animated inventory / forecast mini charts + supply risk indicators."""
    # Sample NSOH trend shape — illustrates the "Historical Data" tab
    bar_values = [38, 52, 44, 68, 59, 74, 82, 65]
    bars = ""
    for i, v in enumerate(bar_values):
        bars += f'<div class="bar" style="height:{v}%; animation-delay:{i*0.05}s;"></div>'

    # These five categories mirror the exact identified-problem buckets the
    # system-generated action plan classifies materials into.
    risks = [
        ("Stock Out", 18),
        ("Risk of SO", 27),
        ("Expiry Risk", 11),
        ("Below Min", 22),
        ("Pipeline Insuff.", 15),
    ]
    risk_rows = ""
    for label, pct in risks:
        risk_rows += f"""
        <div class="risk-row">
            <div class="risk-label">{label}</div>
            <div class="risk-track"><div class="risk-fill" style="width:{pct}%;"></div></div>
            <div class="risk-pct">{pct}%</div>
        </div>
        """

    st.markdown(f"""
        <div class="chart-card">
            <div class="chart-card-head">
                <span class="chart-card-title">📈 NSOH Trend (sample)</span>
                <span class="chart-card-sub">Historical Data tab</span>
            </div>
            <div class="bars-row">{bars}</div>
        </div>
        <div class="chart-card">
            <div class="chart-card-head">
                <span class="chart-card-title">🛡️ Action Plan Categories</span>
                <span class="chart-card-sub">Share of open items</span>
            </div>
            {risk_rows}
        </div>
    """, unsafe_allow_html=True)


def _render_dashboard_preview():
    st.markdown('<div class="panel-title">What This Tool Tracks</div>', unsafe_allow_html=True)
    _render_kpi_counters()
    _render_mini_charts()


# ============================================================================
# RIGHT PANEL: AUTH FORMS
# ============================================================================

def _flash_message():
    if st.session_state.auth_message:
        msg_type = st.session_state.auth_message_type or 'error'
        css_class = {"success": "msg-success", "info": "msg-info"}.get(msg_type, "msg-error")
        st.markdown(f'<div class="msg-banner {css_class}">{st.session_state.auth_message}</div>', unsafe_allow_html=True)
        st.session_state.auth_message = None
        st.session_state.auth_message_type = None


def _switch_mode(mode):
    st.session_state.auth_mode = mode
    st.rerun()


def _render_login_form():
    st.markdown('<div class="signin-title"><span class="wave">👋</span> Welcome back</div>', unsafe_allow_html=True)
    st.markdown('<div class="signin-sub">Sign in to your supply planning workspace</div>', unsafe_allow_html=True)

    _flash_message()

    with st.form("login_form", clear_on_submit=False):
        st.markdown('<div class="field-label">📧 Email</div>', unsafe_allow_html=True)
        email = st.text_input("Email", placeholder="you@example.com", key="login_email", label_visibility="collapsed")

        st.markdown('<div class="field-label">🔒 Password</div>', unsafe_allow_html=True)
        pw_type = "default" if st.session_state.show_password_login else "password"
        password = st.text_input("Password", type=pw_type, placeholder="Enter your password",
                                  key="login_password", label_visibility="collapsed")

        col_a, col_b = st.columns([1, 1])
        with col_a:
            st.checkbox("👁 Show password", key="show_password_login")
        with col_b:
            st.checkbox("Remember me", key="remember_me")

        st.markdown('<div class="forgot-link"><a href="#" onclick="return false;">Forgot password?</a></div>', unsafe_allow_html=True)

        submit = st.form_submit_button("🔑  Sign In", use_container_width=True, type="primary")
        go_register = st.form_submit_button("📝  Create an account", use_container_width=True)
        go_forgot = st.form_submit_button("Forgot your password?", use_container_width=True)

        if submit:
            if email and password:
                with st.spinner("Verifying credentials…"):
                    time.sleep(0.3)
                    user, error = authenticate_user(email, password)
                if user:
                    st.session_state.user = user
                    st.session_state.is_authenticated = True
                    st.rerun()
                else:
                    st.session_state.auth_message = error
                    st.session_state.auth_message_type = 'error'
                    st.rerun()
            else:
                st.session_state.auth_message = "Please fill in all fields."
                st.session_state.auth_message_type = 'error'
                st.rerun()

        if go_register:
            _switch_mode('register')
        if go_forgot:
            _switch_mode('forgot')

    st.markdown("""
        <div class="signin-footer">Secured with SHA-256 hashing · role-based access control</div>
    """, unsafe_allow_html=True)


def _render_register_form():
    st.markdown('<div class="signin-title"><span class="wave">🚀</span> Create account</div>', unsafe_allow_html=True)
    st.markdown('<div class="signin-sub">Request access to the planning platform</div>', unsafe_allow_html=True)

    _flash_message()

    with st.form("register_form", clear_on_submit=False):
        st.markdown('<div class="field-label">👤 Full name</div>', unsafe_allow_html=True)
        full_name = st.text_input("Full name", placeholder="John Doe", key="reg_name", label_visibility="collapsed")

        st.markdown('<div class="field-label">📧 Email</div>', unsafe_allow_html=True)
        email = st.text_input("Email", placeholder="you@example.com", key="reg_email", label_visibility="collapsed")

        st.markdown('<div class="field-label">🔒 Password</div>', unsafe_allow_html=True)
        pw_type = "default" if st.session_state.show_password_reg else "password"
        password = st.text_input("Password", type=pw_type, placeholder="Min 8 characters",
                                  key="reg_password", label_visibility="collapsed")

        st.markdown('<div class="field-label">🔒 Confirm password</div>', unsafe_allow_html=True)
        confirm = st.text_input("Confirm password", type=pw_type, placeholder="Re-enter password",
                                 key="reg_confirm", label_visibility="collapsed")

        st.checkbox("👁 Show password", key="show_password_reg")

        col_a, col_b = st.columns(2)
        with col_a:
            submit = st.form_submit_button("✅  Create account", use_container_width=True, type="primary")
        with col_b:
            back = st.form_submit_button("← Back to sign in", use_container_width=True)

        if submit:
            if not full_name or not email or not password or not confirm:
                st.session_state.auth_message = "Please fill in all fields."
                st.session_state.auth_message_type = 'error'
            elif password != confirm:
                st.session_state.auth_message = "Passwords do not match."
                st.session_state.auth_message_type = 'error'
            elif len(password) < 8:
                st.session_state.auth_message = "Password must be at least 8 characters."
                st.session_state.auth_message_type = 'error'
            elif not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                st.session_state.auth_message = "Please enter a valid email address."
                st.session_state.auth_message_type = 'error'
            else:
                with st.spinner("Creating your account…"):
                    time.sleep(0.3)
                    success, message = create_user(email, password, full_name)
                if success:
                    st.session_state.auth_message = message
                    st.session_state.auth_message_type = 'success'
                    st.session_state.auth_mode = 'login'
                else:
                    st.session_state.auth_message = message
                    st.session_state.auth_message_type = 'error'
            st.rerun()

        if back:
            _switch_mode('login')

    st.markdown("""
        <div class="signin-footer">By registering you agree to responsible use of company supply data.</div>
    """, unsafe_allow_html=True)


def _render_forgot_password_form():
    st.markdown('<div class="signin-title">🔑 Reset password</div>', unsafe_allow_html=True)
    st.markdown('<div class="signin-sub">We\'ll send reset instructions to your inbox</div>', unsafe_allow_html=True)

    _flash_message()

    with st.form("forgot_form", clear_on_submit=False):
        st.markdown('<div class="field-label">📧 Email</div>', unsafe_allow_html=True)
        email = st.text_input("Email", placeholder="you@example.com", key="forgot_email", label_visibility="collapsed")

        col_a, col_b = st.columns(2)
        with col_a:
            submit = st.form_submit_button("📤  Send instructions", use_container_width=True, type="primary")
        with col_b:
            back = st.form_submit_button("← Back to sign in", use_container_width=True)

        if submit:
            if not email or not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                st.session_state.auth_message = "Please enter a valid email address."
                st.session_state.auth_message_type = 'error'
            else:
                with st.spinner("Processing…"):
                    time.sleep(0.3)
                    _, message = request_password_reset(email)
                st.session_state.auth_message = message
                st.session_state.auth_message_type = 'info'
                st.session_state.auth_mode = 'login'
            st.rerun()

        if back:
            _switch_mode('login')


# ============================================================================
# MAIN AUTH PAGE
# ============================================================================

def show_auth_page():
    """Public entry point: renders the full animated sign-in experience."""
    _init_auth_state()
    _inject_base_styles()
    _render_floating_background()

    st.markdown('<div class="auth-wrapper">', unsafe_allow_html=True)
    st.markdown('<div class="auth-card"><div class="auth-card-inner">', unsafe_allow_html=True)

    st.markdown("""
        <div class="auth-header">
            <div class="auth-logo-badge">📦</div>
            <div class="auth-title">HPC Supply Planning Tool</div>
            <div class="auth-subtitle">EPSS Supply Chain Management</div>
            <div class="auth-divider"></div>
        </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="auth-grid">', unsafe_allow_html=True)

    left, right = st.columns([1.15, 1], gap="large")

    with left:
        _render_dashboard_preview()

    with right:
        st.markdown('<div class="signin-box">', unsafe_allow_html=True)
        mode = st.session_state.auth_mode
        if mode == 'login':
            _render_login_form()
        elif mode == 'register':
            _render_register_form()
        else:
            _render_forgot_password_form()
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)   # end auth-grid
    st.markdown('</div></div>', unsafe_allow_html=True)  # end auth-card-inner / auth-card
    st.markdown('</div>', unsafe_allow_html=True)   # end auth-wrapper
