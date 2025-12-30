#!/usr/bin/env python3
"""Portal data propagation (sync timing) MCP tools."""

from typing import Dict, Any, List
from mcp.types import TextContent
from tools.base_tool import BaseTool
from api.portal_data_propagation_api import PortalDataPropagationAPIClient
from utils.portal_nmc_integration import NMCPortalIntegration
from config.logging_setup import get_logger

logger = get_logger(__name__)


class GetVolumePropagationMetricsTool(BaseTool):
    """Tool for data propagation (sync timing) metrics."""
    
    def __init__(
        self, 
        api_client: PortalDataPropagationAPIClient,
        integration_helper: NMCPortalIntegration
    ):
        super().__init__(
            name="get_volume_propagation_metrics",
            description="[TELEMETRY - DATA PROPAGATION] Get sync timing metrics from Portal Ops IQ. Shows how long it takes for snapshots to propagate to connected appliances. USE THIS FOR: (1) Sync/propagation time analysis, (2) Which appliances sync fastest/slowest, (3) Outlier detection (abnormally slow syncs), (4) Latest version sync status, (5) Average propagation time, (6) Sync performance by appliance. ANSWERS: 'How long does sync take?', 'Which appliance syncs slowest?', 'Show propagation metrics', 'Sync performance analysis', 'Are there slow-syncing appliances?'. Accepts volume name or GUID."
        )
        self.api_client = api_client
        self.integration = integration_helper
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema."""
        return {
            "type": "object",
            "properties": {
                "volume": {
                    "type": "string",
                    "description": "Volume name or GUID"
                },
                "period": {
                    "type": "string",
                    "description": "Time period (default: PT3H)"
                },
                "show_outliers": {
                    "type": "boolean",
                    "description": "Show detailed outlier information (default: true)"
                }
            },
            "required": ["volume"]
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the tool."""
        try:
            volume_id = arguments.get("volume", "").strip()
            if not volume_id:
                return self.format_error("Volume name or GUID required")
            
            period = arguments.get("period", "PT3H")
            show_outliers = arguments.get("show_outliers", True)
            
            # Resolve volume
            volume_guid, _ = await self.integration.resolve_volume_identifier(volume_id)
            if not volume_guid:
                return self.format_error(f"Volume not found: {volume_id}")
            
            # Get connected filer serials
            serials = await self.integration.get_filer_serials_for_volume(volume_guid)
            if not serials:
                return self.format_error(f"No filers found for volume: {volume_id}")
            
            # Get propagation data
            analysis = await self.api_client.get_volume_data_propagation_analysis(
                volume_guid=volume_guid,
                serial_numbers=serials,
                period=period
            )
            
            if not analysis.events:
                return [TextContent(
                    type="text",
                    text=f"No propagation data for {volume_id} in period {period}"
                )]
            
            output = self._format_output(volume_id, volume_guid, period, analysis, show_outliers)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            logger.error(f"Tool error: {e}")
            import traceback
            traceback.print_exc()
            return self.format_error(str(e))
    
    def _format_output(self, vol_id, vol_guid, period, analysis, show_outliers) -> str:
        """Format propagation output."""
        stats = analysis.get_statistics()
        insights = analysis.get_insights()
        
        out = f"""🌐 DATA PROPAGATION METRICS - PORTAL OPS IQ

=== VOLUME ===
Name: {vol_id}
GUID: {vol_guid}
Period: {period}

=== SYNC OVERVIEW ===
Total Sync Events: {stats['total_events']}
Versions Synced: {stats['total_versions']}
Snapshot Creators: {', '.join(stats['snapshot_appliances'])}
Sync Appliances: {', '.join(stats['sync_appliances'])}
"""
        
        if stats.get("latest_version"):
            latest = stats["latest_version"]
            out += f"""
📌 LATEST VERSION: {latest['version']}
Created By: {latest['created_by']} at {latest['created_at']}
Syncs Completed: {latest['syncs_completed']}
Avg Propagation: {latest['avg_propagation']}
"""
        
        if stats.get("propagation_statistics"):
            prop = stats["propagation_statistics"]
            out += f"""
=== PROPAGATION PERFORMANCE ===
Average Time: {prop['avg_time']}
Fastest: {prop['min_time']}
Slowest: {prop['max_time']}
"""
        
        if stats.get("slowest_syncs"):
            out += "\n=== ⏱️ SLOWEST SYNCS ===\n"
            for sync in stats["slowest_syncs"]:
                out += f"  • v{sync['version']}: {sync['sync_appliance']} took {sync['duration']}\n"
        
        if show_outliers and stats.get("outliers"):
            out += f"\n=== ⚠️ OUTLIERS ({len(stats['outliers'])}) ===\n"
            for outlier in stats["outliers"]:
                out += f"  • v{outlier['version']}: {outlier['sync_appliance']} - {outlier['duration']} ({outlier['sigma']:.1f}σ)\n"
        
        if stats.get("by_sync_appliance"):
            out += "\n=== BY SYNC APPLIANCE ===\n"
            
            for app, app_stats in sorted(stats["by_sync_appliance"].items(), key=lambda x: x[1]["total_syncs"], reverse=True):
                out += f"\n📡 {app}\n"
                out += f"   Latest Synced: v{app_stats['latest_version_synced']} at {app_stats['latest_sync_time']}\n"
                out += f"   Total Syncs: {app_stats['total_syncs']}\n"
                out += f"   Avg Time: {app_stats['avg_propagation']}\n"
                out += f"   Range: {app_stats['min_propagation']} - {app_stats['max_propagation']}\n"
                if app_stats['outlier_count'] > 0:
                    out += f"   ⚠️ Outliers: {app_stats['outlier_count']}\n"
        
        out += "\n=== 💡 INSIGHTS ===\n"
        for insight in insights:
            out += f"{insight}\n"
        
        out += "\n📊 Portal Ops IQ - Sync timing telemetry\n"
        out += "💡 Shows how quickly snapshots propagate to connected appliances\n"
        
        return out