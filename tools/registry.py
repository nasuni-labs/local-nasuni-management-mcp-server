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
    
    
    def register_portal_auth_tools(self, auth_client):
        """Register Portal authentication tools."""
        from tools.portal_auth_tools import (
            PortalAuthenticateTool,
            PortalCheckTokenTool,
            PortalEnsureValidTokenTool
        )
        
        self.register_tool(PortalAuthenticateTool(auth_client))
        self.register_tool(PortalCheckTokenTool(auth_client))
        self.register_tool(PortalEnsureValidTokenTool(auth_client))
        
        print("✅ Registered 3 Portal authentication tools", file=sys.stderr)
    
    def register_portal_protection_metrics_tools(self, portal_client, integration_helper):
        from tools.portal_telemetry import (
            GetVolumeProtectionMetricsTool,
            CompareVolumeProtectionMetricsTool,
        )
        
        self.register_tool(GetVolumeProtectionMetricsTool(portal_client, integration_helper))
        self.register_tool(CompareVolumeProtectionMetricsTool(portal_client, integration_helper))
        
        print("✅ Registered 2 Portal protection metrics tools (TELEMETRY)", file=sys.stderr)
    
    
    def register_portal_propagation_metrics_tools(self, propagation_client, integration_helper):
        """Register Portal data propagation (sync timing) tools."""
        from tools.portal_telemetry import GetVolumePropagationMetricsTool
        
        self.register_tool(GetVolumePropagationMetricsTool(propagation_client, integration_helper))
        
        print("✅ Registered 1 Portal propagation metrics tool", file=sys.stderr)
    
    def register_portal_combined_metrics_tools(self, protection_client, propagation_client, integration_helper):
        """Register Portal combined (end-to-end) and sync status tools."""
        from tools.portal_telemetry import (
            GetEndToEndProtectionTimingTool,
            GetVolumeLatestVersionTool,
            CheckApplianceSyncStatusTool,
            GetAllAppliancesSyncStatusTool
        )
        
        # End-to-end timing
        self.register_tool(GetEndToEndProtectionTimingTool(
            protection_client,
            propagation_client,
            integration_helper
        ))
        
        # Sync status monitoring
        self.register_tool(GetVolumeLatestVersionTool(protection_client, integration_helper))
        self.register_tool(CheckApplianceSyncStatusTool(protection_client, propagation_client, integration_helper))
        self.register_tool(GetAllAppliancesSyncStatusTool(protection_client, propagation_client, integration_helper))
        
        print("✅ Registered 4 Portal combined & sync status tools", file=sys.stderr)

    def register_portal_telemetry_tools(
        self,
        appliance_client,
        volume_client,
        integration_helper,
    ):
        """Register Portal Ops IQ telemetry tools for appliances and volumes."""
        print("🔍 DEBUG: register_portal_telemetry_tools method ENTERED", file=sys.stderr)
        print(f"🔍 DEBUG: appliance_client={appliance_client}", file=sys.stderr)
        print(f"🔍 DEBUG: volume_client={volume_client}", file=sys.stderr)
        print(f"🔍 DEBUG: integration_helper={integration_helper}", file=sys.stderr)
        
        from tools.portal_telemetry import (
            PortalApplianceTelemetryTool,
            PortalVolumeTelemetryTool,
        )
        from api.portal_telemetry_api import (
            APPLIANCE_TELEMETRY_CONFIG,
            VOLUME_TELEMETRY_CONFIG,
        )
        
        print(f"🔍 DEBUG: APPLIANCE_TELEMETRY_CONFIG has {len(APPLIANCE_TELEMETRY_CONFIG)} entries", file=sys.stderr)
        print(f"🔍 DEBUG: VOLUME_TELEMETRY_CONFIG has {len(VOLUME_TELEMETRY_CONFIG)} entries", file=sys.stderr)

        print("📦 Registering Portal telemetry tools...", file=sys.stderr)
        count = 0
        
        # Metrics to skip (replaced by smart tool)
        SKIP_APPLIANCE_METRICS = {"memory_utilization", "memory_utilization_details"}
        
        for metric_key in APPLIANCE_TELEMETRY_CONFIG.keys():
            if metric_key in SKIP_APPLIANCE_METRICS:
                continue  # Skip - handled by smart memory tool
            try:
                tool = PortalApplianceTelemetryTool(metric_key, appliance_client, integration_helper)
                self.register_tool(tool)
                count += 1
            except Exception as e:
                print(f"  ❌ Failed to register appliance metric '{metric_key}': {e}", file=sys.stderr)
                import traceback
                traceback.print_exc(file=sys.stderr)

        for metric_key in VOLUME_TELEMETRY_CONFIG.keys():
            try:
                tool = PortalVolumeTelemetryTool(metric_key, volume_client, integration_helper)
                self.register_tool(tool)
                count += 1
            except Exception as e:
                print(f"  ❌ Failed to register volume metric '{metric_key}': {e}", file=sys.stderr)
                import traceback
                traceback.print_exc(file=sys.stderr)

        # Register the smart memory tool (replaces memory_utilization and memory_utilization_details)
        from tools.portal_telemetry.appliance_tools import register_smart_memory_tool
        register_smart_memory_tool(self, appliance_client, integration_helper)
        count += 1

        # Register WORKFLOW tools (analysis guidance)
        # These tools return step-by-step instructions for comprehensive analysis
        # They guide the LLM on which data tools to call and in what order
        from tools.portal_telemetry.volume_workflow_tools import register_volume_workflow_tools
        from tools.portal_telemetry.appliance_workflow_tools import register_appliance_workflow_tools
        
        register_volume_workflow_tools(self)
        register_appliance_workflow_tools(self)
        count += 6  # 3 volume + 3 appliance workflow tools

        print(f"✅ Registered {count} Portal telemetry tools (including workflow tools)", file=sys.stderr)

    def register_portal_edge_tools(
        self,
        edges_client,
        integration_helper,
    ):
        """Register Portal Edge tools for appliance hardware details."""
        print("📦 Registering Portal Edge tools...", file=sys.stderr)
        
        from tools.portal_edge_tools import register_portal_edge_tools
        register_portal_edge_tools(self, edges_client, integration_helper)
        
        print("✅ Registered Portal Edge tools", file=sys.stderr)

    def register_portal_volume_tools(
        self,
        volumes_client,
    ):
        """Register Portal Volume tools for volume information."""
        print("📦 Registering Portal Volume tools...", file=sys.stderr)
        
        from tools.portal_volume_tools import register_portal_volume_tools
        register_portal_volume_tools(self, volumes_client)
        
        print("✅ Registered Portal Volume tools", file=sys.stderr)

    def register_tco_tools(self):
        """Register Total Cost of Ownership (TCO) analysis tools."""
        print("📦 Registering TCO tools...", file=sys.stderr)
        
        try:
            from tools.tco import get_tco_tools
            
            for tool in get_tco_tools():
                self.register_tool(tool)
            
            print("✅ Registered 4 TCO analysis tools", file=sys.stderr)
        except ImportError as e:
            print(f"❌ Failed to import TCO tools: {e}", file=sys.stderr)
        except Exception as e:
            print(f"❌ Error registering TCO tools: {e}", file=sys.stderr)


    def get_tool_list(self) -> List[Tool]:
        """Get list of all registered tools for MCP."""
        tools = []
        failed_tools = []
        
        for name, tool in self.tools.items():
            try:
                tools.append(Tool(
                    name=name,
                    description=tool.description,
                    inputSchema=tool.get_schema()
                ))
            except Exception as e:
                failed_tools.append((name, str(e)))
                print(f"  ⚠️  Tool '{name}' failed to serialize: {e}", file=sys.stderr)
        
        if failed_tools:
            print(f"\n❌ {len(failed_tools)} tools failed to serialize:", file=sys.stderr)
            for name, error in failed_tools:
                print(f"   - {name}: {error}", file=sys.stderr)
        
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
            'volume_filer': [],
            'portal': [],
            'tco': []
        }
        
        for name in self.tools.keys():
            
            # TCO tools (cost optimization)
            if name.startswith('tco_'):
                tool_categories['tco'].append(name)
            # Portal tools (auth and telemetry)
            elif name.startswith('portal_'):
                tool_categories['portal'].append(name)
            # Health monitoring
            elif 'filer_health' in name or 'health' in name:
                tool_categories['health'].append(name)
            # Volume-filer operations
            elif 'volume_filer' in name or 'volume_operations' in name:
                tool_categories['volume_filer'].append(name)
            # Filer management
            elif 'filer' in name:
                tool_categories['filer'].append(name)
            # Volume management
            elif 'volume' in name:
                tool_categories['volume'].append(name)
            # Share management
            elif 'share' in name:
                tool_categories['share'].append(name)
            # Authentication
            elif 'auth' in name or 'token' in name:
                tool_categories['auth'].append(name)
            # Credentials
            elif 'credential' in name:
                tool_categories['credential'].append(name)
            # Notifications
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


