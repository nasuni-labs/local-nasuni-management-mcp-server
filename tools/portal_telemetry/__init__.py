"""Portal Ops IQ telemetry MCP tools package.

This package provides tools for querying Portal Ops IQ telemetry data:

REGULAR TOOLS (data retrieval):
- Volume tools: Protection metrics, propagation, sync status (including per-appliance)
- Appliance tools: Config-driven metric queries, health scores

WORKFLOW TOOLS (analysis guidance):
- Volume workflow: Step-by-step instructions for volume analysis (quick/standard/comprehensive)
- Appliance workflow: Step-by-step instructions for appliance analysis (quick/standard/comprehensive)

Usage:
    from tools.portal_telemetry import (
        # Volume data tools
        GetVolumeProtectionMetricsTool,
        GetVolumePropagationMetricsTool,
        GetVolumeLatestVersionTool,
        GetAllAppliancesSyncStatusTool,
        CheckApplianceSyncStatusTool,
        # Appliance data tools  
        PortalApplianceTelemetryTool,
        # Workflow tools (registration functions)
        register_volume_workflow_tools,
        register_appliance_workflow_tools,
    )
"""

from tools.portal_telemetry.volume_tools import (
    PortalVolumeTelemetryTool,
    GetVolumeProtectionMetricsTool,
    GetVolumeDataProtectionReportTool,
    GetVolumeHealthReportTool,
    GetFleetVolumeHealthSummaryTool,
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

from tools.portal_telemetry.volume_workflow_tools import (
    VolumeHealthQuickWorkflowTool,
    VolumeProtectionReportWorkflowTool,
    VolumeComprehensiveAnalysisWorkflowTool,
    register_volume_workflow_tools,
)

from tools.portal_telemetry.appliance_workflow_tools import (
    ApplianceHealthQuickWorkflowTool,
    ApplianceHealthReportWorkflowTool,
    ApplianceComprehensiveAnalysisWorkflowTool,
    register_appliance_workflow_tools,
)

__all__ = [
    # Volume data tools
    "PortalVolumeTelemetryTool",
    "GetVolumeProtectionMetricsTool",
    "GetVolumeDataProtectionReportTool",
    "GetVolumeHealthReportTool",
    "GetFleetVolumeHealthSummaryTool",
    "CompareVolumeProtectionMetricsTool",
    "GetEndToEndProtectionTimingTool",
    "GetVolumePropagationMetricsTool",
    "GetVolumeLatestVersionTool",
    "GetAllAppliancesSyncStatusTool",
    "CheckApplianceSyncStatusTool",
    # Appliance data tools
    "PortalApplianceTelemetryTool",
    # Volume workflow tools
    "VolumeHealthQuickWorkflowTool",
    "VolumeProtectionReportWorkflowTool",
    "VolumeComprehensiveAnalysisWorkflowTool",
    "register_volume_workflow_tools",
    # Appliance workflow tools
    "ApplianceHealthQuickWorkflowTool",
    "ApplianceHealthReportWorkflowTool",
    "ApplianceComprehensiveAnalysisWorkflowTool",
    "register_appliance_workflow_tools",
]
