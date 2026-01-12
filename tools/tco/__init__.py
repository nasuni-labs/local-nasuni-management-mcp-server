"""Total Cost of Ownership (TCO) tools for Nasuni Edge appliances.

This package provides tools for:
- Fetching cloud pricing (AWS EC2, Azure VMs)
- Analyzing appliance utilization
- Recommending right-sizing optimizations
- Calculating cost savings
"""

from tools.tco.pricing_client import (
    CloudPricingClient,
    InstancePricing,
    get_pricing_client,
)
from tools.tco.tco_tools import (
    GetApplianceTCOTool,
    GetFleetTCOSummaryTool,
    GetInstancePricingTool,
    CompareInstancesTool,
    TCOAnalyzer,
    get_tco_tools,
)

__all__ = [
    # Pricing client
    "CloudPricingClient",
    "InstancePricing",
    "get_pricing_client",
    # Tools
    "GetApplianceTCOTool",
    "GetFleetTCOSummaryTool",
    "GetInstancePricingTool",
    "CompareInstancesTool",
    "TCOAnalyzer",
    "get_tco_tools",
]
