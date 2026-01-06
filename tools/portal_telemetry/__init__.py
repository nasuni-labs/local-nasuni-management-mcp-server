"""Portal Ops IQ telemetry MCP tools package.

This package provides tools for querying Portal Ops IQ telemetry data:
- Volume tools: Protection metrics, propagation, sync status (including per-appliance)
- Appliance tools: Config-driven metric queries, health scores

Usage:
    from tools.portal_telemetry import (
        # Volume tools
        PortalVolumeTelemetryTool,
        GetVolumeProtectionMetricsTool,
        GetVolumePropagationMetricsTool,
        GetVolumeLatestVersionTool,
        GetAllAppliancesSyncStatusTool,
        CheckApplianceSyncStatusTool,
        # Appliance tools  
        PortalApplianceTelemetryTool,
    )
"""

from tools.portal_telemetry.volume_tools import (
    PortalVolumeTelemetryTool,
    GetVolumeProtectionMetricsTool,
    CompareVolumeProtectionMetricsTool,
    GetEndToEndProtectionTimingTool,
    GetVolumePropagationMetricsTool,
    GetVolumeLatestVersionTool,
    GetAllAppliancesSyncStatusTool,
    CheckApplianceSyncStatusTool,
)

from tools.portal_telemetry.appliance_tools import (
    PortalApplianceTelemetryTool,
)

__all__ = [
    # Volume tools
    "PortalVolumeTelemetryTool",
    "GetVolumeProtectionMetricsTool",
    "CompareVolumeProtectionMetricsTool",
    "GetEndToEndProtectionTimingTool",
    "GetVolumePropagationMetricsTool",
    "GetVolumeLatestVersionTool",
    "GetAllAppliancesSyncStatusTool",
    "CheckApplianceSyncStatusTool",
    # Appliance tools
    "PortalApplianceTelemetryTool",
]
