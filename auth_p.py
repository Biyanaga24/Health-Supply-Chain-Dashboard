
import streamlit as st
from supabase import create_client
import logging
from typing import Optional, Dict, Any, Tuple
import hashlib
import hmac
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===================================================
# CONSTANTS
# ===================================================
SUPABASE_URL = "https://etjfrptbjecafupbbase.supabase.co"
SUPABASE_KEY = "sb_publishable_j0JwaJAJBuJO79-xh7RkYg_PFKqLK1H"
USERS_TABLE = "users_vehicle"

# ===================================================
# CACHED SUPABASE CLIENT
# ===================================================
@st.cache_resource
def get_supabase():
    """Get cached Supabase client"""
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        logger.error(f"Failed to create Supabase client: {e}")
        return None

# ===================================================
# AUTHENTICATION FUNCTIONS
# ===================================================
@st.cache_data(ttl=3600)  # Cache user data for 1 hour
def get_user_from_db(email: str) -> Optional[Dict]:
    """Get user data from database with caching"""
    if not email:
        return None

    try:
        supabase = get_supabase()
        if not supabase:
            return None

        response = supabase.table(USERS_TABLE).select("*").eq("email", email).execute()

        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        logger.error(f"Error fetching user from database: {e}")
        return None

@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_pending_users_cached() -> list:
    """Get all pending users with caching"""
    try:
        supabase = get_supabase()
        if not supabase:
            return []

        response = supabase.table(USERS_TABLE).select("*").eq("is_approved", 0).execute()
        return response.data if response.data else []
    except Exception as e:
        logger.error(f"Error fetching pending users: {e}")
        return []

@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_all_users_cached() -> list:
    """Get all users with caching"""
    try:
        supabase = get_supabase()
        if not supabase:
            return []

        response = supabase.table(USERS_TABLE).select("*").execute()
        return response.data if response.data else []
    except Exception as e:
        logger.error(f"Error fetching all users: {e}")
        return []

def setup_auth() -> bool:
    """Setup authentication with login/register UI"""
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.title("🚚 Fleet Management System")

        tab1, tab2 = st.tabs(["🔐 Login", "📝 Register"])

        with tab1:
            with st.form("login_form"):
                email = st.text_input("Email", key="login_email")
                password = st.text_input("Password", type="password", key="login_password")
                submitted = st.form_submit_button("Login")

                if submitted:
                    if email and password:
                        result = login_user(email, password)
                        if result["success"]:
                            st.session_state.authenticated = True
                            st.session_state.user_email = email
                            st.session_state.user_data = result["user"]
                            st.rerun()
                        else:
                            st.error(result.get("message", "Login failed"))
                    else:
                        st.warning("Please enter both email and password")

        with tab2:
            with st.form("register_form"):
                full_name = st.text_input("Full Name", key="register_name")
                email = st.text_input("Email", key="register_email")
                password = st.text_input("Password", type="password", key="register_password")
                confirm_password = st.text_input("Confirm Password", type="password", key="register_confirm")
                submitted = st.form_submit_button("Register")

                if submitted:
                    if full_name and email and password and confirm_password:
                        if password != confirm_password:
                            st.error("Passwords don't match")
                        else:
                            result = register_user(email, password, full_name)
                            if result["success"]:
                                st.success("Registration successful! Please wait for admin approval.")
                            else:
                                st.error(result.get("message", "Registration failed"))
                    else:
                        st.warning("Please fill all fields")

        return False

    return True

def login_user(email: str, password: str) -> Dict[str, Any]:
    """Login user with email and password"""
    try:
        supabase = get_supabase()
        if not supabase:
            return {"success": False, "message": "Database connection error"}

        # Get user from database
        user = get_user_from_db(email)
        if not user:
            return {"success": False, "message": "User not found"}

        # Check if user is approved
        if user.get("is_approved", 0) != 1:
            return {"success": False, "message": "Account pending approval. Please wait for admin to approve."}

        # Verify password (simple hash - you can use bcrypt or other methods)
        password_hash = hashlib.sha256((password + email).encode()).hexdigest()
        if user.get("password_hash") != password_hash:
            return {"success": False, "message": "Invalid password"}

        return {
            "success": True,
            "user": {
                "id": user.get("id"),
                "email": user.get("email"),
                "full_name": user.get("full_name"),
                "role": user.get("role", "user"),
                "is_approved": user.get("is_approved", 0)
            }
        }
    except Exception as e:
        logger.error(f"Login error: {e}")
        return {"success": False, "message": f"Login error: {str(e)}"}

def register_user(email: str, password: str, full_name: str) -> Dict[str, Any]:
    """Register a new user"""
    try:
        supabase = get_supabase()
        if not supabase:
            return {"success": False, "message": "Database connection error"}

        # Check if user exists
        existing = get_user_from_db(email)
        if existing:
            return {"success": False, "message": "User already exists"}

        # Hash password
        password_hash = hashlib.sha256((password + email).encode()).hexdigest()

        # Create user
        new_user = {
            "email": email,
            "password_hash": password_hash,
            "full_name": full_name,
            "role": "user",
            "is_approved": 0,  # Pending approval
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        response = supabase.table(USERS_TABLE).insert(new_user).execute()

        if response.data:
            return {"success": True, "message": "Registration successful"}
        else:
            return {"success": False, "message": "Registration failed"}
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return {"success": False, "message": f"Registration error: {str(e)}"}

def approve_user(user_id: int) -> Dict[str, Any]:
    """Approve a pending user"""
    try:
        supabase = get_supabase()
        if not supabase:
            return {"success": False, "message": "Database connection error"}

        response = supabase.table(USERS_TABLE).update({"is_approved": 1}).eq("id", user_id).execute()

        if response.data:
            # Clear cache after approval
            st.cache_data.clear()
            return {"success": True, "message": "User approved successfully"}
        else:
            return {"success": False, "message": "Failed to approve user"}
    except Exception as e:
        logger.error(f"Approval error: {e}")
        return {"success": False, "message": f"Approval error: {str(e)}"}

def reject_user(user_id: int) -> Dict[str, Any]:
    """Reject and delete a pending user"""
    try:
        supabase = get_supabase()
        if not supabase:
            return {"success": False, "message": "Database connection error"}

        response = supabase.table(USERS_TABLE).delete().eq("id", user_id).execute()

        if response.data:
            # Clear cache after rejection
            st.cache_data.clear()
            return {"success": True, "message": "User rejected successfully"}
        else:
            return {"success": False, "message": "Failed to reject user"}
    except Exception as e:
        logger.error(f"Rejection error: {e}")
        return {"success": False, "message": f"Rejection error: {str(e)}"}

def get_user_email() -> Optional[str]:
    """Get current user's email from session state"""
    return st.session_state.get("user_email")

def get_user_metadata() -> Dict[str, Any]:
    """Get current user's metadata from session state"""
    user_data = st.session_state.get("user_data")
    if user_data:
        return {
            "full_name": user_data.get("full_name", "N/A"),
            "role": user_data.get("role", "user"),
            "is_approved": user_data.get("is_approved", 0)
        }
    return {}

def get_user_role() -> Optional[str]:
    """Get current user's role"""
    user_data = st.session_state.get("user_data")
    if user_data:
        return user_data.get("role", "user")
    return None

def is_admin() -> bool:
    """Check if current user is admin"""
    user_data = st.session_state.get("user_data")
    if user_data:
        return user_data.get("role") == "admin" and user_data.get("is_approved") == 1
    return False

def is_authenticated() -> bool:
    """Check if user is authenticated"""
    return st.session_state.get("authenticated", False)

def get_current_user() -> Dict[str, Any]:
    """Get current user data"""
    return st.session_state.get("user_data", {})

def sign_out() -> bool:
    """Sign out current user"""
    try:
        st.session_state.clear()
        st.cache_data.clear()
        return True
    except Exception as e:
        logger.error(f"Sign out error: {e}")
        return False

def get_all_users() -> list:
    """Get all users (admin only)"""
    return get_all_users_cached()

def get_pending_users() -> list:
    """Get pending users (admin only)"""
    return get_pending_users_cached()

def admin_panel() -> None:
    """Display admin panel (to be used in main app)"""
    if not is_admin():
        st.error("⚠️ You don't have permission to access this page.")
        return

    st.markdown("## 👑 Admin Panel")

    # Get users
    all_users = get_all_users()
    pending_users = get_pending_users()

    # Display statistics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Users", len(all_users))
    with col2:
        st.metric("Pending Approval", len(pending_users))
    with col3:
        admins = len([u for u in all_users if u.get('role') == 'admin'])
        st.metric("Admins", admins)

    # Show pending approvals
    if pending_users:
        st.subheader("📋 Pending Approvals")
        for user in pending_users:
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
                with col1:
                    st.markdown(f"**Name:** {user.get('full_name', 'N/A')}")
                with col2:
                    st.markdown(f"**Email:** {user.get('email', 'N/A')}")
                with col3:
                    if st.button("✅ Approve", key=f"approve_{user['id']}"):
                        result = approve_user(user['id'])
                        if result["success"]:
                            st.success(f"User {user.get('email')} approved!")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error(result.get("message", "Approval failed"))
                with col4:
                    if st.button("❌ Reject", key=f"reject_{user['id']}"):
                        result = reject_user(user['id'])
                        if result["success"]:
                            st.warning(f"User {user.get('email')} rejected.")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error(result.get("message", "Rejection failed"))
    else:
        st.info("✅ No pending approvals")

    # Show all users
    if all_users:
        st.subheader("📊 All Users")
        users_df = pd.DataFrame(all_users)
        display_cols = ['id', 'email', 'full_name', 'role', 'is_approved', 'created_at']
        available_cols = [col for col in display_cols if col in users_df.columns]
        st.dataframe(users_df[available_cols], use_container_width=True, hide_index=True)

# ===================================================
# MAIN FUNCTION (for testing)
# ===================================================
if __name__ == "__main__":
    # This allows testing the auth module independently
    st.set_page_config(page_title="Auth Test", layout="wide")

    authenticated = setup_auth()

    if authenticated:
        st.success("✅ You are logged in!")
        st.write(f"Email: {get_user_email()}")
        st.write(f"Metadata: {get_user_metadata()}")
        st.write(f"Is Admin: {is_admin()}")

        if st.button("Sign Out"):
            sign_out()
            st.rerun()
