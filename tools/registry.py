#!/usr/bin/env python3
"""Tool registry for managing MCP tools."""

import sys
from typing import Dict, List, Any
from mcp.types import Tool, TextContent
from api.cloud_credentials_api import CloudCredentialsAPIClient
from tools.base_tool import BaseTool
from tools.filer_tools import ListFilersTool, GetFilerStatsTool, GetFilerTool
from tools.volume_tools import ListVolumesTool
from api.filers_api import FilersAPIClient
from api.volumes_api import VolumesAPIClient
from tools.auth_tools import RefreshTokenTool, CheckTokenStatusTool, EnsureValidTokenTool
from api.auth_api import AuthAPIClient

from tools.filer_health_tools import (
    ListFilerHealthTool, GetFilerHealthStatsTool, GetUnhealthyFilersTool,
    GetCriticalHealthIssuesTool, GetFilerHealthBySerialTool
)
from api.filer_health_api import FilerHealthAPIClient


class ToolRegistry:
    """Registry for managing MCP tools."""
    
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
    
    def register_tool(self, tool: BaseTool):
        """Register a tool."""
        self.tools[tool.name] = tool
        print(f"  ✅ Registered tool: {tool.name}", file=sys.stderr)
    
    def register_filer_tools(self, filers_client: FilersAPIClient):
        """Register all filer-related tools."""
        print("📦 Registering Filer tools...", file=sys.stderr)
        self.register_tool(ListFilersTool(filers_client))
        self.register_tool(GetFilerStatsTool(filers_client))
        self.register_tool(GetFilerTool(filers_client))
    
    def register_volume_tools(self, volumes_client: VolumesAPIClient, filers_client: FilersAPIClient):
        """Register all volume-related tools with enhanced location support."""
        print("📦 Registering Volume tools...", file=sys.stderr)
        self.register_tool(ListVolumesTool(volumes_client))

        #For a give filer, fetches a list of connected volumes.
        from tools.filer_volumes_tool import GetVolumesByFilerTool
        self.register_tool(GetVolumesByFilerTool(volumes_client))

    
    def register_share_tools(self, shares_client):
        """Register all share-related tools."""
        print("📦 Registering Share tools...", file=sys.stderr)
        try:
            from tools.share_tools import (
                ListSharesTool, GetShareStatsTool, GetSharesByFilerTool,
                GetBrowserAccessibleSharesTool, GetSharesByVolumeTool
            )
            self.register_tool(ListSharesTool(shares_client))
            self.register_tool(GetShareStatsTool(shares_client))
            self.register_tool(GetSharesByFilerTool(shares_client))
            self.register_tool(GetBrowserAccessibleSharesTool(shares_client))
            self.register_tool(GetSharesByVolumeTool(shares_client))
        except ImportError as e:
            print(f"  ⚠️ Some share tools could not be imported: {e}", file=sys.stderr)
    
    def register_filer_health_tools(self, filer_health_client: FilerHealthAPIClient):
        """Register all filer health-related tools."""
        print("📦 Registering Filer Health tools...", file=sys.stderr)
        self.register_tool(ListFilerHealthTool(filer_health_client))
        self.register_tool(GetFilerHealthStatsTool(filer_health_client))
        self.register_tool(GetUnhealthyFilersTool(filer_health_client))
        self.register_tool(GetCriticalHealthIssuesTool(filer_health_client))
        self.register_tool(GetFilerHealthBySerialTool(filer_health_client))
    
    def register_auth_tools(self, auth_client: AuthAPIClient):
        """Register authentication-related tools."""
        print("📦 Registering Authentication tools...", file=sys.stderr)
        self.register_tool(RefreshTokenTool(auth_client))
        self.register_tool(CheckTokenStatusTool(auth_client))
        self.register_tool(EnsureValidTokenTool(auth_client))
    
    def register_cloud_credential_tools(self, cloud_creds_client: CloudCredentialsAPIClient, volumes_client: VolumesAPIClient = None):
        """Register all cloud credential-related tools."""
        from tools.cloud_credential_tools import (
            ListCloudCredentialsTool,
            GetCredentialStatsTool,
            GetCredentialsByFilerTool,
            GetCredentialUsageAnalysisTool,
            GetInactiveCredentialsTool
        )
        
        self.register_tool(ListCloudCredentialsTool(cloud_creds_client))
        self.register_tool(GetCredentialStatsTool(cloud_creds_client))
        self.register_tool(GetCredentialsByFilerTool(cloud_creds_client))
        self.register_tool(GetInactiveCredentialsTool(cloud_creds_client))
        
        # Register usage analysis tool with volumes client if available
        if volumes_client:
            self.register_tool(GetCredentialUsageAnalysisTool(cloud_creds_client, volumes_client))
            print("âœ… Cloud credential tools registered with volume analysis", file=sys.stderr)
        else:
            self.register_tool(GetCredentialUsageAnalysisTool(cloud_creds_client, None))
            print("âœ… Cloud credential tools registered (without volume analysis)", file=sys.stderr)
    
    def register_notification_tools(self, notifications_client):
        """Register all notification-related tools."""
        try:
            from api.notifications_api import NotificationsAPIClient
            from tools.notification_tools import (
                ListNotificationsTool,
                GetNotificationSummaryTool,
                AnalyzeNotificationPatternsTool
            )
            
            self.register_tool(ListNotificationsTool(notifications_client))
            self.register_tool(GetNotificationSummaryTool(notifications_client))
            self.register_tool(AnalyzeNotificationPatternsTool(notifications_client))
            
            print("âœ… Notification tools registered successfully", file=sys.stderr)
            
        except ImportError as e:
            print(f"âŒ Failed to import notification tools: {e}", file=sys.stderr)
        except Exception as e:
            print(f"âŒ Error registering notification tools: {e}", file=sys.stderr)
    
    def register_volume_filer_details_tools(self, 
                                           volume_filer_client,
                                           volumes_client):
        """
        Register consolidated volume-filer details tools.
        Uses the improved /volumes/:volume_guid/filers/ endpoint.
        """
        print("📦 Registering Volume-Filer Details tools (consolidated)...", file=sys.stderr)
        
        try:
            from tools.volume_filer_details_tools import (
                # Core tools
                GetVolumeFilerDetailsTool,
                AnalyzeVolumeOperationsTool,
                GetVolumeAccessSummaryTool,
                FindUnprotectedVolumesTool,
                # Report tools
                GetSnapshotHealthReportTool,
                GetSyncConfigurationReportTool,
                GetAuditingComplianceReportTool,
                GetDataProtectionSummaryTool
            )
            
            # Register core tools
            self.register_tool(GetVolumeFilerDetailsTool(volume_filer_client))
            self.register_tool(AnalyzeVolumeOperationsTool(volume_filer_client, volumes_client))
            self.register_tool(GetVolumeAccessSummaryTool(volume_filer_client))
            self.register_tool(FindUnprotectedVolumesTool(volume_filer_client, volumes_client))
            
            # Register report tools
            self.register_tool(GetSnapshotHealthReportTool(volume_filer_client))
            self.register_tool(GetSyncConfigurationReportTool(volume_filer_client))
            self.register_tool(GetAuditingComplianceReportTool(volume_filer_client))
            self.register_tool(GetDataProtectionSummaryTool(volume_filer_client))
            
            print(f"  ✅ Registered 8 consolidated volume-filer tools", file=sys.stderr)
            
            # Note about deprecated tools
            print("  ℹ️ Note: Previous separate analysis tools are now consolidated into AnalyzeVolumeOperationsTool", file=sys.stderr)
            print("    Use focus parameter: 'snapshots', 'sync', 'auditing', or 'data_protection'", file=sys.stderr)
            
        except ImportError as e:
            print(f"  ⚠️ Failed to import volume-filer details tools: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
    
    def get_tool_list(self) -> List[Tool]:
        """Get list of all registered tools for MCP."""
        tools = []
        for name, tool in self.tools.items():
            tools.append(Tool(
                name=name,
                description=tool.description,
                inputSchema=tool.get_schema()
            ))
        return tools
    
    def get_tool_names(self) -> List[str]:
        """Get list of all registered tool names."""
        return list(self.tools.keys())
    
    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute a tool by name."""
        if name not in self.tools:
            return [TextContent(
                type="text",
                text=f"❌ Error: Tool '{name}' not found. Available tools: {', '.join(self.tools.keys())}"
            )]
        
        try:
            tool = self.tools[name]
            return await tool.execute(arguments)
        except Exception as e:
            print(f"❌ Error executing tool {name}: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            return [TextContent(
                type="text",
                text=f"❌ Error executing tool '{name}': {str(e)}"
            )]
    
    def get_tool_stats(self) -> Dict[str, Any]:
        """Get statistics about registered tools."""
        tool_categories = {
            'filer': [],
            'volume': [],
            'share': [],
            'health': [],
            'auth': [],
            'credential': [],
            'notification': [],
            'volume_filer': []
        }
        
        for name in self.tools.keys():
            if 'filer_health' in name or 'health' in name:
                tool_categories['health'].append(name)
            elif 'volume_filer' in name or 'volume_operations' in name:
                tool_categories['volume_filer'].append(name)
            elif 'filer' in name:
                tool_categories['filer'].append(name)
            elif 'volume' in name:
                tool_categories['volume'].append(name)
            elif 'share' in name:
                tool_categories['share'].append(name)
            elif 'auth' in name or 'token' in name:
                tool_categories['auth'].append(name)
            elif 'credential' in name:
                tool_categories['credential'].append(name)
            elif 'notification' in name:
                tool_categories['notification'].append(name)
        
        return {
            'total_tools': len(self.tools),
            'categories': {
                category: {
                    'count': len(tools),
                    'tools': tools
                }
                for category, tools in tool_categories.items()
                if tools
            }
        }