import secrets
import requests
import streamlit as st
from token_manager import TokenManager
from utils import get_config

class MetaAuth:
    def __init__(self, token_manager):
        """Initialize with the token manager for storing tokens"""
        self.token_manager = token_manager
        self.app_id = get_config("META_APP_ID")
        self.app_secret = get_config("META_APP_SECRET")
        self.redirect_uri = get_config("REDIRECT_URI")
        
        if not all([self.app_id, self.app_secret, self.redirect_uri]):
            raise ValueError("Missing required Meta API credentials")
    
    def generate_auth_url(self, state):
        """Generate the Meta OAuth URL for user authentication"""
        auth_url = "https://www.facebook.com/v18.0/dialog/oauth"
        
        params = {
            'client_id': self.app_id,
            'redirect_uri': self.redirect_uri,
            'state': state,
            'scope': 'pages_read_engagement,instagram_basic,instagram_manage_insights,business_management,ads_read'
        }
        
        # Build the URL with query parameters
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        return f"{auth_url}?{query_string}"
    
    def exchange_code_for_token(self, code):
        """Exchange an authorization code for an access token"""
        token_url = "https://graph.facebook.com/v18.0/oauth/access_token"
        
        response = requests.get(token_url, params={
            'client_id': self.app_id,
            'client_secret': self.app_secret,
            'redirect_uri': self.redirect_uri,
            'code': code
        })
        
        response.raise_for_status()  # Raise exception for HTTP errors
        return response.json()
    
    def get_long_lived_token(self, access_token):
        """Exchange a short-lived token for a long-lived token"""
        token_url = "https://graph.facebook.com/v18.0/oauth/access_token"
        
        response = requests.get(token_url, params={
            'grant_type': 'fb_exchange_token',
            'client_id': self.app_id,
            'client_secret': self.app_secret,
            'fb_exchange_token': access_token
        })
        
        response.raise_for_status()
        return response.json()
    
    def get_user_info(self, access_token):
        """Get user details from Meta Graph API"""
        response = requests.get("https://graph.facebook.com/v18.0/me", params={
            'access_token': access_token,
            'fields': 'id,name,email'
        })
        
        response.raise_for_status()
        return response.json()
    
    def get_pages(self, access_token):
        """Get pages the user has access to"""
        response = requests.get("https://graph.facebook.com/v18.0/me/accounts", params={
            'access_token': access_token,
            'fields': 'id,name,access_token,category,instagram_business_account{id,name,username}'
        })
        
        if response.status_code == 200:
            return response.json().get('data', [])
        else:
            # Handle case where user has no pages
            return []
    
    def get_instagram_accounts(self, access_token):
        """Get connected Instagram accounts"""
        try:
            response = requests.get("https://graph.facebook.com/v18.0/me/accounts", params={
                'access_token': access_token,
                'fields': 'instagram_business_account{id,name,username}'
            })
            
            response.raise_for_status()
            accounts = []
            
            for page in response.json().get('data', []):
                if 'instagram_business_account' in page:
                    ig_account = page['instagram_business_account']
                    ig_account['page_id'] = page['id']
                    accounts.append(ig_account)
            
            return accounts
        except Exception as e:
            st.error(f"Error fetching Instagram accounts: {str(e)}")
            return []
    
    def complete_oauth_flow(self, user_id, code):
        """Complete the entire OAuth flow from code to stored tokens"""
        try:
            # Exchange code for short-lived token
            token_data = self.exchange_code_for_token(code)
            access_token = token_data['access_token']
            
            # Exchange for long-lived token
            long_lived_data = self.get_long_lived_token(access_token)
            long_lived_token = long_lived_data['access_token']
            expires_in = long_lived_data['expires_in']
            
            # Get user information
            user_info = self.get_user_info(long_lived_token)
            meta_user_id = user_info['id']
            
            # Get pages
            pages = self.get_pages(long_lived_token)
            
            # Store tokens
            success = self.token_manager.store_user_token(
                user_id, meta_user_id, long_lived_token, expires_in, pages
            )
            
            if not success:
                return None
            
            return {
                'user_info': user_info,
                'pages': pages
            }
        except Exception as e:
            st.error(f"Error completing OAuth flow: {str(e)}")
            return None
    
    def store_existing_token(self, user_id, access_token, expiry_days=60):
        """Store an existing token"""
        try:
            # Check if token is valid
            user_info = self.get_user_info(access_token)
            meta_user_id = user_info['id']
            
            # Get pages
            pages = self.get_pages(access_token)
            
            # Calculate expiry (typically 60 days for long-lived tokens)
            expires_in = expiry_days * 24 * 60 * 60
            
            # Store the token
            success = self.token_manager.store_user_token(
                user_id, meta_user_id, access_token, expires_in, pages
            )
            
            return success
        except Exception as e:
            st.error(f"Error storing existing token: {str(e)}")
            return False