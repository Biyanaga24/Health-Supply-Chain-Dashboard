import streamlit as st
import hashlib
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import pickle
import os
import warnings
import logging

# Suppress all warnings and connection-related messages
warnings.filterwarnings("ignore")
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)
logging.getLogger("googleapiclient").setLevel(logging.ERROR)

# Suppress Streamlit ScriptRunContext warnings
warnings.filterwarnings("ignore", message=".*missing ScriptRunContext.*")

# Page config must be the first Streamlit command
st.set_page_config(
    page_title="Health Program Medicines Dashboard",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CREATE DATABASE AND TABLES
conn = sqlite3.connect('users.db')
c = conn.cursor()

# Create users table with is_approved column
c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT DEFAULT 'user',
        is_approved INTEGER DEFAULT 0
    )
''')

# Add admin user if not exists (auto-approved)
admin_password = hashlib.sha256('Admin@123'.encode()).hexdigest()
c.execute("INSERT OR IGNORE INTO users (email, password, full_name, role, is_approved) VALUES (?, ?, ?, ?, ?)",
          ('admin@health.gov.et', admin_password, 'System Administrator', 'admin', 1))

# Add test user if not exists (auto-approved for testing)
test_password = hashlib.sha256('Test@123'.encode()).hexdigest()
c.execute("INSERT OR IGNORE INTO users (email, password, full_name, role, is_approved) VALUES (?, ?, ?, ?, ?)",
          ('test@health.gov.et', test_password, 'Test User', 'user', 1))

conn.commit()
conn.close()

# DATABASE FUNCTIONS
def authenticate_user(email, password):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    hashed = hashlib.sha256(password.encode()).hexdigest()
    # Only allow login if approved
    c.execute("SELECT id, email, full_name, role, is_approved FROM users WHERE email = ? AND password = ?", (email, hashed))
    user = c.fetchone()
    conn.close()

    if user:
        if user[4] == 0:  # Check if approved
            return {'error': 'not_approved'}
        return {
            'id': user[0],
            'email': user[1],
            'full_name': user[2],
            'role': user[3],
            'is_approved': user[4]
        }
    return None

def create_user(email, password, full_name):
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        hashed = hashlib.sha256(password.encode()).hexdigest()
        # New users start with is_approved = 0
        c.execute("INSERT INTO users (email, password, full_name, role, is_approved) VALUES (?, ?, ?, ?, ?)",
                  (email, hashed, full_name, 'user', 0))
        conn.commit()
        conn.close()
        return True, "Registration successful! Your account is pending admin approval."
    except sqlite3.IntegrityError:
        return False, "Email already exists. Please use a different email."
    except Exception as e:
        return False, f"Registration failed: {e}"

def get_pending_users():
    conn = sqlite3.connect('users.db')
    df = pd.read_sql_query("SELECT id, email, full_name FROM users WHERE is_approved = 0", conn)
    conn.close()
    return df

def get_all_users():
    conn = sqlite3.connect('users.db')
    df = pd.read_sql_query("SELECT id, email, full_name, role, is_approved FROM users", conn)
    conn.close()
    return df

def approve_user(user_id):
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("UPDATE users SET is_approved = 1 WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        return False

def reject_user(user_id):
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        return False

def delete_user(user_id):
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()

        # First check if user exists
        c.execute("SELECT id, email, full_name FROM users WHERE id = ?", (user_id,))
        user = c.fetchone()

        if not user:
            conn.close()
            return False, f"User with ID {user_id} not found"

        # Delete the user
        c.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        affected_rows = c.rowcount
        conn.close()

        if affected_rows > 0:
            return True, f"User {user[2]} deleted successfully"
        else:
            return False, "No rows were deleted"
    except Exception as e:
        return False, str(e)

# Initialize session state with persistence (no auto-expiry)
def init_session_state():
    """Initialize all session state variables with persistence check"""

    # Check if we have a saved session in query params (for page refreshes)
    if 'auth' not in st.session_state:
        st.session_state['auth'] = False

    if 'user' not in st.session_state:
        st.session_state['user'] = None

    if 'login_time' not in st.session_state:
        st.session_state['login_time'] = None

def check_session_validity():
    """Check if the session is still valid - now always returns True (no expiry)"""
    # Removed the 8-hour expiry - session never expires automatically
    # Only logout will clear the session
    return True

# PAGE FUNCTIONS
def show_login_page():
    st.markdown("""
        <style>
        .main-title {
            text-align: center;
            padding: 2rem;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 10px;
            margin-bottom: 2rem;
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown('<h1 class="main-title">🏥 Health Program Medicines Dashboard</h1>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        # Create a card-like container
        with st.container():
            st.markdown("### 🔐 Welcome Come")
            st.markdown("Please login to access the dashboard")

            tab1, tab2 = st.tabs(["🔐 Login", "📝 Register"])

            with tab1:
                with st.form("login_form"):
                    email = st.text_input("Email", placeholder="Enter your email")
                    password = st.text_input("Password", type="password", placeholder="Enter your password")
                    submitted = st.form_submit_button("Login", use_container_width=True)

                    if submitted:
                        if email and password:
                            user = authenticate_user(email, password)
                            if user and 'error' in user:
                                st.error("⏳ Your account is pending admin approval. Please wait.")
                            elif user:
                                st.session_state['auth'] = True
                                st.session_state['user'] = user
                                st.session_state['login_time'] = datetime.now()
                                st.rerun()
                            else:
                                st.error("Invalid email or password")
                        else:
                            st.warning("Please enter email and password")

            with tab2:
                with st.form("register_form"):
                    new_email = st.text_input("Email", placeholder="Enter your email")
                    new_full_name = st.text_input("Full Name", placeholder="Enter your full name")
                    new_password = st.text_input("Password", type="password", placeholder="Create a password")
                    confirm_password = st.text_input("Confirm Password", type="password", placeholder="Confirm your password")
                    submitted = st.form_submit_button("Register", use_container_width=True)

                    if submitted:
                        if not new_email or not new_full_name or not new_password:
                            st.warning("Please fill all fields")
                        elif new_password != confirm_password:
                            st.error("Passwords do not match")
                        elif len(new_password) < 6:
                            st.error("Password must be at least 6 characters")
                        else:
                            success, message = create_user(new_email, new_password, new_full_name)
                            if success:
                                st.success(message)
                                st.balloons()
                            else:
                                st.error(message)

def show_profile_page():
    st.subheader("👤 User Profile")
    user = st.session_state['user']

    # Profile card
    col1, col2 = st.columns([1, 2])
    with col1:
        st.image("https://via.placeholder.com/150", caption=user['full_name'])
    with col2:
        st.markdown(f"""
        ### {user['full_name']}

        | | |
        |---|---|
        | **Email** | {user['email']} |
        | **Role** | {user['role']} |
        | **User ID** | {user['id']} |
        | **Status** | {"✅ Approved" if user.get('is_approved', 1) else "⏳ Pending Approval"} |
        """)

    # Session info
    if st.session_state.get('login_time'):
        st.info(f"Logged in since: {st.session_state['login_time'].strftime('%Y-%m-%d %H:%M:%S')}")

def show_admin_panel():
    st.subheader("👑 Admin Panel - User Management")

    tab1, tab2, tab3 = st.tabs(["⏳ Pending Approvals", "📋 All Users", "🗑️ Delete User"])

    # Tab 1: Pending Approvals
    with tab1:
        pending_df = get_pending_users()
        if not pending_df.empty:
            st.success(f"**{len(pending_df)} users waiting for approval**")
            for idx, row in pending_df.iterrows():
                with st.container():
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
                                st.success(f"Rejected {row['full_name']}")
                                st.rerun()
                    st.divider()
        else:
            st.info("No pending approvals")

    # Tab 2: All Users
    with tab2:
        users_df = get_all_users()
        if not users_df.empty:
            # Show users table
            display_df = users_df.copy()
            display_df['status'] = display_df['is_approved'].apply(lambda x: "✅ Approved" if x == 1 else "⏳ Pending")
            st.dataframe(
                display_df[['id', 'email', 'full_name', 'role', 'status']],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "id": "ID",
                    "email": "Email",
                    "full_name": "Full Name",
                    "role": "Role",
                    "status": "Status"
                }
            )

            # Show total count
            st.caption(f"Total users: {len(users_df)}")
        else:
            st.info("No users found")

    # Tab 3: Delete User
    with tab3:
        st.subheader("Delete User")
        users_df = get_all_users()

        if not users_df.empty:
            # Don't allow deleting yourself
            current_user_email = st.session_state['user']['email']
            other_users = users_df[users_df['email'] != current_user_email]

            if not other_users.empty:
                # Create a friendly display name for selection
                other_users['display'] = other_users.apply(
                    lambda x: f"{x['full_name']} ({x['email']}) - ID: {x['id']}", axis=1
                )

                # User selection
                selected_display = st.selectbox(
                    "Select user to delete",
                    other_users['display'].tolist(),
                    key="delete_user_select"
                )

                # Get the selected user's data
                selected_user = other_users[other_users['display'] == selected_display].iloc[0]
                user_id = int(selected_user['id'])

                # Show warning and user details
                st.warning("⚠️ You are about to delete:")
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Name:** {selected_user['full_name']}")
                    st.write(f"**Email:** {selected_user['email']}")
                with col2:
                    st.write(f"**Role:** {selected_user['role']}")
                    st.write(f"**ID:** {user_id}")

                # Delete button with confirmation
                delete_confirmation = st.checkbox("I understand this action cannot be undone")
                if delete_confirmation:
                    if st.button("🗑️ Confirm Delete", type="primary", use_container_width=True):
                        with st.spinner("Deleting user..."):
                            success, message = delete_user(user_id)
                            if success:
                                st.success(f"✅ {message}")
                                st.balloons()
                                st.rerun()
                            else:
                                st.error(f"❌ Delete failed: {message}")
            else:
                st.info("No other users to delete (you are the only user)")
        else:
            st.info("No users found in database")

def show_dashboard():
    st.title("🏥 Dashboard")

    # Welcome message
    st.markdown(f"""
    ### Welcome, {st.session_state['user']['full_name']}! 👋

    You have successfully logged in to the Health Program Medicines Dashboard.
    """)

    # Quick stats or info
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Users", len(get_all_users()))
    with col2:
        st.metric("Pending Approvals", len(get_pending_users()))
    with col3:
        st.metric("Your Role", st.session_state['user']['role'].title())

# Main app logic
def main():
    # Initialize session state
    init_session_state()

    # Check session validity - now always returns True (no expiry)
    if st.session_state['auth']:
        check_session_validity()  # Always returns True now

    # Custom CSS for better UI
    st.markdown("""
        <style>
        .stButton > button {
            width: 100%;
        }
        .st-emotion-cache-1y4p8pa {
            padding-top: 2rem;
        }
        div[data-testid="stSidebar"] {
            background-color: #f0f2f6;
            padding: 2rem 1rem;
        }
        </style>
    """, unsafe_allow_html=True)

    # Sidebar (only show if authenticated)
    if st.session_state['auth']:
        with st.sidebar:
            st.markdown(f"""
            ### 👋 Hello, {st.session_state['user']['full_name']}
            **Role:** {st.session_state['user']['role'].title()}
            """)

            st.divider()

            # Navigation
            if st.session_state['user']['role'] == 'admin':
                pages = ["Dashboard", "Profile", "Admin Panel"]
            else:
                pages = ["Dashboard", "Profile"]

            page = st.radio(
                "Navigation",
                pages,
                key="navigation"
            )

            st.divider()

            # Session info - showing persistent session
            if st.session_state.get('login_time'):
                st.caption(f"Logged in since: {st.session_state['login_time'].strftime('%Y-%m-%d %H:%M:%S')}")
                st.caption("✨ Session never expires automatically")

            # Logout button
            if st.button("🚪 Logout", use_container_width=True):
                # Clear all session state
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()

        # Main content area
        if page == "Dashboard":
            show_dashboard()
        elif page == "Profile":
            show_profile_page()
        elif page == "Admin Panel" and st.session_state['user']['role'] == 'admin':
            show_admin_panel()
    else:
        # Show login page
        show_login_page()

if __name__ == "__main__":
    main()
