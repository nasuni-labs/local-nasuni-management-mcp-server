#!/usr/bin/env python3
"""Base API client for common functionality."""

import sys
import httpx
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod
from config.settings import APIConfig


class BaseAPIClient(ABC):
    """Base class for API clients."""
    
    def __init__(self, config: APIConfig):
        self.config = config
        self.base_url = config.base_url.rstrip('/')
        self.headers = self._build_headers(config.token)
    
    def _build_headers(self, token: Optional[str]) -> Dict[str, str]:
        """Build common headers for API requests."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        if token:
            headers["Authorization"] = f"Token {token}"
        return headers
    
    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        **kwargs
    ) -> Dict[str, Any]:
        """Make an HTTP request with common error handling."""
        url = f"{self.base_url}{endpoint}"
        
        # Log request details
        self._log_request(method, url, kwargs)
        
        try:
            async with httpx.AsyncClient(verify=self.config.verify_ssl) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    timeout=self.config.timeout,
                    **kwargs
                )
                
                self._log_response(response)
                response.raise_for_status()
                return response.json()
                
        except httpx.HTTPStatusError as e:
            return self._handle_http_error(e)
        except Exception as e:
            return self._handle_general_error(e)
    
    def _log_request(self, method: str, url: str, kwargs: Dict[str, Any]):
        """Log request details."""
        print(f"Making {method} request to: {url}", file=sys.stderr)
        print(f"SSL Verification: {self.config.verify_ssl}", file=sys.stderr)
        print(f"Headers: {self.headers}", file=sys.stderr)
    
    def _log_response(self, response: httpx.Response):
        """Log response details."""
        print(f"Response status: {response.status_code}", file=sys.stderr)
    
    def _handle_http_error(self, error: httpx.HTTPStatusError) -> Dict[str, Any]:
        """Handle HTTP errors."""
        print(f"HTTP Error {error.response.status_code}: {error}", file=sys.stderr)
        return {
            "error": f"HTTP {error.response.status_code}: {str(error)}",
            "status_code": error.response.status_code
        }
    
    def _handle_general_error(self, error: Exception) -> Dict[str, Any]:
        """Handle general errors."""
        print(f"API Error: {error}", file=sys.stderr)
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
        """Test the API connection."""
        pass