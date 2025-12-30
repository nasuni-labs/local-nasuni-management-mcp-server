#!/usr/bin/env python3
"""Base API client for Portal with automatic token refresh."""

import sys
import httpx
import asyncio
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod
from api.portal_auth_api import PortalAuthAPIClient
from config.logging_setup import get_logger

logger = get_logger(__name__)


class PortalBaseAPIClient(ABC):
    """Base class for Portal API clients with automatic token management."""
    
    def __init__(self, config, auth_client: PortalAuthAPIClient):
        """
        Initialize Portal base client.
        
        Args:
            config: Configuration object with base_url, timeout, verify_ssl
            auth_client: Portal authentication client for token management
        """
        self.config = config
        self.base_url = config.base_url.rstrip('/')
        self.auth_client = auth_client
    
    def _build_headers(self) -> Dict[str, str]:
        """Build headers for API requests with current access token."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        # Get current valid token
        token = self.auth_client.get_valid_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        
        return headers
    
    async def _ensure_authenticated(self) -> bool:
        """
        Ensure we have a valid authentication token.
        If token is expired, automatically refresh it.
        
        Returns:
            True if authenticated, False otherwise
        """
        result = await self.auth_client.ensure_valid_token()
        
        if "error" in result:
            logger.error(f"Portal authentication failed: {result['error']}")
            return False
        
        return True
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        max_retries: int = 1,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make an HTTP request with automatic token refresh on 401 errors.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (e.g., '/appliances')
            max_retries: Number of times to retry on 401 (default: 1)
            **kwargs: Additional arguments for httpx request
            
        Returns:
            Dict with response data or error
        """
        url = f"{self.base_url}{endpoint}"
        
        # Log request details
        logger.debug(f"Making {method} request to: {url}")
        logger.debug(f"SSL Verification: {self.config.verify_ssl}")
        
        for attempt in range(max_retries + 1):
            # Ensure we have a valid token before making request
            authenticated = await self._ensure_authenticated()
            if not authenticated:
                return {
                    "error": "Portal authentication failed",
                    "details": "Could not obtain valid access token"
                }
            
            # Build headers with current token
            headers = self._build_headers()
            
            if attempt > 0:
                logger.info(f"Retrying Portal request (attempt {attempt + 1}/{max_retries + 1})")
            
            try:
                async with httpx.AsyncClient(
                    verify=self.config.verify_ssl,
                    timeout=self.config.timeout
                ) as client:
                    
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        **kwargs
                    )
                    
                    logger.debug(f"Response status: {response.status_code}")
                    
                    # Handle 401 Unauthorized - token might have expired
                    if response.status_code == 401:
                        logger.warning("Received 401 Unauthorized from Portal API")
                        
                        if attempt < max_retries:
                            logger.info("Token may have expired during request, forcing re-authentication...")
                            # Force re-authentication by clearing current token
                            self.auth_client.access_token = None
                            await asyncio.sleep(0.5)  # Brief delay before retry
                            continue  # Retry the request
                        else:
                            return {
                                "error": "Portal authentication failed after retry",
                                "status_code": 401
                            }
                    
                    # Raise for other HTTP errors
                    response.raise_for_status()
                    
                    # Parse and return response
                    return response.json()
                    
            except httpx.HTTPStatusError as e:
                logger.error(f"Portal API HTTP error: {e}")
                return self._handle_http_error(e)
                
            except Exception as e:
                logger.error(f"Portal API error: {e}")
                return self._handle_general_error(e)
        
        # Should not reach here, but just in case
        return {"error": "Maximum retries exceeded"}
    
    def _handle_http_error(self, error: httpx.HTTPStatusError) -> Dict[str, Any]:
        """Handle HTTP errors."""
        logger.error(f"HTTP Error {error.response.status_code}: {error}")
        
        # Try to get error details from response
        try:
            error_body = error.response.json()
            return {
                "error": f"HTTP {error.response.status_code}",
                "status_code": error.response.status_code,
                "details": error_body
            }
        except:
            return {
                "error": f"HTTP {error.response.status_code}: {str(error)}",
                "status_code": error.response.status_code
            }
    
    def _handle_general_error(self, error: Exception) -> Dict[str, Any]:
        """Handle general errors."""
        logger.error(f"API Error: {error}")
        import traceback
        traceback.print_exc(file=sys.stderr)
        return {
            "error": str(error),
            "type": type(error).__name__
        }
    
    async def get(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make a GET request."""
        return await self._make_request("GET", endpoint, **kwargs)
    
    async def post(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make a POST request."""
        return await self._make_request("POST", endpoint, **kwargs)
    
    async def put(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make a PUT request."""
        return await self._make_request("PUT", endpoint, **kwargs)
    
    async def delete(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make a DELETE request."""
        return await self._make_request("DELETE", endpoint, **kwargs)
    
    @abstractmethod
    async def test_connection(self) -> bool:
        """Test the API connection. Must be implemented by subclasses."""
        pass