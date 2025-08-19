#!/usr/bin/env python3
"""Authentication-related MCP tools."""

from typing import Dict, Any, List
from mcp.types import TextContent
from tools.base_tool import BaseTool
from api.auth_api import AuthAPIClient


class RefreshTokenTool(BaseTool):
    """Tool to refresh the authentication token."""
    
    def __init__(self, api_client: AuthAPIClient):
        super().__init__(
            name="refresh_auth_token",
            description="Refresh the authentication token by logging in with stored credentials and updating the .env file. Use this when API calls fail due to token expiration."
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
        """Execute the token refresh tool."""
        try:
            result = await self.api_client.refresh_token_and_update_env()
            
            if "error" in result:
                return self.format_error(f"Token refresh failed: {result['error']}")
            
            output = f"""🔄 AUTHENTICATION TOKEN REFRESHED

✅ Status: {result['message']}
🔑 New Token: {result['token'][:8]}...{result['token'][-8:]}
⏰ Expires: {result['expires']}
💾 .env File: Updated successfully

The new token has been saved to your .env file and is now active for all API calls.
"""
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error during token refresh: {str(e)}")


class CheckTokenStatusTool(BaseTool):
    """Tool to check the current token status."""
    
    def __init__(self, api_client: AuthAPIClient):
        super().__init__(
            name="check_auth_token_status",
            description="Check the status of the current authentication token including expiration time and validity. Use this to monitor token health."
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
        """Execute the token status check tool."""
        try:
            token_info = self.api_client.get_token_info()
            
            # Determine status icon
            if not token_info['has_token']:
                status_icon = "❌ NO TOKEN"
            elif token_info['is_expired']:
                status_icon = "⚠️ EXPIRED"
            else:
                status_icon = "✅ VALID"
            
            output = f"""🔑 AUTHENTICATION TOKEN STATUS

{status_icon} Token Status: {"Present" if token_info['has_token'] else "Missing"}
🔍 Token Preview: {token_info['token_preview']}
⏰ Expires: {token_info.get('expires', 'Unknown')}
⏳ Time Until Expiry: {token_info.get('time_until_expiry', 'Unknown')}

"""
            
            if token_info['is_expired']:
                output += """⚠️ TOKEN ACTION REQUIRED
Your authentication token has expired or will expire soon.
Use the 'refresh_auth_token' tool to get a new token.

"""
            else:
                output += """✅ TOKEN IS HEALTHY
Your authentication token is valid and ready for API calls.

"""
            
            # Test API connectivity
            try:
                is_connected = await self.api_client.test_connection()
                if is_connected:
                    output += "🌐 API Connection: ✅ Working\n"
                else:
                    output += "🌐 API Connection: ❌ Failed (may need token refresh)\n"
            except Exception:
                output += "🌐 API Connection: ❓ Could not test\n"
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error checking token status: {str(e)}")


class EnsureValidTokenTool(BaseTool):
    """Tool to ensure a valid token (refresh if needed)."""
    
    def __init__(self, api_client: AuthAPIClient):
        super().__init__(
            name="ensure_valid_auth_token",
            description="Automatically check token validity and refresh if needed. Use this before important operations to ensure authentication is working."
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
                output = """✅ AUTHENTICATION STATUS: HEALTHY

🔑 Current token is valid and working
⏰ No refresh needed at this time
🌐 API calls will work normally

Your authentication is ready for all operations.
"""
            else:
                output = f"""🔄 AUTHENTICATION STATUS: REFRESHED

✅ Token was expired and has been refreshed
💾 .env file updated with new token
🌐 API calls are now ready to work

{result.get('message', 'Token refresh completed successfully')}
"""
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error ensuring valid token: {str(e)}")