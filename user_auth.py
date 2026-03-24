import streamlit as st
import hashlib
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import os
import traceback

# Database file path - use absolute path to avoid issues
DB_PATH = os.path.join(os.path.dirname(__file__), 'users.db')

def get_db_connection():
    """Get database connection with proper error handling"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        st.error(f"Database connection error: {e}")
        return None

def init_database():
    """Initialize the database and create tables if they don't exist"""
    try:
        conn = get_db_connection()
        if conn is None:
            return False

        c = conn.cursor()

        # Create users table with is_approved column
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                is_approved INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        return True
    except Exception as e:
        st.error(f"Database initialization error: {e}")
        return False

# Initialize database on module load
try:
    init_database()
except Exception as e:
    print(f"Database initialization failed: {e}")

# DATABASE FUNCTIONS
def authenticate_user(email, password):
    """Authenticate a user and return user info if valid"""
    try:
        conn = get_db_connection()
        if conn is None:
            return None

        c = conn.cursor()
        hashed = hashlib.sha256(password.encode()).hexdigest()
        # Only allow login if approved
        c.execute("SELECT id, email, full_name, role, is_approved FROM users WHERE email = ? AND password = ?", 
                  (email, hashed))
        user = c.fetchone()
        conn.close()

        if user:
            if user['is_approved'] == 0:  # Check if approved
                return {'error': 'not_approved'}
            return {
                'id': user['id'],
                'email': user['email'],
                'full_name': user['full_name'],
                'role': user['role'],
                'is_approved': user['is_approved']
            }
        return None
    except Exception as e:
        st.error(f"Authentication error: {e}")
        return None

def create_user(email, password, full_name):
    """Create a new user account"""
    try:
        conn = get_db_connection()
        if conn is None:
            return False, "Database connection error"

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
    """Get list of users pending approval"""
    try:
        conn = get_db_connection()
        if conn is None:
            return pd.DataFrame()

        df = pd.read_sql_query("SELECT id, email, full_name FROM users WHERE is_approved = 0", conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Error fetching pending users: {e}")
        return pd.DataFrame()

def get_all_users():
    """Get list of all users"""
    try:
        conn = get_db_connection()
        if conn is None:
            return pd.DataFrame()

        df = pd.read_sql_query("SELECT id, email, full_name, role, is_approved FROM users", conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Error fetching users: {e}")
        return pd.DataFrame()

def approve_user(user_id):
    """Approve a pending user"""
    try:
        conn = get_db_connection()
        if conn is None:
            return False

        c = conn.cursor()
        c.execute("UPDATE users SET is_approved = 1 WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error approving user: {e}")
        return False

def reject_user(user_id):
    """Reject a pending user (delete from database)"""
    try:
        conn = get_db_connection()
        if conn is None:
            return False

        c = conn.cursor()
        c.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error rejecting user: {e}")
        return False

def delete_user(user_id):
    """Delete a user from the database"""
    try:
        conn = get_db_connection()
        if conn is None:
            return False, "Database connection error"

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
            return True, f"User {user['full_name']} deleted successfully"
        else:
            return False, "No rows were deleted"
    except Exception as e:
        return False, str(e)

def update_user_role(user_id, new_role):
    """Update user role"""
    try:
        conn = get_db_connection()
        if conn is None:
            return False

        c = conn.cursor()
        c.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error updating user role: {e}")
        return False

# PAGE FUNCTIONS
def show_login_page():
    """Display the login page"""
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
        .login-container {
            background-color: white;
            padding: 2rem;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown('<h1 class="main-title">🏥 Health Program Medicines Dashboard</h1>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.container():
            st.markdown('<div class="login-container">', unsafe_allow_html=True)

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
                    new_password = st.text_input("Password", type="password", placeholder="Create a password (min. 6 characters)")
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

            st.markdown('</div>', unsafe_allow_html=True)

def show_profile_page():
    """Display user profile page"""
    st.markdown("<h1 style='font-size: 32px; font-weight: bold; font-family: Times New Roman;'>👤 User Profile</h1>", unsafe_allow_html=True)

    if 'user' not in st.session_state or st.session_state['user'] is None:
        st.warning("User data not available")
        return

    user = st.session_state['user']

    col1, col2 = st.columns([1, 2])
    with col1:
        # Create a circular placeholder for profile image
        st.markdown(f"""
        <div style='text-align: center;'>
            <div style='
                width: 150px;
                height: 150px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto;
                font-size: 48px;
                color: white;
                font-weight: bold;
            '>
                {user['full_name'][0].upper()}
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        ### {user['full_name']}

        | | |
        |---|---|
        | **Email** | {user['email']} |
        | **Role** | {user['role'].title()} |
        | **User ID** | {user['id']} |
        | **Status** | {"✅ Approved" if user.get('is_approved', 1) else "⏳ Pending Approval"} |
        """)

    st.divider()

    # Session info
    if st.session_state.get('login_time'):
        st.info(f"📅 Logged in since: {st.session_state['login_time'].strftime('%Y-%m-%d %H:%M:%S')}")

    # Account actions
    st.markdown("### 🔧 Account Actions")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Refresh Session", use_container_width=True):
            st.session_state['login_time'] = datetime.now()
            st.success("Session refreshed!")
            st.rerun()
    with col2:
        if st.button("🚪 Logout", use_container_width=True):
            # Clear session state
            st.session_state['auth'] = False
            st.session_state['user'] = None
            st.session_state['login_time'] = None
            st.rerun()

def show_admin_panel():
    """Display admin panel for user management"""
    st.markdown("<h1 style='font-size: 32px; font-weight: bold; font-family: Times New Roman;'>👑 Admin Panel - User Management</h1>", unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["⏳ Pending Approvals", "📋 All Users", "🗑️ Delete User"])

    # Tab 1: Pending Approvals
    with tab1:
        st.markdown("### Pending User Approvals")
        pending_df = get_pending_users()
        if not pending_df.empty:
            st.success(f"**{len(pending_df)} users waiting for approval**")

            for idx, row in pending_df.iterrows():
                with st.container():
                    col1, col2, col3, col4 = st.columns([3, 3, 1, 1])
                    with col1:
                        st.markdown(f"**👤 {row['full_name']}**")
                    with col2:
                        st.write(row['email'])
                    with col3:
                        if st.button("✅ Approve", key=f"approve_{row['id']}"):
                            if approve_user(row['id']):
                                st.success(f"✅ Approved {row['full_name']}")
                                st.rerun()
                    with col4:
                        if st.button("❌ Reject", key=f"reject_{row['id']}"):
                            if reject_user(row['id']):
                                st.success(f"❌ Rejected {row['full_name']}")
                                st.rerun()
                    st.divider()
        else:
            st.info("✨ No pending approvals")

    # Tab 2: All Users
    with tab2:
        st.markdown("### All Registered Users")
        users_df = get_all_users()
        if not users_df.empty:
            # Show users table
            display_df = users_df.copy()
            display_df['status'] = display_df['is_approved'].apply(lambda x: "✅ Approved" if x == 1 else "⏳ Pending")

            st.dataframe(
                display_df[['id', 'email', 'full_name', 'role', 'status']],
                use_container_width=True,
                hide_index=True
            )

            # Show statistics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Users", len(users_df))
            with col2:
                st.metric("Approved Users", len(users_df[users_df['is_approved'] == 1]))
            with col3:
                st.metric("Pending Users", len(users_df[users_df['is_approved'] == 0]))
        else:
            st.info("No users found")

    # Tab 3: Delete User
    with tab3:
        st.markdown("### Delete User Account")
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
                st.warning("⚠️ You are about to delete this user. This action cannot be undone!")

                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Name:** {selected_user['full_name']}")
                    st.write(f"**Email:** {selected_user['email']}")
                with col2:
                    st.write(f"**Role:** {selected_user['role']}")
                    st.write(f"**ID:** {user_id}")

                # Delete button with confirmation
                delete_confirmation = st.checkbox("I understand this action cannot be undone and confirm deletion")
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
                st.info("ℹ️ No other users to delete (you are the only user in the system)")
        else:
            st.info("No users found in database")

def check_session_validity():
    """Check if the session is still valid"""
    if st.session_state.get('login_time'):
        login_time = st.session_state['login_time']
        # Session expires after 8 hours
        if datetime.now() - login_time > timedelta(hours=8):
            # Session expired
            st.session_state['auth'] = False
            st.session_state['user'] = None
            st.session_state['login_time'] = None
            return False
    return True

def init_session_state():
    """Initialize all session state variables"""
    if 'auth' not in st.session_state:
        st.session_state['auth'] = False
    if 'user' not in st.session_state:
        st.session_state['user'] = None
    if 'login_time' not in st.session_state:
        st.session_state['login_time'] = None
