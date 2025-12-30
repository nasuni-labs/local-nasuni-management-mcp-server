#!/usr/bin/env python3
"""Portal API authentication client with automatic token refresh."""

import sys
import os
import json
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from dotenv import set_key
import httpx
from config.logging_setup import setup_logging, get_logger

logger = get_logger(__name__)


class PortalAuthAPIClient:
    """Client for handling Portal authentication with service keys."""
    
    def __init__(self, config):
        """
        Initialize Portal authentication client.
        
        Args:
            config: Configuration object with base_url, service_key, service_secret, etc.
        """
        setup_logging()
        self.config = config
        self.base_url = config.base_url.rstrip('/')
        self.service_key = os.getenv("PORTAL_SERVICE_KEY")
        self.service_secret = os.getenv("PORTAL_SERVICE_SECRET")
        self.access_token = os.getenv("PORTAL_ACCESS_TOKEN")
        self.refresh_token = os.getenv("PORTAL_REFRESH_TOKEN")
        self.token_expires_at = None
        
        # Parse token expiration if we have a cached token
        if self.access_token:
            self.token_expires_at = self._parse_token_expiration(self.access_token)
    
    def _parse_token_expiration(self, token: str) -> Optional[datetime]:
        """Parse JWT token to get expiration time."""
        try:
            import base64
            # JWT format: header.payload.signature
            parts = token.split('.')
            if len(parts) != 3:
                return None
            
            # Decode payload (add padding if needed)
            payload = parts[1]
            payload += '=' * (4 - len(payload) % 4)
            decoded = base64.urlsafe_b64decode(payload)
            payload_data = json.loads(decoded)
            
            # Get expiration timestamp
            exp = payload_data.get('exp')
            if exp:
                return datetime.fromtimestamp(exp)
            
        except Exception as e:
            logger.debug(f"Could not parse token expiration: {e}")
        
        return None
    
    def is_token_expired(self) -> bool:
        """
        Check if the current access token is expired or will expire soon.
        Uses a 2-minute buffer for safety.
        """
        if not self.access_token:
            logger.debug("No access token available")
            return True
        
        if not self.token_expires_at:
            logger.debug("Cannot determine token expiration, assuming expired")
            return True
        
        # Check if token expires within the next 2 minutes (safety buffer)
        now = datetime.now()
        buffer = timedelta(minutes=2)
        
        is_expired = (self.token_expires_at - now) < buffer
        
        if is_expired:
            logger.debug(f"Token expired or expiring soon (expires at {self.token_expires_at})")
        else:
            time_remaining = self.token_expires_at - now
            logger.debug(f"Token valid for {time_remaining.total_seconds():.0f} more seconds")
        
        return is_expired
    
    async def authenticate(self) -> Dict[str, Any]:
        """
        Authenticate with Portal using service key and secret.
        Returns tokens and saves them to environment.
        """
        if not self.service_key or not self.service_secret:
            return {
                "error": "Portal service key and secret are required. Set PORTAL_SERVICE_KEY and PORTAL_SERVICE_SECRET in .env file."
            }
        
        logger.info(f"Authenticating with Portal at {self.base_url}")
        
        auth_url = f"{self.base_url}/auth/token"
        
        # Build headers exactly as shown in the curl example
        headers = {
            "x-service-key": self.service_key,
            "x-service-secret": self.service_secret,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Note: The curl example shows an Authorization header with a Bearer token,
        # but for initial authentication, we only need service key/secret
        # The Bearer token is what we GET from this call
        
        logger.debug(f"POST {auth_url}")
        logger.debug(f"Headers: x-service-key={self.service_key[:20]}..., x-service-secret=***")
        
        try:
            async with httpx.AsyncClient(
                verify=self.config.verify_ssl,
                timeout=self.config.timeout
            ) as client:
                
                response = await client.post(
                    url=auth_url,
                    headers=headers,
                    json={}  # Empty body as shown in curl example
                )
                
                logger.debug(f"Response status: {response.status_code}")
                
                # Try to get response body for debugging
                try:
                    response_body = response.json()
                    logger.debug(f"Response body: {json.dumps(response_body, indent=2)}")
                except:
                    response_body = response.text
                    logger.debug(f"Response text: {response_body}")
                
                # Check for HTTP errors
                response.raise_for_status()
                
                # Parse successful response
                result = response.json()
                
                if "access_token" in result:
                    logger.info("✅ Portal authentication successful")
                    
                    # Extract tokens
                    access_token = result["access_token"]
                    refresh_token = result.get("refresh_token", "")
                    
                    # Parse expiration
                    expires_at = self._parse_token_expiration(access_token)
                    
                    # Update instance variables
                    self.access_token = access_token
                    self.refresh_token = refresh_token
                    self.token_expires_at = expires_at
                    
                    # Update environment variables
                    os.environ["PORTAL_ACCESS_TOKEN"] = access_token
                    os.environ["PORTAL_REFRESH_TOKEN"] = refresh_token
                    
                    # Save to .env file for persistence
                    self._update_env_file(access_token, refresh_token)
                    
                    return {
                        "success": True,
                        "access_token": access_token,
                        "refresh_token": refresh_token,
                        "expires_at": expires_at.isoformat() if expires_at else "unknown",
                        "message": "Portal authentication successful"
                    }
                else:
                    logger.error(f"No access_token in response: {result}")
                    return {"error": "No access_token in response", "details": result}
                    
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {str(e)}"
            logger.error(f"Portal authentication HTTP error: {error_msg}")
            
            # Try to get error details from response
            try:
                error_details = e.response.json()
                logger.error(f"Error details: {error_details}")
                return {"error": error_msg, "details": error_details, "status_code": e.response.status_code}
            except:
                return {"error": error_msg, "status_code": e.response.status_code}
                
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Portal authentication exception: {error_msg}")
            import traceback
            traceback.print_exc(file=sys.stderr)
            return {"error": error_msg}
    
    def _update_env_file(self, access_token: str, refresh_token: str):
        """Update the .env file with new tokens."""
        env_file_path = ".env"
        
        try:
            # Read current .env content
            if os.path.exists(env_file_path):
                with open(env_file_path, 'r') as f:
                    lines = f.readlines()
            else:
                lines = []
            
            # Update or add token lines
            updated_lines = []
            access_found = False
            refresh_found = False
            
            for line in lines:
                if line.startswith("PORTAL_ACCESS_TOKEN="):
                    updated_lines.append(f"PORTAL_ACCESS_TOKEN={access_token}\n")
                    access_found = True
                elif line.startswith("PORTAL_REFRESH_TOKEN="):
                    updated_lines.append(f"PORTAL_REFRESH_TOKEN={refresh_token}\n")
                    refresh_found = True
                else:
                    updated_lines.append(line)
            
            # Add if not found
            if not access_found:
                updated_lines.append(f"PORTAL_ACCESS_TOKEN={access_token}\n")
            if not refresh_found:
                updated_lines.append(f"PORTAL_REFRESH_TOKEN={refresh_token}\n")
            
            # Write back
            with open(env_file_path, 'w') as f:
                f.writelines(updated_lines)
            
            logger.debug(f"Updated tokens in {env_file_path}")
            
        except Exception as e:
            logger.error(f"Failed to update .env file: {e}")
    
    async def ensure_valid_token(self) -> Dict[str, Any]:
        """
        Ensure we have a valid access token.
        If token is expired or missing, authenticate to get a new one.
        """
        if self.is_token_expired():
            logger.info("Portal token expired or missing, re-authenticating...")
            return await self.authenticate()
        else:
            logger.debug("Portal token is still valid")
            return {
                "success": True,
                "access_token": self.access_token,
                "message": "Token is still valid",
                "expires_at": self.token_expires_at.isoformat() if self.token_expires_at else "unknown"
            }
    
    def get_valid_token(self) -> Optional[str]:
        """
        Get a valid access token synchronously.
        This is a helper for API clients to use.
        Returns None if token is invalid and needs refresh.
        """
        if not self.is_token_expired():
            return self.access_token
        return None
    
    def get_token_info(self) -> Dict[str, Any]:
        """Get information about the current token."""
        info = {
            "has_token": bool(self.access_token),
            "has_refresh_token": bool(self.refresh_token),
            "token_preview": f"{self.access_token[:20]}...{self.access_token[-20:]}" if self.access_token and len(self.access_token) > 40 else "No token",
            "is_expired": self.is_token_expired()
        }
        
        if self.token_expires_at:
            info["expires_at"] = self.token_expires_at.isoformat()
            
            if not self.is_token_expired():
                now = datetime.now()
                time_remaining = self.token_expires_at - now
                minutes = int(time_remaining.total_seconds() / 60)
                seconds = int(time_remaining.total_seconds() % 60)
                info["time_until_expiry"] = f"{minutes}m {seconds}s"
            else:
                info["time_until_expiry"] = "Expired"
        else:
            info["expires_at"] = "Unknown"
            info["time_until_expiry"] = "Unknown"
        
        return info
    
    async def test_connection(self) -> bool:
        """Test the Portal API connection by attempting authentication."""
        try:
            result = await self.ensure_valid_token()
            return "error" not in result
        except Exception:
            return False