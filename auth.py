import streamlit as st
import hashlib
import pandas as pd
from datetime import datetime
import warnings
import logging
from supabase import create_client

# Suppress warnings
warnings.filterwarnings("ignore")
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)

# Page config
st.set_page_config(
    page_title="Health Program Medicines Dashboard",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize Supabase client
@st.cache_resource
def init_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_supabase()

# ============================================================
# DATABASE FUNCTIONS
# ============================================================

def authenticate_user(email, password):
    """Authenticate user from Supabase"""
    hashed = hashlib.sha256(password.encode()).hexdigest()

    response = supabase.table("users") \
        .select("id, email, full_name, role, is_approved") \
        .eq("email", email) \
        .eq("password", hashed) \
        .execute()

    if response.data:
        user = response.data[0]
        if user['is_approved'] == 0:
            return {'error': 'not_approved'}
        return {
            'id': user['id'],
            'email': user['email'],
            'full_name': user['full_name'],
            'role': user['role'],
            'is_approved': user['is_approved']
        }
    return None

def create_user(email, password, full_name):
    """Create new user in Supabase"""
    try:
        hashed = hashlib.sha256(password.encode()).hexdigest()
        supabase.table("users").insert({
            "email": email,
            "password": hashed,
            "full_name": full_name,
            "role": "user",
            "is_approved": 0
        }).execute()
        return True, "Registration successful! Your account is pending admin approval."
    except Exception as e:
        if "duplicate key" in str(e).lower() or "unique constraint" in str(e).lower():
            return False, "Email already exists. Please use a different email."
        return False, f"Registration failed: {e}"

def get_pending_users():
    """Get all pending users"""
    response = supabase.table("users") \
        .select("id, email, full_name, created_at") \
        .eq("is_approved", 0) \
        .execute()
    return pd.DataFrame(response.data) if response.data else pd.DataFrame()

def get_all_users():
    """Get all users"""
    response = supabase.table("users") \
        .select("*") \
        .execute()
    return pd.DataFrame(response.data) if response.data else pd.DataFrame()

def approve_user(user_id):
    """Approve a user"""
    try:
        supabase.table("users") \
            .update({"is_approved": 1}) \
            .eq("id", user_id) \
            .execute()
        return True
    except Exception as e:
        return False

def reject_user(user_id):
    """Reject/delete a user"""
    try:
        supabase.table("users").delete().eq("id", user_id).execute()
        return True
    except Exception as e:
        return False

def delete_user(user_id):
    """Delete a user"""
    try:
        response = supabase.table("users") \
            .select("id, email, full_name") \
            .eq("id", user_id) \
            .execute()

        if not response.data:
            return False, f"User with ID {user_id} not found"

        user = response.data[0]
        supabase.table("users").delete().eq("id", user_id).execute()
        return True, f"User {user['full_name']} deleted successfully"
    except Exception as e:
        return False, str(e)

def init_session_state():
    """Initialize all session state variables"""
    if 'auth' not in st.session_state:
        st.session_state['auth'] = False
    if 'user' not in st.session_state:
        st.session_state['user'] = None
    if 'login_time' not in st.session_state:
        st.session_state['login_time'] = None

def check_session_validity():
    return True

# ============================================================
# UI FUNCTIONS
# ============================================================

def show_login_page():
    st.markdown("""
    <style>
    * { font-family: 'Times New Roman', Times, serif !important; }
    .stApp { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
    .main-title {
        text-align: center;
        padding: 1.5rem;
        background: linear-gradient(135deg, rgba(255,255,255,0.2) 0%, rgba(255,255,255,0.1) 100%);
        backdrop-filter: blur(10px);
        border-radius: 20px;
        margin-bottom: 2rem;
        color: white;
        animation: fadeInDown 0.8s ease-out;
    }
    @keyframes fadeInDown {
        from { opacity: 0; transform: translateY(-30px); }
        to { opacity: 1; transform: translateY(0); }
    }
    @keyframes fadeInUp {
        from { opacity: 0; transform: translateY(30px); }
        to { opacity: 1; transform: translateY(0); }
    }
    .login-container {
        background: rgba(255, 255, 255, 0.95);
        border-radius: 20px;
        padding: 2rem;
        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        animation: fadeInUp 0.8s ease-out;
    }
    .welcome-text {
        text-align: center;
        font-size: 1.3rem;
        color: #667eea;
        margin-bottom: 1.5rem;
        font-weight: 600;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid #667eea;
    }
    .feature-card {
        background: white;
        border-radius: 15px;
        padding: 1.5rem;
        text-align: center;
        transition: transform 0.3s ease, box-shadow 0.3s ease;
        cursor: pointer;
    }
    .feature-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
    }
    .feature-icon { font-size: 2.5rem; margin-bottom: 1rem; }
    .feature-title { font-weight: 600; color: #333; margin-bottom: 0.5rem; }
    .feature-desc { font-size: 0.85rem; color: #666; }
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 10px;
        padding: 0.5rem 1rem;
        font-weight: 600;
        transition: all 0.3s ease;
        font-size: 14px;
    }
    .stButton > button:hover {
        transform: scale(1.02);
        box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
    }
    div[data-testid="stTabs"] button {
        font-weight: 600;
        font-size: 1rem;
    }
    .stTextInput > div > div > input {
        border-radius: 10px;
        border: 1px solid #ddd;
        padding: 0.5rem 1rem;
    }
    .stTextInput > div > div > input:focus {
        border-color: #667eea;
        box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.2);
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="main-title">
        <h1 style="font-size: 2.5rem; margin: 0;">💊 Health Program Medicines Dashboard</h1>
        <p style="margin-top: 0.5rem; opacity: 0.9;">Comprehensive Stock Management & Analytics Platform</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1, 1.5])

    with col1:
        st.markdown("""
        <div class="login-container" style="background: rgba(255,255,255,0.95);">
            <h3 style="text-align: center; color: #667eea;">✨ Key Features</h3>
        </div>
        """, unsafe_allow_html=True)

        features = [
            ("📊", "Real-time Analytics", "Monitor stock levels and KPIs instantly"),
            ("🚚", "Pipeline Tracking", "Track GIT, LC, WB, and TMD orders"),
            ("📍", "Hub Distribution", "Visualize stock across all branches"),
            ("📋", "Decision Support", "Get actionable insights and recommendations"),
            ("🔐", "Secure Access", "Role-based access control"),
            ("📈", "Performance Metrics", "Track availability and SAP achievements")
        ]

        for i in range(0, len(features), 2):
            cols = st.columns(2)
            for j in range(2):
                if i + j < len(features):
                    icon, title, desc = features[i + j]
                    cols[j].markdown(f"""
                    <div class="feature-card">
                        <div class="feature-icon">{icon}</div>
                        <div class="feature-title">{title}</div>
                        <div class="feature-desc">{desc}</div>
                    </div>
                    """, unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="login-container">', unsafe_allow_html=True)
        st.markdown("""
        <div class="welcome-text">
            👋 Welcome! Please login to access the dashboard
        </div>
        """, unsafe_allow_html=True)

        tab1, tab2 = st.tabs(["🔐 **Login**", "📝 **Register**"])

        with tab1:
            with st.form("login_form", clear_on_submit=False):
                email = st.text_input("📧 Email", placeholder="Enter your email")
                password = st.text_input("🔒 Password", type="password", placeholder="Enter your password")
                submitted = st.form_submit_button("🚪 Login", use_container_width=True, type="primary")

                if submitted:
                    if email and password:
                        with st.spinner("Authenticating..."):
                            user = authenticate_user(email, password)
                            if user and 'error' in user:
                                st.error("⏳ Your account is pending admin approval. Please wait.")
                            elif user:
                                st.session_state['auth'] = True
                                st.session_state['user'] = user
                                st.session_state['login_time'] = datetime.now()
                                st.success("✅ Login successful! Redirecting...")
                                st.balloons()
                                st.rerun()
                            else:
                                st.error("❌ Invalid email or password")
                    else:
                        st.warning("⚠️ Please enter both email and password")

        with tab2:
            with st.form("register_form", clear_on_submit=False):
                new_email = st.text_input("📧 Email", placeholder="you@example.com")
                new_full_name = st.text_input("👤 Full Name", placeholder="Enter your full name")
                new_password = st.text_input("🔒 Password", type="password", placeholder="Create a password (min 6 characters)")
                confirm_password = st.text_input("✓ Confirm Password", type="password", placeholder="Confirm your password")
                submitted = st.form_submit_button("📝 Register", use_container_width=True, type="primary")

                if submitted:
                    if not new_email or not new_full_name or not new_password:
                        st.warning("⚠️ Please fill all fields")
                    elif new_password != confirm_password:
                        st.error("❌ Passwords do not match")
                    elif len(new_password) < 6:
                        st.error("❌ Password must be at least 6 characters")
                    else:
                        with st.spinner("Creating your account..."):
                            success, message = create_user(new_email, new_password, new_full_name)
                            if success:
                                st.success(f"✅ {message}")
                                st.balloons()
                                st.info("📋 Admin will review and approve your account.")
                            else:
                                st.error(f"❌ {message}")

        st.markdown('</div>', unsafe_allow_html=True)

def show_profile_page():
    st.markdown("## 👤 User Profile")
    user = st.session_state['user']

    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**📧 Email:** {user['email']}")
        st.write(f"**👤 Full Name:** {user['full_name']}")
    with col2:
        st.write(f"**🔑 Role:** {user['role'].title()}")
        st.write(f"**✅ Status:** {'Approved' if user.get('is_approved', 1) else 'Pending Approval'}")

def show_admin_panel():
    st.markdown("## 👑 Admin Control Panel")

    pending_df = get_pending_users()
    all_users = get_all_users()

    # Display metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("👥 Total Users", len(all_users))
    with col2:
        st.metric("⏳ Pending Approvals", len(pending_df))
    with col3:
        approved_count = len(all_users[all_users['is_approved'] == 1]) if not all_users.empty else 0
        st.metric("✅ Approved Users", approved_count)

    st.markdown("---")

    tab1, tab2 = st.tabs(["⏳ Pending Approvals", "📋 All Users"])

    # Tab 1: Pending Approvals
    with tab1:
        if not pending_df.empty:
            for idx, row in pending_df.iterrows():
                col1, col2, col3, col4 = st.columns([3, 3, 1, 1])
                with col1:
                    st.write(f"**{row['full_name']}**")
                with col2:
                    st.write(row['email'])
                with col3:
                    if st.button("✅ Approve", key=f"approve_{row['id']}"):
                        if approve_user(row['id']):
                            st.success(f"Approved {row['full_name']}")
                            st.rerun()
                with col4:
                    if st.button("❌ Reject", key=f"reject_{row['id']}"):
                        if reject_user(row['id']):
                            st.warning(f"Rejected {row['full_name']}")
                            st.rerun()
                st.divider()
        else:
            st.info("✅ No pending approvals")

    # Tab 2: All Users
    with tab2:
        if not all_users.empty:
            # Display all users in a clean table
            display_df = all_users[['id', 'email', 'full_name', 'role', 'is_approved', 'created_at']].copy()
            display_df['is_approved'] = display_df['is_approved'].apply(lambda x: "✅ Yes" if x == 1 else "⏳ No")

            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "id": st.column_config.NumberColumn("ID", width="small"),
                    "email": st.column_config.TextColumn("Email", width="medium"),
                    "full_name": st.column_config.TextColumn("Full Name", width="medium"),
                    "role": st.column_config.TextColumn("Role", width="small"),
                    "is_approved": st.column_config.TextColumn("Approved", width="small"),
                    "created_at": st.column_config.TextColumn("Registered", width="medium")
                }
            )
            st.caption(f"📊 Total: {len(all_users)} users")
        else:
            st.info("No users found")

def show_dashboard():
    st.markdown("## 📊 Dashboard")
    user = st.session_state['user']
    st.markdown(f"### 👋 Welcome, {user['full_name']}!")
    st.info("Your main dashboard will load your health data here...")

def main():
    init_session_state()

    if st.session_state['auth']:
        check_session_validity()

    if st.session_state['auth']:
        with st.sidebar:
            user = st.session_state['user']
            st.title(f"Welcome, {user['full_name']}!")
            st.caption(f"Role: {user['role'].title()}")

            if user['role'] == 'admin':
                pages = ["📊 Dashboard", "👤 Profile", "👑 Admin Panel"]
            else:
                pages = ["📊 Dashboard", "👤 Profile"]

            page = st.radio("Navigation", pages)

            if st.button("🚪 Logout", use_container_width=True):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()

        if page == "📊 Dashboard":
            show_dashboard()
        elif page == "👤 Profile":
            show_profile_page()
        elif page == "👑 Admin Panel" and user['role'] == 'admin':
            show_admin_panel()
    else:
        show_login_page()

if __name__ == "__main__":
    main()
