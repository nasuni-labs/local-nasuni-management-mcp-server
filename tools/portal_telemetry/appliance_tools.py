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

    # Endpoints that are snapshots (fixed time window, period parameter ignored)
    SNAPSHOT_ENDPOINTS = {"current_appliance_performance"}

    def __init__(
        self,
        metric_key: str,
        api_client: PortalApplianceTelemetryAPIClient,
        integration_helper: NMCPortalIntegration,
    ):
        if metric_key not in APPLIANCE_TELEMETRY_CONFIG:
            raise ValueError(f"Unsupported appliance metric '{metric_key}'")

        config = APPLIANCE_TELEMETRY_CONFIG[metric_key]
        
        # Special description for snapshot endpoints (no period parameter)
        if metric_key in self.SNAPSHOT_ENDPOINTS:
            description = (
                f"[TELEMETRY] Portal Ops IQ — {config['display_name']}. "
                f"{config['description']} "
                "NOTE: This returns a SNAPSHOT based on the last 30 minutes of data only. "
                "No time period can be specified. For historical trends over hours/days, "
                "use cpu_utilization, memory_utilization, or other time-series metrics instead."
            )
        else:
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
        self.is_snapshot = metric_key in self.SNAPSHOT_ENDPOINTS

    def get_schema(self) -> Dict[str, Any]:
        # Base properties for all appliance telemetry tools
        properties = {
            "appliance": {
                "type": "string",
                "description": "Filer serial number or name",
            },
        }
        
        # Only add period for non-snapshot endpoints
        # Snapshot endpoints (like current_appliance_performance) use a fixed 30-minute window
        if not self.is_snapshot:
            properties["period"] = {
                "type": "string",
                "description": (
                    "ISO 8601 duration or explicit range (default PT3H)."
                ),
                "default": "PT3H",
            }
            properties["panel_width"] = {
                "type": "integer",
                "description": "Panel width in pixels (100-5200) for sampling hints.",
            }
            properties["bin_size"] = {
                "type": "integer",
                "description": "Bin size in seconds (60-3600) for sampling hints.",
            }
            properties["timezone_offset_minutes"] = {
                "type": "integer",
                "description": (
                    "Optional timezone offset minutes (only used for health_score)."
                ),
            }
        
        properties["include_raw"] = {
            "type": "boolean",
            "description": "Include a truncated JSON preview of the raw payload.",
            "default": False,
        }
        
        return {
            "type": "object",
            "properties": properties,
            "required": ["appliance"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        try:
            appliance = arguments.get("appliance", "").strip()
            include_raw = arguments.get("include_raw", False)
            
            # For snapshot endpoints, we don't expose period to users but the API
            # still requires it (bug in Portal API). Send a dummy value.
            if self.is_snapshot:
                # API requires period but ignores it - send PT30M to match the 30-minute window
                period = "PT30M"
                panel_width = None
                bin_size = None
                tz_offset = None
            else:
                period = arguments.get("period", "PT3H")
                panel_width = arguments.get("panel_width")
                bin_size = arguments.get("bin_size")
                tz_offset = arguments.get("timezone_offset_minutes")

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

            # Build context for display
            if self.is_snapshot:
                context = {"time_window": "Last 30 minutes (snapshot)"}
            else:
                context = {
                    "period": period,
                    "panel_width": panel_width,
                    "bin_size": bin_size,
                }

            output = self._format_response(
                entity_label=f"Appliance {serial_number} (matched by {match_type})",
                context=context,
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


# ============================================================================
# COMPREHENSIVE APPLIANCE ANALYSIS GUIDANCE TOOL
# ============================================================================


class ApplianceComprehensiveAnalysisGuideTool(BaseTool):
    """Meta-tool that provides guidance for comprehensive appliance analysis.
    
    Instead of making expensive calls to all telemetry endpoints, this tool
    returns instructions to the LLM on how to systematically analyze an appliance.
    """

    def __init__(self, integration_helper: NMCPortalIntegration):
        description = (
            "[PORTAL - ANALYSIS GUIDE] Get step-by-step instructions for comprehensive appliance health analysis. "
            "Returns a systematic approach to analyze all telemetry metrics over 30 days, identify trends, "
            "find issues, and report min/max/averages. USE THIS when user asks for full appliance analysis, "
            "health report, or trend analysis. This tool provides guidance - it does NOT make expensive API calls."
        )
        super().__init__(
            name="portal_appliance_comprehensive_analysis_guide",
            description=description,
        )
        self.integration = integration_helper

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "appliance": {
                    "type": "string",
                    "description": "Filer serial number or name to analyze",
                },
                "analysis_depth": {
                    "type": "string",
                    "enum": ["quick", "standard", "comprehensive"],
                    "description": "Level of analysis: quick (core metrics only), standard (common issues), comprehensive (all metrics)",
                    "default": "standard",
                },
            },
            "required": ["appliance"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        appliance = arguments.get("appliance", "").strip()
        analysis_depth = arguments.get("analysis_depth", "standard")

        if not appliance:
            return self.format_error("Appliance identifier is required")

        # Resolve the appliance to get serial number
        serial_number, match_type = await self.integration.resolve_filer_identifier(appliance)
        if not serial_number:
            return self.format_error(f"Unable to resolve appliance identifier '{appliance}'")

        guide = self._generate_analysis_guide(serial_number, match_type, analysis_depth)
        return [TextContent(type="text", text=guide)]

    def _generate_analysis_guide(self, serial_number: str, match_type: str, depth: str) -> str:
        """Generate the analysis guide based on depth level."""
        
        guide = f"""📊 COMPREHENSIVE APPLIANCE ANALYSIS GUIDE
{'=' * 60}

Target Appliance: {serial_number} (matched by {match_type})
Analysis Depth: {depth.upper()}
Recommended Period: P30D (30 days) for trend analysis

"""

        if depth == "quick":
            guide += self._quick_analysis_steps(serial_number)
        elif depth == "standard":
            guide += self._standard_analysis_steps(serial_number)
        else:  # comprehensive
            guide += self._comprehensive_analysis_steps(serial_number)

        guide += self._analysis_tips()
        
        return guide

    def _quick_analysis_steps(self, serial: str) -> str:
        return f"""
🚀 QUICK ANALYSIS (Core Health Check)
{'─' * 40}

Execute these steps IN ORDER:

STEP 1: Quick Health Snapshot
  Tool: portal_appliance_current_appliance_performance
  Args: appliance="{serial}", period="PT1H"
  Look for: CPU stress, memory pressure, I/O bottlenecks
  
STEP 2: If issues found, check CPU trend
  Tool: portal_appliance_cpu_utilization
  Args: appliance="{serial}", period="P7D"
  Look for: Sustained >80% usage, sudden spikes
  
STEP 3: If memory issues, check memory trend
  Tool: portal_appliance_memory_utilization
  Args: appliance="{serial}", period="P7D"
  Look for: Memory exhaustion trends, OOM risk

ANALYSIS COMPLETE - Report findings with:
- Current health status (healthy/warning/critical)
- Any concerning trends identified
- Recommended actions if issues found
"""

    def _standard_analysis_steps(self, serial: str) -> str:
        return f"""
📋 STANDARD ANALYSIS (Common Issues Detection)
{'─' * 40}

Execute these steps IN ORDER, stopping if critical issues found:

PHASE 1: Initial Health Assessment
──────────────────────────────────
STEP 1: Quick health snapshot
  Tool: portal_appliance_current_appliance_performance
  Args: appliance="{serial}", period="PT3H"
  Evaluate: Overall health state, immediate issues

PHASE 2: Core Resource Analysis (30-day trends)
───────────────────────────────────────────────
STEP 2: CPU utilization trend
  Tool: portal_appliance_cpu_utilization
  Args: appliance="{serial}", period="P30D"
  Report: Min, Max, Average, trend direction
  Alert if: Avg >70%, Max >95%, or upward trend

STEP 3: Memory utilization trend
  Tool: portal_appliance_memory_utilization
  Args: appliance="{serial}", period="P30D"
  Report: Min, Max, Average, trend direction
  Alert if: Avg >85%, Max >95%, or sustained growth

STEP 4: Cache utilization (storage health)
  Tool: portal_appliance_cache_utilization
  Args: appliance="{serial}", period="P30D"
  Report: Utilization trend, capacity concerns
  Alert if: Sustained >90% or rapid growth

PHASE 3: Performance Indicators
───────────────────────────────
STEP 5: Cache disk latency
  Tool: portal_appliance_cache_disk_io_time
  Args: appliance="{serial}", period="P30D"
  Report: Latency trends, performance degradation
  Alert if: Latency increasing or >50ms average

STEP 6: Network throughput
  Tool: portal_appliance_network_utilization
  Args: appliance="{serial}", period="P30D"
  Report: Throughput patterns, saturation risk
  Alert if: Sustained high utilization or drops

FINAL REPORT should include:
- Executive summary (1-2 sentences)
- Health score (Healthy/Warning/Critical)
- Key metrics table (min/max/avg for each)
- Trend analysis (improving/stable/degrading)
- Issues found with severity
- Recommended actions
"""

    def _comprehensive_analysis_steps(self, serial: str) -> str:
        return f"""
🔬 COMPREHENSIVE ANALYSIS (Full Telemetry Review)
{'─' * 40}

⚠️ NOTE: This is a thorough analysis. Execute steps sequentially.

PHASE 1: Health Baseline
────────────────────────
STEP 1: Current performance snapshot
  Tool: portal_appliance_current_appliance_performance
  Args: appliance="{serial}", period="PT3H"

STEP 2: Deep health score (if anomalies suspected)
  Tool: portal_appliance_appliance_health_score
  Args: appliance="{serial}", period="P7D"
  Note: Expensive call - only if Step 1 shows issues

PHASE 2: CPU & Load Analysis
────────────────────────────
STEP 3: CPU utilization (30-day trend)
  Tool: portal_appliance_cpu_utilization
  Args: appliance="{serial}", period="P30D"

STEP 4: Load average (system stress)
  Tool: portal_appliance_load_average
  Args: appliance="{serial}", period="P30D"

PHASE 3: Memory Deep Dive
─────────────────────────
STEP 5: Memory utilization trend
  Tool: portal_appliance_memory_utilization
  Args: appliance="{serial}", period="P30D"

STEP 6: Memory breakdown (if issues in Step 5)
  Tool: portal_appliance_memory_utilization_smart
  Args: appliance="{serial}", period="P7D"

PHASE 4: Storage & Cache Analysis
─────────────────────────────────
STEP 7: Cache utilization
  Tool: portal_appliance_cache_utilization
  Args: appliance="{serial}", period="P30D"

STEP 8: Cache hits/misses (efficiency)
  Tool: portal_appliance_cache_hits_misses
  Args: appliance="{serial}", period="P30D"

STEP 9: Cache disk IOPS
  Tool: portal_appliance_cache_disk_iops
  Args: appliance="{serial}", period="P30D"

STEP 10: Cache disk latency
  Tool: portal_appliance_cache_disk_io_time
  Args: appliance="{serial}", period="P30D"

PHASE 5: OS & System Disk
─────────────────────────
STEP 11: OS disk IOPS
  Tool: portal_appliance_os_disk_iops
  Args: appliance="{serial}", period="P30D"

STEP 12: OS disk latency
  Tool: portal_appliance_os_disk_io_time
  Args: appliance="{serial}", period="P30D"

PHASE 6: Network Analysis
─────────────────────────
STEP 13: Network throughput
  Tool: portal_appliance_network_utilization
  Args: appliance="{serial}", period="P30D"

STEP 14: SMB connections (client load)
  Tool: portal_appliance_smb_connections
  Args: appliance="{serial}", period="P30D"

PHASE 7: Specialized Storage (if applicable)
────────────────────────────────────────────
STEP 15: CoW disk performance
  Tool: portal_appliance_cow_disk_iops
  Args: appliance="{serial}", period="P30D"

STEP 16: File IQ disk performance (if File IQ enabled)
  Tool: portal_appliance_file_iq_disk_iops
  Args: appliance="{serial}", period="P30D"

COMPREHENSIVE REPORT FORMAT:
============================
1. EXECUTIVE SUMMARY
   - Overall health assessment
   - Critical findings (if any)
   - Trend direction (improving/stable/degrading)

2. METRICS SUMMARY TABLE
   | Metric | Min | Max | Avg | Trend | Status |
   |--------|-----|-----|-----|-------|--------|
   (Include all analyzed metrics)

3. ISSUE ANALYSIS
   For each issue found:
   - Description
   - Severity (Critical/Warning/Info)
   - Evidence (specific data points)
   - Potential root cause
   - Recommended action

4. TREND ANALYSIS
   - 30-day trend direction for each metric
   - Correlation between metrics
   - Predicted issues if trends continue

5. RECOMMENDATIONS
   - Immediate actions required
   - Short-term optimizations
   - Long-term capacity planning
"""

    def _analysis_tips(self) -> str:
        return """

💡 ANALYSIS TIPS
{'─' * 40}

THRESHOLDS FOR ALERTS:
• CPU: Warning >70% avg, Critical >90% avg
• Memory: Warning >80% avg, Critical >95% avg  
• Cache: Warning >85% utilization, Critical >95%
• Disk Latency: Warning >20ms, Critical >50ms
• Cache Hit Rate: Warning <80%, Critical <60%

TREND INTERPRETATION:
• Compare first week vs last week of period
• Calculate % change to determine trend direction
• Look for sudden changes (may indicate events)

CORRELATION PATTERNS:
• High CPU + High Memory = Resource exhaustion
• Low Cache Hits + High Disk I/O = Cache sizing issue
• High Network + High CPU = Heavy client load
• High Latency + Normal IOPS = Disk performance issue

REPORTING BEST PRACTICES:
• Lead with the most critical finding
• Use specific numbers, not vague descriptions
• Always include recommended actions
• Note any data gaps or anomalies
"""


def register_comprehensive_analysis_guide_tool(
    registry,
    integration_helper: NMCPortalIntegration,
) -> None:
    """Register the comprehensive analysis guide tool."""
    tool = ApplianceComprehensiveAnalysisGuideTool(integration_helper)
    registry.register_tool(tool)
    logger.info(f"Registered comprehensive analysis guide tool: {tool.name}")


