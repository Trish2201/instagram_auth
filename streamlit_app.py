import streamlit as st
import secrets
import requests
import json
from datetime import datetime
import time
from utils import load_environment, get_config, format_date
from token_manager import TokenManager
from auth import MetaAuth

# Load environment variables
load_environment()

# Page configuration
st.set_page_config(
    page_title="Meta API Connection Manager",
    page_icon="🔑",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize token manager
@st.cache_resource
def get_token_manager():
    return TokenManager()

# Initialize Meta authentication
@st.cache_resource
def get_meta_auth():
    token_manager = get_token_manager()
    return MetaAuth(token_manager)

token_manager = get_token_manager()
meta_auth = get_meta_auth()

# Initialize session state variables
if 'user_id' not in st.session_state:
    # In a real app, this would come from your user authentication system
    st.session_state.user_id = "default_user"

if 'oauth_state' not in st.session_state:
    st.session_state.oauth_state = secrets.token_hex(16)

# Function to make an API call
def make_api_call(endpoint, params):
    """Make a call to the Graph API"""
    token_data = token_manager.get_user_token(st.session_state.user_id)
    
    if not token_data or token_data.get('needs_reauth'):
        st.error("Authentication required")
        return None
    
    params['access_token'] = token_data['access_token']
    
    try:
        response = requests.get(f"https://graph.facebook.com/v18.0/{endpoint}", params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"API call failed: {str(e)}")
        return None

# Custom CSS
st.markdown("""
<style>
    .main .block-container {
        padding-top: 2rem;
    }
    .stButton button {
        width: 100%;
    }
    .connection-status {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .connected {
        background-color: #d4edda;
        color: #155724;
        border: 1px solid #c3e6cb;
    }
    .not-connected {
        background-color: #f8d7da;
        color: #721c24;
        border: 1px solid #f5c6cb;
    }
</style>
""", unsafe_allow_html=True)

# App title
st.title("Meta API Connection Manager")
st.markdown("Connect Instagram and Facebook accounts to access metrics")

# Handle OAuth callback
if 'code' in st.query_params and 'state' in st.query_params:
    # Verify state to prevent CSRF
    if st.query_params['state'] == st.session_state.oauth_state:
        with st.spinner("Completing authentication..."):
            # Exchange code for token
            result = meta_auth.complete_oauth_flow(
                st.session_state.user_id,
                st.query_params['code']
            )
            
            if result:
                st.success("🎉 Meta account connected successfully!")
                st.write(f"Connected as: {result['user_info'].get('name')}")
                
                # Show connected pages
                if result['pages']:
                    st.write(f"Connected to {len(result['pages'])} pages:")
                    for page in result['pages']:
                        if 'instagram_business_account' in page:
                            ig_info = page['instagram_business_account']
                            st.write(f"- {page['name']} ({page['category']}) with Instagram: {ig_info.get('username')}")
                        else:
                            st.write(f"- {page['name']} ({page['category']})")
                
                # Add a delay and rerun to clear the URL parameters
                time.sleep(2)
                st.rerun()
            else:
                st.error("Failed to complete authentication")
    else:
        st.error("Invalid state parameter - possible security issue")

# Sidebar for connection management
with st.sidebar:
    st.header("Connection Management")
    
    # Check if the user already has a token
    token_data = token_manager.get_user_token(st.session_state.user_id)
    
    if token_data and not token_data.get('needs_reauth'):
        st.markdown('<div class="connection-status connected">✅ Connected to Meta</div>', unsafe_allow_html=True)
        
        if token_data.get('meta_user_id'):
            st.write(f"User ID: {token_data['meta_user_id']}")
        
        if token_data.get('token_expiry'):
            st.write(f"Token expires: {format_date(token_data['token_expiry'])}")
        
        if st.button("Disconnect", key="disconnect"):
            # In a real app, you would delete the token
            st.warning("This would delete your connection")
    else:
        st.markdown('<div class="connection-status not-connected">❌ Not connected to Meta</div>', unsafe_allow_html=True)
        
        # Option 1: Connect via OAuth flow
        # auth_url = meta_auth.generate_auth_url(st.session_state.oauth_state)
        try:
            auth_url = meta_auth.generate_auth_url(st.session_state.oauth_state)
        except Exception as e:
            st.error(f"Error generating Facebook auth URL: {str(e)}")
        raise

        st.write("Auth URL:", auth_url)  # Debug line
        st.markdown(f"<a href='{auth_url}' target='_self'><button style='background-color:#1877F2; color:white; border:none; padding:10px; border-radius:4px; cursor:pointer; width:100%;'>Connect with Facebook</button></a>", unsafe_allow_html=True)
        
        # Option 2: Manually enter existing token
        st.subheader("Or use existing token")
        with st.form("existing_token_form"):
            token = st.text_input("Paste your access token:", type="password")
            submit = st.form_submit_button("Save Token")
            
            if submit and token:
                if meta_auth.store_existing_token(st.session_state.user_id, token):
                    st.success("Token stored successfully")
                    st.rerun()

# Main content tabss
tab1, tab2 = st.tabs(["Dashboard", "API Explorer"])

with tab1:
    st.header("Connected Accounts")
    
    if token_data and not token_data.get('needs_reauth'):
        if token_data.get('pages'):
            # Create a grid layout for pages
            col1, col2, col3 = st.columns(3)
            columns = [col1, col2, col3]
            
            for i, page in enumerate(token_data['pages']):
                col = columns[i % 3]
                with col:
                    st.subheader(page['name'])
                    st.write(f"Category: {page.get('category', 'Unknown')}")
                    
                    # Show Instagram info if available
                    if 'instagram_business_account' in page:
                        ig = page['instagram_business_account']
                        st.write(f"📸 Instagram: {ig.get('username', 'Unknown')}")
        else:
            st.info("No pages found for this account")
    else:
        st.info("Connect to Meta using the sidebar to view your accounts")

with tab2:
    st.header("Meta Graph API Explorer")
    
    # Only show if connected
    if token_data and not token_data.get('needs_reauth'):
        # Show available pages
        if token_data.get('pages'):
            page_options = {page['name']: page['id'] for page in token_data['pages']}
            selected_page = st.selectbox("Select a page", options=list(page_options.keys()))
            selected_page_id = page_options[selected_page]
            
            # Find if this page has Instagram
            selected_page_data = next((p for p in token_data['pages'] if p['id'] == selected_page_id), None)
            has_instagram = 'instagram_business_account' in selected_page_data if selected_page_data else False
            
            # Select Facebook or Instagram metrics
            data_source = st.radio(
                "Select data source",
                options=["Facebook Page", "Instagram Business Account"],
                disabled=not has_instagram
            )
            
            if data_source == "Facebook Page":
                endpoint_id = selected_page_id
                
                st.subheader("Page Insights")
                
                metric_options = [
                    "page_impressions", 
                    "page_engaged_users", 
                    "page_fans", 
                    "page_fan_adds"
                ]
                selected_metrics = st.multiselect(
                    "Select metrics", 
                    options=metric_options,
                    default=["page_impressions"]
                )
            else:
                # Using Instagram metrics
                if has_instagram:
                    ig_account = selected_page_data['instagram_business_account']
                    endpoint_id = ig_account['id']
                    
                    st.subheader("Instagram Insights")
                    
                    metric_options = [
                        "impressions",
                        "reach",
                        "profile_views",
                        "follower_count"
                    ]
                    selected_metrics = st.multiselect(
                        "Select metrics",
                        options=metric_options,
                        default=["follower_count"]
                    )
                else:
                    st.warning("This page does not have an Instagram account connected")
                    st.stop()
            
            period_options = ["day", "week", "month"]
            selected_period = st.selectbox("Select period", options=period_options)
            
            date_preset_options = [
                "today", "yesterday", "this_week", "last_week", 
                "this_month", "last_month", "last_3_months", "last_90_days"
            ]
            selected_date_preset = st.selectbox("Select date range", options=date_preset_options)
            
            if st.button("Get Insights"):
                with st.spinner("Fetching insights..."):
                    insights = make_api_call(
                        f"{endpoint_id}/insights", 
                        {
                            "metric": ",".join(selected_metrics),
                            "period": selected_period,
                            "date_preset": selected_date_preset
                        }
                    )
                    
                    if insights:
                        st.json(insights)
                        
                        # You could add visualization here
                        try:
                            st.subheader("Visualization")
                            # Process and display the data
                            for metric in insights.get('data', []):
                                metric_name = metric['name']
                                values = metric['values']
                                
                                if values and 'value' in values[0]:
                                    # Simple metrics with single values
                                    data = [{'date': v.get('end_time', 'unknown'), 'value': v['value']} for v in values]
                                    st.write(f"**{metric_name}**")
                                    
                                    # Create a simple table
                                    st.dataframe(data)
                        except Exception as e:
                            st.error(f"Error visualizing data: {str(e)}")
    else:
        st.info("Connect to Meta using the sidebar to access Graph API")

# Footer
st.markdown("---")
st.markdown("This application securely manages Meta API connections. Your tokens are encrypted in storage.")