#!/usr/bin/env python3
"""TCO (Total Cost of Ownership) analysis tools for Nasuni Edge Appliances.

This module provides tools for analyzing cloud costs and providing
right-sizing recommendations based on utilization metrics.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from mcp.types import TextContent

from tools.base_tool import BaseTool
from tools.tco.pricing_client import (
    CloudPricingClient,
    InstancePricing,
    get_pricing_client,
)
from config.logging_setup import get_logger

logger = get_logger(__name__)


# =============================================================================
# UTILIZATION THRESHOLDS
# =============================================================================

@dataclass
class UtilizationThresholds:
    """Thresholds for determining right-sizing recommendations."""
    # CPU thresholds
    cpu_underutilized: float = 20.0  # Below this = consider downsizing
    cpu_optimal_low: float = 20.0
    cpu_optimal_high: float = 70.0
    cpu_overutilized: float = 70.0  # Above this = consider upsizing
    
    # Memory thresholds
    memory_underutilized: float = 30.0
    memory_optimal_low: float = 30.0
    memory_optimal_high: float = 80.0
    memory_overutilized: float = 80.0
    
    # Load thresholds (normalized per CPU)
    load_underutilized: float = 0.3  # Load per CPU
    load_optimal_low: float = 0.3
    load_optimal_high: float = 0.7
    load_overutilized: float = 0.7


DEFAULT_THRESHOLDS = UtilizationThresholds()


# =============================================================================
# NASUNI EDGE APPLIANCE MINIMUM REQUIREMENTS
# =============================================================================

@dataclass
class NasuniMinimumRequirements:
    """Minimum hardware requirements for Nasuni Edge Appliances.
    
    These are the official minimum specifications from Nasuni documentation.
    Appliances running below these specs may experience performance issues
    or may not be supported.
    """
    # Compute requirements
    min_vcpus: int = 8
    min_memory_gib: int = 16
    
    # Disk requirements (in GiB)
    min_os_disk_gib: int = 32
    min_cache_disk_gib: int = 250
    min_cow_disk_gib: int = 62  # Copy-on-Write disk
    min_total_disk_gib: int = 344  # Total free disk space required
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "compute": {
                "min_vcpus": self.min_vcpus,
                "min_memory_gib": self.min_memory_gib,
            },
            "storage": {
                "min_os_disk_gib": self.min_os_disk_gib,
                "min_cache_disk_gib": self.min_cache_disk_gib,
                "min_cow_disk_gib": self.min_cow_disk_gib,
                "min_total_disk_gib": self.min_total_disk_gib,
            },
        }


# Singleton instance of minimum requirements
NASUNI_MIN_REQUIREMENTS = NasuniMinimumRequirements()


@dataclass
class MinimumRequirementsCheck:
    """Result of checking an appliance against minimum requirements."""
    meets_requirements: bool
    vcpus_ok: bool
    memory_ok: bool
    actual_vcpus: int
    actual_memory_gib: float
    required_vcpus: int
    required_memory_gib: int
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "meets_minimum_requirements": self.meets_requirements,
            "checks": {
                "vcpus": {
                    "ok": self.vcpus_ok,
                    "actual": self.actual_vcpus,
                    "required": self.required_vcpus,
                },
                "memory_gib": {
                    "ok": self.memory_ok,
                    "actual": self.actual_memory_gib,
                    "required": self.required_memory_gib,
                },
            },
            "violations": self.violations,
            "warnings": self.warnings,
        }
    
    def to_text(self) -> str:
        """Generate text summary of requirements check."""
        lines = []
        if self.meets_requirements:
            lines.append("✅ **Meets Minimum Requirements**")
        else:
            lines.append("❌ **BELOW MINIMUM REQUIREMENTS**")
            for violation in self.violations:
                lines.append(f"  - {violation}")
        
        if self.warnings:
            for warning in self.warnings:
                lines.append(f"  ⚠️ {warning}")
        
        return "\n".join(lines)


# =============================================================================
# SUPPORTED CLOUD PLATFORMS FOR TCO ANALYSIS
# =============================================================================

# TCO analysis is only available for cloud-hosted Edge Appliances on AWS and Azure.
# Physical/on-premises appliances do not have cloud compute costs to analyze.
SUPPORTED_TCO_PLATFORMS = frozenset([
    "amazon",
    "aws",
    "ec2",
    "azure",
    "microsoft",
])

# Platform strings that indicate AWS
AWS_PLATFORM_INDICATORS = frozenset([
    "amazon",
    "aws",
    "ec2",
    "nitro",
])

# Platform strings that indicate Azure
AZURE_PLATFORM_INDICATORS = frozenset([
    "azure",
    "microsoft",
    "hyper-v",
])


def is_supported_tco_platform(platform: Optional[str]) -> bool:
    """Check if the platform supports TCO analysis.
    
    TCO analysis is only available for AWS and Azure Edge Appliances
    where cloud compute costs can be analyzed.
    
    Args:
        platform: Platform string from EdgeBuild (e.g., "NVM Filer on Amazon EC2 (Nitro)")
        
    Returns:
        True if the platform is AWS or Azure, False otherwise
    """
    if not platform:
        return False
    
    platform_lower = platform.lower()
    
    # Check for AWS indicators
    for indicator in AWS_PLATFORM_INDICATORS:
        if indicator in platform_lower:
            return True
    
    # Check for Azure indicators
    for indicator in AZURE_PLATFORM_INDICATORS:
        if indicator in platform_lower:
            return True
    
    return False


def get_platform_provider(platform: Optional[str]) -> Optional[str]:
    """Determine the cloud provider from platform string.
    
    Args:
        platform: Platform string from EdgeBuild
        
    Returns:
        "aws", "azure", or None if not a supported cloud platform
    """
    if not platform:
        return None
    
    platform_lower = platform.lower()
    
    for indicator in AWS_PLATFORM_INDICATORS:
        if indicator in platform_lower:
            return "aws"
    
    for indicator in AZURE_PLATFORM_INDICATORS:
        if indicator in platform_lower:
            return "azure"
    
    return None


def get_unsupported_platform_message(platform: Optional[str], appliance_name: str) -> str:
    """Generate a helpful error message for unsupported platforms.
    
    Args:
        platform: The platform string (may be None)
        appliance_name: Name of the appliance for the error message
        
    Returns:
        User-friendly error message explaining why TCO is not available
    """
    if not platform:
        return (
            f"TCO analysis is not available for '{appliance_name}': "
            "No platform information found. "
            "TCO analysis requires AWS EC2 or Azure VM Edge Appliances."
        )
    
    return (
        f"TCO analysis is not available for '{appliance_name}'. "
        f"Platform '{platform}' is not supported. "
        "TCO analysis is only available for AWS EC2 and Azure VM Edge Appliances. "
        "Physical or on-premises appliances do not have cloud compute costs to analyze."
    )


# =============================================================================
# TCO ANALYSIS RESULT
# =============================================================================

@dataclass
class RightSizingRecommendation:
    """Right-sizing recommendation for an appliance."""
    action: str  # "downsize", "upsize", "optimal"
    reason: str
    confidence: str  # "high", "medium", "low"
    current_instance: str
    recommended_instance: Optional[str] = None
    current_monthly_cost: float = 0.0
    recommended_monthly_cost: float = 0.0
    monthly_savings: float = 0.0
    yearly_savings: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "confidence": self.confidence,
            "current_instance": self.current_instance,
            "recommended_instance": self.recommended_instance,
            "current_monthly_cost": self.current_monthly_cost,
            "recommended_monthly_cost": self.recommended_monthly_cost,
            "monthly_savings": self.monthly_savings,
            "yearly_savings": self.yearly_savings,
        }


@dataclass
class TCOAnalysisResult:
    """Complete TCO analysis result for an appliance."""
    appliance_id: str
    appliance_name: str
    provider: str
    region: str
    instance_type: str
    
    # Current costs
    current_hourly_cost: float
    current_daily_cost: float
    current_monthly_cost: float
    current_yearly_cost: float
    
    # Utilization metrics (average over analysis period)
    avg_cpu_percent: float
    avg_memory_percent: float
    avg_load: float
    
    # Utilization metrics (maximum/peak over analysis period)
    max_cpu_percent: float
    max_memory_percent: float
    max_load: float
    
    # Hardware specs
    vcpus: int
    memory_gib: float  # Memory in GiB for requirements check
    load_per_cpu: float
    max_load_per_cpu: float
    
    # Recommendation (no default - required field)
    recommendation: RightSizingRecommendation
    
    # Metadata and optional fields (all have defaults)
    min_requirements_check: Optional[MinimumRequirementsCheck] = None
    analysis_period_hours: int = 720  # Default 30 days for better baseline
    analysis_timestamp: datetime = field(default_factory=datetime.utcnow)
    pricing_source: str = "live_api"  # "live_api" or "static_fallback"
    utilization_data_available: bool = True  # False if telemetry API failed or returned no data
    
    # Constants for transparency
    HOURS_PER_DAY: int = 24
    HOURS_PER_MONTH: int = 730  # Industry standard: 365 days / 12 months * 24 hours
    HOURS_PER_YEAR: int = 8760  # 365 * 24
    
    def to_dict(self) -> Dict[str, Any]:
        # Put the most important context at the very top for LLM consumption
        result = {
            # This should be stated to the user verbatim
            "important_context": self._get_important_context(),
            "data_sources": {
                "pricing": self._get_pricing_source_summary(),
                "utilization": f"Portal Telemetry API (last {self.analysis_period_hours} hours)",
                "appliance_info": "Portal Edges API",
            },
            "appliance": {
                "id": self.appliance_id,
                "name": self.appliance_name,
                "provider": self.provider.upper(),
                "region": self.region,
                "instance_type": self.instance_type,
                "vcpus": self.vcpus,
                "memory_gib": self.memory_gib,
            },
            # Minimum requirements check (important for compliance)
            "minimum_requirements": self.min_requirements_check.to_dict() if self.min_requirements_check else None,
            "current_costs": {
                "note": self._get_cost_note(),
                "hourly": f"${self.current_hourly_cost:.4f}",
                "daily": f"${self.current_daily_cost:.2f}",
                "monthly": f"${self.current_monthly_cost:.2f}",
                "yearly": f"${self.current_yearly_cost:.2f}",
            },
            "cost_breakdown": {
                "hourly_rate": f"${self.current_hourly_cost:.4f}/hr from {self._get_api_name()}",
                "calculations": {
                    "daily": f"${self.current_hourly_cost:.4f}/hr × 24 hrs = ${self.current_daily_cost:.2f}",
                    "monthly": f"${self.current_hourly_cost:.4f}/hr × 730 hrs = ${self.current_monthly_cost:.2f}",
                    "yearly": f"${self.current_hourly_cost:.4f}/hr × 8,760 hrs = ${self.current_yearly_cost:.2f}",
                },
                "pricing_assumptions": [
                    "On-Demand pricing (no Reserved Instances or Savings Plans)",
                    "Linux/Unix operating system",
                    "Shared tenancy",
                ],
            },
            "utilization": {
                "period": f"Last {self.analysis_period_hours} hours ({self.analysis_period_hours // 24} days)",
                "average": {
                    "cpu_percent": f"{self.avg_cpu_percent:.1f}%",
                    "memory_percent": f"{self.avg_memory_percent:.1f}%",
                    "load": f"{self.avg_load:.2f}",
                    "load_per_cpu": f"{self.load_per_cpu:.2f}",
                },
                "peak": {
                    "cpu_percent": f"{self.max_cpu_percent:.1f}%",
                    "memory_percent": f"{self.max_memory_percent:.1f}%",
                    "load": f"{self.max_load:.2f}",
                    "load_per_cpu": f"{self.max_load_per_cpu:.2f}",
                },
            },
            "recommendation": self.recommendation.to_dict(),
            "analysis_metadata": {
                "timestamp": self.analysis_timestamp.isoformat(),
                "period_hours": self.analysis_period_hours,
            },
        }
        return result
    
    def _get_important_context(self) -> str:
        """Get the key context that should be communicated to the user."""
        if self.provider == "aws":
            return (
                f"Cost estimates are based on live AWS On-Demand pricing for {self.instance_type} "
                f"in {self.region}, fetched from the Vantage pricing API. "
                f"Utilization metrics are from the last {self.analysis_period_hours} hours ({self.analysis_period_hours // 24} days)."
            )
        elif self.provider == "azure":
            return (
                f"Cost estimates are based on live Azure Pay-As-You-Go pricing for {self.instance_type} "
                f"in {self.region}, fetched from the Azure Retail Prices API. "
                f"Utilization metrics are from the last {self.analysis_period_hours} hours ({self.analysis_period_hours // 24} days)."
            )
        else:
            return (
                f"Cost estimates are based on static pricing data for {self.instance_type}. "
                f"Utilization metrics are from the last {self.analysis_period_hours} hours ({self.analysis_period_hours // 24} days)."
            )
    
    def _get_pricing_source_summary(self) -> str:
        """Get a one-line summary of the pricing data source."""
        if self.provider == "aws":
            return f"AWS EC2 On-Demand pricing via Vantage API (instances.vantage.sh) for {self.instance_type} in {self.region}"
        elif self.provider == "azure":
            return f"Azure Retail Prices API (prices.azure.com) for {self.instance_type} in {self.region}"
        else:
            return f"Static pricing data for {self.instance_type}"
    
    def _get_api_name(self) -> str:
        """Get the API name for the pricing source."""
        if self.provider == "aws":
            return "Vantage AWS Pricing API"
        elif self.provider == "azure":
            return "Azure Retail Prices API"
        else:
            return "static data"
    
    def _get_cost_note(self) -> str:
        """Get a note explaining the cost basis."""
        if self.provider == "aws":
            return f"Based on live AWS On-Demand pricing for {self.instance_type} in {self.region}"
        elif self.provider == "azure":
            return f"Based on live Azure Pay-As-You-Go pricing for {self.instance_type} in {self.region}"
        else:
            return f"Based on estimated pricing for {self.instance_type}"
    
    def to_text_report(self) -> str:
        """Generate a formatted text report for LLM consumption."""
        lines = []
        
        # Header
        lines.append(f"# Total Cost of Ownership Report: {self.appliance_name}")
        lines.append("")
        
        # Data Source Attribution (IMPORTANT - must be communicated to user)
        lines.append("## Data Sources")
        lines.append(f"- **Pricing**: {self._get_pricing_source_summary()}")
        lines.append(f"- **Utilization**: Portal Telemetry API (last {self.analysis_period_hours} hours / {self.analysis_period_hours // 24} days)")
        lines.append(f"- **Appliance Info**: Portal Edges API")
        lines.append("")
        
        # Appliance Details
        lines.append("## Appliance Details")
        lines.append(f"- **Name**: {self.appliance_name}")
        lines.append(f"- **Provider**: {self.provider.upper()}")
        lines.append(f"- **Region**: {self.region}")
        lines.append(f"- **Instance Type**: {self.instance_type}")
        lines.append(f"- **vCPUs**: {self.vcpus}")
        lines.append(f"- **Memory**: {self.memory_gib:.1f} GiB")
        lines.append("")
        
        # Minimum Requirements Check (IMPORTANT - show compliance status)
        lines.append("## Nasuni Minimum Requirements Check")
        if self.min_requirements_check:
            lines.append(self.min_requirements_check.to_text())
            lines.append("")
            lines.append(f"| Spec | Actual | Required | Status |")
            lines.append(f"|------|--------|----------|--------|")
            vcpu_status = "✅" if self.min_requirements_check.vcpus_ok else "❌"
            mem_status = "✅" if self.min_requirements_check.memory_ok else "❌"
            lines.append(f"| vCPUs | {self.min_requirements_check.actual_vcpus} | {self.min_requirements_check.required_vcpus} | {vcpu_status} |")
            lines.append(f"| Memory | {self.min_requirements_check.actual_memory_gib:.1f} GiB | {self.min_requirements_check.required_memory_gib} GiB | {mem_status} |")
        else:
            lines.append("*Unable to verify minimum requirements*")
        lines.append("")
        
        # Current Costs with clear attribution
        lines.append("## Current Costs")
        lines.append(f"*{self._get_cost_note()}*")
        lines.append("")
        lines.append(f"| Period | Cost |")
        lines.append(f"|--------|------|")
        lines.append(f"| Hourly | ${self.current_hourly_cost:.4f} |")
        lines.append(f"| Daily | ${self.current_daily_cost:.2f} |")
        lines.append(f"| Monthly | ${self.current_monthly_cost:.2f} |")
        lines.append(f"| Yearly | ${self.current_yearly_cost:.2f} |")
        lines.append("")
        
        # Cost Calculation Breakdown
        lines.append("## How Costs Are Calculated")
        lines.append(f"- **Hourly Rate**: ${self.current_hourly_cost:.4f}/hr (from {self._get_api_name()})")
        lines.append(f"- **Daily**: ${self.current_hourly_cost:.4f}/hr × 24 hours = ${self.current_daily_cost:.2f}")
        lines.append(f"- **Monthly**: ${self.current_hourly_cost:.4f}/hr × 730 hours = ${self.current_monthly_cost:.2f}")
        lines.append(f"- **Yearly**: ${self.current_hourly_cost:.4f}/hr × 8,760 hours = ${self.current_yearly_cost:.2f}")
        lines.append("")
        lines.append("**Pricing Assumptions:**")
        lines.append("- On-Demand pricing (no Reserved Instances or Savings Plans)")
        lines.append("- Linux/Unix operating system")
        lines.append("- Shared tenancy")
        lines.append("")
        
        # Utilization Metrics - show both average and peak
        lines.append("## Utilization Metrics")
        if not self.utilization_data_available:
            lines.append("")
            lines.append("⚠️ **WARNING: TELEMETRY DATA NOT AVAILABLE**")
            lines.append("")
            lines.append("The utilization metrics below could not be retrieved from the Portal Telemetry API.")
            lines.append("This may be because:")
            lines.append("- The appliance has not been online long enough to generate telemetry data")
            lines.append("- The telemetry API is temporarily unavailable")
            lines.append("- The appliance is not configured to report telemetry")
            lines.append("")
            lines.append("**Right-sizing recommendations cannot be made without utilization data.**")
            lines.append("Please verify the appliance is online and has telemetry enabled.")
            lines.append("")
        else:
            lines.append(f"*Based on the last {self.analysis_period_hours} hours ({self.analysis_period_hours // 24} days) of telemetry data*")
            lines.append("")
            lines.append(f"| Metric | Average | Peak (Max) |")
            lines.append(f"|--------|---------|------------|")
            lines.append(f"| CPU | {self.avg_cpu_percent:.1f}% | {self.max_cpu_percent:.1f}% |")
            lines.append(f"| Memory | {self.avg_memory_percent:.1f}% | {self.max_memory_percent:.1f}% |")
            lines.append(f"| System Load | {self.avg_load:.2f} | {self.max_load:.2f} |")
            lines.append(f"| Load per CPU | {self.load_per_cpu:.2f} | {self.max_load_per_cpu:.2f} |")
            lines.append("")
            lines.append("*Note: Peak values indicate maximum utilization during the analysis period. "
                        "High peak values may indicate periodic spikes that should be considered for capacity planning.*")
        lines.append("")
        
        # Recommendation
        lines.append("## Right-Sizing Recommendation")
        rec = self.recommendation
        if rec.action == "unknown":
            lines.append(f"❓ **UNABLE TO DETERMINE**")
            lines.append("")
            lines.append(f"- **Reason**: {rec.reason}")
            lines.append("")
            lines.append("Without utilization data, we cannot make an informed recommendation about right-sizing.")
            lines.append("Please ensure the appliance is online and reporting telemetry data.")
        elif rec.action == "downsize":
            lines.append(f"💰 **COST SAVINGS OPPORTUNITY**")
            lines.append("")
            lines.append(f"Consider downsizing from **{rec.current_instance}** to **{rec.recommended_instance}**")
            lines.append("")
            lines.append(f"- **Reason**: {rec.reason}")
            lines.append(f"- **Confidence**: {rec.confidence}")
            lines.append(f"- **Current Monthly Cost**: ${rec.current_monthly_cost:.2f}")
            lines.append(f"- **Recommended Monthly Cost**: ${rec.recommended_monthly_cost:.2f}")
            lines.append(f"- **Monthly Savings**: ${rec.monthly_savings:.2f}")
            lines.append(f"- **Yearly Savings**: ${rec.yearly_savings:.2f}")
        elif rec.action == "upsize":
            lines.append(f"⚠️ **PERFORMANCE RISK**")
            lines.append("")
            lines.append(f"Consider upsizing from **{rec.current_instance}** to **{rec.recommended_instance}**")
            lines.append("")
            lines.append(f"- **Reason**: {rec.reason}")
            lines.append(f"- **Confidence**: {rec.confidence}")
            lines.append(f"- **Current Monthly Cost**: ${rec.current_monthly_cost:.2f}")
            lines.append(f"- **Recommended Monthly Cost**: ${rec.recommended_monthly_cost:.2f}")
            lines.append(f"- **Additional Monthly Cost**: ${abs(rec.monthly_savings):.2f}")
        else:
            lines.append(f"✅ **OPTIMAL**")
            lines.append("")
            lines.append(f"Current instance size **{rec.current_instance}** is well-matched to utilization.")
            lines.append("")
            lines.append(f"- **Reason**: {rec.reason}")
            lines.append(f"- **Confidence**: {rec.confidence}")
        lines.append("")
        
        # Footer
        lines.append("---")
        lines.append(f"*Analysis performed at {self.analysis_timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}*")
        
        return "\n".join(lines)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def hours_to_period(hours: int) -> str:
    """Convert hours to ISO 8601 duration format (PT format)."""
    if hours <= 3:
        return "PT3H"
    elif hours <= 12:
        return "PT12H"
    elif hours <= 24:
        return "PT24H"
    elif hours <= 72:
        return "PT72H"
    elif hours <= 168:
        return "PT168H"  # 7 days
    else:
        return "PT720H"  # 30 days


async def get_edges_api():
    """Lazily import and create Portal Edges API client."""
    from api.portal_edges_api import PortalEdgesAPIClient
    from config.settings import config
    from api.portal_auth_api import PortalAuthAPIClient
    
    auth_client = PortalAuthAPIClient(config.portal_config)
    return PortalEdgesAPIClient(config.portal_config, auth_client)


async def get_telemetry_api():
    """Lazily import and create Portal Telemetry API client."""
    from config.settings import config
    from api.portal_auth_api import PortalAuthAPIClient
    from api.portal_telemetry_api import PortalApplianceTelemetryAPIClient
    
    auth_client = PortalAuthAPIClient(config.portal_config)
    return PortalApplianceTelemetryAPIClient(config.portal_config, auth_client)


def is_valid_uuid(value: str) -> bool:
    """Check if a string is a valid UUID."""
    uuid_pattern = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        re.IGNORECASE
    )
    return bool(uuid_pattern.match(value))


async def resolve_edge_id_to_guid(edges_api, edge_id: str) -> Optional[str]:
    """Resolve edge ID/serial/name to GUID."""
    # Check if already a UUID
    if is_valid_uuid(edge_id):
        return edge_id
    
    # Search edges list - returns EdgesDto with items list of SimpleEdgeDto
    edges_response = await edges_api.get_edges()
    if not edges_response or not edges_response.items:
        return None
    
    edge_id_lower = edge_id.lower()
    for edge in edges_response.items:
        # SimpleEdgeDto has id, description, serial, build, services
        if (
            (edge.id and edge.id.lower() == edge_id_lower)
            or (edge.serial and edge.serial.lower() == edge_id_lower)
            or (edge.description and edge.description.lower() == edge_id_lower)
        ):
            return edge.id
    
    return None


def parse_ram_to_gib(ram_str: Optional[str]) -> Optional[float]:
    """Parse RAM string (e.g., '16 GiB', '32GB', '16384 MB') to GiB.
    
    Args:
        ram_str: RAM string from EdgeMachine (e.g., '16 GiB', '32 GB', '16384 MB')
        
    Returns:
        Memory in GiB, or None if parsing fails
    """
    if not ram_str:
        return None
    
    ram_str = ram_str.strip().upper()
    
    # Try to extract number and unit
    match = re.match(r'^([\d.]+)\s*([A-Z]+)?$', ram_str)
    if not match:
        return None
    
    try:
        value = float(match.group(1))
        unit = match.group(2) or 'GIB'  # Default to GiB if no unit
        
        # Convert to GiB
        if unit in ('GIB', 'GB', 'G'):
            return value
        elif unit in ('MIB', 'MB', 'M'):
            return value / 1024
        elif unit in ('TIB', 'TB', 'T'):
            return value * 1024
        else:
            # Assume GiB if unknown unit
            return value
    except (ValueError, TypeError):
        return None


def _select_memory_metric_for_version(version_str: Optional[str]) -> str:
    """Select the appropriate memory metric based on appliance version.
    
    Returns 'memory_utilization' for versions < 10.0.4
    Returns 'memory_utilization_details' for versions >= 10.0.4 or if version unknown
    """
    if not version_str:
        # Default to new endpoint if version unknown
        logger.debug("Version unknown, defaulting to memory_utilization_details")
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


async def get_appliance_utilization_metrics(
    telemetry_api,
    serial_number: str,
    hours: int = 720,  # Default to 30 days for better baseline
    appliance_version: Optional[str] = None,  # For version-aware memory metric selection
) -> Dict[str, float]:
    """Get utilization metrics (average and max) for an appliance.
    
    Uses 30 days of telemetry data by default for a more accurate baseline.
    Calculates both average and maximum values for each metric.
    
    Args:
        telemetry_api: Portal telemetry API client
        serial_number: Appliance serial number
        hours: Time range in hours (default 720 = 30 days)
        appliance_version: Appliance version string for smart memory metric selection
    
    Returns metrics with 'data_available' flag to indicate if real data was fetched.
    """
    period = hours_to_period(hours)
    
    # Select the correct memory metric based on version
    memory_metric = _select_memory_metric_for_version(appliance_version)
    logger.debug(f"Using memory metric '{memory_metric}' for version '{appliance_version}'")
    
    try:
        # Get CPU metrics
        cpu_data = await telemetry_api.get_metric(serial_number, "cpu_utilization", period=period)
        logger.debug(f"CPU telemetry response for {serial_number}: {type(cpu_data)} - keys: {cpu_data.keys() if isinstance(cpu_data, dict) else 'N/A'}")
        if isinstance(cpu_data, dict) and "items" in cpu_data:
            logger.debug(f"CPU items count: {len(cpu_data['items'])}")
            if cpu_data['items']:
                # Log first item's structure to understand the format
                logger.debug(f"CPU first item keys: {cpu_data['items'][0].keys() if isinstance(cpu_data['items'][0], dict) else 'N/A'}")
                logger.debug(f"CPU first item: {cpu_data['items'][0]}")
        avg_cpu = calculate_telemetry_average(cpu_data)
        max_cpu = calculate_telemetry_max(cpu_data)
        logger.debug(f"CPU calculated: avg={avg_cpu}, max={max_cpu}")
        
        # Get memory metrics (version-aware)
        memory_data = await telemetry_api.get_metric(serial_number, memory_metric, period=period)
        logger.debug(f"Memory telemetry response for {serial_number}: {type(memory_data)} - keys: {memory_data.keys() if isinstance(memory_data, dict) else 'N/A'}")
        if isinstance(memory_data, dict) and "items" in memory_data:
            logger.debug(f"Memory items count: {len(memory_data['items'])}")
            if memory_data['items']:
                logger.debug(f"Memory first item keys: {memory_data['items'][0].keys() if isinstance(memory_data['items'][0], dict) else 'N/A'}")
        avg_memory = calculate_telemetry_average(memory_data)
        max_memory = calculate_telemetry_max(memory_data)
        logger.debug(f"Memory calculated: avg={avg_memory}, max={max_memory}")
        
        # Get load metrics (load_average is the correct metric name in Portal API)
        load_data = await telemetry_api.get_metric(serial_number, "load_average", period=period)
        logger.debug(f"Load telemetry response for {serial_number}: {type(load_data)} - keys: {load_data.keys() if isinstance(load_data, dict) else 'N/A'}")
        if isinstance(load_data, dict) and "items" in load_data:
            logger.debug(f"Load items count: {len(load_data['items'])}")
            if load_data['items']:
                logger.debug(f"Load first item keys: {load_data['items'][0].keys() if isinstance(load_data['items'][0], dict) else 'N/A'}")
                logger.debug(f"Load first item: {load_data['items'][0]}")
        avg_load = calculate_telemetry_average(load_data)
        max_load = calculate_telemetry_max(load_data)
        
        # Check if we actually got any data
        has_cpu_data = avg_cpu > 0 or max_cpu > 0
        has_memory_data = avg_memory > 0 or max_memory > 0
        has_load_data = avg_load > 0 or max_load > 0
        
        if not has_cpu_data and not has_memory_data and not has_load_data:
            logger.warning(f"Telemetry API returned no data for {serial_number}. CPU response type: {type(cpu_data)}, Memory response type: {type(memory_data)}")
            return {
                "avg_cpu": 0.0,
                "max_cpu": 0.0,
                "avg_memory": 0.0,
                "max_memory": 0.0,
                "avg_load": 0.0,
                "max_load": 0.0,
                "data_available": False,
                "error": "No telemetry data returned from API",
            }
        
        logger.info(f"Got utilization for {serial_number}: CPU avg={avg_cpu:.1f}% max={max_cpu:.1f}%, Memory avg={avg_memory:.1f}% max={max_memory:.1f}%")
        
        return {
            "avg_cpu": avg_cpu,
            "max_cpu": max_cpu,
            "avg_memory": avg_memory,
            "max_memory": max_memory,
            "avg_load": avg_load,
            "max_load": max_load,
            "data_available": True,
        }
        
    except Exception as e:
        logger.error(f"Failed to get utilization metrics for {serial_number}: {e}")
        return {
            "avg_cpu": 0.0,
            "max_cpu": 0.0,
            "avg_memory": 0.0,
            "max_memory": 0.0,
            "avg_load": 0.0,
            "max_load": 0.0,
            "data_available": False,
            "error": str(e),
        }


def calculate_telemetry_average(data: Any) -> float:
    """Calculate average from telemetry response data."""
    values = _extract_telemetry_values(data)
    return sum(values) / len(values) if values else 0.0


def calculate_telemetry_max(data: Any) -> float:
    """Calculate maximum from telemetry response data."""
    values = _extract_telemetry_values(data)
    return max(values) if values else 0.0


def _extract_telemetry_values(data: Any) -> List[float]:
    """Extract numeric values from Portal telemetry response data.
    
    The Portal API returns data in this format:
    {
        "items": [
            {"time": "2026-01-13T10:00:00Z", "value": 5.2},
            {"time": "2026-01-13T10:05:00Z", "value": 6.1},
            ...
        ],
        "metadata": {...}
    }
    
    For cpu_utilization and memory_utilization, each item has a 'value' key with the percentage.
    Some metrics may use different keys like 'avg', 'percent', etc.
    """
    if not data:
        return []
    
    # Time fields to skip when extracting numeric values
    TIME_FIELDS = {"time", "timestamp", "start", "start_time", "end", "end_time", 
                   "bucket_start", "bucket_end", "completed_at", "created_at"}
    
    # Handle different response formats
    values = []
    
    if isinstance(data, dict):
        # Portal API standard format: items list
        if "items" in data and isinstance(data["items"], list):
            items = data["items"]
        # Fallback: check for other nested structures
        elif "data" in data:
            items = data["data"]
        elif "results" in data:
            items = data["results"]
        else:
            items = [data]
    elif isinstance(data, list):
        items = data
    else:
        return []
    
    # Extract numeric values from items
    for item in items:
        if isinstance(item, dict):
            # First try known value keys in order of likelihood
            # Note: cpu_utilization uses 'cpu_usage', memory uses 'value', 
            # load_average uses 'one_minute_load_average', 'five_minute_load_average', etc.
            # We prefer fifteen_minute_load_average for more stable load measurement
            found = False
            for key in ["value", "cpu_usage", "memory_usage", 
                        "fifteen_minute_load_average", "five_minute_load_average", "one_minute_load_average",
                        "load_15min", "load_5min", "load_1min",
                        "avg", "average", "mean", "percent", "utilization", "max"]:
                if key in item:
                    try:
                        val = float(item[key])
                        values.append(val)
                        found = True
                        break
                    except (ValueError, TypeError):
                        pass
            
            # If no known key found, try ALL numeric fields (excluding time fields)
            if not found:
                for key, val in item.items():
                    if key.lower() in TIME_FIELDS:
                        continue
                    try:
                        # Skip booleans
                        if isinstance(val, bool):
                            continue
                        numeric_val = float(val)
                        values.append(numeric_val)
                        # Only take first numeric value per item
                        break
                    except (ValueError, TypeError):
                        pass
                        
        elif isinstance(item, (int, float)):
            values.append(float(item))
    
    return values


def check_minimum_requirements(
    vcpus: int,
    memory_gib: float,
    requirements: NasuniMinimumRequirements = NASUNI_MIN_REQUIREMENTS,
) -> MinimumRequirementsCheck:
    """Check if appliance specs meet Nasuni minimum requirements.
    
    Args:
        vcpus: Number of vCPUs on the appliance
        memory_gib: Memory in GiB
        requirements: Minimum requirements to check against
        
    Returns:
        MinimumRequirementsCheck with compliance status and any violations
    """
    violations = []
    warnings = []
    
    # Check vCPUs
    vcpus_ok = vcpus >= requirements.min_vcpus
    if not vcpus_ok:
        violations.append(
            f"vCPUs ({vcpus}) is below minimum requirement ({requirements.min_vcpus})"
        )
    elif vcpus == requirements.min_vcpus:
        warnings.append(
            f"vCPUs ({vcpus}) is at the minimum - consider headroom for growth"
        )
    
    # Check memory
    memory_ok = memory_gib >= requirements.min_memory_gib
    if not memory_ok:
        violations.append(
            f"Memory ({memory_gib:.1f} GiB) is below minimum requirement ({requirements.min_memory_gib} GiB)"
        )
    elif memory_gib < requirements.min_memory_gib * 1.25:  # Within 25% of minimum
        warnings.append(
            f"Memory ({memory_gib:.1f} GiB) is close to minimum ({requirements.min_memory_gib} GiB) - consider adding headroom"
        )
    
    meets_requirements = vcpus_ok and memory_ok
    
    return MinimumRequirementsCheck(
        meets_requirements=meets_requirements,
        vcpus_ok=vcpus_ok,
        memory_ok=memory_ok,
        actual_vcpus=vcpus,
        actual_memory_gib=memory_gib,
        required_vcpus=requirements.min_vcpus,
        required_memory_gib=requirements.min_memory_gib,
        violations=violations,
        warnings=warnings,
    )


# =============================================================================
# TCO ANALYZER
# =============================================================================

class TCOAnalyzer:
    """Analyzes TCO and provides right-sizing recommendations."""
    
    def __init__(
        self,
        pricing_client: CloudPricingClient,
        thresholds: UtilizationThresholds = DEFAULT_THRESHOLDS,
    ):
        self.pricing_client = pricing_client
        self.thresholds = thresholds
    
    def detect_provider(self, instance_type: str) -> str:
        """Detect cloud provider from instance type format."""
        if instance_type.startswith("Standard_"):
            return "azure"
        elif "." in instance_type:  # AWS format like m5.xlarge
            return "aws"
        else:
            # Try to guess
            if any(char.isdigit() for char in instance_type.split("_")[0] if "_" in instance_type):
                return "azure"
            return "aws"
    
    def normalize_region(self, region: str, provider: str) -> str:
        """Normalize region name for the provider."""
        if not region:
            return "us-east-1" if provider == "aws" else "eastus"
        
        # Handle common variations
        region_lower = region.lower().replace(" ", "").replace("-", "")
        
        if provider == "aws":
            # Map Azure-style to AWS
            aws_map = {
                "eastus": "us-east-1",
                "eastus2": "us-east-2",
                "westus": "us-west-1",
                "westus2": "us-west-2",
                "westeurope": "eu-west-1",
                "northeurope": "eu-west-2",
            }
            return aws_map.get(region_lower, region)
        else:
            # Map AWS-style to Azure
            azure_map = {
                "useast1": "eastus",
                "useast2": "eastus2",
                "uswest1": "westus",
                "uswest2": "westus2",
                "euwest1": "westeurope",
            }
            return azure_map.get(region_lower, region)
    
    async def analyze_appliance(
        self,
        instance_type: str,
        region: str,
        avg_cpu: float,
        avg_memory: float,
        avg_load: float,
        max_cpu: float = 0.0,
        max_memory: float = 0.0,
        max_load: float = 0.0,
        appliance_id: str = "",
        appliance_name: str = "",
        analysis_period_hours: int = 720,  # Default to 30 days for better baseline
        memory_gib: Optional[float] = None,  # Memory in GiB for requirements check
        utilization_data_available: bool = True,  # False if telemetry API failed or returned no data
    ) -> TCOAnalysisResult:
        """Analyze an appliance and provide TCO with recommendations.
        
        Args:
            instance_type: Cloud instance type (e.g., m5.xlarge, Standard_D4s_v3)
            region: Cloud region
            avg_cpu: Average CPU utilization percentage
            avg_memory: Average memory utilization percentage
            avg_load: Average system load
            max_cpu: Maximum/peak CPU utilization percentage
            max_memory: Maximum/peak memory utilization percentage
            max_load: Maximum/peak system load
            appliance_id: Appliance GUID
            appliance_name: Appliance name/description
            analysis_period_hours: Hours of telemetry data analyzed (default 720 = 30 days)
            memory_gib: Actual memory in GiB (for requirements check)
            utilization_data_available: Whether real telemetry data was available
        """
        # Detect provider
        provider = self.detect_provider(instance_type)
        normalized_region = self.normalize_region(region, provider)
        
        # Get current pricing
        if provider == "aws":
            pricing = await self.pricing_client.get_aws_pricing(instance_type, normalized_region)
        else:
            pricing = await self.pricing_client.get_azure_pricing(instance_type, normalized_region)
        
        if not pricing:
            # Create a placeholder with zero costs
            pricing = InstancePricing(
                provider=provider,
                instance_type=instance_type,
                region=normalized_region,
                vcpus=4,  # Default assumption
                memory_gb=16,
                hourly_price=0,
                monthly_price=0,
                yearly_price=0,
            )
            logger.warning(f"Could not find pricing for {instance_type} in {normalized_region}")
        
        # Calculate load per CPU (average and max)
        vcpus = pricing.vcpus or 4
        load_per_cpu = avg_load / vcpus if vcpus > 0 else avg_load
        max_load_per_cpu = max_load / vcpus if vcpus > 0 else max_load
        
        # Use max values for analysis if provided, otherwise use averages
        # This ensures we account for peak utilization when making recommendations
        analysis_cpu = max_cpu if max_cpu > 0 else avg_cpu
        analysis_memory = max_memory if max_memory > 0 else avg_memory
        analysis_load_per_cpu = max_load_per_cpu if max_load > 0 else load_per_cpu
        
        # Use provided memory_gib or get from pricing data
        actual_memory_gib = memory_gib if memory_gib is not None else (pricing.memory_gb or 16)
        
        # Check minimum requirements
        min_requirements_check = check_minimum_requirements(
            vcpus=vcpus,
            memory_gib=actual_memory_gib,
        )
        
        # Generate recommendation based on PEAK utilization for safety
        recommendation = self._generate_recommendation(
            instance_type=instance_type,
            provider=provider,
            region=normalized_region,
            avg_cpu=analysis_cpu,  # Use peak for analysis
            avg_memory=analysis_memory,  # Use peak for analysis
            load_per_cpu=analysis_load_per_cpu,  # Use peak for analysis
            current_pricing=pricing,
            min_requirements_check=min_requirements_check,
            utilization_data_available=utilization_data_available,
        )
        
        return TCOAnalysisResult(
            appliance_id=appliance_id,
            appliance_name=appliance_name,
            provider=provider,
            region=normalized_region,
            instance_type=instance_type,
            current_hourly_cost=pricing.hourly_price,
            current_daily_cost=pricing.daily_price,
            current_monthly_cost=pricing.monthly_price,
            current_yearly_cost=pricing.yearly_price,
            avg_cpu_percent=avg_cpu,
            avg_memory_percent=avg_memory,
            avg_load=avg_load,
            max_cpu_percent=max_cpu if max_cpu > 0 else avg_cpu,
            max_memory_percent=max_memory if max_memory > 0 else avg_memory,
            max_load=max_load if max_load > 0 else avg_load,
            vcpus=vcpus,
            memory_gib=actual_memory_gib,
            load_per_cpu=load_per_cpu,
            max_load_per_cpu=max_load_per_cpu,
            min_requirements_check=min_requirements_check,
            recommendation=recommendation,
            analysis_period_hours=analysis_period_hours,
            utilization_data_available=utilization_data_available,
        )
    
    def _generate_recommendation(
        self,
        instance_type: str,
        provider: str,
        region: str,
        avg_cpu: float,
        avg_memory: float,
        load_per_cpu: float,
        current_pricing: InstancePricing,
        min_requirements_check: Optional[MinimumRequirementsCheck] = None,
        utilization_data_available: bool = True,
    ) -> RightSizingRecommendation:
        """Generate a right-sizing recommendation based on utilization.
        
        Takes into account Nasuni minimum requirements when making recommendations.
        Will not recommend downsizing if it would put the appliance below minimum specs.
        Will flag appliances that are already below minimum requirements.
        Will not recommend downsizing if utilization data is not available.
        """
        t = self.thresholds
        
        # If no utilization data is available, don't make recommendations based on it
        if not utilization_data_available:
            return RightSizingRecommendation(
                action="unknown",
                confidence="none",
                reason="Cannot determine right-sizing recommendation: utilization telemetry data not available. "
                       "Verify the appliance is online and has telemetry enabled.",
                current_instance=instance_type,
                recommended_instance=instance_type,
                current_monthly_cost=current_pricing.monthly_price,
                recommended_monthly_cost=current_pricing.monthly_price,
                monthly_savings=0.0,
                yearly_savings=0.0,
            )
        
        # Analyze each metric
        cpu_status = self._analyze_metric(avg_cpu, t.cpu_underutilized, t.cpu_overutilized)
        memory_status = self._analyze_metric(avg_memory, t.memory_underutilized, t.memory_overutilized)
        load_status = self._analyze_metric(load_per_cpu, t.load_underutilized, t.load_overutilized)
        
        # Count statuses
        underutilized_count = sum(1 for s in [cpu_status, memory_status, load_status] if s == "under")
        overutilized_count = sum(1 for s in [cpu_status, memory_status, load_status] if s == "over")
        
        # Check if appliance is already below minimum requirements
        below_minimum = min_requirements_check and not min_requirements_check.meets_requirements
        at_minimum_vcpus = (min_requirements_check and 
                           min_requirements_check.actual_vcpus == min_requirements_check.required_vcpus)
        at_minimum_memory = (min_requirements_check and 
                            min_requirements_check.actual_memory_gib <= min_requirements_check.required_memory_gib * 1.1)
        
        # Determine action
        if below_minimum:
            # Appliance is BELOW minimum requirements - must upsize
            action = "upsize"
            confidence = "high"
            violations = min_requirements_check.violations if min_requirements_check else []
            reason = f"BELOW MINIMUM REQUIREMENTS: {'; '.join(violations)}. Must upsize to meet Nasuni minimum specs."
            
        elif overutilized_count >= 2:
            action = "upsize"
            confidence = "high" if overutilized_count == 3 else "medium"
            reasons = []
            if cpu_status == "over":
                reasons.append(f"CPU at {avg_cpu:.1f}%")
            if memory_status == "over":
                reasons.append(f"Memory at {avg_memory:.1f}%")
            if load_status == "over":
                reasons.append(f"Load/CPU at {load_per_cpu:.2f}")
            reason = f"High utilization: {', '.join(reasons)}"
            
        elif underutilized_count >= 2 and overutilized_count == 0:
            # Check if downsizing would go below minimum requirements
            if at_minimum_vcpus or at_minimum_memory:
                action = "optimal"
                confidence = "medium"
                reason = (f"Low utilization (CPU: {avg_cpu:.1f}%, Memory: {avg_memory:.1f}%), "
                         f"but CANNOT DOWNSIZE - already at or near Nasuni minimum requirements "
                         f"(min {NASUNI_MIN_REQUIREMENTS.min_vcpus} vCPUs, {NASUNI_MIN_REQUIREMENTS.min_memory_gib} GiB RAM)")
            else:
                action = "downsize"
                confidence = "high" if underutilized_count == 3 else "medium"
                reasons = []
                if cpu_status == "under":
                    reasons.append(f"CPU at {avg_cpu:.1f}%")
                if memory_status == "under":
                    reasons.append(f"Memory at {avg_memory:.1f}%")
                if load_status == "under":
                    reasons.append(f"Load/CPU at {load_per_cpu:.2f}")
                reason = f"Low utilization: {', '.join(reasons)}"
            
        elif overutilized_count == 1:
            action = "upsize"
            confidence = "low"
            metric = "CPU" if cpu_status == "over" else "Memory" if memory_status == "over" else "Load"
            value = avg_cpu if cpu_status == "over" else avg_memory if memory_status == "over" else load_per_cpu
            reason = f"{metric} utilization elevated ({value:.1f}{'%' if metric != 'Load' else ''}), monitor before upsizing"
            
        elif underutilized_count >= 1 and overutilized_count == 0:
            # Check minimum requirements before suggesting downsize
            if at_minimum_vcpus or at_minimum_memory:
                action = "optimal"
                confidence = "medium"
                reason = (f"Some underutilization, but at Nasuni minimum requirements - no downsize possible")
            else:
                action = "downsize"
                confidence = "low"
                reason = "Some metrics show low utilization, consider monitoring before downsizing"
            
        else:
            action = "optimal"
            confidence = "high"
            reason = f"Utilization is optimal (CPU: {avg_cpu:.1f}%, Memory: {avg_memory:.1f}%, Load/CPU: {load_per_cpu:.2f})"
        
        # Get recommended instance if action is to resize
        recommended_instance = None
        recommended_monthly = current_pricing.monthly_price
        monthly_savings = 0.0
        
        if action == "downsize":
            recommended_instance = self.pricing_client.get_smaller_instance(instance_type, provider)
            if recommended_instance:
                # Verify the recommended instance still meets minimum requirements
                if provider == "aws":
                    rec_pricing = self.pricing_client._get_aws_static_pricing(recommended_instance, region)
                else:
                    rec_pricing = self.pricing_client._get_azure_static_pricing(recommended_instance, region)
                
                if rec_pricing:
                    # Check if the smaller instance meets minimum requirements
                    rec_vcpus = rec_pricing.vcpus or 4
                    rec_memory = rec_pricing.memory_gb or 16
                    if rec_vcpus < NASUNI_MIN_REQUIREMENTS.min_vcpus or rec_memory < NASUNI_MIN_REQUIREMENTS.min_memory_gib:
                        # Smaller instance doesn't meet requirements - can't downsize
                        recommended_instance = None
                        action = "optimal"
                        reason = (f"Low utilization, but next smaller instance ({rec_pricing.instance_type}) "
                                 f"would be below Nasuni minimum requirements ({NASUNI_MIN_REQUIREMENTS.min_vcpus} vCPUs, "
                                 f"{NASUNI_MIN_REQUIREMENTS.min_memory_gib} GiB RAM)")
                    else:
                        recommended_monthly = rec_pricing.monthly_price
                        monthly_savings = current_pricing.monthly_price - rec_pricing.monthly_price
        
        elif action == "upsize":
            recommended_instance = self.pricing_client.get_larger_instance(instance_type, provider)
            if recommended_instance:
                if provider == "aws":
                    rec_pricing = self.pricing_client._get_aws_static_pricing(recommended_instance, region)
                else:
                    rec_pricing = self.pricing_client._get_azure_static_pricing(recommended_instance, region)
                
                if rec_pricing:
                    recommended_monthly = rec_pricing.monthly_price
                    monthly_savings = current_pricing.monthly_price - rec_pricing.monthly_price
        
        return RightSizingRecommendation(
            action=action,
            reason=reason,
            confidence=confidence,
            current_instance=instance_type,
            recommended_instance=recommended_instance,
            current_monthly_cost=current_pricing.monthly_price,
            recommended_monthly_cost=recommended_monthly,
            monthly_savings=monthly_savings,
            yearly_savings=monthly_savings * 12,
        )
    
    def _analyze_metric(self, value: float, under_threshold: float, over_threshold: float) -> str:
        """Analyze a metric and return status."""
        if value < under_threshold:
            return "under"
        elif value > over_threshold:
            return "over"
        return "optimal"


# =============================================================================
# MCP TOOLS
# =============================================================================

class GetApplianceTCOTool(BaseTool):
    """Tool for analyzing TCO of a single Edge Appliance."""
    
    def __init__(self):
        super().__init__(
            name="tco_analyze_appliance",
            description="""Analyze the Total Cost of Ownership (TCO) for a Nasuni Edge Appliance.

**IMPORTANT: TCO analysis is ONLY available for AWS EC2 and Azure VM Edge Appliances.**
Physical, VMware, or other on-premises appliances do not have cloud compute costs to analyze.

This tool fetches current cloud pricing, analyzes utilization metrics over 30 days,
and provides right-sizing recommendations to optimize costs.

Analysis uses 30 days of telemetry data by default for a more accurate baseline.
Both average AND peak (maximum) utilization are calculated to ensure recommendations
account for periodic spikes in usage.

Returns:
- Minimum requirements compliance check (8 vCPUs, 16 GiB RAM minimum)
- Current costs (hourly, daily, monthly, yearly)
- Utilization metrics (CPU, Memory, Load) - both average and peak values
- Right-sizing recommendation (downsize, upsize, or optimal) based on PEAK utilization
- Potential savings if downsizing is recommended

Important: The tool validates that the appliance meets Nasuni minimum requirements:
- Minimum 8 vCPUs
- Minimum 16 GiB RAM
- Minimum 344 GiB disk space (32 GiB OS + 250 GiB cache + 62 GiB CoW)

Appliances below minimum requirements will be flagged and upsizing will be recommended.
Downsizing recommendations will never suggest an instance below minimum requirements.

Note: Requires the appliance to be deployed on AWS EC2 or Azure VM with vm_instance_type set in the Portal."""
        )
    
    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "edge_id": {
                    "type": "string",
                    "description": "Edge appliance ID, serial number, or name to analyze"
                },
                "time_range_hours": {
                    "type": "integer",
                    "description": "Hours of historical data to analyze (default: 720 = 30 days for better baseline)",
                    "default": 720
                },
            },
            "required": ["edge_id"],
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        import json
        edge_id = arguments.get("edge_id", "")
        time_range_hours = arguments.get("time_range_hours", 720)
        
        if not edge_id:
            return self.format_error("edge_id is required")
        
        try:
            # Get API clients
            edges_api = await get_edges_api()
            telemetry_api = await get_telemetry_api()
            
            # Find the edge
            edge_guid = await resolve_edge_id_to_guid(edges_api, edge_id)
            if not edge_guid:
                return self.format_error(f"Could not find edge with ID: {edge_id}")
            
            # Get edge details - returns EdgeDto
            edge_details = await edges_api.get_edge(edge_guid)
            if not edge_details:
                return self.format_error(f"Could not get details for edge: {edge_id}")
            
            # Extract appliance name and serial for error messages
            edge_name = edge_details.description or edge_id
            serial_number = edge_details.serial or ""
            
            # Check if platform supports TCO analysis (AWS or Azure only)
            platform = edge_details.build.platform if edge_details.build else None
            if not is_supported_tco_platform(platform):
                return self.format_error(get_unsupported_platform_message(platform, edge_name))
            
            # Extract instance info from EdgeDto (Pydantic model)
            # Machine info contains vm_instance_type, vm_region, ram, cpu_cores
            machine = edge_details.machine
            instance_type = machine.vm_instance_type if machine else None
            region = machine.vm_region if machine else None
            
            # Extract hardware specs for minimum requirements check
            memory_gib = parse_ram_to_gib(machine.ram) if machine else None
            
            # Extract version for smart memory metric selection
            appliance_version = edge_details.build.current if edge_details.build else None
            
            if not instance_type:
                return self.format_error(
                    f"Edge appliance does not have vm_instance_type configured. "
                    f"Edge: {edge_name}. "
                    "Ensure the appliance is deployed in AWS or Azure and has instance type information in the Portal."
                )
            
            # Get utilization metrics using serial number (30 days default)
            utilization = await get_appliance_utilization_metrics(
                telemetry_api, serial_number, time_range_hours, appliance_version
            )
            
            # Check if utilization data was available
            utilization_data_available = utilization.get("data_available", True)
            if not utilization_data_available:
                logger.warning(f"Telemetry data not available for {edge_name} ({serial_number}): {utilization.get('error', 'Unknown error')}")
            
            # Perform TCO analysis
            pricing_client = get_pricing_client()
            analyzer = TCOAnalyzer(pricing_client)
            
            result = await analyzer.analyze_appliance(
                instance_type=instance_type,
                region=region,
                avg_cpu=utilization["avg_cpu"],
                avg_memory=utilization["avg_memory"],
                avg_load=utilization["avg_load"],
                max_cpu=utilization["max_cpu"],
                max_memory=utilization["max_memory"],
                max_load=utilization["max_load"],
                appliance_id=edge_guid,
                appliance_name=edge_name,
                analysis_period_hours=time_range_hours,
                memory_gib=memory_gib,
                utilization_data_available=utilization_data_available,
            )
            
            # Return formatted text report for direct LLM consumption
            text_report = result.to_text_report()
            return [TextContent(type="text", text=text_report)]
            
        except Exception as e:
            logger.error(f"TCO analysis failed: {e}", exc_info=True)
            return self.format_error(f"TCO analysis failed: {str(e)}")


class GetFleetTCOSummaryTool(BaseTool):
    """Tool for analyzing TCO across all Edge Appliances."""
    
    def __init__(self):
        super().__init__(
            name="tco_fleet_summary",
            description="""Get a comprehensive TCO (Total Cost of Ownership) summary for ALL AWS and Azure Nasuni Edge Appliances.

**IMPORTANT: TCO analysis is ONLY available for AWS EC2 and Azure VM Edge Appliances.**
Physical, VMware, or other on-premises appliances are automatically excluded from TCO analysis
as they do not have cloud compute costs. The report will list any excluded appliances.

This tool automatically:
1. Lists all Edge Appliances in your fleet
2. Filters to only AWS EC2 and Azure VM appliances
3. Fetches detailed information (VM instance type, cloud provider, region) for each appliance
4. Validates each appliance against Nasuni minimum requirements (8 vCPUs, 16 GiB RAM)
5. Analyzes historical telemetry (CPU, memory, network) for each appliance
6. Calculates current costs using live cloud pricing APIs
7. Generates right-sizing recommendations based on actual utilization

Returns a detailed report including:
- **Minimum requirements compliance** - flags any appliances below specs
- Per-appliance TCO analysis with instance types and costs
- Total fleet costs (monthly/yearly)
- Potential savings from right-sizing underutilized appliances
- Recommendations for appliances that need upsizing
- Cost breakdown by cloud provider (AWS/Azure)
- List of appliances excluded from analysis (non-cloud platforms)

Analysis uses 30 days of telemetry data by default for a more accurate baseline.
Both average AND peak (maximum) utilization are calculated for each appliance.
Recommendations are based on PEAK utilization to ensure capacity for periodic spikes.

Nasuni Minimum Requirements:
- 8 vCPUs minimum
- 16 GiB RAM minimum  
- 344 GiB total disk (32 OS + 250 cache + 62 CoW)

Use this when asked for:
- "TCO report for all appliances"
- "Cost analysis across my fleet"
- "Find cost optimization opportunities"
- "Which appliances are over/under-provisioned?"
- "Are any appliances below minimum requirements?"

Note: This tool fetches VM instance type from detailed edge data, not the list endpoint."""
        )
    
    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "time_range_hours": {
                    "type": "integer",
                    "description": "Hours of historical data to analyze (default: 720 = 30 days for better baseline)",
                    "default": 720
                },
                "include_details": {
                    "type": "boolean",
                    "description": "Include per-appliance details (default: false)",
                    "default": False
                },
            },
            "required": [],
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        time_range_hours = arguments.get("time_range_hours", 720)
        include_details = arguments.get("include_details", False)
        
        try:
            # Get API clients
            edges_api = await get_edges_api()
            telemetry_api = await get_telemetry_api()
            pricing_client = get_pricing_client()
            analyzer = TCOAnalyzer(pricing_client)
            
            # Get all edges (list endpoint - SimpleEdgeDto, no vm_instance_type)
            edges_response = await edges_api.get_edges()
            if not edges_response or not edges_response.items:
                return self.format_error("No edges found or unable to fetch edges")
            
            # Analyze each edge - need to fetch details for vm_instance_type
            results: List[TCOAnalysisResult] = []
            errors: List[Dict[str, str]] = []
            cloud_appliances: List[Dict[str, str]] = []
            non_cloud_appliances: List[str] = []
            below_minimum_appliances: List[str] = []
            
            for simple_edge in edges_response.items:
                edge_id = simple_edge.id or ""
                edge_name = simple_edge.description or edge_id
                
                try:
                    # Fetch detailed edge info (EdgeDto with machine.vm_instance_type)
                    edge_details = await edges_api.get_edge(edge_id)
                    
                    # Check if platform supports TCO analysis (AWS or Azure only)
                    platform = edge_details.build.platform if edge_details.build else None
                    if not is_supported_tco_platform(platform):
                        # Not a supported cloud platform (physical, VMware, etc.)
                        non_cloud_appliances.append(f"{edge_name} ({platform or 'unknown platform'})")
                        continue
                    
                    machine = edge_details.machine
                    instance_type = machine.vm_instance_type if machine else None
                    region = machine.vm_region if machine else None
                    serial_number = edge_details.serial or ""
                    
                    # Extract hardware specs for minimum requirements check
                    memory_gib = parse_ram_to_gib(machine.ram) if machine else None
                    
                    # Extract version for smart memory metric selection
                    appliance_version = edge_details.build.current if edge_details.build else None
                    
                    if not instance_type:
                        # Supported platform but no VM instance type info
                        non_cloud_appliances.append(f"{edge_name} (no instance type)")
                        continue
                    
                    cloud_appliances.append({
                        "name": edge_name,
                        "instance_type": instance_type,
                        "region": region or "unknown"
                    })
                    
                    # Get utilization (30 days default for better baseline)
                    utilization = await get_appliance_utilization_metrics(
                        telemetry_api, serial_number, time_range_hours, appliance_version
                    )
                    
                    # Check if utilization data was available
                    utilization_data_available = utilization.get("data_available", True)
                    if not utilization_data_available:
                        logger.warning(f"Telemetry data not available for {edge_name} ({serial_number}): {utilization.get('error', 'Unknown error')}")
                    
                    # Analyze
                    result = await analyzer.analyze_appliance(
                        instance_type=instance_type,
                        region=region or "",
                        avg_cpu=utilization["avg_cpu"],
                        avg_memory=utilization["avg_memory"],
                        avg_load=utilization["avg_load"],
                        max_cpu=utilization["max_cpu"],
                        max_memory=utilization["max_memory"],
                        max_load=utilization["max_load"],
                        appliance_id=edge_id,
                        appliance_name=edge_name,
                        analysis_period_hours=time_range_hours,
                        memory_gib=memory_gib,
                        utilization_data_available=utilization_data_available,
                    )
                    results.append(result)
                    
                    # Track appliances below minimum requirements
                    if result.min_requirements_check and not result.min_requirements_check.meets_requirements:
                        below_minimum_appliances.append(edge_name)
                    
                except Exception as e:
                    errors.append({
                        "edge_id": edge_id,
                        "edge_name": edge_name,
                        "error": str(e)
                    })
            
            # Aggregate results
            total_monthly = sum(r.current_monthly_cost for r in results)
            total_yearly = sum(r.current_yearly_cost for r in results)
            
            downsize_candidates = [r for r in results if r.recommendation.action == "downsize"]
            upsize_candidates = [r for r in results if r.recommendation.action == "upsize"]
            optimal = [r for r in results if r.recommendation.action == "optimal"]
            
            potential_savings_monthly = sum(r.recommendation.monthly_savings for r in downsize_candidates)
            potential_savings_yearly = potential_savings_monthly * 12
            
            # Cost by provider
            aws_results = [r for r in results if r.provider == "aws"]
            azure_results = [r for r in results if r.provider == "azure"]
            aws_costs = sum(r.current_monthly_cost for r in aws_results)
            azure_costs = sum(r.current_monthly_cost for r in azure_results)
            
            # Find outliers (appliances with unusual utilization or costs)
            outliers = self._identify_outliers(results)
            
            # Generate text report
            report = self._generate_fleet_report(
                results=results,
                non_cloud_appliances=non_cloud_appliances,
                errors=errors,
                total_monthly=total_monthly,
                total_yearly=total_yearly,
                aws_costs=aws_costs,
                azure_costs=azure_costs,
                aws_count=len(aws_results),
                azure_count=len(azure_results),
                downsize_candidates=downsize_candidates,
                upsize_candidates=upsize_candidates,
                optimal=optimal,
                potential_savings_monthly=potential_savings_monthly,
                potential_savings_yearly=potential_savings_yearly,
                outliers=outliers,
                below_minimum_appliances=below_minimum_appliances,
                time_range_hours=time_range_hours,
                include_details=include_details,
            )
            
            return [TextContent(type="text", text=report)]
            
        except Exception as e:
            logger.error(f"Fleet TCO analysis failed: {e}", exc_info=True)
            return self.format_error(f"Fleet TCO analysis failed: {str(e)}")
    
    def _identify_outliers(self, results: List[TCOAnalysisResult]) -> List[Dict[str, Any]]:
        """Identify appliances with unusual metrics."""
        outliers = []
        
        if len(results) < 2:
            return outliers
        
        # Calculate averages
        avg_cpu = sum(r.avg_cpu_percent for r in results) / len(results)
        avg_memory = sum(r.avg_memory_percent for r in results) / len(results)
        avg_cost = sum(r.current_monthly_cost for r in results) / len(results)
        
        for r in results:
            reasons = []
            
            # High cost outlier (> 2x average)
            if r.current_monthly_cost > avg_cost * 2:
                reasons.append(f"Cost is {r.current_monthly_cost/avg_cost:.1f}x the fleet average")
            
            # Very low CPU utilization (< 10%)
            if r.avg_cpu_percent < 10:
                reasons.append(f"Very low CPU utilization ({r.avg_cpu_percent:.1f}%)")
            
            # Very high CPU utilization (> 90%)
            if r.avg_cpu_percent > 90:
                reasons.append(f"Very high CPU utilization ({r.avg_cpu_percent:.1f}%)")
            
            # Very low memory utilization (< 20%)
            if r.avg_memory_percent < 20:
                reasons.append(f"Very low memory utilization ({r.avg_memory_percent:.1f}%)")
            
            # Very high memory utilization (> 90%)
            if r.avg_memory_percent > 90:
                reasons.append(f"Very high memory utilization ({r.avg_memory_percent:.1f}%)")
            
            # Below minimum requirements (CRITICAL)
            if r.min_requirements_check and not r.min_requirements_check.meets_requirements:
                reasons.append(f"BELOW NASUNI MINIMUM REQUIREMENTS")
            
            if reasons:
                outliers.append({
                    "name": r.appliance_name,
                    "instance_type": r.instance_type,
                    "region": r.region,
                    "monthly_cost": r.current_monthly_cost,
                    "cpu_percent": r.avg_cpu_percent,
                    "memory_percent": r.avg_memory_percent,
                    "reasons": reasons,
                })
        
        return outliers
    
    def _generate_fleet_report(
        self,
        results: List[TCOAnalysisResult],
        non_cloud_appliances: List[str],
        errors: List[Dict[str, str]],
        total_monthly: float,
        total_yearly: float,
        aws_costs: float,
        azure_costs: float,
        aws_count: int,
        azure_count: int,
        downsize_candidates: List[TCOAnalysisResult],
        upsize_candidates: List[TCOAnalysisResult],
        optimal: List[TCOAnalysisResult],
        potential_savings_monthly: float,
        potential_savings_yearly: float,
        outliers: List[Dict[str, Any]],
        below_minimum_appliances: List[str],
        time_range_hours: int,
        include_details: bool,
    ) -> str:
        """Generate a formatted text report for the fleet TCO analysis."""
        lines = []
        
        lines.append("# Fleet Total Cost of Ownership Report")
        lines.append("")
        
        # Data Sources
        lines.append("## Data Sources")
        lines.append("- **Pricing**: Live pricing from Vantage API (AWS) and Azure Retail Prices API")
        lines.append(f"- **Utilization**: Portal Telemetry API (last {time_range_hours} hours / {time_range_hours // 24} days)")
        lines.append("- **Appliance Info**: Portal Edges API (detail endpoint for each appliance)")
        lines.append("")
        
        # Summary
        lines.append("## Summary")
        lines.append(f"- **Cloud Appliances Analyzed**: {len(results)}")
        if non_cloud_appliances:
            lines.append(f"- **Non-Cloud Appliances** (no VM instance type): {len(non_cloud_appliances)}")
        if below_minimum_appliances:
            lines.append(f"- **⚠️ Below Minimum Requirements**: {len(below_minimum_appliances)}")
        if errors:
            lines.append(f"- **Errors**: {len(errors)}")
        lines.append(f"- **Analysis Period**: Last {time_range_hours} hours ({time_range_hours // 24} days)")
        lines.append("")
        
        # Nasuni Minimum Requirements Warning (show FIRST if any violations)
        if below_minimum_appliances:
            lines.append("## ❌ MINIMUM REQUIREMENTS VIOLATIONS")
            lines.append("")
            lines.append("The following appliances are **below Nasuni minimum requirements** and may experience issues:")
            lines.append("")
            lines.append(f"**Required Minimums**: {NASUNI_MIN_REQUIREMENTS.min_vcpus} vCPUs, {NASUNI_MIN_REQUIREMENTS.min_memory_gib} GiB RAM")
            lines.append("")
            for name in below_minimum_appliances:
                # Find the result for this appliance
                result = next((r for r in results if r.appliance_name == name), None)
                if result and result.min_requirements_check:
                    check = result.min_requirements_check
                    lines.append(f"### {name}")
                    lines.append(f"- **Instance**: {result.instance_type}")
                    lines.append(f"- **vCPUs**: {check.actual_vcpus} (required: {check.required_vcpus}) {'❌' if not check.vcpus_ok else '✅'}")
                    lines.append(f"- **Memory**: {check.actual_memory_gib:.1f} GiB (required: {check.required_memory_gib} GiB) {'❌' if not check.memory_ok else '✅'}")
                    for violation in check.violations:
                        lines.append(f"  - ⚠️ {violation}")
                    lines.append("")
            lines.append("**Action Required**: These appliances should be upsized to meet minimum requirements.")
            lines.append("")
        
        # Minimum Requirements Reference
        lines.append("## Nasuni Minimum Requirements Reference")
        lines.append("")
        lines.append("| Spec | Minimum |")
        lines.append("|------|---------|")
        lines.append(f"| vCPUs | {NASUNI_MIN_REQUIREMENTS.min_vcpus} |")
        lines.append(f"| Memory | {NASUNI_MIN_REQUIREMENTS.min_memory_gib} GiB |")
        lines.append(f"| OS Disk | {NASUNI_MIN_REQUIREMENTS.min_os_disk_gib} GiB |")
        lines.append(f"| Cache Disk | {NASUNI_MIN_REQUIREMENTS.min_cache_disk_gib} GiB |")
        lines.append(f"| CoW Disk | {NASUNI_MIN_REQUIREMENTS.min_cow_disk_gib} GiB |")
        lines.append(f"| Total Disk | {NASUNI_MIN_REQUIREMENTS.min_total_disk_gib} GiB |")
        lines.append("")
        
        # Total Costs
        lines.append("## Current Costs")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Total Monthly | ${total_monthly:.2f} |")
        lines.append(f"| Total Yearly | ${total_yearly:.2f} |")
        if aws_count > 0:
            lines.append(f"| AWS ({aws_count} appliances) | ${aws_costs:.2f}/mo |")
        if azure_count > 0:
            lines.append(f"| Azure ({azure_count} appliances) | ${azure_costs:.2f}/mo |")
        lines.append("")
        
        # Outliers (IMPORTANT)
        if outliers:
            lines.append("## ⚠️ Outliers Detected")
            lines.append("")
            for o in outliers:
                lines.append(f"### {o['name']}")
                lines.append(f"- **Instance**: {o['instance_type']} in {o['region']}")
                lines.append(f"- **Monthly Cost**: ${o['monthly_cost']:.2f}")
                lines.append(f"- **CPU**: {o['cpu_percent']:.1f}% | **Memory**: {o['memory_percent']:.1f}%")
                lines.append(f"- **Issues**:")
                for reason in o['reasons']:
                    lines.append(f"  - {reason}")
                lines.append("")
        
        # Optimization Opportunities
        lines.append("## Optimization Opportunities")
        lines.append("")
        lines.append(f"| Category | Count |")
        lines.append(f"|----------|-------|")
        lines.append(f"| ✅ Optimally Sized | {len(optimal)} |")
        lines.append(f"| 💰 Can Downsize (save money) | {len(downsize_candidates)} |")
        lines.append(f"| ⚠️ Should Upsize (performance risk) | {len(upsize_candidates)} |")
        lines.append("")
        
        if potential_savings_monthly > 0:
            lines.append(f"**Potential Savings**: ${potential_savings_monthly:.2f}/month (${potential_savings_yearly:.2f}/year)")
            lines.append("")
        
        # Downsize Recommendations
        if downsize_candidates:
            lines.append("### 💰 Downsize Recommendations")
            lines.append("")
            lines.append("| Appliance | Current | Recommended | Monthly Savings |")
            lines.append("|-----------|---------|-------------|-----------------|")
            for r in downsize_candidates:
                lines.append(f"| {r.appliance_name} | {r.instance_type} | {r.recommendation.recommended_instance} | ${r.recommendation.monthly_savings:.2f} |")
            lines.append("")
        
        # Upsize Recommendations
        if upsize_candidates:
            lines.append("### ⚠️ Upsize Recommendations")
            lines.append("")
            lines.append("| Appliance | Current | Recommended | Reason |")
            lines.append("|-----------|---------|-------------|--------|")
            for r in upsize_candidates:
                lines.append(f"| {r.appliance_name} | {r.instance_type} | {r.recommendation.recommended_instance} | {r.recommendation.reason} |")
            lines.append("")
        
        # Per-appliance details
        if include_details and results:
            lines.append("## Per-Appliance Details")
            lines.append("")
            lines.append("| Appliance | Instance | Region | Monthly | CPU | Memory | Status |")
            lines.append("|-----------|----------|--------|---------|-----|--------|--------|")
            for r in sorted(results, key=lambda x: x.current_monthly_cost, reverse=True):
                status = "✅" if r.recommendation.action == "optimal" else ("💰" if r.recommendation.action == "downsize" else "⚠️")
                lines.append(f"| {r.appliance_name} | {r.instance_type} | {r.region} | ${r.current_monthly_cost:.2f} | {r.avg_cpu_percent:.0f}% | {r.avg_memory_percent:.0f}% | {status} |")
            lines.append("")
        
        # Non-cloud appliances
        if non_cloud_appliances:
            lines.append("## Non-Cloud Appliances")
            lines.append("*These appliances don't have VM instance type information (may be physical appliances):*")
            lines.append("")
            for name in non_cloud_appliances:
                lines.append(f"- {name}")
            lines.append("")
        
        # Errors
        if errors:
            lines.append("## Errors")
            lines.append("")
            for err in errors:
                lines.append(f"- **{err['edge_name']}**: {err['error']}")
            lines.append("")
        
        # Footer
        lines.append("---")
        lines.append(f"*Report generated at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}*")
        lines.append("*Costs assume On-Demand pricing (no Reserved Instances or Savings Plans)*")
        
        return "\n".join(lines)


class GetInstancePricingTool(BaseTool):
    """Tool for looking up cloud instance pricing."""
    
    def __init__(self):
        super().__init__(
            name="tco_get_pricing",
            description="""Get pricing information for a specific cloud instance type.
    
Returns hourly, daily, monthly, and yearly costs for the specified instance type.
Supports both AWS EC2 and Azure VM instance types.

Examples:
- AWS: m5.xlarge, r5.2xlarge, c5.4xlarge
- Azure: Standard_D4s_v3, Standard_E8s_v3"""
        )
    
    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "instance_type": {
                    "type": "string",
                    "description": "Cloud instance type (e.g., 'm5.xlarge' for AWS or 'Standard_D4s_v3' for Azure)"
                },
                "region": {
                    "type": "string",
                    "description": "Cloud region (e.g., 'us-east-1' for AWS or 'eastus' for Azure). Defaults to us-east-1/eastus",
                    "default": ""
                },
                "provider": {
                    "type": "string",
                    "description": "Cloud provider ('aws' or 'azure'). Auto-detected if not specified",
                    "enum": ["aws", "azure", ""],
                    "default": ""
                },
            },
            "required": ["instance_type"],
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        instance_type = arguments.get("instance_type", "")
        region = arguments.get("region", "")
        provider = arguments.get("provider", "")
        
        if not instance_type:
            return self.format_error("instance_type is required")
        
        pricing_client = get_pricing_client()
        
        # Auto-detect provider if not specified
        if not provider:
            if instance_type.startswith("Standard_"):
                provider = "azure"
            else:
                provider = "aws"
        
        # Set default region
        if not region:
            region = "us-east-1" if provider == "aws" else "eastus"
        
        try:
            if provider == "aws":
                pricing = await pricing_client.get_aws_pricing(instance_type, region)
            else:
                pricing = await pricing_client.get_azure_pricing(instance_type, region)
            
            if not pricing:
                return self.format_error(
                    f"Could not find pricing for {instance_type} in region {region}. "
                    "Check that the instance type is valid and try a common region."
                )
            
            # Get family info for right-sizing options
            family = pricing_client.get_instance_family(instance_type, provider)
            smaller = pricing_client.get_smaller_instance(instance_type, provider)
            larger = pricing_client.get_larger_instance(instance_type, provider)
            
            output = {
                "instance_type": instance_type,
                "provider": provider,
                "region": region,
                "specs": {
                    "vcpus": pricing.vcpus,
                    "memory_gb": pricing.memory_gb,
                },
                "pricing": {
                    "hourly": f"${pricing.hourly_price:.4f}",
                    "daily": f"${pricing.daily_price:.2f}",
                    "monthly": f"${pricing.monthly_price:.2f}",
                    "yearly": f"${pricing.yearly_price:.2f}",
                },
                "instance_family": family,
                "alternatives": {
                    "smaller_option": smaller,
                    "larger_option": larger,
                },
            }
            
            return [TextContent(type="text", text=json.dumps(output, indent=2))]
            
        except Exception as e:
            logger.error(f"Pricing lookup failed: {e}", exc_info=True)
            return self.format_error(f"Pricing lookup failed: {str(e)}")


class CompareInstancesTool(BaseTool):
    """Tool for comparing pricing between instance types."""
    
    def __init__(self):
        super().__init__(
            name="tco_compare_instances",
            description="""Compare pricing between two or more cloud instance types.
    
Useful for evaluating right-sizing options or comparing across providers.
Shows cost differences and percentage savings."""
        )
    
    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "instances": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of instance types to compare (e.g., ['m5.xlarge', 'm5.large'])"
                },
                "region": {
                    "type": "string",
                    "description": "Cloud region for pricing",
                    "default": ""
                },
            },
            "required": ["instances"],
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        instances = arguments.get("instances", [])
        region = arguments.get("region", "")
        
        if not instances or len(instances) < 2:
            return self.format_error("At least 2 instance types are required for comparison")
        
        pricing_client = get_pricing_client()
        results = []
        
        for instance_type in instances:
            # Detect provider
            provider = "azure" if instance_type.startswith("Standard_") else "aws"
            inst_region = region or ("us-east-1" if provider == "aws" else "eastus")
            
            if provider == "aws":
                pricing = await pricing_client.get_aws_pricing(instance_type, inst_region)
            else:
                pricing = await pricing_client.get_azure_pricing(instance_type, inst_region)
            
            if pricing:
                results.append({
                    "instance_type": instance_type,
                    "provider": provider,
                    "vcpus": pricing.vcpus,
                    "memory_gb": pricing.memory_gb,
                    "hourly": pricing.hourly_price,
                    "monthly": pricing.monthly_price,
                    "yearly": pricing.yearly_price,
                })
        
        if not results:
            return self.format_error("Could not find pricing for any of the specified instances")
        
        # Sort by monthly cost
        results.sort(key=lambda x: x["monthly"])
        
        # Calculate comparisons
        baseline = results[0]
        comparisons = []
        
        for r in results:
            diff_monthly = r["monthly"] - baseline["monthly"]
            diff_yearly = r["yearly"] - baseline["yearly"]
            pct_diff = ((r["monthly"] - baseline["monthly"]) / baseline["monthly"] * 100) if baseline["monthly"] > 0 else 0
            
            comparisons.append({
                "instance_type": r["instance_type"],
                "provider": r["provider"],
                "specs": f"{r['vcpus']} vCPUs / {r['memory_gb']} GB",
                "monthly_cost": f"${r['monthly']:.2f}",
                "yearly_cost": f"${r['yearly']:.2f}",
                "vs_cheapest": {
                    "monthly_diff": f"+${diff_monthly:.2f}" if diff_monthly > 0 else f"${diff_monthly:.2f}",
                    "yearly_diff": f"+${diff_yearly:.2f}" if diff_yearly > 0 else f"${diff_yearly:.2f}",
                    "percent_diff": f"+{pct_diff:.1f}%" if pct_diff > 0 else f"{pct_diff:.1f}%",
                },
            })
        
        output = {
            "comparison": comparisons,
            "cheapest": baseline["instance_type"],
            "most_expensive": results[-1]["instance_type"],
            "max_savings": {
                "monthly": f"${results[-1]['monthly'] - baseline['monthly']:.2f}",
                "yearly": f"${results[-1]['yearly'] - baseline['yearly']:.2f}",
            },
        }
        
        return [TextContent(type="text", text=json.dumps(output, indent=2))]


# =============================================================================
# TOOL REGISTRATION
# =============================================================================

def get_tco_tools() -> List[BaseTool]:
    """Get all TCO analysis tools."""
    return [
        GetApplianceTCOTool(),
        GetFleetTCOSummaryTool(),
        GetInstancePricingTool(),
        CompareInstancesTool(),
    ]
