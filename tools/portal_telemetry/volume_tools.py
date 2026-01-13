#!/usr/bin/env python3
"""Portal Ops IQ volume telemetry tools.

This module provides tools for volume-focused telemetry operations:
- PortalVolumeTelemetryTool: Dynamic metric tool for volume metrics
- GetVolumeProtectionMetricsTool: Data protection analysis
- CompareVolumeProtectionMetricsTool: Cross-volume comparison
- GetEndToEndProtectionTimingTool: Complete protection cycle timing
- GetVolumePropagationMetricsTool: Sync timing metrics
- GetVolumeLatestVersionTool: Latest snapshot version info
- GetAllAppliancesSyncStatusTool: Multi-appliance sync monitoring
- CheckApplianceSyncStatusTool: Single appliance sync status check
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Tuple

from mcp.types import TextContent

from api.portal_telemetry_api import (
    VOLUME_TELEMETRY_CONFIG,
    PortalVolumeTelemetryAPIClient,
)
from tools.base_tool import BaseTool
from utils.portal_nmc_integration import NMCPortalIntegration
from config.logging_setup import get_logger

from tools.portal_telemetry._common import (
    VOLUME_PROPERTY,
    APPLIANCE_PROPERTY,
    PERIOD_PROPERTY_3H,
    PERIOD_PROPERTY_6H,
    _extract_primary_records,
    _summarize_records,
    _format_metadata,
    _raw_preview,
)

logger = get_logger(__name__)


# ============================================================================
# BASE CLASS FOR VOLUME TELEMETRY TOOLS
# ============================================================================


class VolumeResolutionError(Exception):
    """Raised when volume resolution fails."""
    pass


class BaseVolumeTelemetryTool(BaseTool):
    """Base class for volume telemetry tools with common patterns.
    
    Provides:
    - Volume resolution with error handling
    - Serial number lookup
    - Automatic error handling in execute()
    
    Subclasses only need to implement _do_execute() - no need to override execute().
    """

    def __init__(
        self,
        name: str,
        description: str,
        integration_helper: NMCPortalIntegration,
        protection_client: PortalVolumeTelemetryAPIClient = None,
        propagation_client: PortalVolumeTelemetryAPIClient = None,
    ):
        super().__init__(name=name, description=description)
        self.integration = integration_helper
        self.protection_client = protection_client
        self.propagation_client = propagation_client

    async def _resolve_volume(
        self, volume_id: str
    ) -> Tuple[str, List[str]]:
        """Resolve volume identifier and get filer serials.
        
        Returns:
            Tuple of (volume_guid, serial_numbers)
            
        Raises:
            VolumeResolutionError: If volume not found or no filers
        """
        volume_guid, _ = await self.integration.resolve_volume_identifier(volume_id)
        if not volume_guid:
            raise VolumeResolutionError(f"Volume not found: {volume_id}")

        serials = await self.integration.get_filer_serials_for_volume(volume_guid)
        if not serials:
            raise VolumeResolutionError(f"No filers found for volume: {volume_id}")

        return volume_guid, serials

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute with automatic error handling. Subclasses implement _do_execute()."""
        try:
            return await self._do_execute(arguments)
        except VolumeResolutionError as e:
            return self.format_error(str(e))
        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"{self.name} error: {e}")
            import traceback
            traceback.print_exc()
            return self.format_error(str(e))

    async def _do_execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Implement actual tool logic in subclasses."""
        raise NotImplementedError("Subclasses must implement _do_execute")


# ============================================================================
# DYNAMIC VOLUME METRIC TOOL (Config-driven)
# ============================================================================


class PortalVolumeTelemetryTool(BaseVolumeTelemetryTool):
    """Tool for querying a single Portal volume telemetry metric.
    
    Unlike other volume telemetry tools, this one allows serial_numbers override
    which can bypass volume resolution for serial lookup.
    """

    def __init__(
        self,
        metric_key: str,
        api_client: PortalVolumeTelemetryAPIClient,
        integration_helper: NMCPortalIntegration,
    ):
        if metric_key not in VOLUME_TELEMETRY_CONFIG:
            raise ValueError(f"Unsupported volume metric '{metric_key}'")

        config = VOLUME_TELEMETRY_CONFIG[metric_key]
        description = (
            f"[TELEMETRY] Portal Ops IQ volume metric — {config['display_name']}. "
            f"{config['description']} Automatically resolves volume names to GUIDs and fetches connected appliance serials."
        )
        # Pass api_client as protection_client to satisfy base class
        super().__init__(
            name=f"portal_volume_{metric_key}",
            description=description,
            integration_helper=integration_helper,
            protection_client=api_client,
        )
        self.metric_key = metric_key
        self.metric_config = config
        self.api_client = api_client

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "volume": {
                    "type": "string",
                    "description": "Volume name or GUID",
                },
                "period": {
                    "type": "string",
                    "description": "ISO 8601 duration or explicit range (default PT3H)",
                    "default": "PT3H",
                },
                "chart_width": {
                    "type": "integer",
                    "description": "Optional chart width hint (100-5200).",
                },
                "smart_sampling": {
                    "type": "boolean",
                    "description": "Enable Portal smart sampling (default true)",
                    "default": True,
                },
                "serial_numbers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional override for appliance serials. If omitted, the tool looks up all filers attached to the volume."
                    ),
                },
                "include_raw": {
                    "type": "boolean",
                    "description": "Include a truncated JSON preview of the raw payload.",
                    "default": False,
                },
            },
            "required": ["volume"],
            "additionalProperties": False,
        }

    async def _do_execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        volume_identifier = arguments.get("volume", "").strip()
        period = arguments.get("period", "PT3H")
        chart_width = arguments.get("chart_width")
        smart_sampling = arguments.get("smart_sampling", True)
        override_serials = arguments.get("serial_numbers") or []
        include_raw = arguments.get("include_raw", False)

        if not volume_identifier:
            return self.format_error("Volume name or GUID is required")

        # Use base class for volume resolution
        volume_guid, resolved_serials = await self._resolve_volume(volume_identifier)

        # Allow serial override
        if override_serials:
            serials = [s.strip() for s in override_serials if s.strip()]
        else:
            serials = resolved_serials

        if not serials:
            return self.format_error(
                "No filer serial numbers available for this volume. Provide serial_numbers explicitly if needed."
            )

        response = await self.api_client.get_metric(
            volume_guid=volume_guid,
            metric=self.metric_key,
            serial_numbers=serials,
            period=period,
            chart_width=chart_width,
            smart_sampling=smart_sampling,
        )

        if isinstance(response, dict) and response.get("error"):
            error_msg = f"Portal telemetry error: {response['error']}"
            if response.get("details"):
                error_msg += f" - Details: {response['details']}"
            return self.format_error(error_msg)

        output = self._format_response(
            volume_identifier=volume_identifier,
            volume_guid=volume_guid,
            serials=serials,
            context={
                "period": period,
                "chart_width": chart_width,
                "smart_sampling": smart_sampling,
            },
            payload=response,
            include_raw=include_raw,
        )

        return [TextContent(type="text", text=output)]

    def _format_response(
        self,
        volume_identifier: str,
        volume_guid: str,
        serials: List[str],
        context: Dict[str, Any],
        payload: Dict[str, Any],
        include_raw: bool,
    ) -> str:
        config = self.metric_config
        header = (
            f"📊 PORTAL OPS IQ VOLUME TELEMETRY — {config['display_name']}\n"
            f"{config['description']}\n\n"
        )

        sections = [header]
        sections.append(f"Volume: {volume_identifier}")
        sections.append(f"GUID: {volume_guid}")
        sections.append(f"Connected Appliances: {', '.join(serials)}")
        sections.append(f"Period: {context.get('period')}")
        if context.get("chart_width"):
            sections.append(f"Chart Width: {context['chart_width']} px")
        sections.append(f"Smart Sampling: {context.get('smart_sampling')}\n")

        records = _extract_primary_records(payload)
        sections.append(_summarize_records(records))

        if payload.get("metadata"):
            sections.append("\nMetadata\n" + _format_metadata(payload.get("metadata")))
        if payload.get("snapshot_appliances"):
            sections.append(
                "Snapshot Appliances: " + ", ".join(payload.get("snapshot_appliances", []))
            )
        if payload.get("sync_appliances"):
            sections.append(
                "Sync Appliances: " + ", ".join(payload.get("sync_appliances", []))
            )

        if include_raw:
            sections.append("\nRaw Preview (truncated)")
            sections.append(_raw_preview(payload))

        return "\n".join(section for section in sections if section)


# ============================================================================
# VOLUME PROTECTION & PROPAGATION TOOLS
# ============================================================================


class GetVolumeProtectionMetricsTool(BaseVolumeTelemetryTool):
    """Primary tool for volume data protection metrics from Portal Ops IQ."""

    def __init__(
        self,
        api_client: PortalVolumeTelemetryAPIClient,
        integration_helper: NMCPortalIntegration,
    ):
        super().__init__(
            name="get_volume_protection_metrics",
            description=(
                "[PORTAL] Get protection metrics from Portal Ops IQ. "
                "Returns snapshot version, OUD age, timing, and anomalies. "
                "For comprehensive reports, use get_analysis_workflow with workflow_type='volume-protection-report'. "
                "Accepts volume name or GUID."
            ),
            integration_helper=integration_helper,
            protection_client=api_client,
        )

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "volume": VOLUME_PROPERTY,
                "period": {
                    **PERIOD_PROPERTY_3H,
                    "description": "Time period (ISO 8601). Examples: PT1H, PT3H (default), PT6H, PT24H, P7D",
                },
                "smart_sampling": {
                    "type": "boolean",
                    "description": "Reduce data points while preserving trends (default: true)",
                },
                "show_details": {
                    "type": "boolean",
                    "description": "Show detailed snapshot-by-snapshot data (default: false)",
                },
            },
            "required": ["volume"],
        }

    async def _do_execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        volume_id = arguments.get("volume", "").strip()
        if not volume_id:
            return self.format_error("Volume name or GUID required")

        period = arguments.get("period", "PT3H")
        smart_sampling = arguments.get("smart_sampling", True)
        show_details = arguments.get("show_details", False)

        volume_guid, serials = await self._resolve_volume(volume_id)
        logger.info(f"Using {len(serials)} filer(s): {serials}")

        analysis = await self.protection_client.get_volume_data_protection_analysis(
            volume_guid=volume_guid,
            serial_numbers=serials,
            period=period,
            smart_sampling=smart_sampling,
        )

        if not analysis.complete_snapshots:
            return [
                TextContent(
                    type="text",
                    text=f"No protection data for {volume_id} in period {period}",
                )
            ]

        output = self._format_output(
            volume_id, volume_guid, period, serials, analysis, show_details
        )
        return [TextContent(type="text", text=output)]

    def _format_output(
        self,
        vol_id: str,
        vol_guid: str,
        period: str,
        serials: List[str],
        analysis,
        show_details: bool,
    ) -> str:
        stats = analysis.get_statistics()
        insights = analysis.get_insights()

        out = (
            f"🛡️ DATA PROTECTION METRICS - PORTAL OPS IQ\n\n"
            f"=== VOLUME ===\n"
            f"Name: {vol_id}\n"
            f"GUID: {vol_guid}\n"
        )

        if stats.get("latest_snapshot"):
            latest = stats["latest_snapshot"]
            out += (
                f"\n📌 LATEST SNAPSHOT\n"
                f"Version: {latest['volume_version']}\n"
                f"Appliance: {latest['appliance']} ({latest['serial_number'][:16]}...)\n"
                f"Completed: {latest['completed_at']}\n"
                f"Protection Time: {latest['protect_mean']} (max: {latest['protect_max']})\n"
                f"OUD: {latest['oud']}\n"
                f"Files: {latest['files_protected']}{' (includes GFL)' if latest['has_gfl'] else ''}\n"
            )

        out += (
            f"\n=== ANALYSIS PERIOD ===\n"
            f"Period: {period} | Snapshots: {stats['complete_snapshots']} | Appliances: {len(serials)}\n"
            f"Range: {stats['time_range']['start']} → {stats['time_range']['end']}\n"
        )

        if stats.get("average_data_protection_time"):
            avg = stats["average_data_protection_time"]
            out += (
                f"\n=== ⭐ AVERAGE DATA PROTECTION TIME ===\n"
                f"{avg['human']} ({avg['seconds']:.0f}s)\n"
                f"{avg['description']}\n"
            )

        if stats.get("protection_anomalies"):
            anom = stats["protection_anomalies"]
            out += (
                f"\n=== ⚠️ PROTECTION ANOMALIES ===\n"
                f"Max Unprotected Time: {anom['max_unprotected_time']}\n"
                f"Worst Cases:\n"
            )
            for case in anom["worst_cases"]:
                out += (
                    f"  • {case['appliance']} at {case['time']}: {case['unprotected_time']} (v{case['version']})\n"
                )

        if stats.get("data_phase_performance"):
            data = stats["data_phase_performance"]
            out += (
                f"\n=== DATA PHASE (Cloud Upload) ===\n"
                f"Average: {data['avg']} | Min: {data['min']} | Max: {data['max']}\n"
                f"Slowest: {data['slowest_appliance']} ({data.get('slowest_files', 'N/A')} files)\n"
            )

        if stats.get("metadata_phase_performance"):
            meta = stats["metadata_phase_performance"]
            out += (
                f"\n=== METADATA PHASE (Restore Point Creation) ===\n"
                f"Average: {meta['avg']} | Min: {meta['min']} | Max: {meta['max']}\n"
                f"Slowest: {meta['slowest_appliance']}\n"
            )

        if stats.get("file_statistics"):
            files = stats["file_statistics"]
            out += (
                f"\n=== FILE STATISTICS ===\n"
                f"Total Protected: {files['total_protected']:,} files\n"
                f"Avg per Snapshot: {files['avg_per_snapshot']:.0f}\n"
                f"Range: {files['min_in_snapshot']} - {files['max_in_snapshot']} files\n"
            )

        if stats.get("by_appliance"):
            out += "\n=== BY APPLIANCE ===\n"
            for app, app_stats in sorted(
                stats["by_appliance"].items(),
                key=lambda x: x[1]["snapshots"],
                reverse=True,
            ):
                out += (
                    f"\n📡 {app}\n"
                    f"   Latest: v{app_stats['latest_version']} at {app_stats['latest_time']}\n"
                    f"   Snapshots: {app_stats['snapshots']}\n"
                    f"   Avg Protection: {app_stats['avg_protect_time']}\n"
                    f"   Worst Case: {app_stats['worst_protect_time']}\n"
                    f"   Avg OUD: {app_stats['avg_oud']}\n"
                    f"   Files: {app_stats['total_files']:,}\n"
                )

        out += "\n=== 💡 INSIGHTS ===\n"
        for insight in insights:
            out += f"{insight}\n"

        if show_details and analysis.complete_snapshots:
            out += "\n=== 📊 DETAILED SNAPSHOTS (Last 5) ===\n"
            for snap in analysis.complete_snapshots[-5:]:
                s = snap.get_summary_dict()
                out += (
                    f"\nv{s['volume_version']} | {s['appliance']} | {s['timestamp']}\n"
                )
                out += (
                    f"  Protection: {s['protect_mean']} (max {s['protect_max']}) | OUD: {s['oud']}\n"
                )
                out += (
                    f"  Phases: Data {s['data_phase']}, Metadata {s['metadata_phase']}\n"
                )
                out += (
                    f"  Files: {s['files_total']} ({s['files_gfl'] or 0} GFL)\n"
                )

        out += "\n📊 Portal Ops IQ - Real-time protection telemetry\n"
        return out


class GetVolumeDataProtectionReportTool(BaseVolumeTelemetryTool):
    """Generate a comprehensive Data Protection Report with server-side aggregation.
    
    This tool fetches all protection data and performs aggregations server-side
    to prevent token overflow for large volumes. Returns a compact, pre-formatted
    report with the key metrics.
    """

    def __init__(
        self,
        api_client: PortalVolumeTelemetryAPIClient,
        integration_helper: NMCPortalIntegration,
    ):
        super().__init__(
            name="get_volume_data_protection_report",
            description=(
                "[PORTAL] Generate a comprehensive Data Protection Report for a volume. "
                "USE THIS for data protection reports - it performs all aggregations server-side "
                "to prevent token overflow. Returns: Time to Protect (min/max/avg), "
                "Latest Snapshot details (version, OUD, appliance, file/dir counts), "
                "and Appliance snapshot distribution (most/least active). "
                "Starts with last 24 hours (P1D) by default - can scale up to P4D if more data needed. "
                "Accepts volume name or GUID."
            ),
            integration_helper=integration_helper,
            protection_client=api_client,
        )

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "volume": VOLUME_PROPERTY,
                "period": {
                    "type": "string",
                    "description": "Time period for analysis (ISO 8601). Default: P1D (1 day). Max: P4D (4 days). Examples: PT12H, P1D, P4D",
                    "default": "P1D",
                },
            },
            "required": ["volume"],
        }

    async def _do_execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        volume_id = arguments.get("volume", "").strip()
        if not volume_id:
            return self.format_error("Volume name or GUID required")

        period = arguments.get("period", "P1D")

        volume_guid, serials = await self._resolve_volume(volume_id)
        logger.info(f"Generating Data Protection Report for {volume_id} with {len(serials)} filer(s)")

        # Fetch protection data with smart_sampling disabled for accurate stats
        analysis = await self.protection_client.get_volume_data_protection_analysis(
            volume_guid=volume_guid,
            serial_numbers=serials,
            period=period,
            smart_sampling=False,  # Need all data for accurate min/max/avg
        )

        if not analysis.complete_snapshots:
            return [
                TextContent(
                    type="text",
                    text=f"No protection data available for volume '{volume_id}' in period {period}",
                )
            ]

        # Generate the compact report
        report = self._generate_report(volume_id, volume_guid, period, analysis)
        return [TextContent(type="text", text=report)]

    def _generate_report(
        self,
        vol_id: str,
        vol_guid: str,
        period: str,
        analysis,
    ) -> str:
        """Generate a compact Data Protection Report."""
        stats = analysis.get_statistics()
        snapshots = analysis.complete_snapshots
        
        # ==== HEADER ====
        report = [
            "=" * 60,
            "📊 DATA PROTECTION REPORT",
            "=" * 60,
            f"Volume: {vol_id}",
            f"GUID: {vol_guid}",
            f"Analysis Period: {period}",
            f"Total Snapshots Analyzed: {len(snapshots)}",
            f"Time Range: {stats['time_range']['start']} → {stats['time_range']['end']}",
            "",
        ]
        
        # ==== TIME TO PROTECT (Min/Max/Avg) ====
        protect_times = [s.protect_mean_seconds for s in snapshots if s.protect_mean_seconds is not None]
        
        report.append("=" * 60)
        report.append("⏱️  TIME TO PROTECT (Data Protection Latency)")
        report.append("=" * 60)
        
        if protect_times:
            min_protect = min(protect_times)
            max_protect = max(protect_times)
            avg_protect = sum(protect_times) / len(protect_times)
            
            report.append(f"  Minimum:  {self._fmt(min_protect)}")
            report.append(f"  Maximum:  {self._fmt(max_protect)}")
            report.append(f"  Average:  {self._fmt(avg_protect)}")
            report.append("")
            
            # Health assessment
            if avg_protect < 60:
                report.append("  Status: ✅ EXCELLENT - Files protected quickly")
            elif avg_protect < 180:
                report.append("  Status: ✅ GOOD - Protection time within normal range")
            elif avg_protect < 600:
                report.append("  Status: ⚠️ WARNING - Consider increasing snapshot frequency")
            else:
                report.append("  Status: 🚨 CRITICAL - Files remain unprotected too long")
        else:
            report.append("  No time-to-protect data available")
        
        report.append("")
        
        # ==== LATEST SNAPSHOT DETAILS ====
        report.append("=" * 60)
        report.append("📌 LATEST SNAPSHOT DETAILS")
        report.append("=" * 60)
        
        latest = analysis.latest_snapshot
        if latest:
            report.append(f"  Snapshot Number (Version): {latest.volume_version}")
            report.append(f"  Completed At: {latest.timestamp_str}")
            report.append(f"  OUD (Oldest Unprotected Data): {self._fmt(latest.oud_seconds)}")
            report.append(f"  Appliance: {latest.appliance}")
            report.append(f"  Serial: {latest.serial_number}")
            report.append(f"  Total Files: {latest.file_count_total or 0:,}")
            report.append(f"  Directory Count: {latest.dir_count or 0:,}")
            report.append(f"  Time to Protect (Mean): {self._fmt(latest.protect_mean_seconds)}")
            report.append(f"  Time to Protect (Max): {self._fmt(latest.protect_max_seconds)}")
            
            if latest.has_global_locks:
                report.append(f"  Global File Lock Files: {latest.file_count_gl or 0:,}")
        else:
            report.append("  No latest snapshot data available")
        
        report.append("")
        
        # ==== APPLIANCE SNAPSHOT DISTRIBUTION ====
        report.append("=" * 60)
        report.append("📡 APPLIANCE SNAPSHOT DISTRIBUTION")
        report.append("=" * 60)
        
        by_appliance = stats.get("by_appliance", {})
        
        if by_appliance:
            # Sort by snapshot count
            sorted_appliances = sorted(
                by_appliance.items(),
                key=lambda x: x[1].get("snapshots", 0),
                reverse=True
            )
            
            # Table header
            report.append("")
            report.append(f"  {'Appliance':<25} {'Snapshots':>10} {'% Total':>10} {'Avg Protect':>12}")
            report.append(f"  {'-' * 25} {'-' * 10} {'-' * 10} {'-' * 12}")
            
            total_snapshots = len(snapshots)
            for appliance, app_stats in sorted_appliances:
                snap_count = app_stats.get("snapshots", 0)
                pct = (snap_count / total_snapshots * 100) if total_snapshots > 0 else 0
                avg_protect = app_stats.get("avg_protect_time", "N/A")
                
                # Truncate long appliance names
                display_name = appliance[:25] if len(appliance) > 25 else appliance
                report.append(f"  {display_name:<25} {snap_count:>10} {pct:>9.1f}% {avg_protect:>12}")
            
            report.append("")
            
            # Most active appliance
            most_active = sorted_appliances[0]
            most_name = most_active[0]
            most_count = most_active[1].get("snapshots", 0)
            most_pct = (most_count / total_snapshots * 100) if total_snapshots > 0 else 0
            
            report.append(f"  🥇 Most Active Appliance:")
            report.append(f"     {most_name}")
            report.append(f"     {most_count} snapshots ({most_pct:.1f}% of total)")
            report.append("")
            
            # Least active appliance
            if len(sorted_appliances) > 1:
                least_active = sorted_appliances[-1]
                least_name = least_active[0]
                least_count = least_active[1].get("snapshots", 0)
                least_pct = (least_count / total_snapshots * 100) if total_snapshots > 0 else 0
                
                report.append(f"  📉 Least Active Appliance:")
                report.append(f"     {least_name}")
                report.append(f"     {least_count} snapshots ({least_pct:.1f}% of total)")
                report.append("")
            
            # Distribution balance assessment
            if len(sorted_appliances) > 1:
                if most_pct > 70:
                    report.append("  ⚠️ Distribution: UNEVEN - One appliance dominates snapshot creation")
                elif most_pct > 50 and len(sorted_appliances) > 2:
                    report.append("  ⚠️ Distribution: SLIGHTLY SKEWED")
                else:
                    report.append("  ✅ Distribution: BALANCED - Workload spread across appliances")
        else:
            report.append("  No per-appliance data available")
        
        report.append("")
        
        # ==== OUD STATISTICS ====
        oud_values = [s.oud_seconds for s in snapshots if s.oud_seconds is not None]
        
        if oud_values:
            report.append("=" * 60)
            report.append("📈 OUD (Oldest Unprotected Data) STATISTICS")
            report.append("=" * 60)
            report.append(f"  Minimum OUD: {self._fmt(min(oud_values))}")
            report.append(f"  Maximum OUD: {self._fmt(max(oud_values))}")
            report.append(f"  Average OUD: {self._fmt(sum(oud_values) / len(oud_values))}")
            report.append("")
            
            avg_oud = sum(oud_values) / len(oud_values)
            if avg_oud < 3600:  # Less than 1 hour
                report.append("  Status: ✅ GOOD - Data protection is timely")
            elif avg_oud < 14400:  # Less than 4 hours
                report.append("  Status: ⚠️ WARNING - OUD exceeds 1 hour average")
            else:
                report.append("  Status: 🚨 CRITICAL - OUD exceeds 4 hours average")
            report.append("")
        
        # ==== FOOTER ====
        report.append("=" * 60)
        report.append("📊 Report generated from Portal Ops IQ telemetry")
        report.append("=" * 60)
        
        return "\n".join(report)
    
    def _fmt(self, seconds: float | None) -> str:
        """Format duration in human-readable format."""
        if seconds is None:
            return "N/A"
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            return f"{seconds / 60:.1f}m"
        else:
            return f"{seconds / 3600:.2f}h"


class GetVolumeHealthReportTool(BaseVolumeTelemetryTool):
    """Comprehensive Volume Health Report with Data Protection AND Data Propagation metrics.
    
    This tool provides a complete health picture for a single volume including:
    - Data Protection: Time to protect (min/max/avg), latest snapshot details
    - Data Propagation: Time to propagate (min/max/avg), sync status per appliance
    - Appliance analysis: Most/least active for snapshots, stale appliances for sync
    """

    def __init__(
        self,
        protection_client: PortalVolumeTelemetryAPIClient,
        propagation_client: PortalVolumeTelemetryAPIClient,
        integration_helper: NMCPortalIntegration,
    ):
        super().__init__(
            name="get_volume_health_report",
            description=(
                "[PORTAL] Generate a comprehensive Volume Health Report with both "
                "Data Protection AND Data Propagation metrics. "
                "Returns: Time to Protect (min/max/avg), Latest Snapshot details "
                "(version, OUD, appliance, file/dir counts), Appliance snapshot distribution, "
                "Time to Propagate (min/max/avg), Latest synced version per appliance, "
                "and identifies appliances that are behind (version -100 or more). "
                "Starts with last 24 hours (P1D) by default - can scale up to P4D if more data needed. "
                "USE THIS for complete volume health analysis. Accepts volume name or GUID."
            ),
            integration_helper=integration_helper,
            protection_client=protection_client,
            propagation_client=propagation_client,
        )

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "volume": VOLUME_PROPERTY,
                "period": {
                    "type": "string",
                    "description": "Time period for analysis (ISO 8601). Default: P1D (1 day). Max: P4D (4 days). Examples: PT12H, P1D, P4D",
                    "default": "P1D",
                },
            },
            "required": ["volume"],
        }

    async def _do_execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        volume_id = arguments.get("volume", "").strip()
        if not volume_id:
            return self.format_error("Volume name or GUID required")

        period = arguments.get("period", "P1D")

        volume_guid, serials = await self._resolve_volume(volume_id)
        logger.info(f"Generating Volume Health Report for {volume_id} with {len(serials)} filer(s)")

        # Fetch BOTH protection and propagation data concurrently
        protection_task = self.protection_client.get_volume_data_protection_analysis(
            volume_guid=volume_guid,
            serial_numbers=serials,
            period=period,
            smart_sampling=False,  # Need all data for accurate min/max/avg
        )
        
        propagation_task = self.propagation_client.get_volume_data_propagation_analysis(
            volume_guid=volume_guid,
            serial_numbers=serials,
            period=period,
            smart_sampling=False,
        )
        
        protection_analysis, propagation_analysis = await asyncio.gather(
            protection_task, propagation_task, return_exceptions=True
        )
        
        # Handle exceptions
        if isinstance(protection_analysis, Exception):
            logger.error(f"Protection analysis failed: {protection_analysis}")
            protection_analysis = None
        if isinstance(propagation_analysis, Exception):
            logger.error(f"Propagation analysis failed: {propagation_analysis}")
            propagation_analysis = None

        # Generate the comprehensive report
        report = self._generate_report(
            volume_id, volume_guid, period, serials,
            protection_analysis, propagation_analysis
        )
        return [TextContent(type="text", text=report)]

    def _generate_report(
        self,
        vol_id: str,
        vol_guid: str,
        period: str,
        serials: List[str],
        protection_analysis,
        propagation_analysis,
    ) -> str:
        """Generate a comprehensive Volume Health Report."""
        
        # ==== HEADER ====
        report = [
            "=" * 70,
            "📊 VOLUME HEALTH REPORT",
            "=" * 70,
            f"Volume: {vol_id}",
            f"GUID: {vol_guid}",
            f"Analysis Period: {self._period_to_human(period)}",
            f"Connected Appliances: {len(serials)}",
            "",
        ]
        
        # ================================================================
        # SECTION 1: DATA PROTECTION
        # ================================================================
        report.append("=" * 70)
        report.append("🛡️  DATA PROTECTION")
        report.append("=" * 70)
        
        if protection_analysis and protection_analysis.complete_snapshots:
            snapshots = protection_analysis.complete_snapshots
            stats = protection_analysis.get_statistics()
            
            report.append(f"\nTotal Snapshots Analyzed: {len(snapshots)}")
            report.append(f"Time Range: {stats['time_range']['start']} → {stats['time_range']['end']}")
            report.append("")
            
            # ---- TIME TO PROTECT ----
            report.append("-" * 50)
            report.append("⏱️  TIME TO PROTECT")
            report.append("-" * 50)
            
            protect_times = [s.protect_mean_seconds for s in snapshots if s.protect_mean_seconds is not None]
            if protect_times:
                min_protect = min(protect_times)
                max_protect = max(protect_times)
                avg_protect = sum(protect_times) / len(protect_times)
                
                report.append(f"  Minimum:  {self._fmt(min_protect)}")
                report.append(f"  Maximum:  {self._fmt(max_protect)}")
                report.append(f"  Average:  {self._fmt(avg_protect)}")
                
                # Health status
                if avg_protect < 60:
                    report.append("  Status: ✅ EXCELLENT")
                elif avg_protect < 180:
                    report.append("  Status: ✅ GOOD")
                elif avg_protect < 600:
                    report.append("  Status: ⚠️ WARNING")
                else:
                    report.append("  Status: 🚨 CRITICAL")
            else:
                report.append("  No time-to-protect data available")
            report.append("")
            
            # ---- LATEST SNAPSHOT DETAILS ----
            report.append("-" * 50)
            report.append("📌 LATEST SNAPSHOT DETAILS")
            report.append("-" * 50)
            
            latest = protection_analysis.latest_snapshot
            if latest:
                report.append(f"  Snapshot Number (Version): {latest.volume_version}")
                report.append(f"  OUD (Oldest Unprotected Data): {self._fmt(latest.oud_seconds)}")
                report.append(f"  Appliance: {latest.appliance}")
                report.append(f"  Total Files: {latest.file_count_total or 0:,}")
                report.append(f"  Directory Count: {latest.dir_count or 0:,}")
            else:
                report.append("  No latest snapshot data available")
            report.append("")
            
            # ---- APPLIANCE SNAPSHOT DISTRIBUTION ----
            report.append("-" * 50)
            report.append("📡 APPLIANCE SNAPSHOT DISTRIBUTION")
            report.append("-" * 50)
            
            by_appliance = stats.get("by_appliance", {})
            if by_appliance:
                sorted_appliances = sorted(
                    by_appliance.items(),
                    key=lambda x: x[1].get("snapshots", 0),
                    reverse=True
                )
                
                total_snapshots = len(snapshots)
                
                # Show table
                report.append(f"\n  {'Appliance':<30} {'Snapshots':>10} {'% Total':>10}")
                report.append(f"  {'-' * 30} {'-' * 10} {'-' * 10}")
                
                for appliance, app_stats in sorted_appliances:
                    snap_count = app_stats.get("snapshots", 0)
                    pct = (snap_count / total_snapshots * 100) if total_snapshots > 0 else 0
                    display_name = appliance[:30] if len(appliance) > 30 else appliance
                    report.append(f"  {display_name:<30} {snap_count:>10} {pct:>9.1f}%")
                
                report.append("")
                
                # Most active
                most_active = sorted_appliances[0]
                report.append(f"  🥇 Most Active: {most_active[0]}")
                report.append(f"     {most_active[1].get('snapshots', 0)} snapshots ({most_active[1].get('snapshots', 0) / total_snapshots * 100:.1f}%)")
                
                # Least active
                if len(sorted_appliances) > 1:
                    least_active = sorted_appliances[-1]
                    report.append(f"  📉 Least Active: {least_active[0]}")
                    report.append(f"     {least_active[1].get('snapshots', 0)} snapshots ({least_active[1].get('snapshots', 0) / total_snapshots * 100:.1f}%)")
            else:
                report.append("  No per-appliance data available")
            report.append("")
            
        else:
            # No protection data - but check if propagation shows activity
            has_propagation_activity = (
                propagation_analysis and 
                propagation_analysis.events and 
                len(propagation_analysis.events) > 0
            )
            
            if has_propagation_activity:
                # Propagation shows snapshots ARE being created, so protection IS happening
                prop_stats = propagation_analysis.get_statistics()
                latest_ver = prop_stats.get("latest_version", {})
                report.append("\n  ℹ️ Protection timing metrics not available for this period")
                report.append("  However, propagation data confirms snapshots ARE being created:")
                if latest_ver:
                    report.append(f"    • Latest Version: {latest_ver.get('version', 'N/A')}")
                    report.append(f"    • Created By: {latest_ver.get('created_by', 'N/A')}")
                    report.append(f"    • Created At: {latest_ver.get('created_at', 'N/A')}")
                report.append("  Protection is working - detailed timing metrics may require a longer period (P2D-P4D)")
            else:
                report.append("\n  ⚠️ No protection data available for this period")
                report.append("  This may indicate low volume activity or infrequent snapshots")
                report.append("  Try extending the period (e.g., P2D, P4D)")
            report.append("")
        
        # ================================================================
        # SECTION 2: DATA PROPAGATION
        # ================================================================
        report.append("=" * 70)
        report.append("🔄 DATA PROPAGATION")
        report.append("=" * 70)
        
        if propagation_analysis and propagation_analysis.events:
            events = propagation_analysis.events
            prop_stats = propagation_analysis.get_statistics()
            
            report.append(f"\nTotal Sync Events: {len(events)}")
            report.append(f"Snapshot Appliances: {', '.join(propagation_analysis.snapshot_appliances) or 'N/A'}")
            report.append(f"Sync Appliances: {', '.join(propagation_analysis.sync_appliances) or 'N/A'}")
            report.append("")
            
            # ---- TIME TO PROPAGATE ----
            report.append("-" * 50)
            report.append("⏱️  TIME TO PROPAGATE")
            report.append("-" * 50)
            
            prop_stats_data = prop_stats.get("propagation_statistics", {})
            if prop_stats_data:
                report.append(f"  Minimum:  {prop_stats_data.get('min_time', 'N/A')}")
                report.append(f"  Maximum:  {prop_stats_data.get('max_time', 'N/A')}")
                report.append(f"  Average:  {prop_stats_data.get('avg_time', 'N/A')}")
                
                avg_sec = prop_stats_data.get("avg_seconds", 0)
                if avg_sec < 30:
                    report.append("  Status: ✅ EXCELLENT")
                elif avg_sec < 60:
                    report.append("  Status: ✅ GOOD")
                elif avg_sec < 120:
                    report.append("  Status: ⚠️ WARNING")
                else:
                    report.append("  Status: 🚨 SLOW")
            else:
                report.append("  No propagation timing data available")
            report.append("")
            
            # ---- LATEST SNAPSHOT VERSION ----
            report.append("-" * 50)
            report.append("📌 LATEST SNAPSHOT VERSION")
            report.append("-" * 50)
            
            latest_version_info = prop_stats.get("latest_version", {})
            if latest_version_info:
                report.append(f"  Version: {latest_version_info.get('version', 'N/A')}")
                report.append(f"  Created By: {latest_version_info.get('created_by', 'N/A')}")
                report.append(f"  Created At: {latest_version_info.get('created_at', 'N/A')}")
                report.append(f"  Appliances Synced: {latest_version_info.get('syncs_completed', 0)}")
                report.append(f"  Avg Propagation: {latest_version_info.get('avg_propagation', 'N/A')}")
            report.append("")
            
            # ---- PER-APPLIANCE SYNC STATUS ----
            report.append("-" * 50)
            report.append("📡 APPLIANCE SYNC STATUS")
            report.append("-" * 50)
            
            by_sync_appliance = prop_stats.get("by_sync_appliance", {})
            latest_version = latest_version_info.get("version", 0)
            
            if by_sync_appliance:
                # Show table header
                report.append(f"\n  {'Appliance':<30} {'Latest Synced':>14} {'Avg Prop':>12}")
                report.append(f"  {'-' * 30} {'-' * 14} {'-' * 12}")
                
                stale_appliances = []
                
                for app_name, app_data in sorted(by_sync_appliance.items()):
                    app_latest_version = app_data.get("latest_version_synced", 0)
                    avg_prop = app_data.get("avg_propagation", "N/A")
                    display_name = app_name[:30] if len(app_name) > 30 else app_name
                    report.append(f"  {display_name:<30} v{app_latest_version:>13} {avg_prop:>12}")
                    
                    # Check if appliance is behind by 100+ versions
                    version_diff = latest_version - app_latest_version
                    if version_diff >= 100:
                        stale_appliances.append({
                            "appliance": app_name,
                            "latest_synced": app_latest_version,
                            "behind_by": version_diff,
                            "last_sync_time": app_data.get("latest_sync_time", "Unknown")
                        })
                
                report.append("")
                
                # ---- APPLIANCES THAT HAVEN'T SYNCED (100+ versions behind) ----
                if stale_appliances:
                    report.append("-" * 50)
                    report.append("🚨 STALE APPLIANCES (100+ versions behind)")
                    report.append("-" * 50)
                    
                    for stale in stale_appliances:
                        report.append(f"\n  ⚠️ {stale['appliance']}")
                        report.append(f"     Latest Synced Version: v{stale['latest_synced']}")
                        report.append(f"     Behind By: {stale['behind_by']} versions")
                        report.append(f"     Last Sync: {stale['last_sync_time']}")
                    report.append("")
                else:
                    report.append("  ✅ All appliances are up to date (within 100 versions)")
                    report.append("")
            else:
                report.append("  No per-appliance sync data available")
                report.append("")
        else:
            report.append("\n  ⚠️ No propagation data available for this period")
            report.append("  This may indicate no sync activity or single-appliance volume")
            report.append("")
        
        # ================================================================
        # FOOTER
        # ================================================================
        report.append("=" * 70)
        report.append("📊 Report generated from Portal Ops IQ telemetry")
        report.append("=" * 70)
        
        return "\n".join(report)

    def _period_to_human(self, period: str) -> str:
        """Convert ISO 8601 period to human-readable format."""
        period_map = {
            "PT1H": "Last 1 hour",
            "PT3H": "Last 3 hours",
            "PT6H": "Last 6 hours",
            "PT12H": "Last 12 hours",
            "PT24H": "Last 24 hours",
            "P1D": "Last 24 hours",
            "P2D": "Last 2 days",
            "P3D": "Last 3 days",
            "P4D": "Last 4 days",
        }
        return period_map.get(period.upper(), f"Period: {period}")

    def _fmt(self, seconds: float | None) -> str:
        """Format duration in human-readable format."""
        if seconds is None:
            return "N/A"
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            return f"{seconds / 60:.1f}m"
        else:
            return f"{seconds / 3600:.2f}h"


class GetFleetVolumeHealthSummaryTool(BaseTool):
    """Fleet-wide volume health summary with server-side aggregation.
    
    This tool analyzes ALL volumes in the account and identifies any 
    experiencing health issues. Performs all aggregation server-side
    to prevent token overflow.
    
    Uses Portal APIs directly to get edge connections and serial numbers,
    avoiding the need for NMC API lookups.
    """

    def __init__(
        self,
        protection_client: PortalVolumeTelemetryAPIClient,
        volumes_client,  # PortalVolumesAPIClient
        edges_client,    # PortalEdgesAPIClient - for edge ID to serial mapping
        integration_helper: NMCPortalIntegration,
    ):
        super().__init__(
            name="get_fleet_volume_health_summary",
            description=(
                "[PORTAL - USE THIS FOR FLEET-WIDE VOLUME HEALTH] "
                "Analyze ALL volumes and identify any experiencing health issues. "
                "Starts with last 24 hours (P1D) by default - can scale up to P4D if more data needed. "
                "USE THIS when user asks: 'check all volumes', 'any volume issues?', "
                "'volume health across fleet', 'which volumes have problems'. "
                "Returns a compact summary with: healthy volumes, warning volumes, "
                "critical volumes, and volumes with no recent snapshots. "
                "Note: Volumes without snapshots in the period may be inactive or have low activity. "
                "All aggregation done server-side to prevent token overflow."
            ),
        )
        self.protection_client = protection_client
        self.volumes_client = volumes_client
        self.edges_client = edges_client
        self.integration = integration_helper

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "Time period for analysis (ISO 8601). Default: P1D (1 day), max P4D (4 days). Examples: PT12H, P1D, P4D",
                    "default": "P1D",
                },
            },
            "required": [],
        }

    async def _build_edge_serial_map(self) -> Dict[str, str]:
        """Build a mapping of edge ID to serial number from Portal edges API.
        
        Returns:
            Dict mapping edge_id -> serial_number
        """
        edge_map = {}
        try:
            edges_response = await self.edges_client.get_edges()
            if edges_response and edges_response.items:
                for edge in edges_response.items:
                    if edge.id and edge.serial:
                        edge_map[edge.id] = edge.serial
                logger.info(f"Built edge serial map with {len(edge_map)} entries")
        except Exception as e:
            logger.warning(f"Failed to build edge serial map: {e}")
        return edge_map

    async def _get_volume_serials_from_portal(
        self, 
        vol_id: str, 
        edge_serial_map: Dict[str, str]
    ) -> List[str]:
        """Get serial numbers for a volume using Portal APIs.
        
        Args:
            vol_id: Volume ID/GUID
            edge_serial_map: Mapping of edge_id -> serial
            
        Returns:
            List of serial numbers for connected edges
        """
        serials = []
        try:
            # Get detailed volume info which includes edges
            volume_details = await self.volumes_client.get_volume(vol_id)
            
            if volume_details and volume_details.edges:
                edges = volume_details.edges
                
                # Get master edge serial
                if edges.master and edges.master.id:
                    master_serial = edge_serial_map.get(edges.master.id)
                    if master_serial:
                        serials.append(master_serial)
                        logger.debug(f"Found master edge serial: {master_serial}")
                
                # Get connected edge serials
                for edge_id in edges.connected:
                    serial = edge_serial_map.get(edge_id)
                    if serial and serial not in serials:
                        serials.append(serial)
                        logger.debug(f"Found connected edge serial: {serial}")
                        
        except Exception as e:
            logger.warning(f"Failed to get volume serials from Portal for {vol_id}: {e}")
        
        return serials

    async def _analyze_single_volume(
        self,
        volume,
        edge_serial_map: Dict[str, str],
        period: str,
    ) -> Dict[str, Any]:
        """Analyze a single volume and return result dict.
        
        Returns a dict with keys: type ('healthy'|'warning'|'critical'|'no_data'|'error'), data
        """
        vol_id = volume.id
        vol_name = volume.description or vol_id
        
        try:
            # Get filer serials - try Portal first, then fall back to NMC
            serials = []
            
            if edge_serial_map:
                serials = await self._get_volume_serials_from_portal(vol_id, edge_serial_map)
            
            # Fallback to NMC integration if Portal didn't return serials
            if not serials:
                serials = await self.integration.get_filer_serials_for_volume(vol_id)
            
            if not serials:
                return {
                    "type": "no_data",
                    "data": {"name": vol_name, "id": vol_id, "reason": "No connected filers"}
                }
            
            # Fetch protection data
            analysis = await self.protection_client.get_volume_data_protection_analysis(
                volume_guid=vol_id,
                serial_numbers=serials,
                period=period,
                smart_sampling=True,  # Use sampling for speed
            )
            
            if not analysis.complete_snapshots:
                return {
                    "type": "no_data",
                    "data": {
                        "name": vol_name,
                        "id": vol_id,
                        "reason": f"No snapshots in {period} (checked {len(serials)} filer(s))"
                    }
                }
            
            # Analyze health
            health_result = self._analyze_volume_health(vol_name, vol_id, analysis)
            return {"type": health_result["status"], "data": health_result}
            
        except Exception as e:
            logger.warning(f"Error analyzing volume {vol_name}: {e}")
            return {
                "type": "error",
                "data": {"volume": vol_name, "error": str(e)}
            }

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        period = arguments.get("period", "P1D")
        
        try:
            # Step 1: Build edge ID to serial mapping (one API call)
            edge_serial_map = await self._build_edge_serial_map()
            if not edge_serial_map:
                logger.warning("Edge serial map is empty - falling back to NMC integration")
            
            # Step 2: Get all volumes from Portal
            volumes_response = await self.volumes_client.get_volumes()
            
            if not volumes_response or not volumes_response.items:
                return [TextContent(type="text", text="No volumes found in the account.")]
            
            volumes = volumes_response.items
            logger.info(f"Analyzing health for {len(volumes)} volumes concurrently")
            
            # Step 3: Analyze all volumes CONCURRENTLY (major optimization)
            # Process in batches of 5 to avoid overwhelming the API
            BATCH_SIZE = 5
            all_results = []
            
            for i in range(0, len(volumes), BATCH_SIZE):
                batch = volumes[i:i + BATCH_SIZE]
                batch_tasks = [
                    self._analyze_single_volume(vol, edge_serial_map, period)
                    for vol in batch
                ]
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                all_results.extend(batch_results)
            
            # Step 4: Categorize results
            healthy_volumes = []
            warning_volumes = []
            critical_volumes = []
            no_data_volumes = []
            errors = []
            
            for result in all_results:
                if isinstance(result, Exception):
                    errors.append({"volume": "Unknown", "error": str(result)})
                    continue
                    
                result_type = result.get("type")
                data = result.get("data")
                
                if result_type == "healthy":
                    healthy_volumes.append(data)
                elif result_type == "warning":
                    warning_volumes.append(data)
                elif result_type == "critical":
                    critical_volumes.append(data)
                elif result_type == "no_data":
                    no_data_volumes.append(data)
                elif result_type == "error":
                    errors.append(data)
            
            # Generate report
            report = self._generate_report(
                period=period,
                total_volumes=len(volumes),
                healthy=healthy_volumes,
                warnings=warning_volumes,
                critical=critical_volumes,
                no_data=no_data_volumes,
                errors=errors,
            )
            
            return [TextContent(type="text", text=report)]
            
        except Exception as e:
            logger.error(f"Fleet volume health analysis failed: {e}", exc_info=True)
            return self.format_error(f"Failed to analyze fleet volume health: {str(e)}")

    def _analyze_volume_health(self, vol_name: str, vol_id: str, analysis) -> Dict[str, Any]:
        """Analyze health of a single volume and return status."""
        stats = analysis.get_statistics()
        latest = analysis.latest_snapshot
        snapshots = analysis.complete_snapshots
        
        issues = []
        status = "healthy"
        
        # Check OUD (Oldest Unprotected Data)
        if latest and latest.oud_seconds is not None:
            oud_hours = latest.oud_seconds / 3600
            if oud_hours > 24:
                issues.append(f"🚨 OUD: {oud_hours:.1f}h (>24h critical)")
                status = "critical"
            elif oud_hours > 4:
                issues.append(f"⚠️ OUD: {oud_hours:.1f}h (>4h warning)")
                if status != "critical":
                    status = "warning"
        
        # Check average time to protect
        protect_times = [s.protect_mean_seconds for s in snapshots if s.protect_mean_seconds]
        if protect_times:
            avg_protect = sum(protect_times) / len(protect_times)
            if avg_protect > 7200:  # > 2 hours
                issues.append(f"🚨 Avg protect time: {self._fmt(avg_protect)} (>2h critical)")
                status = "critical"
            elif avg_protect > 1800:  # > 30 min
                issues.append(f"⚠️ Avg protect time: {self._fmt(avg_protect)} (>30m warning)")
                if status != "critical":
                    status = "warning"
        
        # Check snapshot frequency
        if len(snapshots) < 2:
            issues.append(f"⚠️ Only {len(snapshots)} snapshot(s) in period")
            if status != "critical":
                status = "warning"
        
        # Check max protection anomaly
        if stats.get("protection_anomalies"):
            max_unprotected = stats["protection_anomalies"].get("max_unprotected_time_seconds", 0)
            if max_unprotected > 86400:  # > 24 hours
                issues.append(f"🚨 Max unprotected: {self._fmt(max_unprotected)}")
                status = "critical"
        
        return {
            "name": vol_name,
            "id": vol_id,
            "status": status,
            "latest_version": latest.volume_version if latest else None,
            "latest_oud": self._fmt(latest.oud_seconds) if latest else "N/A",
            "avg_protect_time": self._fmt(sum(protect_times) / len(protect_times)) if protect_times else "N/A",
            "snapshot_count": len(snapshots),
            "issues": issues,
        }

    def _generate_report(
        self,
        period: str,
        total_volumes: int,
        healthy: List[Dict],
        warnings: List[Dict],
        critical: List[Dict],
        no_data: List[Dict],
        errors: List[Dict],
    ) -> str:
        """Generate the fleet health summary report."""
        # Convert period to human-readable format
        period_desc = self._period_to_human(period)
        
        report = [
            "=" * 70,
            "📊 FLEET VOLUME HEALTH SUMMARY",
            "=" * 70,
            f"Analysis Period: {period_desc}",
            f"Total Volumes: {total_volumes}",
            "",
        ]
        
        # Summary counts
        report.append("=" * 70)
        report.append("📈 SUMMARY")
        report.append("=" * 70)
        report.append(f"  ✅ Healthy:    {len(healthy)} volumes")
        report.append(f"  ⚠️ Warning:    {len(warnings)} volumes")
        report.append(f"  🚨 Critical:   {len(critical)} volumes")
        report.append(f"  📭 No Data:    {len(no_data)} volumes")
        if errors:
            report.append(f"  ❌ Errors:     {len(errors)} volumes")
        report.append("")
        
        # Critical volumes (always show details)
        if critical:
            report.append("=" * 70)
            report.append("🚨 CRITICAL VOLUMES - IMMEDIATE ATTENTION REQUIRED")
            report.append("=" * 70)
            for vol in critical:
                report.append(f"\n  📦 {vol['name']}")
                report.append(f"     Latest Version: {vol['latest_version'] or 'N/A'}")
                report.append(f"     Current OUD: {vol['latest_oud']}")
                report.append(f"     Avg Protect Time: {vol['avg_protect_time']}")
                report.append(f"     Snapshots: {vol['snapshot_count']}")
                if vol['issues']:
                    report.append("     Issues:")
                    for issue in vol['issues']:
                        report.append(f"       • {issue}")
            report.append("")
        
        # Warning volumes
        if warnings:
            report.append("=" * 70)
            report.append("⚠️ WARNING VOLUMES - REVIEW RECOMMENDED")
            report.append("=" * 70)
            for vol in warnings:
                report.append(f"\n  📦 {vol['name']}")
                report.append(f"     Current OUD: {vol['latest_oud']} | Avg Protect: {vol['avg_protect_time']}")
                if vol['issues']:
                    for issue in vol['issues']:
                        report.append(f"       • {issue}")
            report.append("")
        
        # Healthy volumes (compact list)
        if healthy:
            report.append("=" * 70)
            report.append("✅ HEALTHY VOLUMES")
            report.append("=" * 70)
            # Just show names in compact format
            healthy_names = [v['name'] for v in healthy]
            if len(healthy_names) <= 10:
                for name in healthy_names:
                    report.append(f"  • {name}")
            else:
                # Show first 5 and count
                for name in healthy_names[:5]:
                    report.append(f"  • {name}")
                report.append(f"  ... and {len(healthy_names) - 5} more healthy volumes")
            report.append("")
        
        # No data volumes
        if no_data:
            report.append("=" * 70)
            report.append("📭 VOLUMES WITH NO RECENT SNAPSHOTS")
            report.append("=" * 70)
            report.append(f"  (No snapshot activity found in the {period_desc} analysis window)")
            for vol in no_data:
                report.append(f"  • {vol['name']}: {vol['reason']}")
            report.append("")
        
        # Errors
        if errors:
            report.append("=" * 70)
            report.append("❌ ANALYSIS ERRORS")
            report.append("=" * 70)
            for err in errors:
                report.append(f"  • {err['volume']}: {err['error']}")
            report.append("")
        
        # Thresholds reference
        report.append("=" * 70)
        report.append("📋 HEALTH THRESHOLDS")
        report.append("=" * 70)
        report.append("  OUD Age:           Warning >4h,  Critical >24h")
        report.append("  Time to Protect:   Warning >30m, Critical >2h")
        report.append("")
        report.append("=" * 70)
        report.append("📊 Report generated from Portal Ops IQ telemetry")
        report.append("=" * 70)
        
        return "\n".join(report)

    def _period_to_human(self, period: str) -> str:
        """Convert ISO 8601 period to human-readable format."""
        period_map = {
            "PT1H": "Last 1 hour",
            "PT2H": "Last 2 hours",
            "PT3H": "Last 3 hours",
            "PT6H": "Last 6 hours",
            "PT12H": "Last 12 hours",
            "PT24H": "Last 24 hours",
            "P1D": "Last 24 hours",
            "P2D": "Last 2 days",
            "P3D": "Last 3 days",
            "P4D": "Last 4 days",
        }
        return period_map.get(period.upper(), f"Period: {period}")

    def _fmt(self, seconds: float | None) -> str:
        """Format duration."""
        if seconds is None:
            return "N/A"
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            return f"{seconds / 60:.1f}m"
        else:
            return f"{seconds / 3600:.2f}h"


class CompareVolumeProtectionMetricsTool(BaseVolumeTelemetryTool):
    """Tool to compare protection metrics across multiple volumes."""

    def __init__(
        self,
        api_client: PortalVolumeTelemetryAPIClient,
        integration_helper: NMCPortalIntegration,
    ):
        super().__init__(
            name="compare_volume_protection_metrics",
            description=(
                "[TELEMETRY] Compare data protection metrics across multiple volumes using Portal Ops IQ. "
                "Shows which volumes have better/worse protection times and identifies performance outliers."
            ),
            integration_helper=integration_helper,
            protection_client=api_client,
        )

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "volumes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of volume names or GUIDs to compare (minimum 2)",
                },
                "period": PERIOD_PROPERTY_3H,
            },
            "required": ["volumes"],
        }

    async def _do_execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        volumes = arguments.get("volumes", [])
        if not volumes or len(volumes) < 2:
            return self.format_error("At least 2 volumes required for comparison")

        period = arguments.get("period", "PT3H")
        volume_data = []

        for vol_id in volumes:
            logger.info(f"Analyzing volume: {vol_id}")
            try:
                volume_guid, serials = await self._resolve_volume(vol_id)
            except VolumeResolutionError as e:
                logger.warning(f"{e}, skipping")
                continue

            analysis = await self.protection_client.get_volume_data_protection_analysis(
                volume_guid=volume_guid,
                serial_numbers=serials,
                period=period,
            )

            if analysis.complete_snapshots:
                volume_data.append(
                    {
                        "identifier": vol_id,
                        "guid": volume_guid,
                        "analysis": analysis,
                        "stats": analysis.get_statistics(),
                    }
                )

        if not volume_data:
            return self.format_error("No valid data found for any volumes")

        output = self._format_comparison(volume_data, period)
        return [TextContent(type="text", text=output)]

    def _format_comparison(self, volume_data: List[Dict], period: str) -> str:
        out = (
            f"📊 VOLUME PROTECTION COMPARISON\n\n"
            f"=== OVERVIEW ===\n"
            f"Volumes: {len(volume_data)} | Period: {period}\n\n"
            f"=== COMPARISON TABLE ===\n\n"
            f"{'Volume':<35} {'Latest Ver':<12} {'Avg Protect':<15} {'Snapshots':<10}\n"
            f"{'-'*75}\n"
        )

        for vol in volume_data:
            name = vol["identifier"][:33]
            stats = vol["stats"]
            latest_ver = stats.get("latest_snapshot", {}).get("volume_version", "N/A")
            avg_prot = stats.get("average_data_protection_time", {}).get("human", "N/A")
            snap_count = stats.get("complete_snapshots", 0)
            out += f"{name:<35} {str(latest_ver):<12} {str(avg_prot):<15} {snap_count:<10}\n"

        volumes_with_avg = [
            (v, v["stats"].get("average_data_protection_time", {}).get("seconds", float("inf")))
            for v in volume_data
            if "average_data_protection_time" in v["stats"]
        ]

        if volumes_with_avg:
            volumes_with_avg.sort(key=lambda x: x[1])
            best = volumes_with_avg[0]
            worst = volumes_with_avg[-1]
            out += (
                f"\n=== RANKINGS ===\n\n"
                f"Best Protection (Fastest):\n"
                f"   {best[0]['identifier']}: {best[0]['stats']['average_data_protection_time']['human']}\n\n"
                f"Needs Attention (Slowest):\n"
                f"   {worst[0]['identifier']}: {worst[0]['stats']['average_data_protection_time']['human']}\n"
            )

        out += "\n=== INSIGHTS BY VOLUME ===\n"
        for vol in volume_data:
            insights = vol["analysis"].get_insights()
            if insights:
                out += f"\n{vol['identifier']}:\n"
                for insight in insights[:3]:
                    out += f"  {insight}\n"

        return out


class GetEndToEndProtectionTimingTool(BaseVolumeTelemetryTool):
    """Tool for complete protection + propagation cycle timing."""

    def __init__(self, protection_client, propagation_client, integration_helper):
        super().__init__(
            name="get_end_to_end_protection_timing",
            description=(
                "[TELEMETRY - COMPLETE CYCLE] Get complete protection cycle: data change → snapshot → sync to all appliances. "
                "Combines protection and propagation to show total time for data to be protected AND available everywhere."
            ),
            integration_helper=integration_helper,
            protection_client=protection_client,
            propagation_client=propagation_client,
        )

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "volume": VOLUME_PROPERTY,
                "period": PERIOD_PROPERTY_3H,
            },
            "required": ["volume"],
        }

    async def _do_execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        volume_id = arguments.get("volume", "").strip()
        if not volume_id:
            return self.format_error("Volume required")

        period = arguments.get("period", "PT3H")
        volume_guid, serials = await self._resolve_volume(volume_id)

        protection = await self.protection_client.get_volume_data_protection_analysis(
            volume_guid, serials, period
        )
        propagation = await self.propagation_client.get_volume_data_propagation_analysis(
            volume_guid, serials, period
        )

        output = self._format_combined(volume_id, period, protection, propagation)
        return [TextContent(type="text", text=output)]

    def _format_combined(self, volume_id, period, protection, propagation) -> str:
        prot_stats = protection.get_statistics()
        prop_stats = propagation.get_statistics()

        out = (
            f"🔁 END-TO-END PROTECTION CYCLE\n\n"
            f"Volume: {volume_id}\n"
            f"Period: {period}\n\n"
            f"=== SNAPSHOT PROTECTION (Portal) ===\n"
            f"Total Snapshots: {prot_stats.get('complete_snapshots', 0)}\n"
            f"Latest Version: {prot_stats.get('latest_snapshot', {}).get('volume_version', 'N/A')}\n"
            f"Average Protection Time: {prot_stats.get('average_data_protection_time', {}).get('human', 'N/A')}\n\n"
            f"=== PROPAGATION (Sync Timing) ===\n"
            f"Snapshots Synced: {prop_stats.get('total_versions', 0)}\n"
            f"Average Propagation: {prop_stats.get('propagation_statistics', {}).get('avg_time', 'N/A')}\n"
            f"Slowest Sync: {prop_stats.get('slowest_syncs', [{}])[0].get('duration', 'N/A') if prop_stats.get('slowest_syncs') else 'N/A'}\n\n"
            f"=== INSIGHTS ===\n"
        )

        for insight in protection.get_insights()[:3]:
            out += f"🛡️ {insight}\n"
        for insight in propagation.get_insights()[:3]:
            out += f"🌐 {insight}\n"

        return out


class GetVolumePropagationMetricsTool(BaseVolumeTelemetryTool):
    """Tool for data propagation (sync timing) metrics."""

    def __init__(
        self,
        api_client: PortalVolumeTelemetryAPIClient,
        integration_helper: NMCPortalIntegration,
    ):
        super().__init__(
            name="get_volume_propagation_metrics",
            description=(
                "[PORTAL] Get sync timing metrics from Portal Ops IQ. "
                "Returns propagation delays and outliers to connected appliances. "
                "For comprehensive reports, use get_analysis_workflow with workflow_type='volume-protection-report'."
            ),
            integration_helper=integration_helper,
            propagation_client=api_client,
        )

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "volume": VOLUME_PROPERTY,
                "period": PERIOD_PROPERTY_3H,
                "show_outliers": {
                    "type": "boolean",
                    "description": "Show detailed outlier information (default: true)",
                },
            },
            "required": ["volume"],
        }

    async def _do_execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        volume_id = arguments.get("volume", "").strip()
        if not volume_id:
            return self.format_error("Volume name or GUID required")

        period = arguments.get("period", "PT3H")
        show_outliers = arguments.get("show_outliers", True)

        volume_guid, serials = await self._resolve_volume(volume_id)

        analysis = await self.propagation_client.get_volume_data_propagation_analysis(
            volume_guid=volume_guid,
            serial_numbers=serials,
            period=period,
        )

        if not analysis.events:
            return [
                TextContent(
                    type="text",
                    text=f"No propagation data for {volume_id} in period {period}",
                )
            ]

        output = self._format_output(
            volume_id, volume_guid, period, analysis, show_outliers
        )
        return [TextContent(type="text", text=output)]

    def _format_output(self, vol_id, vol_guid, period, analysis, show_outliers) -> str:
        stats = analysis.get_statistics()
        insights = analysis.get_insights()

        out = (
            f"🌐 DATA PROPAGATION METRICS - PORTAL OPS IQ\n\n"
            f"=== VOLUME ===\n"
            f"Name: {vol_id}\n"
            f"GUID: {vol_guid}\n"
            f"Period: {period}\n\n"
            f"=== SYNC OVERVIEW ===\n"
            f"Total Sync Events: {stats['total_events']}\n"
            f"Versions Synced: {stats['total_versions']}\n"
            f"Snapshot Creators: {', '.join(stats['snapshot_appliances'])}\n"
            f"Sync Appliances: {', '.join(stats['sync_appliances'])}\n"
        )

        if stats.get("latest_version"):
            latest = stats["latest_version"]
            out += (
                f"\n📌 LATEST VERSION: {latest['version']}\n"
                f"Created By: {latest['created_by']} at {latest['created_at']}\n"
                f"Syncs Completed: {latest['syncs_completed']}\n"
                f"Avg Propagation: {latest['avg_propagation']}\n"
            )

        if stats.get("propagation_statistics"):
            prop = stats["propagation_statistics"]
            out += (
                "\n=== PROPAGATION PERFORMANCE ===\n"
                f"Average Time: {prop['avg_time']}\n"
                f"Fastest: {prop['min_time']}\n"
                f"Slowest: {prop['max_time']}\n"
            )

        if stats.get("slowest_syncs"):
            out += "\n=== ⏱️ SLOWEST SYNCS ===\n"
            for sync in stats["slowest_syncs"]:
                out += f"  • v{sync['version']}: {sync['sync_appliance']} took {sync['duration']}\n"

        if show_outliers and stats.get("outliers"):
            out += f"\n=== ⚠️ OUTLIERS ({len(stats['outliers'])}) ===\n"
            for outlier in stats["outliers"]:
                out += (
                    f"  • v{outlier['version']}: {outlier['sync_appliance']} - {outlier['duration']} ({outlier['sigma']:.1f}σ)\n"
                )

        if stats.get("by_sync_appliance"):
            out += "\n=== BY SYNC APPLIANCE ===\n"
            for app, app_stats in sorted(
                stats["by_sync_appliance"].items(),
                key=lambda x: x[1]["total_syncs"],
                reverse=True,
            ):
                out += f"\n📡 {app}\n"
                out += (
                    f"   Latest Synced: v{app_stats['latest_version_synced']} at {app_stats['latest_sync_time']}\n"
                )
                out += f"   Total Syncs: {app_stats['total_syncs']}\n"
                out += f"   Avg Time: {app_stats['avg_propagation']}\n"
                out += (
                    f"   Range: {app_stats['min_propagation']} - {app_stats['max_propagation']}\n"
                )
                if app_stats["outlier_count"] > 0:
                    out += f"   ⚠️ Outliers: {app_stats['outlier_count']}\n"

        out += "\n=== 💡 INSIGHTS ===\n"
        for insight in insights:
            out += f"{insight}\n"

        out += "\n📊 Portal Ops IQ - Sync timing telemetry\n"
        out += "💡 Shows how quickly snapshots propagate to connected appliances\n"
        return out


# ============================================================================
# SYNC STATUS & LAG DETECTION TOOLS
# ============================================================================


class GetVolumeLatestVersionTool(BaseVolumeTelemetryTool):
    """Tool to get the latest volume version and which appliance created it."""
    
    def __init__(
        self,
        protection_client: PortalVolumeTelemetryAPIClient,
        integration_helper: NMCPortalIntegration
    ):
        super().__init__(
            name="get_volume_latest_version",
            description="[TELEMETRY] Get the latest volume/snapshot version number and which appliance created it. USE FOR: 'What is the latest version?', 'Latest snapshot version?', 'Which appliance created the latest snapshot?', 'When was the latest snapshot?'. Shows the highest volume_version across all appliances and when it was created.",
            integration_helper=integration_helper,
            protection_client=protection_client,
        )
    
    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "volume": VOLUME_PROPERTY,
                "period": PERIOD_PROPERTY_3H,
            },
            "required": ["volume"]
        }

    async def _do_execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        volume_id = arguments.get("volume", "").strip()
        if not volume_id:
            return self.format_error("Volume name or GUID required")
        
        period = arguments.get("period", "PT3H")
        volume_guid, serials = await self._resolve_volume(volume_id)
        
        analysis = await self.protection_client.get_volume_data_protection_analysis(
            volume_guid, serials, period
        )
        
        if not analysis.complete_snapshots:
            return [TextContent(
                type="text",
                text=f"No snapshot data found for {volume_id} in period {period}"
            )]
        
        latest = analysis.latest_snapshot
        
        output = (
            f"📌 LATEST VOLUME VERSION\n\n"
            f"Volume: {volume_id}\n"
            f"Latest Version: {latest.volume_version}\n"
            f"Created By: {latest.appliance} ({latest.serial_number})\n"
            f"Completed At: {latest.timestamp_str}\n\n"
            f"Protection Metrics:\n"
            f"  Avg Time Unprotected: {latest.format_duration(latest.protect_mean_seconds)}\n"
            f"  Max Time Unprotected: {latest.format_duration(latest.protect_max_seconds)}\n"
            f"  Oldest Unprotected Data: {latest.format_duration(latest.oud_seconds)}\n"
            f"  Files Protected: {latest.file_count_total}\n\n"
            f"Snapshot Phases:\n"
            f"  Data Phase: {latest.format_duration(latest.data_phase_duration_seconds)}\n"
            f"  Metadata Phase: {latest.format_duration(latest.metadata_phase_duration_seconds)}\n"
            f"  Total Duration: {latest.format_duration(latest.total_snapshot_duration_seconds)}\n"
        )
        
        return [TextContent(type="text", text=output)]


class GetAllAppliancesSyncStatusTool(BaseVolumeTelemetryTool):
    """Tool to check sync status for all appliances connected to a volume."""
    
    def __init__(
        self,
        protection_client: PortalVolumeTelemetryAPIClient,
        propagation_client: PortalVolumeTelemetryAPIClient,
        integration_helper: NMCPortalIntegration
    ):
        super().__init__(
            name="get_all_appliances_sync_status",
            description="[TELEMETRY - SYNC MONITORING] Check sync status for ALL appliances connected to a volume. Identifies lagging, stale, and out-of-sync appliances. USE FOR: 'Check sync status for all appliances', 'Which appliances are behind?', 'Show sync lag across appliances', 'Are all appliances up to date?', 'Sync health check'. Detects appliances >1hr behind (lagging) or >3hr behind (critical).",
            integration_helper=integration_helper,
            protection_client=protection_client,
            propagation_client=propagation_client,
        )
    
    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "volume": VOLUME_PROPERTY,
                "period": PERIOD_PROPERTY_6H,
            },
            "required": ["volume"]
        }

    async def _do_execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        volume_id = arguments.get("volume", "").strip()
        if not volume_id:
            return self.format_error("Volume name or GUID required")
        
        period = arguments.get("period", "PT6H")
        volume_guid, serials = await self._resolve_volume(volume_id)
        
        protection = await self.protection_client.get_volume_data_protection_analysis(
            volume_guid, serials, period
        )
        
        propagation = await self.propagation_client.get_volume_data_propagation_analysis(
            volume_guid, serials, period
        )
        
        if not protection.complete_snapshots:
            return [TextContent(type="text", text=f"No snapshot data for {volume_id}")]
        
        output = self._format_all_status(volume_id, protection, propagation)
        return [TextContent(type="text", text=output)]
    
    def _format_all_status(self, volume_id, protection, propagation) -> str:
        """Format sync status for all appliances."""
        latest_overall = protection.latest_snapshot
        
        out = (
            f"🔍 ALL APPLIANCES SYNC STATUS\n\n"
            f"Volume: {volume_id}\n"
            f"Latest Version: {latest_overall.volume_version}\n"
            f"Created By: {latest_overall.appliance} at {latest_overall.timestamp_str}\n\n"
            f"=== APPLIANCE STATUS ===\n\n"
        )
        
        # Get unique appliances from both sources
        all_appliances = set()
        for snap in protection.complete_snapshots:
            all_appliances.add((snap.appliance, snap.serial_number))
        for event in propagation.events:
            all_appliances.add((event.sync_appliance, event.sync_serial_number))
        
        # Calculate status for each appliance using shared helper
        appliance_statuses = []
        for appliance_name, serial in all_appliances:
            status = _calculate_appliance_sync_status(
                appliance_name, latest_overall, protection, propagation,
                match_serial=serial
            )
            status["name"] = appliance_name
            status["serial"] = serial
            appliance_statuses.append(status)
        
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


class CheckApplianceSyncStatusTool(BaseVolumeTelemetryTool):
    """Tool to check if an appliance is up-to-date with latest snapshot."""
    
    def __init__(
        self,
        protection_client: PortalVolumeTelemetryAPIClient,
        propagation_client: PortalVolumeTelemetryAPIClient,
        integration_helper: NMCPortalIntegration
    ):
        super().__init__(
            name="check_appliance_sync_status",
            description="[TELEMETRY - SYNC STATUS] Check if a specific appliance is up-to-date with the latest volume snapshot. Shows sync lag and detects stale appliances. USE FOR: 'Is appliance X up to date?', 'Check sync status for appliance', 'Is appliance behind?', 'Show appliance sync lag', 'Latest version on appliance X?'. Detects: appliances >1hr behind (lagging), >3hr behind (critical issue). Shows both latest snapshot created and latest sync completed.",
            integration_helper=integration_helper,
            protection_client=protection_client,
            propagation_client=propagation_client,
        )
    
    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "volume": VOLUME_PROPERTY,
                "appliance": APPLIANCE_PROPERTY,
                "period": PERIOD_PROPERTY_6H,
            },
            "required": ["volume", "appliance"]
        }

    async def _do_execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        volume_id = arguments.get("volume", "").strip()
        appliance_id = arguments.get("appliance", "").strip()
        
        if not volume_id or not appliance_id:
            return self.format_error("Both volume and appliance required")
        
        period = arguments.get("period", "PT6H")
        volume_guid, serials = await self._resolve_volume(volume_id)
        
        protection = await self.protection_client.get_volume_data_protection_analysis(
            volume_guid, serials, period
        )
        
        if not protection.complete_snapshots:
            return [TextContent(type="text", text=f"No snapshot data for {volume_id}")]
        
        propagation = await self.propagation_client.get_volume_data_propagation_analysis(
            volume_guid, serials, period
        )
        
        output = self._format_single_appliance_status(
            volume_id, appliance_id, protection, propagation
        )
        return [TextContent(type="text", text=output)]
    
    def _format_single_appliance_status(
        self, volume_id: str, appliance_id: str, protection, propagation
    ) -> str:
        """Format sync status for a single appliance."""
        latest_overall = protection.latest_snapshot
        status = _calculate_appliance_sync_status(
            appliance_id, latest_overall, protection, propagation
        )
        
        out = (
            f"🔍 APPLIANCE SYNC STATUS\n\n"
            f"=== APPLIANCE ===\n"
            f"Appliance: {appliance_id}\n"
            f"Volume: {volume_id}\n"
            f"Status: {status['status_icon']} {status['status_text']}\n\n"
            f"=== LATEST SNAPSHOT (VOLUME-WIDE) ===\n"
            f"Version: {latest_overall.volume_version}\n"
            f"Created By: {latest_overall.appliance}\n"
            f"Completed: {latest_overall.timestamp_str}\n\n"
            f"=== THIS APPLIANCE'S LATEST VERSION ===\n"
            f"Version: {status['version'] if status['version'] else 'No data'}\n"
            f"Source: {status['source'].upper()}\n"
        )
        
        if status['time']:
            out += f"Last Updated: {status['time'].strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        if status['lag_versions'] > 0:
            out += (
                f"\n=== ⚠️ SYNC LAG DETECTED ===\n"
                f"Versions Behind: {status['lag_versions']}\n"
            )
            if status['lag_time']:
                lag_hours = status['lag_time'].total_seconds() / 3600
                lag_minutes = status['lag_time'].total_seconds() / 60
                
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
        if status.get('snapshot_count', 0) > 0:
            out += f"\nSnapshot Activity: {status['snapshot_count']} snapshots created by this appliance\n"
            if status.get('last_snapshot'):
                out += f"  Last created: v{status['last_snapshot']['version']} at {status['last_snapshot']['time']}\n"
        
        if status.get('sync_count', 0) > 0:
            out += f"\nSync Activity: {status['sync_count']} syncs completed by this appliance\n"
            if status.get('last_sync'):
                out += f"  Last synced: v{status['last_sync']['version']} at {status['last_sync']['time']}\n"
                out += f"  Propagation time: {status['last_sync']['duration']}\n"
        
        if status.get('snapshot_count', 0) == 0 and status.get('sync_count', 0) == 0:
            out += "\n⚠️ No snapshot or sync activity found for this appliance in the selected period\n"
        
        return out


# ============================================================================
# SHARED HELPER FUNCTIONS
# ============================================================================


def _calculate_appliance_sync_status(
    appliance_id: str,
    latest_overall,
    protection,
    propagation,
    match_serial: str = None,
) -> Dict[str, Any]:
    """Calculate sync status for a single appliance.
    
    Shared logic used by both CheckApplianceSyncStatusTool and GetAllAppliancesSyncStatusTool.
    
    Args:
        appliance_id: Appliance name or partial identifier
        latest_overall: Latest snapshot across all appliances
        protection: Protection analysis result
        propagation: Propagation analysis result
        match_serial: If provided, use exact serial match instead of substring
    
    Returns:
        Dict with status info including: version, time, source, lag_versions, lag_time,
        status_icon, status_text, snapshot_count, sync_count, last_snapshot, last_sync
    """
    # Find snapshots created by this appliance
    if match_serial:
        app_snapshots = [
            s for s in protection.complete_snapshots
            if s.appliance == appliance_id or s.serial_number == match_serial
        ]
        app_syncs = [
            e for e in propagation.events
            if e.sync_appliance == appliance_id or e.sync_serial_number == match_serial
        ]
    else:
        app_snapshots = [
            s for s in protection.complete_snapshots
            if appliance_id in s.appliance or appliance_id in s.serial_number
        ]
        app_syncs = [
            e for e in propagation.events
            if appliance_id in e.sync_appliance or appliance_id in e.sync_serial_number
        ]
    
    # Determine latest version on this appliance
    latest_version = None
    latest_time = None
    source = "none"
    last_snapshot = None
    last_sync = None
    
    if app_snapshots:
        latest_snap = max(app_snapshots, key=lambda s: s.volume_version)
        latest_version = latest_snap.volume_version
        latest_time = latest_snap.timestamp
        source = "snapshot"
        last_snapshot = {
            "version": latest_snap.volume_version,
            "time": latest_snap.timestamp_str,
        }
    
    if app_syncs:
        latest_sync_event = max(app_syncs, key=lambda e: e.snapshot_version)
        if latest_version is None or latest_sync_event.snapshot_version > latest_version:
            latest_version = latest_sync_event.snapshot_version
            latest_time = latest_sync_event.sync_datetime
            source = "sync"
        last_sync = {
            "version": latest_sync_event.snapshot_version,
            "time": latest_sync_event.sync_time_str,
            "duration": latest_sync_event.format_duration(latest_sync_event.propagation_duration),
        }
    
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
    
    return {
        "version": latest_version,
        "time": latest_time,
        "source": source,
        "lag_versions": lag_versions,
        "lag_time": lag_time,
        "status_icon": status_icon,
        "status_text": status_text,
        "snapshot_count": len(app_snapshots),
        "sync_count": len(app_syncs),
        "last_snapshot": last_snapshot,
        "last_sync": last_sync,
    }


# ============================================================================
# COMPREHENSIVE VOLUME ANALYSIS GUIDANCE TOOL
# ============================================================================


class VolumeComprehensiveAnalysisGuideTool(BaseTool):
    """Meta-tool that provides guidance for comprehensive volume protection analysis.
    
    Instead of making expensive calls to all telemetry endpoints, this tool
    returns instructions to the LLM on how to systematically analyze volume
    protection and propagation metrics.
    """

    def __init__(self, integration_helper: NMCPortalIntegration):
        description = (
            "[PORTAL - USE THIS FIRST FOR VOLUME HEALTH/PROTECTION REPORTS] "
            "Get step-by-step instructions for comprehensive volume protection health report. "
            "USE THIS TOOL FIRST when user asks for: protection health report, volume health analysis, "
            "protection status, sync analysis, snapshot analysis, propagation analysis, or any volume telemetry review. "
            "Returns systematic guidance to analyze protection timing, OUD, propagation delays, snapshot versions, "
            "appliance activity distribution, and sync outliers. This is a guidance tool - efficient, no expensive API calls."
        )
        super().__init__(
            name="portal_volume_comprehensive_analysis_guide",
            description=description,
        )
        self.integration = integration_helper

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "volume": {
                    "type": "string",
                    "description": "Volume name or GUID to analyze",
                },
                "analysis_depth": {
                    "type": "string",
                    "enum": ["quick", "standard", "comprehensive"],
                    "description": "Level of analysis: quick (protection status only), standard (protection + propagation), comprehensive (full analysis with outlier detection)",
                    "default": "standard",
                },
            },
            "required": ["volume"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        volume = arguments.get("volume", "").strip()
        analysis_depth = arguments.get("analysis_depth", "standard")

        if not volume:
            return self.format_error("Volume identifier is required")

        # Resolve the volume to get GUID and connected appliances
        try:
            volume_guid, filer_serials = await self._resolve_volume(volume)
        except Exception as e:
            return self.format_error(f"Unable to resolve volume '{volume}': {e}")

        guide = self._generate_analysis_guide(volume, volume_guid, filer_serials, analysis_depth)
        return [TextContent(type="text", text=guide)]

    async def _resolve_volume(self, volume_id: str) -> Tuple[str, List[str]]:
        """Resolve volume identifier and get connected filer serials."""
        volume_guid, filer_serials = await self.integration.resolve_volume_identifier(volume_id)
        if not volume_guid:
            raise ValueError(f"Could not resolve volume: {volume_id}")
        return volume_guid, filer_serials or []

    def _generate_analysis_guide(self, volume_name: str, volume_guid: str, filer_serials: List[str], depth: str) -> str:
        """Generate the analysis guide based on depth level."""
        
        appliance_list = ", ".join(filer_serials) if filer_serials else "Unknown"
        
        guide = f"""📊 COMPREHENSIVE VOLUME PROTECTION & PROPAGATION ANALYSIS GUIDE
{'=' * 70}

Target Volume: {volume_name}
Volume GUID: {volume_guid}
Connected Appliances: {len(filer_serials)} ({appliance_list})
Analysis Depth: {depth.upper()}
Recommended Period: P30D (30 days) for trend analysis

"""

        if depth == "quick":
            guide += self._quick_analysis_steps(volume_guid, filer_serials)
        elif depth == "standard":
            guide += self._standard_analysis_steps(volume_guid, filer_serials)
        else:  # comprehensive
            guide += self._comprehensive_analysis_steps(volume_guid, filer_serials)

        guide += self._analysis_tips()
        
        return guide

    def _quick_analysis_steps(self, volume_guid: str, filer_serials: List[str]) -> str:
        return f"""
🚀 QUICK ANALYSIS (Protection Status Check)
{'─' * 50}

Execute these steps IN ORDER:

STEP 1: Get Protection Metrics Summary
  Tool: get_volume_protection_metrics
  Args: volume="{volume_guid}", period="P1D"
  Look for:
    • Latest snapshot version
    • Average time to protect
    • Oldest unprotected data age
    • Any anomalies flagged
  
STEP 2: Check Current Sync Status
  Tool: get_all_appliances_sync_status
  Args: volume="{volume_guid}", period="PT6H"
  Look for:
    • Which appliances are up to date
    • Any appliances lagging behind
    • Version mismatches

ANALYSIS COMPLETE - Report findings with:
- Protection health status (healthy/warning/critical)
- Current oldest unprotected data age
- Sync status across all appliances
- Immediate concerns if any
"""

    def _standard_analysis_steps(self, volume_guid: str, filer_serials: List[str]) -> str:
        return f"""
📋 STANDARD ANALYSIS (Protection + Propagation Review)
{'─' * 50}

Execute these steps IN ORDER:

PHASE 1: Protection Health Assessment
─────────────────────────────────────
STEP 1: Get comprehensive protection metrics
  Tool: get_volume_protection_metrics
  Args: volume="{volume_guid}", period="P30D", show_details=true
  Extract and report:
    • Latest volume version
    • Which appliance created the latest snapshot
    • Average time to protect (target: <1 hour)
    • Protection anomalies (worst cases)
    • Oldest Unprotected Data (OUD) age trend
    • Snapshot frequency pattern

STEP 2: Check snapshot timeline details
  Tool: portal_volume_snapshot_timeline
  Args: volume="{volume_guid}", period="P30D"
  Extract and report:
    • Data push duration trends
    • Metadata push duration trends
    • Any failed or incomplete snapshots

PHASE 2: Propagation (Sync) Analysis
────────────────────────────────────
STEP 3: Get propagation metrics
  Tool: get_volume_propagation_metrics
  Args: volume="{volume_guid}", period="P30D", show_outliers=true
  Extract and report:
    • Average sync time per appliance
    • Propagation delay distribution
    • Outlier events (unusually slow syncs)

STEP 4: Check all appliances sync status
  Tool: get_all_appliances_sync_status
  Args: volume="{volume_guid}", period="P1D"
  Extract and report:
    • Current version on each appliance
    • Lag (versions behind) for each
    • Status classification (up-to-date/lagging/critical)

PHASE 3: Appliance Activity Distribution
────────────────────────────────────────
STEP 5: Get snapshot content breakdown
  Tool: portal_volume_snapshot_content
  Args: volume="{volume_guid}", period="P30D"
  Extract and calculate:
    • Total snapshots per appliance (count by creator)
    • Most active appliance (highest snapshot count)
    • Least active appliance (lowest snapshot count)
    • Distribution balance (is one appliance doing all the work?)

FINAL REPORT FORMAT:
====================
1. PROTECTION SUMMARY
   - Current version: [version]
   - Avg time to protect: [X hours/minutes]
   - OUD age: [X hours] (target: <24h)
   - Protection health: [Healthy/Warning/Critical]

2. PROPAGATION SUMMARY
   - Avg sync time: [X minutes]
   - Slowest appliance: [serial] at [X minutes avg]
   - Appliances with lag: [list]

3. APPLIANCE ACTIVITY
   - Most active: [serial] with [N] snapshots
   - Least active: [serial] with [N] snapshots
   - Balance: [Even/Skewed]

4. ISSUES FOUND
   [List any concerns with severity]

5. RECOMMENDATIONS
   [Actionable items]
"""

    def _comprehensive_analysis_steps(self, volume_guid: str, filer_serials: List[str]) -> str:
        # Build appliance list string without complex f-string nesting
        if filer_serials:
            quoted_serials = [f'"{s}"' for s in filer_serials]
            appliance_args = f'filer_ids=[{", ".join(quoted_serials)}]'
        else:
            appliance_args = ""
        
        return f"""
🔬 COMPREHENSIVE ANALYSIS (Full Protection & Propagation Review with Outlier Detection)
{'─' * 70}

⚠️ NOTE: This is a thorough analysis. Execute steps sequentially, collecting data for statistics.

PHASE 1: Protection Baseline
────────────────────────────
STEP 1: Get comprehensive protection metrics
  Tool: get_volume_protection_metrics
  Args: volume="{volume_guid}", period="P30D", show_details=true
  COLLECT DATA FOR:
    • latest_version: [number]
    • latest_snapshot_appliance: [serial]
    • avg_time_to_protect_minutes: [number]
    • oud_age_hours: [number]
    • anomaly_count: [number]
    • per_appliance_snapshot_counts: {{serial: count, ...}}

STEP 2: Get oldest unprotected data trend
  Tool: portal_volume_oldest_unprotected_data
  Args: volume="{volume_guid}", period="P30D"
  COLLECT DATA FOR:
    • oud_min_hours: [number]
    • oud_max_hours: [number]
    • oud_avg_hours: [number]
    • oud_trend: [improving/stable/degrading]

STEP 3: Get average time to protect trend
  Tool: portal_volume_average_time_to_protect
  Args: volume="{volume_guid}", period="P30D"
  COLLECT DATA FOR:
    • protect_time_min_minutes: [number]
    • protect_time_max_minutes: [number]
    • protect_time_avg_minutes: [number]
    • protect_time_trend: [improving/stable/degrading]

PHASE 2: Snapshot Analysis
──────────────────────────
STEP 4: Get snapshot timeline details
  Tool: portal_volume_snapshot_timeline
  Args: volume="{volume_guid}", period="P30D"
  COLLECT DATA FOR:
    • total_snapshots: [number]
    • data_push_avg_seconds: [number]
    • metadata_push_avg_seconds: [number]
    • failed_snapshots: [number]

STEP 5: Get snapshot content breakdown
  Tool: portal_volume_snapshot_content
  Args: volume="{volume_guid}", period="P30D"
  COLLECT DATA FOR (per appliance):
    • appliance_snapshot_counts: {{serial: count, ...}}
    • most_active_appliance: [serial]
    • most_active_count: [number]
    • least_active_appliance: [serial]
    • least_active_count: [number]

STEP 6: Get snapshot details (individual snapshot info)
  Tool: portal_volume_snapshot_details
  Args: volume="{volume_guid}", period="P30D"
  COLLECT DATA FOR:
    • snapshot_versions: [list of versions]
    • snapshot_creators: [list of appliance serials]
    • snapshot_times: [list of timestamps]

PHASE 3: Propagation (Sync) Deep Dive
─────────────────────────────────────
STEP 7: Get propagation metrics with outliers
  Tool: get_volume_propagation_metrics
  Args: volume="{volume_guid}", period="P30D", show_outliers=true
  COLLECT DATA FOR (per appliance):
    • sync_times_per_appliance: {{serial: [list of sync times], ...}}
    • sync_avg_per_appliance: {{serial: avg_minutes, ...}}
    • sync_outliers: [list of {{serial, time, duration}}]

STEP 8: Get snapshot propagation by appliance
  Tool: portal_volume_snapshot_propagation_by_appliance
  Args: volume="{volume_guid}", period="P30D"
  COLLECT DATA FOR:
    • propagation_delays: {{serial: [list of delays], ...}}
    • avg_propagation_per_appliance: {{serial: avg_minutes, ...}}

STEP 9: Check all appliances current sync status
  Tool: get_all_appliances_sync_status
  Args: volume="{volume_guid}", period="P1D"
  COLLECT DATA FOR:
    • current_versions: {{serial: version, ...}}
    • lag_versions: {{serial: lag, ...}}
    • last_sync_times: {{serial: timestamp, ...}}

PHASE 4: Statistical Analysis (PERFORM CALCULATIONS)
────────────────────────────────────────────────────
After collecting all data, perform these calculations:

CALCULATION 1: Snapshot Activity Distribution
  • Calculate mean snapshot count across appliances
  • Calculate standard deviation of snapshot counts
  • Flag appliances with count < (mean - 2*stddev) as "underactive"
  • Flag appliances with count > (mean + 2*stddev) as "overactive"

CALCULATION 2: Sync Time Outlier Detection (3 Standard Deviations)
  For each appliance:
    • Calculate mean sync time
    • Calculate standard deviation
    • Identify sync events > (mean + 3*stddev) as OUTLIERS
    • Flag appliance if >5% of syncs are outliers

CALCULATION 3: Sync Freshness Analysis
  For each appliance:
    • Calculate hours since last sync
    • Calculate typical sync interval (from historical data)
    • Flag if current gap > 3 * typical_interval

CALCULATION 4: Protection Timing Trends
  • Compare first week avg vs last week avg for:
    - Time to protect
    - OUD age
    - Sync delays
  • Calculate % change to determine trend direction

COMPREHENSIVE REPORT FORMAT:
============================

1. EXECUTIVE SUMMARY
   ─────────────────
   Volume: {volume_guid}
   Analysis Period: 30 days
   Overall Health: [Healthy/Warning/Critical]
   Key Finding: [One sentence summary of most important finding]

2. PROTECTION METRICS
   ──────────────────
   | Metric | Min | Max | Avg | Trend | Status |
   |--------|-----|-----|-----|-------|--------|
   | Time to Protect | Xm | Xm | Xm | ↑/→/↓ | ✅/⚠️/🚨 |
   | OUD Age | Xh | Xh | Xh | ↑/→/↓ | ✅/⚠️/🚨 |
   
   Latest Version: [version] (created by [appliance] at [time])

3. APPLIANCE ACTIVITY DISTRIBUTION
   ────────────────────────────────
   | Appliance | Snapshots | % of Total | Status |
   |-----------|-----------|------------|--------|
   | [serial]  | [count]   | [%]        | Most Active / Normal / Least Active |
   
   Distribution Balance: [Even/Skewed]
   ⚠️ Flags: [List any under/overactive appliances]

4. PROPAGATION (SYNC) ANALYSIS
   ───────────────────────────
   | Appliance | Avg Sync | Current Version | Lag | Status |
   |-----------|----------|-----------------|-----|--------|
   | [serial]  | [Xm]     | [version]       | [N] | ✅/⚠️/🚨 |
   
   🚨 SYNC OUTLIERS (>3 Standard Deviations):
   [List appliances with sync time outliers]
   
   ⚠️ SYNC FRESHNESS WARNINGS:
   [List appliances that haven't synced recently]

5. TREND ANALYSIS (30-Day)
   ───────────────────────
   • Time to Protect: [improving/stable/degrading] ([X]% change)
   • OUD Age: [improving/stable/degrading] ([X]% change)
   • Sync Delays: [improving/stable/degrading] ([X]% change)

6. ISSUES & ANOMALIES
   ──────────────────
   [For each issue:]
   🚨/⚠️ [Issue title]
      Evidence: [Specific data points]
      Impact: [What this means]
      Severity: Critical/Warning/Info

7. RECOMMENDATIONS
   ───────────────
   IMMEDIATE ACTIONS:
   • [Action 1 if critical issues]
   
   SHORT-TERM:
   • [Action 2]
   
   MONITORING:
   • [Ongoing monitoring recommendations]
"""

    def _analysis_tips(self) -> str:
        return """

💡 VOLUME ANALYSIS TIPS
{'─' * 50}

THRESHOLDS FOR ALERTS:
• OUD Age: Warning >4 hours, Critical >24 hours
• Time to Protect: Warning >30 min, Critical >2 hours
• Sync Lag (versions): Warning >5, Critical >20
• Sync Time: Warning >15 min, Critical >1 hour
• Sync Freshness: Warning if 2x typical interval, Critical if 3x

OUTLIER DETECTION (3 Standard Deviations):
• Calculate mean (μ) and standard deviation (σ) for sync times
• Outlier threshold = μ + 3σ
• Example: If mean=5min, stddev=2min, outlier threshold=11min
• Flag appliances with >5% outlier rate

SNAPSHOT DISTRIBUTION ANALYSIS:
• Ideal: All appliances contribute roughly equally
• Warning sign: One appliance doing >70% of snapshots
• This could indicate: failover scenario, misconfiguration, or load imbalance

SYNC FRESHNESS INTERPRETATION:
• Calculate typical sync interval from historical patterns
• Current gap > 3x typical = potential issue
• Consider: network issues, appliance offline, or configuration problems

TREND CALCULATION:
• Week 1 avg = mean of first 7 days
• Week 4 avg = mean of last 7 days
• % Change = ((Week4 - Week1) / Week1) * 100
• Improving: negative % for OUD/protect time (lower is better)
• Degrading: positive % for OUD/protect time (higher is worse)

CORRELATION PATTERNS:
• High OUD + Normal Protect Time = Snapshot frequency too low
• High Protect Time + High OUD = System overloaded or network issues
• Uneven Snapshot Distribution + High OUD = Failover/recovery scenario
• Sync Outliers on Single Appliance = Network issue to that appliance
• Sync Outliers Everywhere = Volume-level issue (size, complexity)
"""


def register_volume_comprehensive_analysis_guide_tool(
    registry,
    integration_helper: NMCPortalIntegration,
) -> None:
    """Register the volume comprehensive analysis guide tool."""
    tool = VolumeComprehensiveAnalysisGuideTool(integration_helper)
    registry.register_tool(tool)
    logger.info(f"Registered volume comprehensive analysis guide tool: {tool.name}")

