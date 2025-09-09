#!/usr/bin/env python3
"""Fixed Authentication API client implementation."""

import sys
import os
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from dotenv import load_dotenv, set_key, find_dotenv
import httpx
from api.base_client import BaseAPIClient
from config.logging_setup import setup_logging, get_logger

logger = get_logger(__name__)

class AuthAPIClient(BaseAPIClient):
    """Client for handling authentication and token management."""
    
    def __init__(self, config):
        super().__init__(config)
        setup_logging()
        # Load environment variables
        load_dotenv()
        self.username = os.getenv("NMC_USERNAME")
        self.password = os.getenv("NMC_PASSWORD")
        # Find the .env file path once during initialization
        self.env_file_path = find_dotenv() or '.env'
        logger.debug(f"Using .env file at: {self.env_file_path}")
    
    async def login(self, username: str = None, password: str = None) -> Dict[str, Any]:
        """Login and get a fresh token."""
        # Use provided credentials or fall back to environment variables
        login_username = username or self.username
        login_password = password or self.password
        
        if not login_username or not login_password:
            return {
                "error": "Username and password are required. Set NMC_USERNAME and NMC_PASSWORD in .env file."
            }
        
        print(f"Attempting login for user: {login_username}", file=sys.stderr)

        login_data = {
            "username": login_username,
            "password": login_password
        }
        
        # Build URL manually to ensure we're using the right base
        url = f"{self.base_url}/api/v1.2/auth/login/"
        
        # Create completely clean headers with NO auth
        clean_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        # Debug logging
        logger.debug(f"Making POST request to: {url}")
        logger.debug(f"SSL Verification: {self.config.verify_ssl}")
        logger.debug(f"Headers: {clean_headers}", file=sys.stderr)
        logger.debug(f"Request body: {login_data}", file=sys.stderr)
        
        try:
            # Create a completely fresh HTTP client
            async with httpx.AsyncClient(
                verify=self.config.verify_ssl,
                timeout=self.config.timeout
            ) as client:
                
                response = await client.post(
                    url=url,
                    headers=clean_headers,
                    json=login_data
                )
                
                logger.debug(f"Response status: {response.status_code}")
                
                # Check for HTTP errors
                response.raise_for_status()
                
                # Parse successful response
                result = response.json()
                
                if "token" in result:
                    new_token = result["token"]
                    expires = result.get("expires", "")
                    
                    print(f"✅ Login successful, token expires: {expires}", file=sys.stderr)
                    
                    # Update environment variables in memory
                    os.environ["API_TOKEN"] = new_token
                    os.environ["API_TOKEN_EXPIRES"] = expires
                    
                    # Save to .env file using python-dotenv's set_key
                    try:
                        set_key(self.env_file_path, "API_TOKEN", new_token)
                        set_key(self.env_file_path, "API_TOKEN_EXPIRES", expires)
                        print(f"✅ Token saved to {self.env_file_path}", file=sys.stderr)
                    except Exception as e:
                        print(f"⚠️ Warning: Could not save token to .env file: {e}", file=sys.stderr)
                    
                    # Update the config object for immediate use
                    self.config.token = new_token
                    
                    # Update the headers in the base client for subsequent requests
                    self.headers["Authorization"] = f"Token {new_token}"
                    
                    
                    return {
                        "success": True,
                        "token": new_token,
                        "expires": expires
                    }
                else:
                    error_msg = result.get('error', 'No token in response')
                    print(f"❌ Login failed: {error_msg}", file=sys.stderr)
                    return {"error": error_msg}
                
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {str(e)}"
            print(f"❌ Login HTTP error: {error_msg}", file=sys.stderr)
            
            try:
                error_details = e.response.json()
                return {"error": error_msg, "details": error_details, "status_code": e.response.status_code}
            except:
                return {"error": error_msg, "status_code": e.response.status_code}
                
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Login exception: {error_msg}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            return {"error": error_msg}
    
    async def refresh_token_and_update_env(self) -> Dict[str, Any]:
        """Get a fresh token and update the .env file."""
        print("🔄 Refreshing authentication token...", file=sys.stderr)
        
        # Get fresh token
        login_response = await self.login()
        
        if "error" in login_response:
            return login_response
        
        if login_response.get("success"):
            return {
                "success": True,
                "token": login_response.get("token"),
                "expires": login_response.get("expires"),
                "message": "Token refreshed and .env file updated"
            }
        else:
            return {"error": "Failed to refresh token"}
    
    def is_token_expired(self) -> bool:
        """Check if the current token is expired or will expire soon."""
        # Check both possible environment variable names
        expires_str = os.getenv("API_TOKEN_EXPIRES") or os.getenv("FILERS_TOKEN_EXPIRES")
        
        if not expires_str:
            print("⚠️ No token expiration info found", file=sys.stderr)
            return True  # No expiration info, assume expired
        
        try:
            # Parse the expiration time: "2025-08-09T08:00:27UTC"
            expires_str_clean = expires_str.replace("UTC", "+00:00")
            expires_time = datetime.fromisoformat(expires_str_clean)
            
            # Check if token expires within the next 10 minutes
            now = datetime.now(expires_time.tzinfo)
            time_until_expiry = expires_time - now
            
            is_expired = time_until_expiry < timedelta(minutes=10)
            
            if is_expired:
                print(f"⚠️ Token is expired or expiring soon (expires: {expires_str})", file=sys.stderr)
            else:
                print(f"✅ Token is valid until {expires_str}", file=sys.stderr)
            
            return is_expired
            
        except Exception as e:
            print(f"⚠️ Error parsing token expiration: {e}", file=sys.stderr)
            return True  # Assume expired if we can't parse
    
    async def ensure_valid_token(self) -> Dict[str, Any]:
        """Ensure we have a valid, non-expired token."""
        if self.is_token_expired():
            print("🔄 Token is expired or missing, refreshing...", file=sys.stderr)
            return await self.refresh_token_and_update_env()
        else:
            print("✅ Token is still valid", file=sys.stderr)
            return {"success": True, "message": "Token is still valid"}
    
    async def test_connection(self) -> bool:
        """Test the API connection."""
        try:
            # Try a simple API call to test authentication
            response = await self.get("/api/v1.2/filers/")
            return "error" not in response
        except Exception as e:
            print(f"Connection test failed: {e}", file=sys.stderr)
            return False
    
    def get_token_info(self) -> Dict[str, Any]:
        """Get information about the current token."""
        # Check both possible environment variable names
        token = os.getenv("API_TOKEN") or os.getenv("FILERS_API_TOKEN")
        expires = os.getenv("API_TOKEN_EXPIRES") or os.getenv("FILERS_TOKEN_EXPIRES")
        
        info = {
            "has_token": bool(token),
            "token_preview": f"{token[:8]}...{token[-8:]}" if token and len(token) > 16 else "No token",
            "expires": expires,
            "is_expired": self.is_token_expired()
        }
        
        if expires:
            try:
                expires_str_clean = expires.replace("UTC", "+00:00")
                expires_time = datetime.fromisoformat(expires_str_clean)
                now = datetime.now(expires_time.tzinfo)
                time_until_expiry = expires_time - now
                
                if time_until_expiry.total_seconds() > 0:
                    info["time_until_expiry"] = str(time_until_expiry).split('.')[0]  # Remove microseconds
                else:
                    info["time_until_expiry"] = "Expired"
                    
            except Exception:
                info["time_until_expiry"] = "Unknown"
        
        # Also show where the .env file is located
        info["env_file_path"] = self.env_file_path
        
        return info