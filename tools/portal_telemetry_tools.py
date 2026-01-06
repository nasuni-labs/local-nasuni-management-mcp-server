#!/usr/bin/env python3
"""Portal Ops IQ telemetry MCP tools for appliance and volume metrics."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from statistics import StatisticsError, mean
from typing import Any, Dict, List, Optional

from mcp.types import TextContent

from api.portal_telemetry_api import (
    APPLIANCE_TELEMETRY_CONFIG,
    VOLUME_TELEMETRY_CONFIG,
    PortalApplianceTelemetryAPIClient,
    PortalVolumeTelemetryAPIClient,
)
from tools.base_tool import BaseTool
from utils.portal_nmc_integration import NMCPortalIntegration
from config.logging_setup import get_logger

logger = get_logger(__name__)

_TIME_FIELDS = {
    "time",
    "timestamp",
    "start",
    "start_time",
    "end",
    "end_time",
    "bucket_start",
    "bucket_end",
    "completed_at",
    "created_at",
}


class PortalApplianceTelemetryTool(BaseTool):
    """Tool for querying a single Portal appliance telemetry metric."""

    def __init__(
        self,
        metric_key: str,
        api_client: PortalApplianceTelemetryAPIClient,
        integration_helper: NMCPortalIntegration,
    ):
        if metric_key not in APPLIANCE_TELEMETRY_CONFIG:
            raise ValueError(f"Unsupported appliance metric '{metric_key}'")

        config = APPLIANCE_TELEMETRY_CONFIG[metric_key]
        description = (
            f"[TELEMETRY] Portal Ops IQ appliance metric — {config['display_name']}. "
            f"{config['description']} Accepts a filer serial/name and returns aggregated statistics with optional raw data."
        )
        super().__init__(
            name=f"portal_appliance_{metric_key}",
            description=description,
        )
        self.metric_key = metric_key
        self.metric_config = config
        self.api_client = api_client
        self.integration = integration_helper

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "appliance": {
                    "type": "string",
                    "description": "Filer serial number or name",
                },
                "period": {
                    "type": "string",
                    "description": (
                        "ISO 8601 duration or explicit range (default PT3H)."
                    ),
                    "default": "PT3H",
                },
                "panel_width": {
                    "type": "integer",
                    "description": "Panel width in pixels (100-5200) for sampling hints.",
                },
                "bin_size": {
                    "type": "integer",
                    "description": "Bin size in seconds (60-3600) for sampling hints.",
                },
                "timezone_offset_minutes": {
                    "type": "integer",
                    "description": (
                        "Optional timezone offset minutes (only used for health_score)."
                    ),
                },
                "include_raw": {
                    "type": "boolean",
                    "description": "Include a truncated JSON preview of the raw payload.",
                    "default": False,
                },
            },
            "required": ["appliance"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        try:
            appliance = arguments.get("appliance", "").strip()
            period = arguments.get("period", "PT3H")
            panel_width = arguments.get("panel_width")
            bin_size = arguments.get("bin_size")
            tz_offset = arguments.get("timezone_offset_minutes")
            include_raw = arguments.get("include_raw", False)

            if not appliance:
                return self.format_error("Appliance identifier is required")

            serial_number, match_type = await self.integration.resolve_filer_identifier(appliance)
            if not serial_number:
                return self.format_error(f"Unable to resolve appliance identifier '{appliance}'")

            response = await self.api_client.get_metric(
                serial_number=serial_number,
                metric=self.metric_key,
                period=period,
                panel_width=panel_width,
                bin_size=bin_size,
                timezone_offset_minutes=tz_offset,
            )

            if isinstance(response, dict) and response.get("error"):
                error_msg = f"Portal telemetry error: {response['error']}"
                if response.get("details"):
                    error_msg += f" - Details: {response['details']}"
                return self.format_error(error_msg)

            output = self._format_response(
                entity_label=f"Appliance {serial_number} (matched by {match_type})",
                context={
                    "period": period,
                    "panel_width": panel_width,
                    "bin_size": bin_size,
                },
                payload=response,
                include_raw=include_raw,
            )

            return [TextContent(type="text", text=output)]

        except Exception as exc:
            logger.error(f"Appliance telemetry tool failure: {exc}")
            import traceback

            traceback.print_exc()
            return self.format_error(f"Unexpected error: {exc}")

    def _format_response(
        self,
        entity_label: str,
        context: Dict[str, Any],
        payload: Dict[str, Any],
        include_raw: bool,
    ) -> str:
        config = self.metric_config
        header = (
            f"📡 PORTAL OPS IQ TELEMETRY — {config['display_name']}\n"
            f"{config['description']}\n\n"
        )

        sections = [header]
        sections.append(f"Entity: {entity_label}")
        sections.append(f"Period: {context.get('period')}")
        if context.get("panel_width"):
            sections.append(f"Panel Width: {context['panel_width']} px")
        if context.get("bin_size"):
            sections.append(f"Bin Size: {context['bin_size']} s")

        sections.append("")

        if self.metric_key == "appliance_health_score":
            sections.append(self._format_health_score(payload))
        else:
            records = _extract_primary_records(payload)
            sections.append(_summarize_records(records))
            metadata_summary = _format_metadata(payload.get("metadata"))
            if metadata_summary:
                sections.append("\nMetadata\n" + metadata_summary)

        if include_raw:
            sections.append("\nRaw Preview (truncated)")
            sections.append(_raw_preview(payload))

        return "\n".join(section for section in sections if section)

    def _format_health_score(self, payload: Dict[str, Any]) -> str:
        parts = ["=== Health Score Summary ==="]
        score = payload.get("health_score", "Unknown")
        appliance_name = payload.get("appliance_name") or payload.get("serial_number")
        parts.append(f"Health Score: {score}")
        if appliance_name:
            parts.append(f"Reported Appliance: {appliance_name}")

        description = payload.get("description", {})
        if description:
            label = description.get("label") or description.get("title")
            text = description.get("message") or description.get("text")
            if label:
                parts.append(f"Status: {label}")
            if text:
                parts.append(f"Summary: {text}")

        stats = payload.get("statistics", {})
        if stats:
            stat_lines = [f"{k}: {v}" for k, v in stats.items() if v is not None]
            if stat_lines:
                parts.append("\nStatistics\n" + "\n".join(stat_lines[:8]))

        anomaly = payload.get("anomaly_details")
        if anomaly:
            parts.append("\nAnomaly Details\n" + json.dumps(anomaly, indent=2))

        return "\n".join(parts)


class PortalVolumeTelemetryTool(BaseTool):
    """Tool for querying a single Portal volume telemetry metric."""

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
        super().__init__(
            name=f"portal_volume_{metric_key}",
            description=description,
        )
        self.metric_key = metric_key
        self.metric_config = config
        self.api_client = api_client
        self.integration = integration_helper

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

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        try:
            volume_identifier = arguments.get("volume", "").strip()
            period = arguments.get("period", "PT3H")
            chart_width = arguments.get("chart_width")
            smart_sampling = arguments.get("smart_sampling", True)
            override_serials = arguments.get("serial_numbers") or []
            include_raw = arguments.get("include_raw", False)

            if not volume_identifier:
                return self.format_error("Volume name or GUID is required")

            volume_guid, identifier_type = await self.integration.resolve_volume_identifier(volume_identifier)
            if not volume_guid:
                return self.format_error(f"Unable to resolve volume '{volume_identifier}'")

            if override_serials:
                serials = [s.strip() for s in override_serials if s.strip()]
            else:
                serials = await self.integration.get_filer_serials_for_volume(volume_guid)

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

        except Exception as exc:
            logger.error(f"Volume telemetry tool failure: {exc}")
            import traceback

            traceback.print_exc()
            return self.format_error(f"Unexpected error: {exc}")

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


class GetVolumeProtectionMetricsTool(BaseTool):
    """Primary tool for volume data protection metrics from Portal Ops IQ."""

    def __init__(
        self,
        api_client: PortalVolumeTelemetryAPIClient,
        integration_helper: NMCPortalIntegration,
    ):
        super().__init__(
            name="get_volume_protection_metrics",
            description=(
                "[TELEMETRY - DATA PROTECTION] Get comprehensive data protection metrics from Portal Ops IQ. "
                "Provides timing and performance data NOT available from NMC. USE THIS TO ANSWER: (1) Latest volume/snapshot version, (2) Which appliance created latest snapshot, "
                "(3) Average data protection time (how long files remain unprotected), (4) Protection anomalies (worst cases of unprotected files), (5) Oldest Unprotected Data (OUD) age, "
                "(6) Snapshot phase timing (data & metadata duration), (7) Files and directories protected per snapshot, (8) Most active appliance, (9) Protection performance by appliance. "
                "Accepts volume name or GUID."
            ),
        )
        self.api_client = api_client
        self.integration = integration_helper

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
                    "description": (
                        "Time period (ISO 8601). Examples: PT1H, PT3H (default), PT6H, PT24H, P7D"
                    ),
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

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        try:
            volume_id = arguments.get("volume", "").strip()
            if not volume_id:
                return self.format_error("Volume name or GUID required")

            period = arguments.get("period", "PT3H")
            smart_sampling = arguments.get("smart_sampling", True)
            show_details = arguments.get("show_details", False)

            volume_guid, _ = await self.integration.resolve_volume_identifier(volume_id)
            if not volume_guid:
                return self.format_error(f"Volume not found: {volume_id}")

            serials = await self.integration.get_filer_serials_for_volume(volume_guid)
            if not serials:
                return self.format_error(f"No filers found for volume: {volume_id}")

            logger.info(f"Using {len(serials)} filer(s): {serials}")

            analysis = await self.api_client.get_volume_data_protection_analysis(
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

        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"Protection metrics tool error: {e}")
            import traceback

            traceback.print_exc()
            return self.format_error(str(e))

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


class CompareVolumeProtectionMetricsTool(BaseTool):
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
        )
        self.api_client = api_client
        self.integration = integration_helper

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "volumes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of volume names or GUIDs to compare (minimum 2)",
                },
                "period": {
                    "type": "string",
                    "description": "Time period for analysis (default: PT3H)",
                    "default": "PT3H",
                },
            },
            "required": ["volumes"],
        }

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        try:
            volumes = arguments.get("volumes", [])
            if not volumes or len(volumes) < 2:
                return self.format_error("At least 2 volumes required for comparison")

            period = arguments.get("period", "PT3H")
            volume_data = []

            for vol_id in volumes:
                logger.info(f"Analyzing volume: {vol_id}")
                volume_guid, _ = await self.integration.resolve_volume_identifier(vol_id)
                if not volume_guid:
                    logger.warning(f"Volume not found: {vol_id}, skipping")
                    continue

                serials = await self.integration.get_filer_serials_for_volume(volume_guid)
                if not serials:
                    logger.warning(f"No filers found for volume: {vol_id}, skipping")
                    continue

                analysis = await self.api_client.get_volume_data_protection_analysis(
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

        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"Protection comparison error: {e}")
            import traceback

            traceback.print_exc()
            return self.format_error(str(e))

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


class GetEndToEndProtectionTimingTool(BaseTool):
    """Tool for complete protection + propagation cycle timing."""

    def __init__(self, protection_client, propagation_client, integration_helper):
        super().__init__(
            name="get_end_to_end_protection_timing",
            description=(
                "[TELEMETRY - COMPLETE CYCLE] Get complete protection cycle: data change → snapshot → sync to all appliances. "
                "Combines protection and propagation to show total time for data to be protected AND available everywhere."
            ),
        )
        self.protection_client = protection_client
        self.propagation_client = propagation_client
        self.integration = integration_helper

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "volume": {"type": "string", "description": "Volume name or GUID"},
                "period": {
                    "type": "string",
                    "description": "Time period (default: PT3H)",
                },
            },
            "required": ["volume"],
        }

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
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

            protection = await self.protection_client.get_volume_data_protection_analysis(
                volume_guid, serials, period
            )
            propagation = await self.propagation_client.get_volume_data_propagation_analysis(
                volume_guid, serials, period
            )

            output = self._format_combined(volume_id, period, protection, propagation)
            return [TextContent(type="text", text=output)]

        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"End-to-end timing error: {e}")
            import traceback

            traceback.print_exc()
            return self.format_error(str(e))

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


class GetVolumePropagationMetricsTool(BaseTool):
    """Tool for data propagation (sync timing) metrics."""

    def __init__(
        self,
        api_client: PortalVolumeTelemetryAPIClient,
        integration_helper: NMCPortalIntegration,
    ):
        super().__init__(
            name="get_volume_propagation_metrics",
            description=(
                "[TELEMETRY - DATA PROPAGATION] Get sync timing metrics from Portal Ops IQ. "
                "Shows how long it takes for snapshots to propagate to connected appliances."
            ),
        )
        self.api_client = api_client
        self.integration = integration_helper

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
                    "description": "Time period (default: PT3H)",
                },
                "show_outliers": {
                    "type": "boolean",
                    "description": "Show detailed outlier information (default: true)",
                },
            },
            "required": ["volume"],
        }

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        try:
            volume_id = arguments.get("volume", "").strip()
            if not volume_id:
                return self.format_error("Volume name or GUID required")

            period = arguments.get("period", "PT3H")
            show_outliers = arguments.get("show_outliers", True)

            volume_guid, _ = await self.integration.resolve_volume_identifier(volume_id)
            if not volume_guid:
                return self.format_error(f"Volume not found: {volume_id}")

            serials = await self.integration.get_filer_serials_for_volume(volume_guid)
            if not serials:
                return self.format_error(f"No filers found for volume: {volume_id}")

            analysis = await self.api_client.get_volume_data_propagation_analysis(
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

        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"Propagation metrics tool error: {e}")
            import traceback

            traceback.print_exc()
            return self.format_error(str(e))

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


def _extract_primary_records(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("items"), list):
        return payload["items"]
    if isinstance(payload.get("records"), list):
        return payload["records"]

    combined: List[Dict[str, Any]] = []
    for key in ("data_events", "metadata_events", "events"):
        entries = payload.get(key)
        if isinstance(entries, list):
            combined.extend([entry for entry in entries if isinstance(entry, dict)])
    return combined


def _summarize_records(records: List[Dict[str, Any]]) -> str:
    if not records:
        return "No telemetry records returned."

    timestamps: List[Any] = []
    field_samples: Dict[str, List[float]] = {}

    for record in records:
        timestamp = _extract_timestamp(record)
        if timestamp is not None:
            timestamps.append(timestamp)
        for key, value in record.items():
            if key.lower() in _TIME_FIELDS:
                continue
            numeric_value = _coerce_float(value)
            if numeric_value is None:
                continue
            field_samples.setdefault(key, []).append(numeric_value)

    lines: List[str] = [f"Records: {len(records)}"]

    if timestamps:
        try:
            start = _format_timestamp(min(timestamps))
            end = _format_timestamp(max(timestamps))
            lines.append(f"Window: {start} → {end}")
        except Exception:
            pass

    shown = 0
    for field, values in field_samples.items():
        if not values:
            continue
        try:
            avg_val = mean(values)
        except StatisticsError:
            avg_val = values[0]
        try:
            line = (
                f"{field}: avg {avg_val:,.2f} | min {min(values):,.2f} | max {max(values):,.2f}"
            )
        except Exception:
            line = f"{field}: avg {avg_val}"
        lines.append(line)
        shown += 1
        if shown >= 6:
            break

    return "\n".join(lines)


def _format_metadata(metadata: Any) -> str:
    if not isinstance(metadata, dict) or not metadata:
        return "No metadata provided."
    lines = []
    for idx, (key, value) in enumerate(metadata.items()):
        if idx >= 8:
            lines.append("… (truncated)")
            break
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def _raw_preview(payload: Any, limit_chars: int = 1800) -> str:
    try:
        raw = json.dumps(payload, indent=2, default=str)
    except TypeError:
        raw = str(payload)
    if len(raw) > limit_chars:
        raw = raw[:limit_chars] + "\n… (truncated)"
    return raw


def _extract_timestamp(record: Dict[str, Any]) -> Optional[Any]:
    for key in _TIME_FIELDS:
        if key in record and record[key] is not None:
            return record[key]
    return None


def _coerce_float(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _format_timestamp(value: Any) -> str:
    if value is None:
        return "Unknown"
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 1_000_000_000_000:  # assume ms
            seconds = seconds / 1000.0
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
    return str(value)


# ============================================================================
# SYNC STATUS & LAG DETECTION TOOLS
# ============================================================================


class GetVolumeLatestVersionTool(BaseTool):
    """Tool to get the latest volume version and which appliance created it."""
    
    def __init__(
        self,
        protection_client: PortalVolumeTelemetryAPIClient,
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
            
        except Exception as e:
            logger.error(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return self.format_error(str(e))


class CheckApplianceSyncStatusTool(BaseTool):
    """Tool to check if an appliance is up-to-date with latest snapshot."""
    
    def __init__(
        self,
        protection_client: PortalVolumeTelemetryAPIClient,
        propagation_client: PortalVolumeTelemetryAPIClient,
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
        out = (
            f"🔍 APPLIANCE SYNC STATUS\n\n"
            f"=== APPLIANCE ===\n"
            f"Appliance: {appliance_id}\n"
            f"Volume: {volume_id}\n"
            f"Status: {status}\n\n"
            f"=== LATEST SNAPSHOT (VOLUME-WIDE) ===\n"
            f"Version: {latest_overall.volume_version}\n"
            f"Created By: {latest_overall.appliance}\n"
            f"Completed: {latest_overall.timestamp_str}\n\n"
            f"=== THIS APPLIANCE'S LATEST VERSION ===\n"
            f"Version: {latest_snapshot_version if latest_snapshot_version else 'No data'}\n"
            f"Source: {latest_snapshot_source.upper()}\n"
        )
        
        if latest_snapshot_time:
            out += f"Last Updated: {latest_snapshot_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        if lag_versions > 0:
            out += (
                f"\n=== ⚠️ SYNC LAG DETECTED ===\n"
                f"Versions Behind: {lag_versions}\n"
            )
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
        protection_client: PortalVolumeTelemetryAPIClient,
        propagation_client: PortalVolumeTelemetryAPIClient,
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
        
        out = (
            f"🔍 ALL APPLIANCES SYNC STATUS\n\n"
            f"Volume: {volume_id}\n"
            f"Latest Version: {latest_overall.volume_version}\n"
            f"Created By: {latest_overall.appliance} at {latest_overall.timestamp_str}\n\n"
            f"=== APPLIANCE STATUS ===\n\n"
        )
        
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
