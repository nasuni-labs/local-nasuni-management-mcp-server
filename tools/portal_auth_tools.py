#!/usr/bin/env python3
"""Portal authentication-related MCP tools."""

from typing import Dict, Any, List
from mcp.types import TextContent
from tools.base_tool import BaseTool
from api.portal_auth_api import PortalAuthAPIClient


class PortalAuthenticateTool(BaseTool):
    """Tool to authenticate with Portal API."""
    
    def __init__(self, api_client: PortalAuthAPIClient):
        super().__init__(
            name="portal_authenticate",
            description="Authenticate with Nasuni Portal using service key credentials. Returns access token valid for 15 minutes."
        )
        self.api_client = api_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the Portal authentication tool."""
        try:
            result = await self.api_client.authenticate()
            
            if "error" in result:
                return self.format_error(f"Portal authentication failed: {result['error']}")
            
            output = f"""🔐 PORTAL AUTHENTICATION SUCCESSFUL

✅ Status: Authenticated
🔑 Access Token: {result['access_token'][:20]}...{result['access_token'][-20:]}
⏰ Expires At: {result.get('expires_at', 'Unknown')}
🔄 Refresh Token: {'Present' if result.get('refresh_token') else 'Not provided'}
💾 Tokens saved to .env file

The access token is valid for 15 minutes and will be automatically refreshed when needed.
"""
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error during Portal authentication: {str(e)}")


class PortalCheckTokenTool(BaseTool):
    """Tool to check Portal token status."""
    
    def __init__(self, api_client: PortalAuthAPIClient):
        super().__init__(
            name="portal_check_token",
            description="Check the status of the current Portal access token including expiration time and validity."
        )
        self.api_client = api_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the Portal token check tool."""
        try:
            token_info = self.api_client.get_token_info()
            
            # Determine status icon
            if not token_info['has_token']:
                status_icon = "❌ NO TOKEN"
            elif token_info['is_expired']:
                status_icon = "⚠️ EXPIRED"
            else:
                status_icon = "✅ VALID"
            
            output = f"""🔐 PORTAL TOKEN STATUS

{status_icon} Token Status: {"Present" if token_info['has_token'] else "Missing"}
🔍 Token Preview: {token_info['token_preview']}
⏰ Expires At: {token_info.get('expires_at', 'Unknown')}
⏳ Time Until Expiry: {token_info.get('time_until_expiry', 'Unknown')}
🔄 Refresh Token: {"Present" if token_info['has_refresh_token'] else "Not available"}

"""
            
            if token_info['is_expired']:
                output += """⚠️ TOKEN ACTION REQUIRED
Your Portal access token has expired or will expire soon.
The token will be automatically refreshed on the next Portal API call.
Or use the 'portal_authenticate' tool to refresh it now.

"""
            else:
                output += """✅ TOKEN IS HEALTHY
Your Portal access token is valid and ready for API calls.
Note: Portal tokens expire after 15 minutes.

"""
            
            # Test API connectivity
            try:
                is_connected = await self.api_client.test_connection()
                if is_connected:
                    output += "🌐 Portal API: ✅ Connected\n"
                else:
                    output += "🌐 Portal API: ❌ Connection failed\n"
            except Exception:
                output += "🌐 Portal API: ❓ Could not test\n"
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error checking Portal token: {str(e)}")


class PortalEnsureValidTokenTool(BaseTool):
    """Tool to ensure a valid Portal token (refresh if needed)."""
    
    def __init__(self, api_client: PortalAuthAPIClient):
        super().__init__(
            name="portal_ensure_valid_token",
            description="Automatically check Portal token validity and refresh if needed. Use before important Portal API operations."
        )
        self.api_client = api_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the ensure valid token tool."""
        try:
            result = await self.api_client.ensure_valid_token()
            
            if "error" in result:
                return self.format_error(f"Token validation failed: {result['error']}")
            
            if "Token is still valid" in result.get('message', ''):
                output = """✅ PORTAL TOKEN STATUS: HEALTHY

🔐 Current token is valid and working
⏰ No refresh needed at this time
🌐 Portal API calls will work normally
⏳ Time remaining: Check with 'portal_check_token' for details

Your Portal authentication is ready for all operations.
"""
            else:
                output = f"""🔄 PORTAL TOKEN STATUS: REFRESHED

✅ Token was expired and has been refreshed
💾 .env file updated with new tokens
🌐 Portal API calls are now ready to work
⏰ New token expires at: {result.get('expires_at', 'Unknown')}

{result.get('message', 'Token refresh completed successfully')}
"""
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error ensuring valid token: {str(e)}")