import os
import json
from datetime import datetime, timedelta
from cryptography.fernet import Fernet

# Generate a key for encryption
def generate_encryption_key():
    return Fernet.generate_key().decode()

# Load environment variables
def load_environment():
    """Load environment varisables from .env file for local development,
    or use Streamlit secrets in production"""
    try:
        import dotenv
        dotenv.load_dotenv()
    except ImportError:
        pass  # .env file not found, assume we're using Streamlit secrets

# Get a config value, checking both environment and Streamlit secrets
def get_config(key, default=None):
    """Get configuration from environment variables or Streamlit secrets"""
    import streamlit as st
    
    # First try environment variables (local development)
    value = os.environ.get(key)
    
    # If not found, try Streamlit secrets (production)
    if value is None:
        try:
            value = st.secrets[key]
        except (KeyError, TypeError):
            value = default
            
    return value

# Format a date for display
def format_date(date_obj):
    if isinstance(date_obj, datetime):
        return date_obj.strftime("%Y-%m-%d %H:%M:%S")
    return str(date_obj)