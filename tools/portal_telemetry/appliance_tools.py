#!/usr/bin/env python3
"""Portal Ops IQ appliance telemetry tools.

This module provides tools for appliance-focused telemetry operations:
- PortalApplianceTelemetryTool: Dynamic metric tool for appliance metrics
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from mcp.types import TextContent

from api.portal_telemetry_api import (
    APPLIANCE_TELEMETRY_CONFIG,
    PortalApplianceTelemetryAPIClient,
)
from tools.base_tool import BaseTool
from utils.portal_nmc_integration import NMCPortalIntegration
from config.logging_setup import get_logger

from tools.portal_telemetry._common import (
    _extract_primary_records,
    _summarize_records,
    _format_metadata,
    _raw_preview,
)

logger = get_logger(__name__)


# ============================================================================
# DYNAMIC APPLIANCE METRIC TOOL (Config-driven)
# ============================================================================


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


# ============================================================================
# SMART MEMORY UTILIZATION TOOL (Version-aware)
# ============================================================================


class PortalApplianceMemoryUtilizationSmartTool(BaseTool):
    """
    Smart memory utilization tool that chooses the correct endpoint based on
    appliance version.
    
    - For appliances version < 10.0.4: Uses memory_utilization endpoint
    - For appliances version >= 10.0.4: Uses memory_utilization_details endpoint
    """

    def __init__(
        self,
        api_client: PortalApplianceTelemetryAPIClient,
        integration_helper: NMCPortalIntegration,
    ):
        description = (
            "[TELEMETRY] Smart Portal Ops IQ appliance memory utilization tool. "
            "Automatically selects the correct memory endpoint based on appliance version: "
            "uses memory_utilization for versions < 10.0.4, and memory_utilization_details "
            "for versions >= 10.0.4."
        )
        super().__init__(
            name="portal_appliance_memory_utilization_smart",
            description=description,
        )
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
            include_raw = arguments.get("include_raw", False)

            if not appliance:
                return self.format_error("Appliance identifier is required")

            serial_number, match_type = await self.integration.resolve_filer_identifier(appliance)
            if not serial_number:
                return self.format_error(f"Unable to resolve appliance identifier '{appliance}'")

            # Get the appliance version
            version_str = await self._get_appliance_version(serial_number)
            metric_key = self._select_metric_based_on_version(version_str)
            
            logger.info(
                f"Smart memory tool: appliance {serial_number} version={version_str}, "
                f"selected metric={metric_key}"
            )

            response = await self.api_client.get_metric(
                serial_number=serial_number,
                metric=metric_key,
                period=period,
                panel_width=panel_width,
                bin_size=bin_size,
            )

            if isinstance(response, dict) and response.get("error"):
                error_msg = f"Portal telemetry error: {response['error']}"
                if response.get("details"):
                    error_msg += f" - Details: {response['details']}"
                return self.format_error(error_msg)

            output = self._format_response(
                serial_number=serial_number,
                match_type=match_type,
                version=version_str,
                metric_key=metric_key,
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
            logger.error(f"Smart memory utilization tool failure: {exc}")
            import traceback
            traceback.print_exc()
            return self.format_error(f"Unexpected error: {exc}")

    async def _get_appliance_version(self, serial_number: str) -> str | None:
        """Get the version string for the appliance."""
        try:
            filers = await self.integration._get_cached_filers()
            for filer in filers:
                if filer.serial_number == serial_number:
                    if filer.status and filer.status.current_version:
                        return filer.status.current_version
            return None
        except Exception as exc:
            logger.warning(f"Could not get version for {serial_number}: {exc}")
            return None

    def _select_metric_based_on_version(self, version_str: str | None) -> str:
        """
        Select the appropriate metric based on version.
        
        Returns 'memory_utilization' for versions < 10.0.4
        Returns 'memory_utilization_details' for versions >= 10.0.4 or if version unknown
        """
        if not version_str:
            # Default to new endpoint if version unknown
            logger.info("Version unknown, defaulting to memory_utilization_details")
            return "memory_utilization_details"
        
        try:
            # Parse version string (e.g., "10.0.4" or "9.15.2")
            parts = version_str.split(".")
            version_tuple = tuple(int(p) for p in parts[:3])
            
            threshold = (10, 0, 4)
            
            if version_tuple < threshold:
                return "memory_utilization"
            else:
                return "memory_utilization_details"
        except (ValueError, IndexError) as exc:
            logger.warning(f"Could not parse version '{version_str}': {exc}")
            # Default to new endpoint on parse error
            return "memory_utilization_details"

    def _format_response(
        self,
        serial_number: str,
        match_type: str,
        version: str | None,
        metric_key: str,
        context: Dict[str, Any],
        payload: Dict[str, Any],
        include_raw: bool,
    ) -> str:
        config = APPLIANCE_TELEMETRY_CONFIG[metric_key]
        header = (
            f"📡 PORTAL OPS IQ TELEMETRY — Smart Memory Utilization\n"
            f"Automatically selected endpoint: {config['display_name']}\n\n"
        )

        sections = [header]
        sections.append(f"Entity: Appliance {serial_number} (matched by {match_type})")
        sections.append(f"Version: {version or 'Unknown'}")
        sections.append(f"Selected Endpoint: {metric_key}")
        sections.append(f"Period: {context.get('period')}")
        if context.get("panel_width"):
            sections.append(f"Panel Width: {context['panel_width']} px")
        if context.get("bin_size"):
            sections.append(f"Bin Size: {context['bin_size']} s")

        sections.append("")

        records = _extract_primary_records(payload)
        sections.append(_summarize_records(records))
        metadata_summary = _format_metadata(payload.get("metadata"))
        if metadata_summary:
            sections.append("\nMetadata\n" + metadata_summary)

        if include_raw:
            sections.append("\nRaw Preview (truncated)")
            sections.append(_raw_preview(payload))

        return "\n".join(section for section in sections if section)


def register_smart_memory_tool(
    registry,
    api_client: PortalApplianceTelemetryAPIClient,
    integration_helper: NMCPortalIntegration,
) -> None:
    """Register the smart memory utilization tool."""
    tool = PortalApplianceMemoryUtilizationSmartTool(api_client, integration_helper)
    registry.register_tool(tool)
    logger.info(f"Registered smart memory tool: {tool.name}")

