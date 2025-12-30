#!/usr/bin/env python3
"""Portal data protection telemetry MCP tools."""

from typing import Dict, Any, List
from mcp.types import TextContent
from tools.base_tool import BaseTool
from api.portal_data_protection_api import PortalDataProtectionAPIClient
from utils.portal_nmc_integration import NMCPortalIntegration
from config.logging_setup import get_logger

logger = get_logger(__name__)


class GetVolumeProtectionMetricsTool(BaseTool):
    """Primary tool for volume data protection metrics from Portal Ops IQ."""
    
    def __init__(
        self, 
        api_client: PortalDataProtectionAPIClient,
        integration_helper: NMCPortalIntegration
    ):
        super().__init__(
            name="get_volume_protection_metrics",
            description="[TELEMETRY - DATA PROTECTION] Get comprehensive data protection metrics from Portal Ops IQ. Provides timing and performance data NOT available from NMC. USE THIS TO ANSWER: (1) Latest volume/snapshot version, (2) Which appliance created latest snapshot, (3) Average data protection time (how long files remain unprotected), (4) Protection anomalies (worst cases of unprotected files), (5) Oldest Unprotected Data (OUD) age, (6) Snapshot phase timing (data & metadata duration), (7) Files and directories protected per snapshot, (8) Most active appliance, (9) Protection performance by appliance. EXAMPLE QUERIES: 'Summarize data protection for VolumeX', 'What is latest volume version?', 'Average protection time?', 'Which appliance took latest snapshot?', 'How long do snapshots take?', 'Show protection metrics'. Accepts volume name or GUID."
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
                    "description": "Time period (ISO 8601). Examples: PT1H, PT3H (default), PT6H, PT24H, P7D"
                },
                "smart_sampling": {
                    "type": "boolean",
                    "description": "Reduce data points while preserving trends (default: true)"
                },
                "show_details": {
                    "type": "boolean",
                    "description": "Show detailed snapshot-by-snapshot data (default: false)"
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
            smart_sampling = arguments.get("smart_sampling", True)
            show_details = arguments.get("show_details", False)
            
            # Resolve volume
            volume_guid, _ = await self.integration.resolve_volume_identifier(volume_id)
            if not volume_guid:
                return self.format_error(f"Volume not found: {volume_id}")
            
            # Get connected filer serials
            serials = await self.integration.get_filer_serials_for_volume(volume_guid)
            if not serials:
                return self.format_error(f"No filers found for volume: {volume_id}")
            
            logger.info(f"Using {len(serials)} filer(s): {serials}")
            
            # Get protection data
            analysis = await self.api_client.get_volume_data_protection_analysis(
                volume_guid=volume_guid,
                serial_numbers=serials,
                period=period,
                smart_sampling=smart_sampling
            )
            
            if not analysis.complete_snapshots:
                return [TextContent(
                    type="text",
                    text=f"No protection data for {volume_id} in period {period}"
                )]
            
            output = self._format_output(volume_id, volume_guid, period, serials, analysis, show_details)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            logger.error(f"Tool error: {e}")
            import traceback
            traceback.print_exc()
            return self.format_error(str(e))
    
    def _format_output(self, vol_id, vol_guid, period, serials, analysis, show_details) -> str:
        """Format comprehensive output."""
        stats = analysis.get_statistics()
        insights = analysis.get_insights()
        
        out = f"""🛡️ DATA PROTECTION METRICS - PORTAL OPS IQ

=== VOLUME ===
Name: {vol_id}
GUID: {vol_guid}
"""
        
        if stats.get("latest_snapshot"):
            latest = stats["latest_snapshot"]
            out += f"""
📌 LATEST SNAPSHOT
Version: {latest['volume_version']}
Appliance: {latest['appliance']} ({latest['serial_number'][:16]}...)
Completed: {latest['completed_at']}
Protection Time: {latest['protect_mean']} (max: {latest['protect_max']})
OUD: {latest['oud']}
Files: {latest['files_protected']}{' (includes GFL)' if latest['has_gfl'] else ''}
"""
        
        out += f"""
=== ANALYSIS PERIOD ===
Period: {period} | Snapshots: {stats['complete_snapshots']} | Appliances: {len(serials)}
Range: {stats['time_range']['start']} → {stats['time_range']['end']}
"""
        
        if stats.get("average_data_protection_time"):
            avg = stats["average_data_protection_time"]
            out += f"""
=== ⭐ AVERAGE DATA PROTECTION TIME ===
{avg['human']} ({avg['seconds']:.0f}s)
{avg['description']}
"""
        
        if stats.get("protection_anomalies"):
            anom = stats["protection_anomalies"]
            out += f"""
=== ⚠️ PROTECTION ANOMALIES ===
Max Unprotected Time: {anom['max_unprotected_time']}
Worst Cases:
"""
            for case in anom["worst_cases"]:
                out += f"  • {case['appliance']} at {case['time']}: {case['unprotected_time']} (v{case['version']})\n"
        
        if stats.get("data_phase_performance"):
            data = stats["data_phase_performance"]
            out += f"""
=== DATA PHASE (Cloud Upload) ===
Average: {data['avg']} | Min: {data['min']} | Max: {data['max']}
Slowest: {data['slowest_appliance']} ({data.get('slowest_files', 'N/A')} files)
"""
        
        if stats.get("metadata_phase_performance"):
            meta = stats["metadata_phase_performance"]
            out += f"""
=== METADATA PHASE (Restore Point Creation) ===
Average: {meta['avg']} | Min: {meta['min']} | Max: {meta['max']}
Slowest: {meta['slowest_appliance']}
"""
        
        if stats.get("file_statistics"):
            files = stats["file_statistics"]
            out += f"""
=== FILE STATISTICS ===
Total Protected: {files['total_protected']:,} files
Avg per Snapshot: {files['avg_per_snapshot']:.0f}
Range: {files['min_in_snapshot']} - {files['max_in_snapshot']} files
"""
        
        if stats.get("by_appliance"):
            out += "\n=== BY APPLIANCE ===\n"
            
            for app, app_stats in sorted(stats["by_appliance"].items(), key=lambda x: x[1]["snapshots"], reverse=True):
                out += f"\n📡 {app}\n"
                out += f"   Latest: v{app_stats['latest_version']} at {app_stats['latest_time']}\n"
                out += f"   Snapshots: {app_stats['snapshots']}\n"
                out += f"   Avg Protection: {app_stats['avg_protect_time']}\n"
                out += f"   Worst Case: {app_stats['worst_protect_time']}\n"
                out += f"   Avg OUD: {app_stats['avg_oud']}\n"
                out += f"   Files: {app_stats['total_files']:,}\n"
        
        out += "\n=== 💡 INSIGHTS ===\n"
        for insight in insights:
            out += f"{insight}\n"
        
        if show_details and analysis.complete_snapshots:
            out += "\n=== 📊 DETAILED SNAPSHOTS (Last 5) ===\n"
            for snap in analysis.complete_snapshots[-5:]:
                s = snap.get_summary_dict()
                out += f"\nv{s['volume_version']} | {s['appliance']} | {s['timestamp']}\n"
                out += f"  Protection: {s['protect_mean']} (max {s['protect_max']}) | OUD: {s['oud']}\n"
                out += f"  Phases: Data {s['data_phase']}, Metadata {s['metadata_phase']}\n"
                out += f"  Files: {s['files_total']} ({s['files_gfl'] or 0} GFL)\n"
        
        out += "\n📊 Portal Ops IQ - Real-time protection telemetry\n"
        
        return out


class CompareVolumeProtectionMetricsTool(BaseTool):

    """Tool to compare protection metrics across multiple volumes."""
    
    def __init__(
        self, 
        api_client: PortalDataProtectionAPIClient,
        integration_helper: NMCPortalIntegration
    ):
        super().__init__(
            name="compare_volume_protection_metrics",
            description="[TELEMETRY] Compare data protection metrics across multiple volumes using Portal Ops IQ. Shows which volumes have better/worse protection times, faster/slower snapshots, and identifies performance outliers."
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
                    "description": "List of volume names or GUIDs to compare (minimum 2)"
                },
                "period": {
                    "type": "string",
                    "description": "Time period for analysis (default: PT3H)",
                    "default": "PT3H"
                }
            },
            "required": ["volumes"]
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
                
                # Get filer serials
                serials = await self.integration.get_filer_serials_for_volume(volume_guid)
                if not serials:
                    logger.warning(f"No filers found for volume: {vol_id}, skipping")
                    continue
                
                # Get telemetry
                analysis = await self.api_client.get_volume_data_protection_analysis(
                    volume_guid=volume_guid,
                    serial_numbers=serials,
                    period=period
                )
                
                if analysis.complete_snapshots:
                    volume_data.append({
                        "identifier": vol_id,
                        "guid": volume_guid,
                        "analysis": analysis,
                        "stats": analysis.get_statistics()
                    })
            
            if not volume_data:
                return self.format_error("No valid data found for any volumes")
            
            output = self._format_comparison(volume_data, period)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            logger.error(f"Comparison error: {e}")
            import traceback
            traceback.print_exc()
            return self.format_error(str(e))
    
    def _format_comparison(self, volume_data: List[Dict], period: str) -> str:
        """Format comparison output."""
        
        out = f"""📊 VOLUME PROTECTION COMPARISON

=== OVERVIEW ===
Volumes: {len(volume_data)} | Period: {period}

=== COMPARISON TABLE ===

{"Volume":<35} {"Latest Ver":<12} {"Avg Protect":<15} {"Snapshots":<10}
{"-"*75}
"""
        
        for vol in volume_data:
            name = vol["identifier"][:33]
            stats = vol["stats"]
            
            latest_ver = stats.get("latest_snapshot", {}).get("volume_version", "N/A")
            avg_prot = stats.get("average_data_protection_time", {}).get("human", "N/A")
            snap_count = stats.get("complete_snapshots", 0)
            
            out += f"{name:<35} {str(latest_ver):<12} {str(avg_prot):<15} {snap_count:<10}\n"
        
        # Rankings
        volumes_with_avg = [
            (v, v["stats"].get("average_data_protection_time", {}).get("seconds", float('inf')))
            for v in volume_data
            if "average_data_protection_time" in v["stats"]
        ]
        
        if volumes_with_avg:
            volumes_with_avg.sort(key=lambda x: x[1])
            best = volumes_with_avg[0]
            worst = volumes_with_avg[-1]
            
            out += f"""
=== RANKINGS ===

Best Protection (Fastest):
   {best[0]['identifier']}: {best[0]['stats']['average_data_protection_time']['human']}

Needs Attention (Slowest):
   {worst[0]['identifier']}: {worst[0]['stats']['average_data_protection_time']['human']}
"""
        
        # Per-volume insights
        out += "\n=== INSIGHTS BY VOLUME ===\n"
        for vol in volume_data:
            insights = vol["analysis"].get_insights()
            if insights:
                out += f"\n{vol['identifier']}:\n"
                for insight in insights[:3]:  # Top 3
                    out += f"  {insight}\n"
        
        return out
    

class GetEndToEndProtectionTimingTool(BaseTool):
    """Tool for complete protection + propagation cycle timing."""
    
    def __init__(self, protection_client, propagation_client, integration_helper):
        super().__init__(
            name="get_end_to_end_protection_timing",
            description="[TELEMETRY - COMPLETE CYCLE] Get complete protection cycle: data change → snapshot → sync to all appliances. Combines protection and propagation to show total time for data to be protected AND available everywhere. USE FOR: 'End-to-end protection time', 'Total protection cycle', 'How long until data is everywhere?'."
        )
        self.protection_client = protection_client
        self.propagation_client = propagation_client
        self.integration = integration_helper
    
    def get_schema(self) -> Dict[str, Any]:
        """Get schema."""
        return {
            "type": "object",
            "properties": {
                "volume": {"type": "string", "description": "Volume name or GUID"},
                "period": {"type": "string", "description": "Time period (default: PT3H)"}
            },
            "required": ["volume"]
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute."""
        try:
            volume_id = arguments.get("volume", "").strip()
            if not volume_id:
                return self.format_error("Volume required")
            
            period = arguments.get("period", "PT3H")
            
            volume_guid, _ = await self.integration.resolve_volume_identifier(volume_id)
            if not volume_guid:
                return self.format_error(f"Volume not found: {volume_id}")
            
            serials = await self.integration.get_filer_serials_for_volume(volume_guid)
            if not serials:
                return self.format_error(f"No filers found: {volume_id}")
            
            # Get both datasets
            protection = await self.protection_client.get_volume_data_protection_analysis(
                volume_guid, serials, period
            )
            propagation = await self.propagation_client.get_volume_data_propagation_analysis(
                volume_guid, serials, period
            )
            
            output = self._format_combined(volume_id, period, protection, propagation)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            logger.error(f"Error: {e}")
            return self.format_error(str(e))
    
    def _format_combined(self, vol_id, period, protection, propagation) -> str:
        """Format combined output."""
        prot_stats = protection.get_statistics()
        prop_stats = propagation.get_statistics() if propagation.events else {}
        
        out = f"""🔄 END-TO-END PROTECTION TIMING

Volume: {vol_id} | Period: {period}
"""
        
        if prot_stats.get("latest_snapshot"):
            latest = prot_stats["latest_snapshot"]
            out += f"\n📌 Latest: v{latest['volume_version']} by {latest['appliance']}\n"
        
        if prot_stats.get("average_data_protection_time"):
            avg_prot = prot_stats["average_data_protection_time"]
            out += f"\n⏱️ STEP 1: Protection (Change → Snapshot)\nAvg: {avg_prot['human']}\n"
        
        if prop_stats.get("propagation_statistics"):
            avg_prop = prop_stats["propagation_statistics"]
            out += f"\n⏱️ STEP 2: Propagation (Snapshot → All Appliances)\nAvg: {avg_prop['avg_time']}\n"
        
        if prot_stats.get("average_data_protection_time") and prop_stats.get("propagation_statistics"):
            total = prot_stats["average_data_protection_time"]["seconds"] + prop_stats["propagation_statistics"]["avg_seconds"]
            out += f"\n⏱️ TOTAL: {self._fmt(total)}\n"
        
        return out
    
    def _fmt(self, sec):
        """Format seconds."""
        if sec < 60:
            return f"{sec:.1f}s"
        return f"{sec/60:.1f}m"