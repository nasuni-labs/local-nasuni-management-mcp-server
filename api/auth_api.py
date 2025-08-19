#!/usr/bin/env python3
"""Authentication API client implementation."""

import sys
import os
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import httpx
from api.base_client import BaseAPIClient


class AuthAPIClient(BaseAPIClient):
    """Client for handling authentication and token management."""
    
    def __init__(self, config):
        super().__init__(config)
        self.username = os.getenv("NMC_USERNAME")
        self.password = os.getenv("NMC_PASSWORD")
    
    import httpx

    async def login(self, username: str = None, password: str = None) -> Dict[str, Any]:
        """Login and get a fresh token."""
        # Use provided credentials or fall back to environment variables
        login_username = username or self.username
        login_password = password or self.password
        
        if not login_username or not login_password:
            return {
                "error": "Username and password are required. Set FILERS_USERNAME and FILERS_PASSWORD in .env file."
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
        print(f"Making POST request to: {url}", file=sys.stderr)
        print(f"SSL Verification: {self.config.verify_ssl}", file=sys.stderr)
        print(f"Headers: {clean_headers}", file=sys.stderr)
        print(f"Request body: {login_data}", file=sys.stderr)
        
        try:
            # Create a completely fresh HTTP client
            async with httpx.AsyncClient(
                verify=self.config.verify_ssl,
                timeout=self.config.timeout
            ) as client:
                
                response = await client.post(
                    url=url,
                    headers=clean_headers,  # Use our clean headers
                    json=login_data
                )
                
                print(f"Response status: {response.status_code}", file=sys.stderr)
                print(f"Response headers: {dict(response.headers)}", file=sys.stderr)
                
                # Try to get response body even on error for debugging
                try:
                    response_body = response.json()
                    print(f"Response body: {response_body}", file=sys.stderr)
                except:
                    response_body = response.text
                    print(f"Response text: {response_body}", file=sys.stderr)
                
                # Check for HTTP errors
                response.raise_for_status()
                
                # Parse successful response
                result = response.json()
                
                if "token" in result:
                    print(f"✅ Login successful, token expires: {result.get('expires')}", file=sys.stderr)
                    # Set the token to environment variables
                    new_token = result["token"]
                    os.environ["FILERS_API_TOKEN"] = new_token
                    os.environ["API_TOKEN"] = new_token
                    
                    # Also update the config object for immediate use
                    self.config.token = new_token
                    
                    # Update the headers in the base client for subsequent requests
                    self.headers = self._build_headers(new_token)                    
                else:
                    print(f"❌ Login failed: {result.get('error', 'No token in response')}", file=sys.stderr)
                
                return result
                
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {str(e)}"
            print(f"❌ Login HTTP error: {error_msg}", file=sys.stderr)
            
            # Try to get error details from response
            try:
                error_details = e.response.json()
                print(f"Error details: {error_details}", file=sys.stderr)
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
        
        new_token = login_response.get("token")
        expires = login_response.get("expires")
        
        if not new_token:
            return {"error": "No token received from login response"}
        
        # Update .env file
        try:
            self._update_env_file(new_token, expires)
            print(f"✅ Token updated in .env file, expires: {expires}", file=sys.stderr)
            
            # Update the current client's headers
            self.headers["Authorization"] = f"Token {new_token}"
            
            return {
                "success": True,
                "token": new_token,
                "expires": expires,
                "message": "Token refreshed and .env file updated"
            }
            
        except Exception as e:
            print(f"❌ Failed to update .env file: {e}", file=sys.stderr)
            return {"error": f"Failed to update .env file: {str(e)}"}
    
    def _update_env_file(self, new_token: str, expires: str):
        """Update the .env file with the new token."""
        env_file_path = ".env"
        
        # Read current .env content
        if os.path.exists(env_file_path):
            with open(env_file_path, 'r') as f:
                lines = f.readlines()
        else:
            lines = []
        
        # Find and update the token line, or add it
        token_updated = False
        expires_updated = False
        new_lines = []
        
        for line in lines:
            if line.startswith("FILERS_API_TOKEN="):
                new_lines.append(f"FILERS_API_TOKEN={new_token}\n")
                token_updated = True
            elif line.startswith("FILERS_TOKEN_EXPIRES="):
                new_lines.append(f"FILERS_TOKEN_EXPIRES={expires}\n")
                expires_updated = True
            else:
                new_lines.append(line)
        
        # Add token if it wasn't found
        if not token_updated:
            new_lines.append(f"FILERS_API_TOKEN={new_token}\n")
        
        # Add expiration if it wasn't found
        if not expires_updated:
            new_lines.append(f"FILERS_TOKEN_EXPIRES={expires}\n")
        
        # Write back to .env file
        with open(env_file_path, 'w') as f:
            f.writelines(new_lines)
    
    def is_token_expired(self) -> bool:
        """Check if the current token is expired or will expire soon."""
        expires_str = os.getenv("FILERS_TOKEN_EXPIRES")
        if not expires_str:
            return True  # No expiration info, assume expired
        
        try:
            # Parse the expiration time: "2025-08-09T08:00:27UTC"
            expires_str_clean = expires_str.replace("UTC", "+00:00")
            expires_time = datetime.fromisoformat(expires_str_clean)
            
            # Check if token expires within the next 10 minutes
            now = datetime.now(expires_time.tzinfo)
            time_until_expiry = expires_time - now
            
            return time_until_expiry < timedelta(minutes=10)
            
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
        except Exception:
            return False
    
    def get_token_info(self) -> Dict[str, Any]:
        """Get information about the current token."""
        token = os.getenv("FILERS_API_TOKEN")
        expires = os.getenv("FILERS_TOKEN_EXPIRES")
        
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
        
        return info