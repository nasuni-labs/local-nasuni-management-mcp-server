#!/usr/bin/env python3
"""Cloud credential-related MCP tools."""

import json
from typing import Dict, Any, List, Optional
from mcp.types import TextContent
from tools.base_tool import BaseTool
from api.cloud_credentials_api import CloudCredentialsAPIClient

# Import these only when needed to avoid circular imports
# from utils.formatting import format_cloud_credentials_output, format_credential_statistics


class ListCloudCredentialsTool(BaseTool):
    """Tool to list all cloud credentials."""
    
    def __init__(self, api_client: CloudCredentialsAPIClient):
        super().__init__(
            name="list_cloud_credentials",
            description="Returns a list of cloud credentials configured in NMC including provider details, account information, sync status, and filer associations. Use this to manage cloud storage credentials."
        )
        self.api_client = api_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "description": "Optional: Filter by cloud provider (e.g., 'S3', 'Azure', 'Google')"
                },
                "in_use_only": {
                    "type": "boolean",
                    "description": "Optional: Show only credentials that are in use"
                }
            },
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the list cloud credentials tool."""
        try:
            # Import formatting here to avoid circular imports
            from utils.formatting import format_cloud_credentials_output
            
            # Get all credentials
            credentials = await self.api_client.get_credentials_as_models()
            
            if not credentials:
                raw_response = await self.api_client.list_credentials()
                if "error" in raw_response:
                    return self.format_error(f"Failed to fetch credentials: {raw_response['error']}")
                else:
                    return [TextContent(type="text", text="No cloud credentials found.")]
            
            # Apply filters
            provider_filter = arguments.get("provider", "").lower()
            in_use_only = arguments.get("in_use_only", False)
            
            if provider_filter:
                credentials = [c for c in credentials if provider_filter in c.cloud_provider.lower()]
            
            if in_use_only:
                credentials = [c for c in credentials if c.in_use]
            
            # Format the output
            output = format_cloud_credentials_output(credentials)
            
            # Add raw data for complex queries
            raw_response = await self.api_client.list_credentials()
            if "error" not in raw_response:
                output += "\n\n=== RAW API DATA (for complex queries) ===\n"
                output += json.dumps(raw_response, indent=2)
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")


class GetCredentialStatsTool(BaseTool):
    """Tool to get cloud credential statistics."""
    
    def __init__(self, api_client: CloudCredentialsAPIClient):
        super().__init__(
            name="get_credential_stats",
            description="Get aggregate statistics about cloud credentials including provider distribution, usage status, and multi-filer deployments."
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
        """Execute the credential statistics tool."""
        try:
            from utils.formatting import format_credential_statistics
            
            stats = await self.api_client.get_credential_statistics()
            
            if "error" in stats:
                return self.format_error(stats["error"])
            
            output = format_credential_statistics(stats)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")


class GetCredentialsByFilerTool(BaseTool):
    """Tool to get cloud credentials for a specific filer."""
    
    def __init__(self, api_client: CloudCredentialsAPIClient):
        super().__init__(
            name="get_credentials_by_filer",
            description="Get all cloud credentials associated with a specific filer by its serial number."
        )
        self.api_client = api_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "filer_serial": {
                    "type": "string",
                    "description": "The serial number of the filer"
                }
            },
            "required": ["filer_serial"],
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the get credentials by filer tool."""
        try:
            from utils.formatting import format_cloud_credentials_output
            
            filer_serial = arguments.get("filer_serial", "").strip()
            if not filer_serial:
                return self.format_error("Filer serial number is required")
            
            credentials = await self.api_client.get_credentials_by_filer(filer_serial)
            
            if not credentials:
                return [TextContent(type="text", text=f"No credentials found for filer: {filer_serial}")]
            
            output = f"CLOUD CREDENTIALS FOR FILER: {filer_serial}\n\n"
            output += format_cloud_credentials_output(credentials)
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")


class GetCredentialUsageAnalysisTool(BaseTool):
    """Tool to analyze cloud credential usage across volumes."""
    
    def __init__(self, api_client: CloudCredentialsAPIClient, volumes_client=None):
        super().__init__(
            name="analyze_credential_usage",
            description="Analyze cloud credential usage across volumes and identify unused credentials."
        )
        self.api_client = api_client
        self.volumes_client = volumes_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the credential usage analysis tool."""
        try:
            analysis = await self.api_client.get_credential_usage_analysis(self.volumes_client)
            
            if "error" in analysis:
                return self.format_error(analysis["error"])
            
            output = "CLOUD CREDENTIAL USAGE ANALYSIS\n\n"
            
            # Summary
            total_creds = len(analysis["credentials"])
            unused_count = len(analysis["unused_credentials"])
            
            output += f"=== SUMMARY ===\n"
            output += f"Total Unique Credentials: {total_creds}\n"
            output += f"Unused Credentials: {unused_count}\n\n"
            
            # Unused credentials details
            if analysis["unused_credentials"]:
                output += "=== UNUSED CREDENTIALS ===\n"
                for cred in analysis["unused_credentials"]:
                    output += f"\n- {cred['name']} ({cred['uuid'][:8]}...)\n"
                    output += f"  Provider: {cred['provider']}\n"
                    output += f"  Deployed to filers: {', '.join(cred['filers'])}\n"
                output += "\n"
            
            # Credential usage details
            output += "=== CREDENTIAL USAGE DETAILS ===\n"
            for uuid, info in analysis["credentials"].items():
                volume_count = len(info["volumes"])
                filer_count = len(info["filers"])
                
                output += f"\n{info['name']} ({uuid[:8]}...)\n"
                output += f"  Provider: {info['provider']}\n"
                output += f"  Status: {'In Use' if info['in_use'] else 'Not In Use'}\n"
                output += f"  Deployed to {filer_count} filer(s)\n"
                
                if self.volumes_client:
                    output += f"  Used by {volume_count} volume(s)\n"
                    if volume_count > 0 and volume_count <= 5:
                        for vol in info["volumes"][:5]:
                            output += f"    - {vol['name']}\n"
                    elif volume_count > 5:
                        for vol in info["volumes"][:3]:
                            output += f"    - {vol['name']}\n"
                        output += f"    ... and {volume_count - 3} more\n"
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")


class GetInactiveCredentialsTool(BaseTool):
    """Tool to get inactive cloud credentials."""
    
    def __init__(self, api_client: CloudCredentialsAPIClient):
        super().__init__(
            name="get_inactive_credentials",
            description="Get all cloud credentials that are marked as not in use."
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
        """Execute the get inactive credentials tool."""
        try:
            from utils.formatting import format_cloud_credentials_output
            
            credentials = await self.api_client.get_inactive_credentials()
            
            if not credentials:
                return [TextContent(type="text", text="No inactive credentials found.")]
            
            output = "INACTIVE CLOUD CREDENTIALS\n\n"
            output += f"Found {len(credentials)} inactive credential(s)\n\n"
            output += format_cloud_credentials_output(credentials)
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")