#!/usr/bin/env python3
"""Portal tools for checking appliance sync status and lag detection."""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from mcp.types import TextContent
from tools.base_tool import BaseTool
from api.portal_data_protection_api import PortalDataProtectionAPIClient
from api.portal_data_propagation_api import PortalDataPropagationAPIClient
from utils.portal_nmc_integration import NMCPortalIntegration
from config.logging_setup import get_logger

logger = get_logger(__name__)


class GetVolumeLatestVersionTool(BaseTool):
    """Tool to get the latest volume version and which appliance created it."""
    
    def __init__(
        self,
        protection_client: PortalDataProtectionAPIClient,
        integration_helper: NMCPortalIntegration
    ):
        super().__init__(
            name="get_volume_latest_version",
            description="[TELEMETRY] Get the latest volume/snapshot version number and which appliance created it. USE FOR: 'What is the latest version?', 'Latest snapshot version?', 'Which appliance created the latest snapshot?', 'When was the latest snapshot?'. Shows the highest volume_version across all appliances and when it was created."
        )
        self.protection_client = protection_client
        self.integration = integration_helper
    
    def get_schema(self) -> Dict[str, Any]:
        """Get schema."""
        return {
            "type": "object",
            "properties": {
                "volume": {
                    "type": "string",
                    "description": "Volume name or GUID"
                },
                "period": {
                    "type": "string",
                    "description": "Time period to check (default: PT3H)",
                    "default": "PT3H"
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
            
            # Resolve volume
            volume_guid, _ = await self.integration.resolve_volume_identifier(volume_id)
            if not volume_guid:
                return self.format_error(f"Volume not found: {volume_id}")
            
            # Get serials
            serials = await self.integration.get_filer_serials_for_volume(volume_guid)
            if not serials:
                return self.format_error(f"No filers found for volume: {volume_id}")
            
            # Get protection data to find latest snapshot
            analysis = await self.protection_client.get_volume_data_protection_analysis(
                volume_guid, serials, period
            )
            
            if not analysis.complete_snapshots:
                return [TextContent(
                    type="text",
                    text=f"No snapshot data found for {volume_id} in period {period}"
                )]
            
            latest = analysis.latest_snapshot
            
            output = f"""📌 LATEST VOLUME VERSION

Volume: {vol_id}
Latest Version: {latest.volume_version}
Created By: {latest.appliance} ({latest.serial_number})
Completed At: {latest.timestamp_str}

Protection Metrics:
  Avg Time Unprotected: {latest.format_duration(latest.protect_mean_seconds)}
  Max Time Unprotected: {latest.format_duration(latest.protect_max_seconds)}
  Oldest Unprotected Data: {latest.format_duration(latest.oud_seconds)}
  Files Protected: {latest.file_count_total}

Snapshot Phases:
  Data Phase: {latest.format_duration(latest.data_phase_duration_seconds)}
  Metadata Phase: {latest.format_duration(latest.metadata_phase_duration_seconds)}
  Total Duration: {latest.format_duration(latest.total_snapshot_duration_seconds)}
"""
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            logger.error(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return self.format_error(str(e))


class CheckApplianceSyncStatusTool(BaseTool):
    """Tool to check if an appliance is up-to-date with latest snapshot."""
    
    def __init__(
        self,
        protection_client: PortalDataProtectionAPIClient,
        propagation_client: PortalDataPropagationAPIClient,
        integration_helper: NMCPortalIntegration
    ):
        super().__init__(
            name="check_appliance_sync_status",
            description="[TELEMETRY - SYNC STATUS] Check if a specific appliance is up-to-date with the latest volume snapshot. Shows sync lag and detects stale appliances. USE FOR: 'Is appliance X up to date?', 'Check sync status for appliance', 'Is appliance behind?', 'Show appliance sync lag', 'Latest version on appliance X?'. Detects: appliances >1hr behind (lagging), >3hr behind (critical issue). Shows both latest snapshot created and latest sync completed."
        )
        self.protection_client = protection_client
        self.propagation_client = propagation_client
        self.integration = integration_helper
    
    def get_schema(self) -> Dict[str, Any]:
        """Get schema."""
        return {
            "type": "object",
            "properties": {
                "volume": {
                    "type": "string",
                    "description": "Volume name or GUID"
                },
                "appliance": {
                    "type": "string",
                    "description": "Appliance name (description) or serial number to check"
                },
                "period": {
                    "type": "string",
                    "description": "Time period to analyze (default: PT6H)",
                    "default": "PT6H"
                }
            },
            "required": ["volume", "appliance"]
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the tool."""
        try:
            volume_id = arguments.get("volume", "").strip()
            appliance_id = arguments.get("appliance", "").strip()
            
            if not volume_id or not appliance_id:
                return self.format_error("Both volume and appliance required")
            
            period = arguments.get("period", "PT6H")
            
            # Resolve volume
            volume_guid, _ = await self.integration.resolve_volume_identifier(volume_id)
            if not volume_guid:
                return self.format_error(f"Volume not found: {volume_id}")
            
            # Get serials
            serials = await self.integration.get_filer_serials_for_volume(volume_guid)
            if not serials:
                return self.format_error(f"No filers found for volume: {volume_id}")
            
            # Get protection data (to find latest snapshot overall)
            protection = await self.protection_client.get_volume_data_protection_analysis(
                volume_guid, serials, period
            )
            
            if not protection.complete_snapshots:
                return [TextContent(
                    type="text",
                    text=f"No snapshot data for {volume_id}"
                )]
            
            # Find latest snapshot across ALL appliances
            latest_overall = protection.latest_snapshot
            
            # Get propagation data (to see sync status)
            propagation = await self.propagation_client.get_volume_data_propagation_analysis(
                volume_guid, serials, period
            )
            
            # Find this specific appliance's status
            output = self._analyze_appliance_status(
                volume_id,
                appliance_id,
                latest_overall,
                protection,
                propagation
            )
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            logger.error(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return self.format_error(str(e))
    
    def _analyze_appliance_status(
        self,
        volume_id: str,
        appliance_id: str,
        latest_overall,
        protection,
        propagation
    ) -> str:
        """Analyze specific appliance's sync status."""
        
        # Find snapshots created by this appliance
        appliance_snapshots = [
            s for s in protection.complete_snapshots
            if appliance_id in s.appliance or appliance_id in s.serial_number
        ]
        
        # Find syncs TO this appliance
        appliance_syncs = [
            e for e in propagation.events
            if appliance_id in e.sync_appliance or appliance_id in e.sync_serial_number
        ]
        
        # Determine latest version on this appliance
        latest_snapshot_version = None
        latest_snapshot_time = None
        latest_snapshot_source = "none"
        
        if appliance_snapshots:
            latest_snap = max(appliance_snapshots, key=lambda s: s.volume_version)
            latest_snapshot_version = latest_snap.volume_version
            latest_snapshot_time = latest_snap.timestamp
            latest_snapshot_source = "snapshot"
        
        if appliance_syncs:
            latest_sync = max(appliance_syncs, key=lambda e: e.snapshot_version)
            if (latest_snapshot_version is None or 
                latest_sync.snapshot_version > latest_snapshot_version):
                latest_snapshot_version = latest_sync.snapshot_version
                latest_snapshot_time = latest_sync.sync_datetime
                latest_snapshot_source = "sync"
        
        # Calculate lag
        lag_versions = 0
        lag_time = None
        status = "✅ UP TO DATE"
        
        if latest_snapshot_version and latest_overall.volume_version:
            lag_versions = latest_overall.volume_version - latest_snapshot_version
            
            if latest_snapshot_time and latest_overall.timestamp:
                lag_time = latest_overall.timestamp - latest_snapshot_time
                lag_hours = lag_time.total_seconds() / 3600
                
                if lag_versions > 0:
                    if lag_hours > 3:
                        status = "🚨 CRITICAL LAG"
                    elif lag_hours > 1:
                        status = "⚠️ LAGGING"
                    else:
                        status = "⏳ SLIGHTLY BEHIND"
        
        # Build output
        out = f"""🔍 APPLIANCE SYNC STATUS

=== APPLIANCE ===
Appliance: {appliance_id}
Volume: {volume_id}
Status: {status}

=== LATEST SNAPSHOT (VOLUME-WIDE) ===
Version: {latest_overall.volume_version}
Created By: {latest_overall.appliance}
Completed: {latest_overall.timestamp_str}

=== THIS APPLIANCE'S LATEST VERSION ===
Version: {latest_snapshot_version if latest_snapshot_version else 'No data'}
Source: {latest_snapshot_source.upper()}
"""
        
        if latest_snapshot_time:
            out += f"Last Updated: {latest_snapshot_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        if lag_versions > 0:
            out += f"""
=== ⚠️ SYNC LAG DETECTED ===
Versions Behind: {lag_versions}
"""
            if lag_time:
                lag_hours = lag_time.total_seconds() / 3600
                lag_minutes = lag_time.total_seconds() / 60
                
                out += f"Time Behind: {lag_hours:.1f} hours ({lag_minutes:.0f} minutes)\n"
                
                if lag_hours > 3:
                    out += "\n🚨 CRITICAL: Appliance hasn't synced in over 3 hours - investigate immediately!\n"
                    out += "   Possible issues: Network connectivity, sync disabled, appliance offline\n"
                elif lag_hours > 1:
                    out += "\n⚠️ WARNING: Appliance hasn't synced in over 1 hour\n"
                    out += "   Monitor closely - may indicate sync performance issues\n"
                else:
                    out += "\nℹ️ Minor lag - within normal sync schedule\n"
        else:
            out += "\n✅ Appliance is current with latest snapshot\n"
        
        # Show snapshot vs sync activity
        if appliance_snapshots:
            out += f"\nSnapshot Activity: {len(appliance_snapshots)} snapshots created by this appliance\n"
            latest_created = max(appliance_snapshots, key=lambda s: s.volume_version)
            out += f"  Last created: v{latest_created.volume_version} at {latest_created.timestamp_str}\n"
        
        if appliance_syncs:
            out += f"\nSync Activity: {len(appliance_syncs)} syncs completed by this appliance\n"
            latest_sync = max(appliance_syncs, key=lambda e: e.snapshot_version)
            out += f"  Last synced: v{latest_sync.snapshot_version} at {latest_sync.sync_time_str}\n"
            out += f"  Propagation time: {latest_sync.format_duration(latest_sync.propagation_duration)}\n"
        
        if not appliance_snapshots and not appliance_syncs:
            out += "\n⚠️ No snapshot or sync activity found for this appliance in the selected period\n"
        
        return out


class GetAllAppliancesSyncStatusTool(BaseTool):
    """Tool to check sync status for all appliances connected to a volume."""
    
    def __init__(
        self,
        protection_client: PortalDataProtectionAPIClient,
        propagation_client: PortalDataPropagationAPIClient,
        integration_helper: NMCPortalIntegration
    ):
        super().__init__(
            name="get_all_appliances_sync_status",
            description="[TELEMETRY - SYNC MONITORING] Check sync status for ALL appliances connected to a volume. Identifies lagging, stale, and out-of-sync appliances. USE FOR: 'Check sync status for all appliances', 'Which appliances are behind?', 'Show sync lag across appliances', 'Are all appliances up to date?', 'Sync health check'. Detects appliances >1hr behind (lagging) or >3hr behind (critical)."
        )
        self.protection_client = protection_client
        self.propagation_client = propagation_client
        self.integration = integration_helper
    
    def get_schema(self) -> Dict[str, Any]:
        """Get schema."""
        return {
            "type": "object",
            "properties": {
                "volume": {
                    "type": "string",
                    "description": "Volume name or GUID"
                },
                "period": {
                    "type": "string",
                    "description": "Time period to analyze (default: PT6H)"
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
            
            period = arguments.get("period", "PT6H")
            
            # Resolve volume
            volume_guid, _ = await self.integration.resolve_volume_identifier(volume_id)
            if not volume_guid:
                return self.format_error(f"Volume not found: {volume_id}")
            
            # Get serials
            serials = await self.integration.get_filer_serials_for_volume(volume_guid)
            if not serials:
                return self.format_error(f"No filers found for volume: {volume_id}")
            
            # Get both datasets
            protection = await self.protection_client.get_volume_data_protection_analysis(
                volume_guid, serials, period
            )
            
            propagation = await self.propagation_client.get_volume_data_propagation_analysis(
                volume_guid, serials, period
            )
            
            if not protection.complete_snapshots:
                return [TextContent(
                    type="text",
                    text=f"No snapshot data for {volume_id}"
                )]
            
            output = self._format_all_status(volume_id, protection, propagation, serials)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            logger.error(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return self.format_error(str(e))
    
    def _format_all_status(self, volume_id, protection, propagation, all_serials) -> str:
        """Format sync status for all appliances."""
        
        latest_overall = protection.latest_snapshot
        
        out = f"""🔍 ALL APPLIANCES SYNC STATUS

Volume: {volume_id}
Latest Version: {latest_overall.volume_version}
Created By: {latest_overall.appliance} at {latest_overall.timestamp_str}

=== APPLIANCE STATUS ===

"""
        
        # Build status for each appliance
        appliance_statuses = []
        
        # Get unique appliances from both sources
        all_appliances = set()
        
        for snap in protection.complete_snapshots:
            all_appliances.add((snap.appliance, snap.serial_number))
        
        for event in propagation.events:
            all_appliances.add((event.sync_appliance, event.sync_serial_number))
        
        for appliance_name, serial in all_appliances:
            # Find latest version for this appliance
            app_snapshots = [s for s in protection.complete_snapshots 
                           if s.appliance == appliance_name or s.serial_number == serial]
            
            app_syncs = [e for e in propagation.events
                        if e.sync_appliance == appliance_name or e.sync_serial_number == serial]
            
            latest_version = None
            latest_time = None
            source = "none"
            
            if app_snapshots:
                latest_snap = max(app_snapshots, key=lambda s: s.volume_version)
                latest_version = latest_snap.volume_version
                latest_time = latest_snap.timestamp
                source = "snapshot"
            
            if app_syncs:
                latest_sync = max(app_syncs, key=lambda e: e.snapshot_version)
                if latest_version is None or latest_sync.snapshot_version > latest_version:
                    latest_version = latest_sync.snapshot_version
                    latest_time = latest_sync.sync_datetime
                    source = "sync"
            
            # Calculate lag
            lag_versions = latest_overall.volume_version - (latest_version or 0)
            lag_time = None
            status_icon = "✅"
            status_text = "UP TO DATE"
            
            if latest_time and latest_overall.timestamp:
                lag_time = latest_overall.timestamp - latest_time
                lag_hours = lag_time.total_seconds() / 3600
                
                if lag_versions > 0:
                    if lag_hours > 3:
                        status_icon = "🚨"
                        status_text = "CRITICAL LAG"
                    elif lag_hours > 1:
                        status_icon = "⚠️"
                        status_text = "LAGGING"
                    else:
                        status_icon = "⏳"
                        status_text = "SLIGHTLY BEHIND"
            
            appliance_statuses.append({
                "name": appliance_name,
                "serial": serial,
                "version": latest_version,
                "time": latest_time,
                "source": source,
                "lag_versions": lag_versions,
                "lag_time": lag_time,
                "status_icon": status_icon,
                "status_text": status_text
            })
        
        # Sort by lag (worst first)
        appliance_statuses.sort(key=lambda x: x["lag_versions"], reverse=True)
        
        # Display each appliance
        for app in appliance_statuses:
            out += f"{app['status_icon']} {app['name']} ({app['serial'][:16]}...)\n"
            out += f"   Status: {app['status_text']}\n"
            out += f"   Latest Version: {app['version'] if app['version'] else 'No data'}\n"
            
            if app['time']:
                out += f"   Last Updated: {app['time'].strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            out += f"   Source: {app['source'].upper()}\n"
            
            if app['lag_versions'] > 0:
                out += f"   ⚠️ Versions Behind: {app['lag_versions']}\n"
                
                if app['lag_time']:
                    hours = app['lag_time'].total_seconds() / 3600
                    minutes = app['lag_time'].total_seconds() / 60
                    out += f"   ⚠️ Time Behind: {hours:.1f}h ({minutes:.0f}m)\n"
            
            out += "\n"
        
        # Summary
        critical = sum(1 for a in appliance_statuses if a['status_icon'] == '🚨')
        lagging = sum(1 for a in appliance_statuses if a['status_icon'] == '⚠️')
        current = sum(1 for a in appliance_statuses if a['status_icon'] == '✅')
        
        out += f"=== SUMMARY ===\n"
        out += f"Total Appliances: {len(appliance_statuses)}\n"
        out += f"✅ Up to Date: {current}\n"
        out += f"⚠️ Lagging (>1hr): {lagging}\n"
        out += f"🚨 Critical (>3hr): {critical}\n"
        
        if critical > 0:
            out += "\n🚨 ACTION REQUIRED: Investigate critical lag issues immediately\n"
        elif lagging > 0:
            out += "\n⚠️ ATTENTION: Monitor lagging appliances\n"
        else:
            out += "\n✅ All appliances are synchronized\n"
        
        return out