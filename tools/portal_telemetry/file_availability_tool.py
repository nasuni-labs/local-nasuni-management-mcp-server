#!/usr/bin/env python3
"""File Availability Timing Tool.

This tool calculates the total time for a file to be protected and propagated
from a source appliance to a destination appliance. It answers questions like:

"For VolDemoOpsIQ, if I upload a file on demoedge2, how long before 
the data shows up on the demoedge3 appliance?"

The calculation combines:
1. Average Time to Protect (from source appliance)
2. Snapshot Propagation Time (from source to destination appliance)

Total Time = Protection Time + Propagation Time
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from mcp.types import TextContent

from api.portal_telemetry_api import PortalVolumeTelemetryAPIClient
from tools.base_tool import BaseTool
from tools.portal_telemetry.volume_tools import BaseVolumeTelemetryTool, VolumeResolutionError
from utils.portal_nmc_integration import NMCPortalIntegration
from config.logging_setup import get_logger

logger = get_logger(__name__)


class FileAvailabilityTimingTool(BaseVolumeTelemetryTool):
    """
    Calculate total time for a file to be available on a destination appliance.
    
    This tool combines:
    1. Protection time - How long to protect data on the source appliance
    2. Propagation time - How long for that snapshot to sync to destination
    
    Answers questions like: "If I upload a file on Edge A, how long until 
    it appears on Edge B?"
    """

    def __init__(
        self,
        api_client: PortalVolumeTelemetryAPIClient,
        integration_helper: NMCPortalIntegration,
    ):
        super().__init__(
            name="end_to_end_data_propagation",
            description=(
                "[PORTAL] Calculate total time for a file uploaded on one appliance to be "
                "available on another appliance. Combines protection time (time to create snapshot) "
                "and propagation time (time to sync snapshot to destination). "
                "Use this to answer: 'If I upload a file on Edge A, how long until it shows up on Edge B?' "
                "Accepts volume name or GUID, and appliance names or serial numbers."
            ),
            integration_helper=integration_helper,
            protection_client=api_client,
            propagation_client=api_client,
        )
        self.api_client = api_client

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "volume": {
                    "type": "string",
                    "description": "Volume name or GUID (e.g., 'VolDemoOpsIQ' or the volume GUID)",
                },
                "source_appliance": {
                    "type": "string",
                    "description": "Source appliance where files are uploaded (name or serial number, e.g., 'demoEdge2')",
                },
                "destination_appliance": {
                    "type": "string",
                    "description": "Destination appliance where files should appear (name or serial number, e.g., 'demoEdge3')",
                },
                "period": {
                    "type": "string",
                    "description": "Time period for analysis (ISO 8601). Default: P3D (3 days). Max: P4D (4 days). Examples: PT12H, P1D, P3D, P4D",
                    "default": "P3D",
                },
            },
            "required": ["volume", "source_appliance", "destination_appliance"],
        }

    async def _resolve_appliance_serial(self, identifier: str) -> Optional[str]:
        """Resolve appliance name/identifier to serial number."""
        serial, match_type = await self.integration.resolve_filer_identifier(identifier)
        if serial:
            logger.info(f"Resolved appliance '{identifier}' to serial '{serial}' via {match_type}")
            return serial
        logger.warning(f"Could not resolve appliance identifier: {identifier}")
        return None

    async def _do_execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        volume_id = arguments.get("volume", "").strip()
        source_appliance = arguments.get("source_appliance", "").strip()
        dest_appliance = arguments.get("destination_appliance", "").strip()
        period = arguments.get("period", "P3D")

        if not volume_id:
            return self.format_error("Volume name or GUID required")
        if not source_appliance:
            return self.format_error("Source appliance required")
        if not dest_appliance:
            return self.format_error("Destination appliance required")

        # Resolve volume
        volume_guid, all_serials = await self._resolve_volume(volume_id)
        logger.info(f"Resolved volume '{volume_id}' to GUID '{volume_guid}' with {len(all_serials)} filer(s)")

        # Resolve appliance identifiers to serial numbers
        source_serial = await self._resolve_appliance_serial(source_appliance)
        dest_serial = await self._resolve_appliance_serial(dest_appliance)

        if not source_serial:
            return self.format_error(f"Could not resolve source appliance: {source_appliance}")
        if not dest_serial:
            return self.format_error(f"Could not resolve destination appliance: {dest_appliance}")

        # Validate that both appliances are connected to this volume
        if source_serial not in all_serials:
            logger.warning(f"Source appliance {source_serial} not in volume's appliance list: {all_serials}")
        if dest_serial not in all_serials:
            logger.warning(f"Destination appliance {dest_serial} not in volume's appliance list: {all_serials}")

        # Fetch protection timing for source appliance
        protection_result = await self._get_protection_time(
            volume_guid, source_serial, period
        )

        # Fetch propagation timing from source to destination
        propagation_result = await self._get_propagation_time(
            volume_guid, all_serials, source_serial, dest_serial, period
        )

        # Generate report
        report = self._generate_report(
            volume_id=volume_id,
            volume_guid=volume_guid,
            source_appliance=source_appliance,
            source_serial=source_serial,
            dest_appliance=dest_appliance,
            dest_serial=dest_serial,
            period=period,
            protection_result=protection_result,
            propagation_result=propagation_result,
        )

        return [TextContent(type="text", text=report)]

    async def _get_protection_time(
        self,
        volume_guid: str,
        source_serial: str,
        period: str,
    ) -> Dict[str, Any]:
        """Get average time to protect from source appliance.
        
        Uses the snapshot_details endpoint (via get_volume_data_protection_analysis)
        and filters snapshots created by the source appliance.
        """
        try:
            # Use snapshot_details which has protect_mean data
            analysis = await self.api_client.get_volume_data_protection_analysis(
                volume_guid=volume_guid,
                serial_numbers=[source_serial],
                period=period,
                smart_sampling=False,  # Get all data for accurate stats
            )

            if not analysis.complete_snapshots:
                logger.warning(f"No complete snapshots found for appliance {source_serial}")
                return {"error": "No protection data available for this appliance", "avg_seconds": None}

            # Filter snapshots created by the source appliance
            source_snapshots = [
                s for s in analysis.complete_snapshots
                if s.serial_number == source_serial
            ]
            
            # If no exact match, use all snapshots (might be filtering issue)
            if not source_snapshots:
                logger.info(f"No snapshots matched serial {source_serial}, using all {len(analysis.complete_snapshots)} snapshots")
                source_snapshots = analysis.complete_snapshots

            # Extract protection times (in seconds)
            protect_times = [
                s.protect_mean_seconds for s in source_snapshots
                if s.protect_mean_seconds is not None
            ]
            
            logger.info(f"Found {len(protect_times)} protection time values from {len(source_snapshots)} snapshots")
            
            if not protect_times:
                return {"error": "No valid protection time data", "avg_seconds": None}

            avg_seconds = sum(protect_times) / len(protect_times)
            min_seconds = min(protect_times)
            max_seconds = max(protect_times)

            return {
                "avg_seconds": avg_seconds,
                "min_seconds": min_seconds,
                "max_seconds": max_seconds,
                "data_points": len(protect_times),
                "error": None,
            }

        except Exception as e:
            logger.error(f"Error fetching protection time: {e}")
            return {"error": str(e), "avg_seconds": None}

    async def _get_propagation_time(
        self,
        volume_guid: str,
        all_serials: List[str],
        source_serial: str,
        dest_serial: str,
        period: str,
    ) -> Dict[str, Any]:
        """Get average propagation time from source to destination.
        
        Uses the snapshot_propagation_by_appliance endpoint and filters
        events where:
        - snapshot_serial_number == source_serial (snapshot created by source)
        - sync_serial_number == dest_serial (synced by destination)
        """
        try:
            # Fetch propagation data for all appliances on the volume
            response = await self.api_client.get_volume_data_propagation(
                volume_guid=volume_guid,
                serial_numbers=all_serials,
                period=period,
                smart_sampling=False,  # Get all data for accurate analysis
            )

            if "error" in response:
                return {"error": response["error"], "avg_seconds": None}

            items = response.get("items", [])
            if not items:
                return {"error": "No propagation data available", "avg_seconds": None}

            # Filter events: source created snapshot, destination synced it
            sync_times = []
            for item in items:
                snapshot_serial = item.get("snapshot_serial_number", "")
                sync_serial = item.get("sync_serial_number", "")
                propagation_duration = item.get("propagation_duration")

                # Match: snapshot from source, sync to destination
                if (snapshot_serial == source_serial and 
                    sync_serial == dest_serial and
                    propagation_duration is not None):
                    try:
                        sync_times.append(float(propagation_duration))
                    except (ValueError, TypeError):
                        pass

            if not sync_times:
                # Try alternative: just look at destination's sync times
                # This might happen if naming doesn't match exactly
                for item in items:
                    sync_serial = item.get("sync_serial_number", "")
                    propagation_duration = item.get("propagation_duration")
                    
                    if sync_serial == dest_serial and propagation_duration is not None:
                        try:
                            sync_times.append(float(propagation_duration))
                        except (ValueError, TypeError):
                            pass
                
                if sync_times:
                    logger.info(f"Using all sync times for destination {dest_serial} (no exact source match)")

            if not sync_times:
                return {
                    "error": f"No sync events found from {source_serial} to {dest_serial}",
                    "avg_seconds": None,
                }

            avg_ms = sum(sync_times) / len(sync_times)
            min_ms = min(sync_times)
            max_ms = max(sync_times)

            return {
                "avg_seconds": avg_ms / 1000.0,
                "min_seconds": min_ms / 1000.0,
                "max_seconds": max_ms / 1000.0,
                "data_points": len(sync_times),
                "error": None,
            }

        except Exception as e:
            logger.error(f"Error fetching propagation time: {e}")
            return {"error": str(e), "avg_seconds": None}

    def _format_time(self, seconds: Optional[float]) -> str:
        """Format time in human-readable format."""
        if seconds is None:
            return "N/A"
        
        if seconds < 60:
            return f"{seconds:.1f} seconds"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f} minutes ({seconds:.0f}s)"
        else:
            hours = seconds / 3600
            minutes = (seconds % 3600) / 60
            return f"{hours:.1f} hours ({minutes:.0f}m)"

    def _generate_report(
        self,
        volume_id: str,
        volume_guid: str,
        source_appliance: str,
        source_serial: str,
        dest_appliance: str,
        dest_serial: str,
        period: str,
        protection_result: Dict[str, Any],
        propagation_result: Dict[str, Any],
    ) -> str:
        """Generate the file availability timing report."""
        
        lines = [
            "=" * 70,
            "📁 FILE AVAILABILITY TIMING REPORT",
            "=" * 70,
            "",
            f"Volume: {volume_id}",
            f"Volume GUID: {volume_guid}",
            f"Analysis Period: {period}",
            "",
            f"Source Appliance: {source_appliance}",
            f"  Serial: {source_serial}",
            f"Destination Appliance: {dest_appliance}",
            f"  Serial: {dest_serial}",
            "",
        ]

        # Protection Time Section
        lines.append("=" * 70)
        lines.append("⏱️  STEP 1: TIME TO PROTECT (on source appliance)")
        lines.append("=" * 70)
        lines.append("")
        lines.append("This is how long it takes for a file uploaded on the source")
        lines.append("appliance to be included in a protection snapshot.")
        lines.append("")

        protection_avg = protection_result.get("avg_seconds")
        if protection_result.get("error"):
            lines.append(f"⚠️  Error: {protection_result['error']}")
            lines.append("")
        elif protection_avg is not None:
            lines.append(f"  Average Protection Time: {self._format_time(protection_avg)}")
            lines.append(f"  Minimum: {self._format_time(protection_result.get('min_seconds'))}")
            lines.append(f"  Maximum: {self._format_time(protection_result.get('max_seconds'))}")
            lines.append(f"  Data Points: {protection_result.get('data_points', 0)}")
            lines.append("")
        else:
            lines.append("  No protection time data available")
            lines.append("")

        # Propagation Time Section
        lines.append("=" * 70)
        lines.append("🔄 STEP 2: TIME TO PROPAGATE (source → destination)")
        lines.append("=" * 70)
        lines.append("")
        lines.append("This is how long it takes for a snapshot created on the source")
        lines.append("appliance to sync to the destination appliance.")
        lines.append("")

        propagation_avg = propagation_result.get("avg_seconds")
        if propagation_result.get("error"):
            lines.append(f"⚠️  Error: {propagation_result['error']}")
            lines.append("")
        elif propagation_avg is not None:
            lines.append(f"  Average Propagation Time: {self._format_time(propagation_avg)}")
            lines.append(f"  Minimum: {self._format_time(propagation_result.get('min_seconds'))}")
            lines.append(f"  Maximum: {self._format_time(propagation_result.get('max_seconds'))}")
            lines.append(f"  Data Points: {propagation_result.get('data_points', 0)}")
            lines.append("")
        else:
            lines.append("  No propagation time data available")
            lines.append("")

        # Total Time Section
        lines.append("=" * 70)
        lines.append("⏰ TOTAL FILE AVAILABILITY TIME")
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"Question: If I upload a file on {source_appliance}, how long")
        lines.append(f"until it appears on {dest_appliance}?")
        lines.append("")

        if protection_avg is not None and propagation_avg is not None:
            total_avg = protection_avg + propagation_avg
            total_min = (protection_result.get("min_seconds") or 0) + (propagation_result.get("min_seconds") or 0)
            total_max = (protection_result.get("max_seconds") or 0) + (propagation_result.get("max_seconds") or 0)

            lines.append("  ┌─────────────────────────────────────────────────────────────┐")
            lines.append(f"  │  AVERAGE TOTAL TIME: {self._format_time(total_avg):^38} │")
            lines.append("  └─────────────────────────────────────────────────────────────┘")
            lines.append("")
            lines.append("  Breakdown:")
            lines.append(f"    • Protection Time:   {self._format_time(protection_avg)}")
            lines.append(f"    • Propagation Time:  {self._format_time(propagation_avg)}")
            lines.append(f"    ─────────────────────────────")
            lines.append(f"    • TOTAL:             {self._format_time(total_avg)}")
            lines.append("")
            lines.append(f"  Best Case (minimum):   {self._format_time(total_min)}")
            lines.append(f"  Worst Case (maximum):  {self._format_time(total_max)}")
            lines.append("")

            # Health assessment
            lines.append("  Status Assessment:")
            if total_avg < 120:  # < 2 minutes
                lines.append("  ✅ EXCELLENT - Files become available very quickly")
            elif total_avg < 300:  # < 5 minutes
                lines.append("  ✅ GOOD - Files become available within a reasonable time")
            elif total_avg < 900:  # < 15 minutes
                lines.append("  ⚠️ MODERATE - Consider snapshot frequency or network optimization")
            elif total_avg < 3600:  # < 1 hour
                lines.append("  ⚠️ SLOW - Review protection schedule and network connectivity")
            else:
                lines.append("  🚨 CRITICAL - Significant delay in file availability")
                lines.append("     Consider: Increase snapshot frequency, check network latency")
        else:
            lines.append("  ❌ Unable to calculate total time due to missing data")
            lines.append("")
            if protection_avg is None:
                lines.append(f"     • Missing protection time data for {source_appliance}")
            if propagation_avg is None:
                lines.append(f"     • Missing propagation data from {source_appliance} to {dest_appliance}")

        lines.append("")
        lines.append("=" * 70)
        lines.append("ℹ️  UNDERSTANDING THIS REPORT")
        lines.append("=" * 70)
        lines.append("")
        lines.append("Protection Time: The interval between when a file is written and")
        lines.append("when it's included in a protection snapshot. This depends on your")
        lines.append("snapshot frequency configuration.")
        lines.append("")
        lines.append("Propagation Time: The time for a completed snapshot to sync from")
        lines.append("the source appliance to the destination. This depends on network")
        lines.append("speed, snapshot size, and appliance workload.")
        lines.append("")
        lines.append("Note: These are historical averages. Actual times may vary based")
        lines.append("on current conditions (file sizes, network load, etc.)")
        lines.append("")

        return "\n".join(lines)


def register_file_availability_timing_tool(
    registry,
    api_client: PortalVolumeTelemetryAPIClient,
    integration_helper: NMCPortalIntegration,
) -> None:
    """Register the file availability timing tool."""
    tool = FileAvailabilityTimingTool(api_client, integration_helper)
    registry.register_tool(tool)
    logger.info(f"Registered file availability timing tool: {tool.name}")
