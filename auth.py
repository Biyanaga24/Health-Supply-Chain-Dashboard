import streamlit as st
import hashlib
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import pickle
import os
import warnings
import logging
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------
# Email Notification Functions
# ---------------------------------------------------

def get_smtp_config():
    """Get SMTP configuration from secrets"""
    try:
        # Try to get from secrets
        smtp_server = st.secrets.get("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = st.secrets.get("SMTP_PORT", 587)
        sender_email = st.secrets.get("SENDER_EMAIL", "")
        sender_password = st.secrets.get("SENDER_PASSWORD", "")
        admin_email = st.secrets.get("ADMIN_EMAIL", "admin@health.gov.et")

        return {
            'server': smtp_server,
            'port': smtp_port,
            'sender': sender_email,
            'password': sender_password,
            'admin_email': admin_email
        }
    except:
        # Return default values if secrets not available
        return {
            'server': "smtp.gmail.com",
            'port': 587,
            'sender': "",
            'password': "",
            'admin_email': "admin@health.gov.et"
        }

def send_email_notification(subject, body, to_email):
    """Send email notification"""
    config = get_smtp_config()

    if not config['sender'] or not config['password']:
        print("Email credentials not configured. Skipping email notification.")
        return False

    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = config['sender']
        msg['To'] = to_email if to_email != "admin" else config['admin_email']
        msg['Subject'] = subject

        # Attach HTML body
        msg.attach(MIMEText(body, 'html'))

        # Send email
        server = smtplib.SMTP(config['server'], config['port'])
        server.starttls()
        server.login(config['sender'], config['password'])
        server.send_message(msg)
        server.quit()

        return True
    except Exception as e:
        print(f"Email notification failed: {e}")
        return False

def notify_admin_new_user_registration(user_data):
    """Send notification to admin when a new user registers"""
    subject = "🔔 New User Registration - Health Dashboard"

    body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: 'Times New Roman', Times, serif; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                      color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
            .content {{ background: #f8f9fa; padding: 20px; border-radius: 0 0 10px 10px; }}
            .info-row {{ margin: 10px 0; padding: 10px; background: white; border-radius: 5px; }}
            .label {{ font-weight: bold; color: #667eea; }}
            .footer {{ text-align: center; margin-top: 20px; padding: 10px; font-size: 12px; color: #666; }}
            .button {{ background: #667eea; color: white; padding: 10px 20px; text-decoration: none; 
                      border-radius: 5px; display: inline-block; margin-top: 15px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>🔔 New User Registration</h2>
            </div>
            <div class="content">
                <p>Hello Administrator,</p>
                <p>A new user has registered for the Health Program Medicines Dashboard. Please review their details below:</p>

                <div class="info-row">
                    <div><span class="label">📧 Email:</span> {user_data.get('email', 'N/A')}</div>
                </div>
                <div class="info-row">
                    <div><span class="label">👤 Full Name:</span> {user_data.get('full_name', 'N/A')}</div>
                </div>
                <div class="info-row">
                    <div><span class="label">🔑 Role:</span> {user_data.get('role', 'user').title()}</div>
                </div>
                <div class="info-row">
                    <div><span class="label">📅 Registered at:</span> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
                </div>
                <div class="info-row">
                    <div><span class="label">🆔 User ID:</span> {user_data.get('id', 'N/A')}</div>
                </div>

                <div style="text-align: center;">
                    <a href="#" style="background: #667eea; color: white; padding: 10px 20px; text-decoration: none; 
                       border-radius: 5px; display: inline-block; margin-top: 15px;">
                        Go to Admin Panel
                    </a>
                </div>

                <p style="margin-top: 20px;">Please review and approve this user account in the admin panel.</p>
                <hr>
                <p style="font-size: 12px; color: #666;">This is an automated notification from Health Program Medicines Dashboard.</p>
            </div>
        </div>
    </body>
    </html>
    """

    return send_email_notification(subject, body, "admin")

def notify_admin_account_removal(user_data, removed_by):
    """Send notification to admin when a user account is removed"""
    subject = "⚠️ User Account Removed - Health Dashboard"

    body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: 'Times New Roman', Times, serif; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%); 
                      color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
            .content {{ background: #f8f9fa; padding: 20px; border-radius: 0 0 10px 10px; }}
            .info-row {{ margin: 10px 0; padding: 10px; background: white; border-radius: 5px; }}
            .label {{ font-weight: bold; color: #e74c3c; }}
            .footer {{ text-align: center; margin-top: 20px; padding: 10px; font-size: 12px; color: #666; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>⚠️ User Account Removed</h2>
            </div>
            <div class="content">
                <p>Hello Administrator,</p>
                <p>The following user account has been removed from the system:</p>

                <div class="info-row">
                    <div><span class="label">📧 Email:</span> {user_data.get('email', 'N/A')}</div>
                </div>
                <div class="info-row">
                    <div><span class="label">👤 Full Name:</span> {user_data.get('full_name', 'N/A')}</div>
                </div>
                <div class="info-row">
                    <div><span class="label">🔑 Role:</span> {user_data.get('role', 'N/A').title()}</div>
                </div>
                <div class="info-row">
                    <div><span class="label">🗑️ Removed by:</span> {removed_by}</div>
                </div>
                <div class="info-row">
                    <div><span class="label">📅 Removed at:</span> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
                </div>
                <div class="info-row">
                    <div><span class="label">🆔 User ID:</span> {user_data.get('id', 'N/A')}</div>
                </div>

                <hr>
                <p style="font-size: 12px; color: #666;">This is an automated notification from Health Program Medicines Dashboard.</p>
            </div>
        </div>
    </body>
    </html>
    """

    return send_email_notification(subject, body, "admin")

def notify_user_account_approved(user_email, user_name):
    """Notify user that their account has been approved"""
    subject = "✅ Account Approved - Health Program Medicines Dashboard"

    body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: 'Times New Roman', Times, serif; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #27ae60 0%, #2ecc71 100%); 
                      color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
            .content {{ background: #f8f9fa; padding: 20px; border-radius: 0 0 10px 10px; }}
            .footer {{ text-align: center; margin-top: 20px; padding: 10px; font-size: 12px; color: #666; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>✅ Account Approved!</h2>
            </div>
            <div class="content">
                <p>Dear {user_name},</p>
                <p>We are pleased to inform you that your account has been approved by the administrator.</p>
                <p>You can now access the Health Program Medicines Dashboard with full privileges.</p>

                <div style="text-align: center;">
                    <a href="#" style="background: #27ae60; color: white; padding: 10px 20px; text-decoration: none; 
                       border-radius: 5px; display: inline-block; margin-top: 15px;">
                        Access Dashboard
                    </a>
                </div>

                <p style="margin-top: 20px;">If you have any questions, please contact the system administrator.</p>
                <hr>
                <p style="font-size: 12px; color: #666;">This is an automated notification from Health Program Medicines Dashboard.</p>
            </div>
        </div>
    </body>
    </html>
    """

    return send_email_notification(subject, body, user_email)

def notify_admin_test_connection():
    """Test email configuration"""
    subject = "✅ Health Dashboard - Email Test"

    body = """
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body { font-family: 'Times New Roman', Times, serif; }
            .container { max-width: 600px; margin: 0 auto; padding: 20px; }
            .header { background: linear-gradient(135deg, #27ae60 0%, #2ecc71 100%); 
                      color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }
            .content { background: #f8f9fa; padding: 20px; border-radius: 0 0 10px 10px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>✅ Email Test Successful!</h2>
            </div>
            <div class="content">
                <p>Your email notification system is configured correctly.</p>
                <p>You will receive notifications for:</p>
                <ul>
                    <li>New user registrations</li>
                    <li>Account removals</li>
                    <li>Account approvals</li>
                </ul>
                <hr>
                <p style="font-size: 12px; color: #666;">This is a test notification from Health Program Medicines Dashboard.</p>
            </div>
        </div>
    </body>
    </html>
    """

    config = get_smtp_config()
    return send_email_notification(subject, body, config['admin_email'])

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

# DATABASE FUNCTIONS
def authenticate_user(email, password):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    hashed = hashlib.sha256(password.encode()).hexdigest()
    c.execute("SELECT id, email, full_name, role, is_approved FROM users WHERE email = ? AND password = ?", (email, hashed))
    user = c.fetchone()
    conn.close()

    if user:
        if user[4] == 0:
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
        c.execute("INSERT INTO users (email, password, full_name, role, is_approved) VALUES (?, ?, ?, ?, ?)",
                  (email, hashed, full_name, 'user', 0))

        # Get the inserted user ID
        user_id = c.lastrowid

        conn.commit()

        # Send notification to admin about new registration
        user_data = {
            'id': user_id,
            'email': email,
            'full_name': full_name,
            'role': 'user'
        }
        notify_admin_new_user_registration(user_data)

        conn.close()
        return True, "Registration successful! Your account is pending admin approval. You will receive an email when approved."
    except sqlite3.IntegrityError:
        return False, "Email already exists. Please use a different email."
    except Exception as e:
        return False, f"Registration failed: {e}"

def get_pending_users():
    conn = sqlite3.connect('users.db')
    df = pd.read_sql_query("SELECT id, email, full_name, created_at FROM users WHERE is_approved = 0", conn)
    conn.close()
    return df

def get_all_users():
    conn = sqlite3.connect('users.db')
    df = pd.read_sql_query("SELECT id, email, full_name, role, is_approved, created_at FROM users", conn)
    conn.close()
    return df

def approve_user(user_id):
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()

        # Get user details before approving
        c.execute("SELECT email, full_name FROM users WHERE id = ?", (user_id,))
        user = c.fetchone()

        c.execute("UPDATE users SET is_approved = 1 WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()

        # Send approval notification to user
        if user:
            notify_user_account_approved(user[0], user[1])

        return True
    except Exception as e:
        return False

def reject_user(user_id):
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()

        # Get user details before rejecting
        c.execute("SELECT email, full_name FROM users WHERE id = ?", (user_id,))
        user = c.fetchone()

        c.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()

        # Optionally send rejection notification
        # if user:
        #     notify_user_account_rejected(user[0], user[1])

        return True
    except Exception as e:
        return False

def delete_user(user_id):
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()

        # Get user details before deletion
        c.execute("SELECT id, email, full_name, role FROM users WHERE id = ?", (user_id,))
        user = c.fetchone()

        if not user:
            conn.close()
            return False, f"User with ID {user_id} not found"

        c.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        affected_rows = c.rowcount
        conn.close()

        if affected_rows > 0:
            # Send notification to admin about account removal
            user_data = {
                'id': user[0],
                'email': user[1],
                'full_name': user[2],
                'role': user[3]
            }
            # Get current user email from session state if available
            removed_by = st.session_state.get('user', {}).get('email', 'System Administrator')
            notify_admin_account_removal(user_data, removed_by)

            return True, f"User {user[2]} deleted successfully"
        else:
            return False, "No rows were deleted"
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

# PAGE FUNCTIONS
def show_login_page():
    # Enhanced CSS for login page with Times New Roman font
    st.markdown("""
    <style>
    * {
        font-family: 'Times New Roman', Times, serif !important;
    }

    .stApp {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    }

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
        from {
            opacity: 0;
            transform: translateY(-30px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    @keyframes fadeInUp {
        from {
            opacity: 0;
            transform: translateY(30px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
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
        font-family: 'Times New Roman', Times, serif !important;
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

    .feature-icon {
        font-size: 2.5rem;
        margin-bottom: 1rem;
    }

    .feature-title {
        font-weight: 600;
        color: #333;
        margin-bottom: 0.5rem;
        font-family: 'Times New Roman', Times, serif !important;
    }

    .feature-desc {
        font-size: 0.85rem;
        color: #666;
        font-family: 'Times New Roman', Times, serif !important;
    }

    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 10px;
        padding: 0.5rem 1rem;
        font-weight: 600;
        transition: all 0.3s ease;
        font-family: 'Times New Roman', Times, serif !important;
        font-size: 14px;
    }

    .stButton > button:hover {
        transform: scale(1.02);
        box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
    }

    div[data-testid="stTabs"] {
        background: transparent;
    }

    div[data-testid="stTabs"] button {
        font-weight: 600;
        font-size: 1rem;
        font-family: 'Times New Roman', Times, serif !important;
    }

    .stTextInput > div > div > input {
        border-radius: 10px;
        border: 1px solid #ddd;
        padding: 0.5rem 1rem;
        font-family: 'Times New Roman', Times, serif !important;
    }

    .stTextInput > div > div > input:focus {
        border-color: #667eea;
        box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.2);
    }

    label {
        font-family: 'Times New Roman', Times, serif !important;
    }

    h1, h2, h3, h4, h5, h6, p, span, div {
        font-family: 'Times New Roman', Times, serif !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # Main title with icon
    st.markdown("""
    <div class="main-title">
        <h1 style="font-size: 2.5rem; margin: 0; font-family: 'Times New Roman', Times, serif;">💊 Health Program Medicines Dashboard</h1>
        <p style="margin-top: 0.5rem; opacity: 0.9; font-family: 'Times New Roman', Times, serif;">Comprehensive Stock Management & Analytics Platform</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1, 1.5])

    with col1:
        # Features section
        st.markdown("""
        <div class="login-container" style="background: rgba(255,255,255,0.95);">
            <h3 style="text-align: center; color: #667eea; font-family: 'Times New Roman', Times, serif;">✨ Key Features</h3>
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
        # Login/Register container with welcome message INSIDE the card
        st.markdown('<div class="login-container">', unsafe_allow_html=True)

        # Welcome message - INSIDE THE CARD
        st.markdown("""
        <div class="welcome-text">
            👋 Welcome! Please login to access the dashboard
        </div>
        """, unsafe_allow_html=True)

        tab1, tab2 = st.tabs(["🔐 **Login**", "📝 **Register**"])

        with tab1:
            with st.form("login_form", clear_on_submit=False):
                email = st.text_input("📧 Email", placeholder="Enter your email", help="Enter your registered email")
                password = st.text_input("🔒 Password", type="password", placeholder="Enter your password", help="Enter your password")

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
                new_email = st.text_input("📧 Email", placeholder="you@example.com", help="Use a valid email address")
                new_full_name = st.text_input("👤 Full Name", placeholder="Enter your full name", help="Your full name as you want it displayed")
                new_password = st.text_input("🔒 Password", type="password", placeholder="Create a password (min 6 characters)", help="Minimum 6 characters")
                confirm_password = st.text_input("✓ Confirm Password", type="password", placeholder="Confirm your password", help="Must match the password above")

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
                                st.info("📧 You will be notified once your account is approved by an administrator.")
                            else:
                                st.error(f"❌ {message}")

        st.markdown('</div>', unsafe_allow_html=True)

def show_profile_page():
    st.markdown("""
    <style>
    * {
        font-family: 'Times New Roman', Times, serif !important;
    }
    .profile-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 20px;
        color: white;
        margin-bottom: 2rem;
    }
    .profile-card {
        background: white;
        border-radius: 15px;
        padding: 1.5rem;
        box-shadow: 0 5px 15px rgba(0,0,0,0.1);
    }
    .stat-card {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        border-radius: 15px;
        padding: 1rem;
        text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)

    user = st.session_state['user']

    # Profile header
    st.markdown(f"""
    <div class="profile-header">
        <h1 style="margin: 0; font-family: 'Times New Roman', Times, serif;">👤 User Profile</h1>
        <p style="margin: 0.5rem 0 0 0; opacity: 0.9; font-family: 'Times New Roman', Times, serif;">Manage your account settings and preferences</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1, 2])

    with col1:
        # Avatar based on user name
        initials = ''.join([word[0].upper() for word in user['full_name'].split()[:2]])
        st.markdown(f"""
        <div class="profile-card" style="text-align: center;">
            <div style="width: 120px; height: 120px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                        border-radius: 60px; display: flex; align-items: center; justify-content: center; 
                        margin: 0 auto 1rem auto;">
                <span style="font-size: 48px; color: white; font-weight: bold; font-family: 'Times New Roman', Times, serif;">{initials}</span>
            </div>
            <h3 style="margin: 0; font-family: 'Times New Roman', Times, serif;">{user['full_name']}</h3>
            <p style="color: #666; font-family: 'Times New Roman', Times, serif;">{user['role'].title()} User</p>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="profile-card">
            <h3 style="font-family: 'Times New Roman', Times, serif;">📋 Account Information</h3>
            <table style="width: 100%;">
                <tr>
                    <td style="padding: 8px 0; font-family: 'Times New Roman', Times, serif;"><strong>📧 Email</strong></td>
                    <td style="padding: 8px 0; font-family: 'Times New Roman', Times, serif;">{user['email']}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; font-family: 'Times New Roman', Times, serif;"><strong>👤 Full Name</strong></td>
                    <td style="padding: 8px 0; font-family: 'Times New Roman', Times, serif;">{user['full_name']}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; font-family: 'Times New Roman', Times, serif;"><strong>🔑 Role</strong></td>
                    <td style="padding: 8px 0; font-family: 'Times New Roman', Times, serif;"><span style="background: {'#4CAF50' if user['role'] == 'admin' else '#2196F3'}; color: white; padding: 2px 8px; border-radius: 20px;">{user['role'].title()}</span></td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; font-family: 'Times New Roman', Times, serif;"><strong>🆔 User ID</strong></td>
                    <td style="padding: 8px 0; font-family: 'Times New Roman', Times, serif;">{user['id']}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; font-family: 'Times New Roman', Times, serif;"><strong>✅ Status</strong></td>
                    <td style="padding: 8px 0; font-family: 'Times New Roman', Times, serif;"><span style="color: {'#4CAF50' if user.get('is_approved', 1) else '#ff9800'}; font-weight: bold;">{'Approved' if user.get('is_approved', 1) else 'Pending Approval'}</span></td>
                </tr>
            </table>
        </div>
        """, unsafe_allow_html=True)

    # Session info
    if st.session_state.get('login_time'):
        login_duration = datetime.now() - st.session_state['login_time']
        hours = login_duration.seconds // 3600
        minutes = (login_duration.seconds % 3600) // 60

        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <div class="stat-card">
                <div style="font-size: 2rem;">🕐</div>
                <div style="font-size: 1.5rem; font-weight: bold; font-family: 'Times New Roman', Times, serif;">{st.session_state['login_time'].strftime('%H:%M:%S')}</div>
                <div style="font-family: 'Times New Roman', Times, serif;">Login Time</div>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown(f"""
            <div class="stat-card">
                <div style="font-size: 2rem;">📅</div>
                <div style="font-size: 1.5rem; font-weight: bold; font-family: 'Times New Roman', Times, serif;">{st.session_state['login_time'].strftime('%b %d, %Y')}</div>
                <div style="font-family: 'Times New Roman', Times, serif;">Login Date</div>
            </div>
            """, unsafe_allow_html=True)
        with col3:
            st.markdown(f"""
            <div class="stat-card">
                <div style="font-size: 2rem;">⏱️</div>
                <div style="font-size: 1.5rem; font-weight: bold; font-family: 'Times New Roman', Times, serif;">{hours}h {minutes}m</div>
                <div style="font-family: 'Times New Roman', Times, serif;">Session Duration</div>
            </div>
            """, unsafe_allow_html=True)

def show_admin_panel():
    st.markdown("""
    <style>
    * {
        font-family: 'Times New Roman', Times, serif !important;
    }
    .admin-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 20px;
        color: white;
        margin-bottom: 2rem;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="admin-header">
        <h1 style="margin: 0; font-family: 'Times New Roman', Times, serif;">👑 Admin Control Panel</h1>
        <p style="margin: 0.5rem 0 0 0; opacity: 0.9; font-family: 'Times New Roman', Times, serif;">Manage users, approvals, and system settings</p>
    </div>
    """, unsafe_allow_html=True)

    # Email Test Section
    with st.expander("📧 Email Notification Settings", expanded=False):
        st.markdown("""
        ### Email Configuration
        Configure email notifications for:
        - New user registrations
        - Account approvals
        - Account removals
        """)

        config = get_smtp_config()
        if config['sender'] and config['password']:
            st.success("✅ Email credentials configured")

            if st.button("📧 Test Email Notification", use_container_width=True):
                with st.spinner("Sending test email..."):
                    if notify_admin_test_connection():
                        st.success("✅ Test email sent successfully!")
                    else:
                        st.error("❌ Failed to send test email. Please check your email configuration.")
        else:
            st.warning("⚠️ Email credentials not configured. Add to `.streamlit/secrets.toml`:")
            st.code("""
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "your-email@gmail.com"
SENDER_PASSWORD = "your-app-password"
ADMIN_EMAIL = "admin@health.gov.et"
            """, language="toml")

    # Stats
    all_users = get_all_users()
    pending_df = get_pending_users()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("👥 Total Users", len(all_users), delta=None)
    with col2:
        st.metric("⏳ Pending Approvals", len(pending_df), delta=None, delta_color="inverse")
    with col3:
        st.metric("👑 Admins", len(all_users[all_users['role'] == 'admin']) if not all_users.empty else 0, delta=None)
    with col4:
        st.metric("✅ Approved Users", len(all_users[all_users['is_approved'] == 1]) if not all_users.empty else 0, delta=None)

    st.markdown("---")

    tab1, tab2, tab3 = st.tabs(["⏳ **Pending Approvals**", "📋 **All Users**", "🗑️ **Delete User**"])

    with tab1:
        if not pending_df.empty:
            st.success(f"✨ **{len(pending_df)} users waiting for approval**")
            for idx, row in pending_df.iterrows():
                with st.container():
                    col1, col2, col3, col4, col5 = st.columns([2, 2, 1, 1, 1])
                    with col1:
                        st.markdown(f"**👤 {row['full_name']}**")
                    with col2:
                        st.markdown(f"📧 {row['email']}")
                    with col3:
                        if 'created_at' in row:
                            st.caption(f"📅 {row['created_at'][:10]}")
                    with col4:
                        if st.button("✅ Approve", key=f"approve_{row['id']}", use_container_width=True):
                            if approve_user(row['id']):
                                st.success(f"✅ Approved {row['full_name']} - Email notification sent")
                                st.balloons()
                                st.rerun()
                    with col5:
                        if st.button("❌ Reject", key=f"reject_{row['id']}", use_container_width=True):
                            if reject_user(row['id']):
                                st.warning(f"❌ Rejected {row['full_name']}")
                                st.rerun()
                    st.divider()
        else:
            st.info("🎉 No pending approvals! All users are approved.")

    with tab2:
        if not all_users.empty:
            display_df = all_users.copy()
            display_df['status'] = display_df['is_approved'].apply(lambda x: "✅ Approved" if x == 1 else "⏳ Pending")
            display_df['role'] = display_df['role'].apply(lambda x: "👑 Admin" if x == 'admin' else "👤 User")

            st.dataframe(
                display_df[['id', 'email', 'full_name', 'role', 'status', 'created_at']],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "id": st.column_config.NumberColumn("ID", width="small"),
                    "email": st.column_config.TextColumn("Email", width="medium"),
                    "full_name": st.column_config.TextColumn("Full Name", width="medium"),
                    "role": st.column_config.TextColumn("Role", width="small"),
                    "status": st.column_config.TextColumn("Status", width="small"),
                    "created_at": st.column_config.TextColumn("Registered", width="medium")
                }
            )
            st.caption(f"📊 Total users: {len(all_users)}")
        else:
            st.info("No users found in database")

    with tab3:
        st.subheader("🗑️ Delete User")
        st.warning("⚠️ **Note:** When you delete a user, an email notification will be sent to the admin.")

        users_df = get_all_users()

        if not users_df.empty:
            current_user_email = st.session_state['user']['email']
            other_users = users_df[users_df['email'] != current_user_email]

            if not other_users.empty:
                other_users['display'] = other_users.apply(
                    lambda x: f"{x['full_name']} ({x['email']})", axis=1
                )

                selected_display = st.selectbox(
                    "👤 Select user to delete",
                    other_users['display'].tolist(),
                    key="delete_user_select"
                )

                selected_user = other_users[other_users['display'] == selected_display].iloc[0]
                user_id = int(selected_user['id'])

                st.info(f"""
                **User Details:**
                - **Name:** {selected_user['full_name']}
                - **Email:** {selected_user['email']}
                - **Role:** {selected_user['role']}
                - **ID:** {user_id}
                """)

                delete_confirmation = st.checkbox("✓ I understand this action cannot be undone")
                if delete_confirmation:
                    if st.button("🗑️ **Confirm Delete**", use_container_width=True, type="primary"):
                        with st.spinner("Deleting user..."):
                            success, message = delete_user(user_id)
                            if success:
                                st.success(f"✅ {message}")
                                st.balloons()
                                st.rerun()
                            else:
                                st.error(f"❌ Delete failed: {message}")
            else:
                st.info("ℹ️ No other users to delete (you are the only user)")
        else:
            st.info("No users found in database")

def show_dashboard():
    st.markdown("""
    <style>
    * {
        font-family: 'Times New Roman', Times, serif !important;
    }
    .welcome-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 20px;
        color: white;
        margin-bottom: 2rem;
    }
    .quick-stat {
        background: white;
        border-radius: 15px;
        padding: 1.5rem;
        text-align: center;
        transition: transform 0.3s ease;
    }
    .quick-stat:hover {
        transform: translateY(-5px);
    }
    </style>
    """, unsafe_allow_html=True)

    user = st.session_state['user']

    st.markdown(f"""
    <div class="welcome-header">
        <h1 style="margin: 0; font-family: 'Times New Roman', Times, serif;">👋 Welcome, {user['full_name']}!</h1>
        <p style="margin: 0.5rem 0 0 0; opacity: 0.9; font-family: 'Times New Roman', Times, serif;">You have successfully logged in to the Health Program Medicines Dashboard</p>
    </div>
    """, unsafe_allow_html=True)

    # Quick stats
    all_users = get_all_users()
    pending_users = get_pending_users()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"""
        <div class="quick-stat">
            <div style="font-size: 2.5rem;">👥</div>
            <div style="font-size: 1.8rem; font-weight: bold; font-family: 'Times New Roman', Times, serif;">{len(all_users)}</div>
            <div style="font-family: 'Times New Roman', Times, serif;">Total Users</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="quick-stat">
            <div style="font-size: 2.5rem;">⏳</div>
            <div style="font-size: 1.8rem; font-weight: bold; font-family: 'Times New Roman', Times, serif;">{len(pending_users)}</div>
            <div style="font-family: 'Times New Roman', Times, serif;">Pending Approvals</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class="quick-stat">
            <div style="font-size: 2.5rem;">🔑</div>
            <div style="font-size: 1.8rem; font-weight: bold; font-family: 'Times New Roman', Times, serif;">{user['role'].title()}</div>
            <div style="font-family: 'Times New Roman', Times, serif;">Your Role</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # Getting started guide
    with st.expander("🚀 **Getting Started Guide**", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("""
            ### 📋 Quick Tips
            1. Use the sidebar to navigate between sections
            2. Select a program from the dropdown to filter data
            3. Use search to find specific medicines
            4. Toggle between Table View and Card View
            """)
        with col2:
            st.markdown("""
            ### 💡 Pro Tips
            - 📊 Monitor KPIs in the Analytics tab
            - 🚚 Track pipeline orders in real-time
            - 📍 Check hub distribution patterns
            - 📥 Download reports for offline analysis
            """)

# Main app logic
def main():
    init_session_state()

    if st.session_state['auth']:
        check_session_validity()

    st.markdown("""
    <style>
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #667eea 0%, #764ba2 100%);
    }

    [data-testid="stSidebar"] * {
        color: white !important;
        font-family: 'Times New Roman', Times, serif !important;
    }

    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stRadio label {
        color: white !important;
        font-weight: bold;
        font-family: 'Times New Roman', Times, serif !important;
    }

    [data-testid="stSidebar"] .stButton button {
        background: rgba(255,255,255,0.2);
        border: 1px solid rgba(255,255,255,0.3);
        font-family: 'Times New Roman', Times, serif !important;
    }

    [data-testid="stSidebar"] .stButton button:hover {
        background: rgba(255,255,255,0.3);
    }

    /* Main content area */
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    }

    /* Tab styling */
    button[data-baseweb="tab"] {
        font-size: 16px;
        font-weight: 600;
        transition: all 0.3s ease;
        font-family: 'Times New Roman', Times, serif !important;
    }

    button[data-baseweb="tab"]:hover {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white !important;
    }

    /* All text elements */
    .stMarkdown, .stText, .stCaption, label, .stMetric {
        font-family: 'Times New Roman', Times, serif !important;
    }
    </style>
    """, unsafe_allow_html=True)

    if st.session_state['auth']:
        with st.sidebar:
            # User avatar
            user = st.session_state['user']
            initials = ''.join([word[0].upper() for word in user['full_name'].split()[:2]])
            st.markdown(f"""
            <div style="text-align: center; margin-bottom: 2rem;">
                <div style="width: 60px; height: 60px; background: rgba(255,255,255,0.2); 
                            border-radius: 30px; display: flex; align-items: center; justify-content: center; 
                            margin: 0 auto 0.5rem auto;">
                    <span style="font-size: 24px; color: white; font-weight: bold; font-family: 'Times New Roman', Times, serif;">{initials}</span>
                </div>
                <h3 style="margin: 0; color: white; font-family: 'Times New Roman', Times, serif;">{user['full_name']}</h3>
                <p style="margin: 0; opacity: 0.8; font-family: 'Times New Roman', Times, serif;">{user['role'].title()}</p>
            </div>
            """, unsafe_allow_html=True)

            st.divider()

            if st.session_state['user']['role'] == 'admin':
                pages = ["📊 Dashboard", "👤 Profile", "👑 Admin Panel"]
            else:
                pages = ["📊 Dashboard", "👤 Profile"]

            page = st.radio(
                "Navigation",
                pages,
                key="navigation",
                label_visibility="collapsed"
            )

            st.divider()

            if st.session_state.get('login_time'):
                st.caption(f"🕐 Logged in: {st.session_state['login_time'].strftime('%Y-%m-%d %H:%M:%S')}")
                st.caption("✨ Session never expires")

            if st.button("🚪 Logout", use_container_width=True):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()

        # Main content
        if page == "📊 Dashboard":
            show_dashboard()
        elif page == "👤 Profile":
            show_profile_page()
        elif page == "👑 Admin Panel" and st.session_state['user']['role'] == 'admin':
            show_admin_panel()
    else:
        show_login_page()

if __name__ == "__main__":
    main()
