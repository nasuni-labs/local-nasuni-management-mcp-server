#!/usr/bin/env python3
"""Portal snapshot protection metrics MCP tools."""

from typing import Dict, Any, List
from mcp.types import TextContent
from models.snapshot_timeline import SnapshotTimelineAnalysis
from tools.base_tool import BaseTool
from api.portal_snapshot_timeline_api import PortalSnapshotTimelineAPIClient
from utils.portal_nmc_integration import NMCPortalIntegration
from config.logging_setup import get_logger

logger = get_logger(__name__)


class GetVolumeProtectionMetricsTool(BaseTool):
    """Tool to get volume protection metrics from Portal Ops IQ."""
    
    def __init__(
        self, 
        api_client: PortalSnapshotTimelineAPIClient,
        integration_helper: NMCPortalIntegration
    ):
        super().__init__(
            name="get_volume_protection_metrics",
            description="[TELEMETRY - PRIMARY FOR PROTECTION TIMING] Get snapshot protection metrics and timing data from Portal Ops IQ telemetry service. This tool provides real-time snapshot performance data that is NOT available from NMC configuration APIs. Use this tool when asked to SUMMARIZE data protection, show protection DETAILS, or analyze protection TIMING/PERFORMANCE. Provides: (1) Latest volume/snapshot version number, (2) Which appliance created the latest snapshot and when, (3) Data phase timing (how long to protect data to cloud), (4) Metadata phase timing (how long to create restore point), (5) Average snapshot duration across all appliances, (6) Longest/slowest snapshot and which appliance, (7) Most active appliance creating snapshots, (8) Snapshot frequency and distribution. Answers questions like: 'Summarize data protection for volume X', 'What is the latest volume version?', 'Which appliance took the latest snapshot?', 'How long do snapshots take?', 'Show protection metrics', 'Show protection details', 'Which appliance is most active?', 'Give me snapshot performance data'. Accepts volume name or GUID, automatically looks up connected appliances from NMC."
        )
        self.api_client = api_client
        self.integration = integration_helper
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "volume": {
                    "type": "string",
                    "description": "Volume name or GUID"
                },
                "period": {
                    "type": "string",
                    "description": "Time period to analyze (ISO 8601 duration). Examples: PT1H (1 hour), PT3H (3 hours, default), PT6H (6 hours), PT24H (24 hours), P7D (7 days)",
                    "default": "PT3H"
                },
                "smart_sampling": {
                    "type": "boolean",
                    "description": "Reduce data points while preserving trends and outliers (default: true). Set to false for granular details.",
                    "default": True
                },
                "show_raw_data": {
                    "type": "boolean",
                    "description": "Include raw snapshot event data in output (default: false)",
                    "default": False
                }
            },
            "required": ["volume"],
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the protection metrics tool."""
        try:
            volume_identifier = arguments.get("volume", "").strip()
            if not volume_identifier:
                return self.format_error("Volume name or GUID is required")
            
            period = arguments.get("period", "PT3H")
            smart_sampling = arguments.get("smart_sampling", True)
            show_raw = arguments.get("show_raw_data", False)
            
            # Step 1: Resolve volume to GUID
            logger.info(f"Resolving volume identifier: {volume_identifier}")
            volume_guid, id_type = await self.integration.resolve_volume_identifier(volume_identifier)
            
            if not volume_guid:
                return self.format_error(f"Volume not found: {volume_identifier}")
            
            logger.info(f"Resolved to volume GUID: {volume_guid}")
            
            # Step 2: Get filer serial numbers connected to this volume
            logger.info("Fetching connected filer serial numbers from NMC...")
            serial_numbers = await self.integration.get_filer_serials_for_volume(volume_guid)
            
            if not serial_numbers:
                return self.format_error(f"No filers found connected to volume: {volume_identifier}")
            
            logger.info(f"Found {len(serial_numbers)} connected filer(s): {serial_numbers}")
            
            # Step 3: Fetch snapshot timeline from Portal
            logger.info(f"Fetching snapshot timeline (period: {period})...")
            analysis = await self.api_client.get_volume_snapshot_timeline_analysis(
                volume_guid=volume_guid,
                serial_numbers=serial_numbers,
                period=period,
                smart_sampling=smart_sampling
            )
            
            if not analysis.data_events and not analysis.metadata_events:
                return [TextContent(
                    type="text",
                    text=f"No snapshot timeline data available for volume: {volume_identifier} in period {period}"
                )]
            
            # Step 4: Format output
            output = self._format_protection_metrics_output(
                volume_identifier=volume_identifier,
                volume_guid=volume_guid,
                period=period,
                smart_sampling=smart_sampling,
                serial_numbers=serial_numbers,
                analysis=analysis,
                show_raw=show_raw
            )
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            logger.error(f"Error in protection metrics tool: {e}")
            import traceback
            traceback.print_exc()
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _format_protection_metrics_output(
        self,
        volume_identifier: str,
        volume_guid: str,
        period: str,
        smart_sampling: bool,
        serial_numbers: List[str],
        analysis: 'SnapshotTimelineAnalysis',
        show_raw: bool
    ) -> str:
        """Format the protection metrics output."""
        
        stats = analysis.get_statistics()
        insights = analysis.get_insights()
        
        output = f"""🛡️ SNAPSHOT PROTECTION METRICS - PORTAL OPS IQ

=== VOLUME INFORMATION ===
Volume: {volume_identifier}
GUID: {volume_guid}
"""
        
        # Latest snapshot prominently displayed
        if stats.get("latest_snapshot"):
            latest = stats["latest_snapshot"]
            output += f"""📌 Latest Snapshot Version: {latest['volume_version']}
🏆 Created By: {latest['appliance']} ({latest['serial_number']})
📅 Completed At: {latest['completed_at']}
⏱️ Duration: {latest['duration']}

"""
        
        output += f"""=== ANALYSIS PERIOD ===
Time Period: {period}
Smart Sampling: {'Enabled' if smart_sampling else 'Disabled (granular data)'}
Connected Appliances: {len(serial_numbers)}
Data Events: {stats['total_data_events']} (data protection phases)
Metadata Events: {stats['total_metadata_events']} (snapshot versions created)
Time Range: {stats['time_range']['start']} → {stats['time_range']['end']}

"""
        
        # Snapshot phase performance
        if stats.get("data_phase_statistics"):
            data = stats["data_phase_statistics"]
            output += f"""=== DATA PHASE PERFORMANCE (Protecting Data to Cloud) ===
Total Events: {data['total_events']}
Average Duration: {data['avg_duration']}
Fastest: {data['min_duration']}
Slowest: {data['max_duration']} on {data['longest_on_appliance']}

"""
        
        if stats.get("metadata_phase_statistics"):
            meta = stats["metadata_phase_statistics"]
            output += f"""=== METADATA PHASE PERFORMANCE (Creating Restore Points) ===
Total Events: {meta['total_events']}
Average Duration: {meta['avg_duration']}
Fastest: {meta['min_duration']}
Slowest: {meta['max_duration']} on {meta['longest_on_appliance']}

"""
        
        # Most active appliance
        if stats.get("most_active_appliance"):
            active = stats["most_active_appliance"]
            output += f"""=== 🏆 MOST ACTIVE APPLIANCE ===
{active['name']}
Snapshots Created: {active['snapshots_created']} ({active['percentage']:.1f}% of total)

"""
        
        # Per-appliance breakdown
        if stats.get("by_appliance"):
            output += "=== BY APPLIANCE BREAKDOWN ===\n"
            
            # Sort by snapshots created (most active first)
            appliances_sorted = sorted(
                stats["by_appliance"].items(),
                key=lambda x: x[1]["metadata_events"],
                reverse=True
            )
            
            for appliance, app_stats in appliances_sorted:
                output += f"\n📡 {appliance} ({app_stats['serial_number'][:8]}...)\n"
                output += f"   Latest Version Created: {app_stats.get('latest_version_created', 'N/A')}"
                if app_stats.get('latest_snapshot_time'):
                    output += f" at {app_stats['latest_snapshot_time']}"
                output += "\n"
                output += f"   Snapshots Created: {app_stats['metadata_events']}\n"
                output += f"   Data Events: {app_stats['data_events']}\n"
                output += f"   Avg Data Phase: {app_stats['avg_data_phase']}\n"
                output += f"   Avg Metadata Phase: {app_stats['avg_metadata_phase']}\n"
        
        # Insights
        output += "\n=== 💡 INSIGHTS ===\n"
        if insights:
            for insight in insights:
                output += f"{insight}\n"
        else:
            output += "✅ No issues detected - snapshot protection is healthy\n"
        
        # Raw data if requested
        if show_raw:
            if analysis.metadata_events:
                output += "\n=== 📊 METADATA EVENTS (Last 5 Snapshots Created) ===\n"
                for i, event in enumerate(analysis.metadata_events[-5:], 1):
                    summary = event.get_summary_dict()
                    output += f"\n[{i}] Version {summary['volume_version']}\n"
                    output += f"    Appliance: {summary['appliance']}\n"
                    output += f"    Completed: {summary['end_time']}\n"
                    output += f"    Duration: {summary['duration']}\n"
                
                if len(analysis.metadata_events) > 5:
                    output += f"\n... and {len(analysis.metadata_events) - 5} earlier versions\n"
            
            if analysis.data_events:
                output += "\n=== 📊 DATA EVENTS (Last 5 Data Protection Phases) ===\n"
                for i, event in enumerate(analysis.data_events[-5:], 1):
                    summary = event.get_summary_dict()
                    output += f"\n[{i}] {summary['appliance']}\n"
                    output += f"    Started: {summary['start_time']}\n"
                    output += f"    Ended: {summary['end_time']}\n"
                    output += f"    Duration: {summary['duration']}\n"
                
                if len(analysis.data_events) > 5:
                    output += f"\n... and {len(analysis.data_events) - 5} earlier events\n"
        
        output += f"\n📊 Portal Ops IQ provides real-time telemetry for snapshot protection monitoring.\n"
        output += f"💡 This shows WHEN snapshots occurred and HOW LONG they took (timing data).\n"
        output += f"💡 For protection STATUS and CONFIGURATION, use NMC tools instead.\n"
        
        return output


class CompareVolumeProtectionMetricsTool(BaseTool):
    """Tool to compare protection metrics across volumes."""
    
    def __init__(
        self, 
        api_client: PortalSnapshotTimelineAPIClient,
        integration_helper: NMCPortalIntegration
    ):
        super().__init__(
            name="compare_volume_protection_metrics",
            description="[TELEMETRY] Compare snapshot protection performance across multiple volumes. Shows which volumes have faster/slower snapshots and identifies performance differences."
        )
        self.api_client = api_client
        self.integration = integration_helper
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "volumes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of volume names or GUIDs to compare"
                },
                "period": {
                    "type": "string",
                    "description": "Time period for analysis (default: PT3H)",
                    "default": "PT3H"
                }
            },
            "required": ["volumes"],
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the comparison tool."""
        try:
            volumes = arguments.get("volumes", [])
            if not volumes or len(volumes) < 2:
                return self.format_error("At least 2 volumes required for comparison")
            
            period = arguments.get("period", "PT3H")
            
            # Collect data for each volume
            volume_data = []
            
            for vol_id in volumes:
                logger.info(f"Analyzing volume: {vol_id}")
                
                # Resolve volume
                volume_guid, _ = await self.integration.resolve_volume_identifier(vol_id)
                if not volume_guid:
                    logger.warning(f"Volume not found: {vol_id}, skipping")
                    continue
                
                # Get filer serial numbers
                serial_numbers = await self.integration.get_filer_serials_for_volume(volume_guid)
                if not serial_numbers:
                    logger.warning(f"No filers found for volume: {vol_id}, skipping")
                    continue
                
                # Get telemetry
                analysis = await self.api_client.get_volume_snapshot_timeline_analysis(
                    volume_guid=volume_guid,
                    serial_numbers=serial_numbers,
                    period=period,
                    smart_sampling=True
                )
                
                if analysis.metadata_events:
                    volume_data.append({
                        "identifier": vol_id,
                        "guid": volume_guid,
                        "analysis": analysis,
                        "stats": analysis.get_statistics()
                    })
            
            if not volume_data:
                return self.format_error("No valid data found for any volumes")
            
            # Format comparison
            output = self._format_comparison_output(volume_data, period)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            logger.error(f"Error in comparison tool: {e}")
            import traceback
            traceback.print_exc()
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _format_comparison_output(self, volume_data: List[Dict], period: str) -> str:
        """Format the comparison output."""
        
        output = f"""📊 VOLUME PROTECTION METRICS COMPARISON

=== OVERVIEW ===
Volumes Analyzed: {len(volume_data)}
Time Period: {period}

=== COMPARISON TABLE ===

"""
        
        # Create comparison table
        output += "Volume".ljust(40) + "Latest Ver".ljust(15) + "Avg Data Phase".ljust(18) + "Avg Metadata".ljust(18) + "Snapshots\n"
        output += "-" * 110 + "\n"
        
        for vol in volume_data:
            name = vol["identifier"][:38]
            stats = vol["stats"]
            
            latest_ver = stats.get("latest_snapshot", {}).get("volume_version", "N/A")
            data_avg = stats.get("data_phase_statistics", {}).get("avg_duration", "N/A")
            meta_avg = stats.get("metadata_phase_statistics", {}).get("avg_duration", "N/A")
            snap_count = stats.get("total_metadata_events", 0)
            
            output += f"{name.ljust(40)}{str(latest_ver).ljust(15)}{str(data_avg).ljust(18)}{str(meta_avg).ljust(18)}{snap_count}\n"
        
        # Rankings
        output += "\n=== RANKINGS ===\n"
        
        # Fastest data phase
        volumes_with_data = [
            (v, v["stats"].get("data_phase_statistics", {}).get("avg_duration_seconds", float('inf'))) 
            for v in volume_data 
            if "data_phase_statistics" in v["stats"]
        ]
        
        if volumes_with_data:
            volumes_with_data.sort(key=lambda x: x[1])
            fastest = volumes_with_data[0]
            slowest = volumes_with_data[-1]
            
            output += f"\n🏆 Fastest Data Protection:\n"
            output += f"   {fastest[0]['identifier']}: {fastest[0]['stats']['data_phase_statistics']['avg_duration']}\n"
            
            output += f"\n⚠️ Slowest Data Protection:\n"
            output += f"   {slowest[0]['identifier']}: {slowest[0]['stats']['data_phase_statistics']['avg_duration']}\n"
        
        return output