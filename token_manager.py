import json
from datetime import datetime, timedelta
import snowflake.connector
from cryptography.fernet import Fernet
import streamlit as st
from utils import get_config

class TokenManager:
    def __init__(self):
        """Initialize the token manager with encryption key"""
        # Get encryption key from config
        encryption_key = get_config("ENCRYPTION_KEY")
        if not encryption_key:
            raise ValueError("Encryption key not found. Set ENCRYPTION_KEY in environment or secrets.")
        
        # Initialize encryption
        self.fernet = Fernet(encryption_key.encode())
        
        # Create table if it doesn't exist
        self._create_table_if_not_exists()
    
    def _get_snowflake_connection(self):
        """Create a connection to Snowflake"""
        return snowflake.connector.connect(
            user=get_config("SNOWFLAKE_USER"),
            password=get_config("SNOWFLAKE_PASSWORD"),
            account=get_config("SNOWFLAKE_ACCOUNT"),
            warehouse=get_config("SNOWFLAKE_WAREHOUSE"),
            database=get_config("SNOWFLAKE_DATABASE"),
            schema=get_config("SNOWFLAKE_SCHEMA")
        )
    
    def _create_table_if_not_exists(self):
        """Table creation is now handled manually in Snowflake"""
        pass  # Table already exists in Snowflake
    
    def encrypt_token(self, token):
        """Encrypt a token using Fernet symmetric encryption"""
        return self.fernet.encrypt(token.encode()).decode()
    
    def decrypt_token(self, encrypted_token):
        """Decrypt a token that was encrypted with Fernet"""
        return self.fernet.decrypt(encrypted_token.encode()).decode()
    
    def store_user_token(self, user_id, meta_user_id, access_token, expires_in, pages=None):
        """Store a user's Meta access token in Snowflake"""
        try:
            conn = self._get_snowflake_connection()
            cursor = conn.cursor()
            
            # Encrypt the token
            encrypted_token = self.encrypt_token(access_token)
            
            # Calculate expiry date
            expiry_date = datetime.now() + timedelta(seconds=expires_in)
            
            # Encrypt and format page tokens if available
            encrypted_pages = None
            if pages:
                encrypted_pages = []
                for page in pages:
                    page_copy = page.copy()
                    if 'access_token' in page_copy:
                        page_copy['access_token'] = self.encrypt_token(page_copy['access_token'])
                    encrypted_pages.append(page_copy)
                encrypted_pages = json.dumps(encrypted_pages)
            
            # Use MERGE to handle upsert logic
            cursor.execute("""
                MERGE INTO META_TOKENS t
                USING (SELECT %s as USER_ID) s
                ON t.USER_ID = s.USER_ID
                WHEN MATCHED THEN
                    UPDATE SET 
                        META_USER_ID = %s,
                        ACCESS_TOKEN = %s,
                        TOKEN_EXPIRY = %s,
                        PAGES = PARSE_JSON(%s),
                        LAST_REFRESHED = CURRENT_TIMESTAMP(),
                        NEEDS_REAUTH = FALSE
                WHEN NOT MATCHED THEN
                    INSERT (USER_ID, META_USER_ID, ACCESS_TOKEN, TOKEN_EXPIRY, PAGES)
                    VALUES (%s, %s, %s, %s, PARSE_JSON(%s))
            """, (user_id, meta_user_id, encrypted_token, expiry_date, encrypted_pages,
                  user_id, meta_user_id, encrypted_token, expiry_date, encrypted_pages))
            
            conn.close()
            return True
        except Exception as e:
            st.error(f"Error storing token: {str(e)}")
            return False
    
    def get_user_token(self, user_id):
        """Retrieve a user's Meta access token from Snowflake"""
        try:
            conn = self._get_snowflake_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT USER_ID, META_USER_ID, ACCESS_TOKEN, TOKEN_EXPIRY, PAGES, NEEDS_REAUTH
                FROM META_TOKENS
                WHERE USER_ID = %s
            """, (user_id,))
            
            record = cursor.fetchone()
            conn.close()
            
            if not record:
                return None
            
            user_id, meta_user_id, encrypted_token, token_expiry, encrypted_pages, needs_reauth = record
            
            # Check if token needs reauthorization
            if needs_reauth:
                return {'needs_reauth': True}
            
            # Check if token is expired
            if token_expiry and token_expiry < datetime.now():
                # Mark token as needing reauthorization
                self._mark_token_for_reauth(user_id)
                return {'needs_reauth': True}
            
            # Decrypt token
            token = self.decrypt_token(encrypted_token)
            
            # Decrypt page tokens if available
            pages = None
            if encrypted_pages:
                pages = []
                for page in encrypted_pages:
                    page_copy = dict(page)
                    if 'access_token' in page_copy:
                        page_copy['access_token'] = self.decrypt_token(page_copy['access_token'])
                    pages.append(page_copy)
            
            return {
                'user_id': user_id,
                'meta_user_id': meta_user_id,
                'access_token': token,
                'token_expiry': token_expiry,
                'pages': pages,
                'needs_reauth': False
            }
        except Exception as e:
            st.error(f"Error retrieving token: {str(e)}")
            return None
    
    def _mark_token_for_reauth(self, user_id):
        """Mark a token as needing reauthorization"""
        try:
            conn = self._get_snowflake_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE META_TOKENS
                SET NEEDS_REAUTH = TRUE
                WHERE USER_ID = %s
            """, (user_id,))
            conn.close()
        except Exception as e:
            st.error(f"Error marking token for reauth: {str(e)}")