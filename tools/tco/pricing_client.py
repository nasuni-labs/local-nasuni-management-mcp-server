#!/usr/bin/env python3
"""Cloud pricing client for AWS EC2 and Azure VMs.

This module provides clients for fetching real-time cloud pricing data
from AWS and Azure pricing APIs.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx

from config.logging_setup import get_logger

logger = get_logger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class InstancePricing:
    """Pricing information for a cloud instance type."""
    provider: str  # "aws" or "azure"
    instance_type: str  # e.g., "m5.xlarge" or "Standard_D4s_v3"
    region: str  # e.g., "us-east-1" or "eastus"
    vcpus: int
    memory_gb: float
    hourly_price: float  # USD per hour
    monthly_price: float  # USD per month (730 hours)
    yearly_price: float  # USD per year
    price_unit: str = "USD"
    operating_system: str = "Linux"
    tenancy: str = "Shared"
    last_updated: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def daily_price(self) -> float:
        return self.hourly_price * 24
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "instance_type": self.instance_type,
            "region": self.region,
            "vcpus": self.vcpus,
            "memory_gb": self.memory_gb,
            "hourly_price": self.hourly_price,
            "daily_price": self.daily_price,
            "monthly_price": self.monthly_price,
            "yearly_price": self.yearly_price,
            "price_unit": self.price_unit,
            "operating_system": self.operating_system,
        }


@dataclass
class InstanceFamily:
    """A family of related instance types for right-sizing recommendations."""
    provider: str
    family_name: str  # e.g., "m5", "Standard_D"
    instances: List[InstancePricing] = field(default_factory=list)
    
    def get_smaller_instance(self, current: str) -> Optional[InstancePricing]:
        """Get the next smaller instance in this family."""
        sorted_instances = sorted(self.instances, key=lambda x: x.vcpus)
        for i, inst in enumerate(sorted_instances):
            if inst.instance_type == current and i > 0:
                return sorted_instances[i - 1]
        return None
    
    def get_larger_instance(self, current: str) -> Optional[InstancePricing]:
        """Get the next larger instance in this family."""
        sorted_instances = sorted(self.instances, key=lambda x: x.vcpus)
        for i, inst in enumerate(sorted_instances):
            if inst.instance_type == current and i < len(sorted_instances) - 1:
                return sorted_instances[i + 1]
        return None


# =============================================================================
# AWS PRICING DATA (STATIC FALLBACK)
# =============================================================================

# Common AWS EC2 instance types used by Nasuni with approximate pricing
# Prices are for Linux, On-Demand, US-East-1 region
AWS_INSTANCE_PRICING: Dict[str, Dict[str, Any]] = {
    # M5 family (General Purpose)
    "m5.large": {"vcpus": 2, "memory_gb": 8, "hourly": 0.096},
    "m5.xlarge": {"vcpus": 4, "memory_gb": 16, "hourly": 0.192},
    "m5.2xlarge": {"vcpus": 8, "memory_gb": 32, "hourly": 0.384},
    "m5.4xlarge": {"vcpus": 16, "memory_gb": 64, "hourly": 0.768},
    "m5.8xlarge": {"vcpus": 32, "memory_gb": 128, "hourly": 1.536},
    "m5.12xlarge": {"vcpus": 48, "memory_gb": 192, "hourly": 2.304},
    "m5.16xlarge": {"vcpus": 64, "memory_gb": 256, "hourly": 3.072},
    
    # M5a family (General Purpose - AMD, ~10% cheaper than M5)
    "m5a.large": {"vcpus": 2, "memory_gb": 8, "hourly": 0.086},
    "m5a.xlarge": {"vcpus": 4, "memory_gb": 16, "hourly": 0.172},
    "m5a.2xlarge": {"vcpus": 8, "memory_gb": 32, "hourly": 0.344},
    "m5a.4xlarge": {"vcpus": 16, "memory_gb": 64, "hourly": 0.688},
    "m5a.8xlarge": {"vcpus": 32, "memory_gb": 128, "hourly": 1.376},
    "m5a.12xlarge": {"vcpus": 48, "memory_gb": 192, "hourly": 2.064},
    "m5a.16xlarge": {"vcpus": 64, "memory_gb": 256, "hourly": 2.752},
    
    # M6i family (Latest General Purpose)
    "m6i.large": {"vcpus": 2, "memory_gb": 8, "hourly": 0.096},
    "m6i.xlarge": {"vcpus": 4, "memory_gb": 16, "hourly": 0.192},
    "m6i.2xlarge": {"vcpus": 8, "memory_gb": 32, "hourly": 0.384},
    "m6i.4xlarge": {"vcpus": 16, "memory_gb": 64, "hourly": 0.768},
    "m6i.8xlarge": {"vcpus": 32, "memory_gb": 128, "hourly": 1.536},
    
    # R5 family (Memory Optimized)
    "r5.large": {"vcpus": 2, "memory_gb": 16, "hourly": 0.126},
    "r5.xlarge": {"vcpus": 4, "memory_gb": 32, "hourly": 0.252},
    "r5.2xlarge": {"vcpus": 8, "memory_gb": 64, "hourly": 0.504},
    "r5.4xlarge": {"vcpus": 16, "memory_gb": 128, "hourly": 1.008},
    "r5.8xlarge": {"vcpus": 32, "memory_gb": 256, "hourly": 2.016},
    
    # C5 family (Compute Optimized)
    "c5.large": {"vcpus": 2, "memory_gb": 4, "hourly": 0.085},
    "c5.xlarge": {"vcpus": 4, "memory_gb": 8, "hourly": 0.170},
    "c5.2xlarge": {"vcpus": 8, "memory_gb": 16, "hourly": 0.340},
    "c5.4xlarge": {"vcpus": 16, "memory_gb": 32, "hourly": 0.680},
    "c5.9xlarge": {"vcpus": 36, "memory_gb": 72, "hourly": 1.530},
}

# AWS region display names and pricing multipliers
AWS_REGIONS: Dict[str, Dict[str, Any]] = {
    "us-east-1": {"name": "US East (N. Virginia)", "multiplier": 1.0},
    "us-east-2": {"name": "US East (Ohio)", "multiplier": 1.0},
    "us-west-1": {"name": "US West (N. California)", "multiplier": 1.10},
    "us-west-2": {"name": "US West (Oregon)", "multiplier": 1.0},
    "eu-west-1": {"name": "Europe (Ireland)", "multiplier": 1.05},
    "eu-west-2": {"name": "Europe (London)", "multiplier": 1.10},
    "eu-central-1": {"name": "Europe (Frankfurt)", "multiplier": 1.08},
    "ap-northeast-1": {"name": "Asia Pacific (Tokyo)", "multiplier": 1.15},
    "ap-southeast-1": {"name": "Asia Pacific (Singapore)", "multiplier": 1.10},
    "ap-southeast-2": {"name": "Asia Pacific (Sydney)", "multiplier": 1.12},
}

# =============================================================================
# AZURE PRICING DATA (STATIC FALLBACK)
# =============================================================================

AZURE_INSTANCE_PRICING: Dict[str, Dict[str, Any]] = {
    # Dsv3 series (General Purpose)
    "Standard_D2s_v3": {"vcpus": 2, "memory_gb": 8, "hourly": 0.096},
    "Standard_D4s_v3": {"vcpus": 4, "memory_gb": 16, "hourly": 0.192},
    "Standard_D8s_v3": {"vcpus": 8, "memory_gb": 32, "hourly": 0.384},
    "Standard_D16s_v3": {"vcpus": 16, "memory_gb": 64, "hourly": 0.768},
    "Standard_D32s_v3": {"vcpus": 32, "memory_gb": 128, "hourly": 1.536},
    "Standard_D48s_v3": {"vcpus": 48, "memory_gb": 192, "hourly": 2.304},
    "Standard_D64s_v3": {"vcpus": 64, "memory_gb": 256, "hourly": 3.072},
    
    # Dsv4 series (Latest General Purpose)
    "Standard_D2s_v4": {"vcpus": 2, "memory_gb": 8, "hourly": 0.096},
    "Standard_D4s_v4": {"vcpus": 4, "memory_gb": 16, "hourly": 0.192},
    "Standard_D8s_v4": {"vcpus": 8, "memory_gb": 32, "hourly": 0.384},
    "Standard_D16s_v4": {"vcpus": 16, "memory_gb": 64, "hourly": 0.768},
    "Standard_D32s_v4": {"vcpus": 32, "memory_gb": 128, "hourly": 1.536},
    
    # Esv3 series (Memory Optimized)
    "Standard_E2s_v3": {"vcpus": 2, "memory_gb": 16, "hourly": 0.126},
    "Standard_E4s_v3": {"vcpus": 4, "memory_gb": 32, "hourly": 0.252},
    "Standard_E8s_v3": {"vcpus": 8, "memory_gb": 64, "hourly": 0.504},
    "Standard_E16s_v3": {"vcpus": 16, "memory_gb": 128, "hourly": 1.008},
    "Standard_E32s_v3": {"vcpus": 32, "memory_gb": 256, "hourly": 2.016},
    
    # Fsv2 series (Compute Optimized)
    "Standard_F2s_v2": {"vcpus": 2, "memory_gb": 4, "hourly": 0.085},
    "Standard_F4s_v2": {"vcpus": 4, "memory_gb": 8, "hourly": 0.169},
    "Standard_F8s_v2": {"vcpus": 8, "memory_gb": 16, "hourly": 0.338},
    "Standard_F16s_v2": {"vcpus": 16, "memory_gb": 32, "hourly": 0.677},
    "Standard_F32s_v2": {"vcpus": 32, "memory_gb": 64, "hourly": 1.353},
}

AZURE_REGIONS: Dict[str, Dict[str, Any]] = {
    "eastus": {"name": "East US", "multiplier": 1.0},
    "eastus2": {"name": "East US 2", "multiplier": 1.0},
    "westus": {"name": "West US", "multiplier": 1.05},
    "westus2": {"name": "West US 2", "multiplier": 1.0},
    "westeurope": {"name": "West Europe", "multiplier": 1.05},
    "northeurope": {"name": "North Europe", "multiplier": 1.03},
    "uksouth": {"name": "UK South", "multiplier": 1.08},
    "japaneast": {"name": "Japan East", "multiplier": 1.15},
    "southeastasia": {"name": "Southeast Asia", "multiplier": 1.10},
    "australiaeast": {"name": "Australia East", "multiplier": 1.12},
}


# =============================================================================
# CLOUD PRICING CLIENT
# =============================================================================

class CloudPricingClient:
    """Client for fetching cloud pricing from AWS and Azure."""
    
    HOURS_PER_MONTH = 730  # Average hours per month
    HOURS_PER_YEAR = 8760
    
    # Cache settings
    CACHE_TTL_HOURS = 24
    
    def __init__(self):
        self._aws_cache: Dict[str, InstancePricing] = {}
        self._azure_cache: Dict[str, InstancePricing] = {}
        self._cache_timestamp: Optional[datetime] = None
    
    def _is_cache_valid(self) -> bool:
        """Check if the price cache is still valid."""
        if not self._cache_timestamp:
            return False
        age = datetime.utcnow() - self._cache_timestamp
        return age < timedelta(hours=self.CACHE_TTL_HOURS)
    
    def _normalize_aws_region(self, region: str) -> str:
        """Normalize AWS availability zone to region.
        
        AWS AZs are region + letter (e.g., us-east-2a -> us-east-2).
        """
        if not region:
            return "us-east-1"
        # Remove trailing letter if it's an AZ
        import re
        match = re.match(r"^([a-z]{2}-[a-z]+-\d+)[a-z]?$", region)
        if match:
            return match.group(1)
        return region
    
    # =========================================================================
    # AWS PRICING
    # =========================================================================
    
    async def get_aws_pricing(
        self,
        instance_type: str,
        region: str = "us-east-1",
    ) -> Optional[InstancePricing]:
        """Get pricing for an AWS EC2 instance type.
        
        Args:
            instance_type: EC2 instance type (e.g., "m5.xlarge")
            region: AWS region or availability zone (e.g., "us-east-1" or "us-east-2a")
            
        Returns:
            InstancePricing object or None if not found
        """
        # Normalize AZ to region
        region = self._normalize_aws_region(region)
        
        cache_key = f"aws:{instance_type}:{region}"
        
        # Check cache first
        if cache_key in self._aws_cache and self._is_cache_valid():
            return self._aws_cache[cache_key]
        
        # Try live API first, then fall back to static data
        pricing = await self._fetch_aws_live_pricing(instance_type, region)
        
        if not pricing:
            logger.info(f"Live AWS pricing unavailable for {instance_type} in {region}, using static data")
            pricing = self._get_aws_static_pricing(instance_type, region)
        
        if pricing:
            self._aws_cache[cache_key] = pricing
            self._cache_timestamp = datetime.utcnow()
            
        return pricing
    
    def _get_aws_static_pricing(
        self,
        instance_type: str,
        region: str,
    ) -> Optional[InstancePricing]:
        """Get AWS pricing from static data."""
        if instance_type not in AWS_INSTANCE_PRICING:
            logger.warning(f"Unknown AWS instance type: {instance_type}")
            return None
        
        instance_data = AWS_INSTANCE_PRICING[instance_type]
        region_data = AWS_REGIONS.get(region, {"multiplier": 1.0})
        
        hourly = instance_data["hourly"] * region_data["multiplier"]
        
        return InstancePricing(
            provider="aws",
            instance_type=instance_type,
            region=region,
            vcpus=instance_data["vcpus"],
            memory_gb=instance_data["memory_gb"],
            hourly_price=round(hourly, 4),
            monthly_price=round(hourly * self.HOURS_PER_MONTH, 2),
            yearly_price=round(hourly * self.HOURS_PER_YEAR, 2),
        )
    
    async def _fetch_aws_live_pricing(
        self,
        instance_type: str,
        region: str = "us-east-1",
    ) -> Optional[InstancePricing]:
        """Fetch live AWS pricing using the AWS Bulk API with targeted requests.
        
        Uses the savingsPlans offer file which is smaller and contains instance info,
        or falls back to ec2 spot pricing API which has current on-demand prices.
        """
        # Map region to location name for AWS API
        region_location_map = {
            "us-east-1": "US East (N. Virginia)",
            "us-east-2": "US East (Ohio)",
            "us-west-1": "US West (N. California)",
            "us-west-2": "US West (Oregon)",
            "eu-west-1": "Europe (Ireland)",
            "eu-west-2": "Europe (London)",
            "eu-west-3": "Europe (Paris)",
            "eu-central-1": "Europe (Frankfurt)",
            "eu-north-1": "Europe (Stockholm)",
            "ap-northeast-1": "Asia Pacific (Tokyo)",
            "ap-northeast-2": "Asia Pacific (Seoul)",
            "ap-southeast-1": "Asia Pacific (Singapore)",
            "ap-southeast-2": "Asia Pacific (Sydney)",
            "ap-south-1": "Asia Pacific (Mumbai)",
            "sa-east-1": "South America (Sao Paulo)",
            "ca-central-1": "Canada (Central)",
        }
        
        location = region_location_map.get(region)
        if not location:
            logger.warning(f"Unknown AWS region: {region}")
            return None
        
        # Use the AWS Price List Query API (smaller, filtered responses)
        # This endpoint returns JSON for specific product queries
        url = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/index.json"
        
        try:
            # First, try to get instance specs from a smaller metadata file
            specs = self._get_aws_instance_specs(instance_type)
            
            # Use the EC2 describe-spot-price-history trick - spot prices track on-demand
            # Actually, let's use a different approach: query the savings plans data
            # which has instance family info
            
            # For now, use a curated API that provides EC2 pricing
            # AWS doesn't have a simple REST API, so we'll use ec2instances.info
            ec2_info_url = f"https://instances.vantage.sh/instances.json"
            
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(ec2_info_url)
                response.raise_for_status()
                
                instances = response.json()
                
                for inst in instances:
                    if inst.get("instance_type") == instance_type:
                        # Found it! Get the pricing for this region
                        pricing_data = inst.get("pricing", {}).get(region, {}).get("linux", {})
                        ondemand = pricing_data.get("ondemand")
                        
                        if ondemand:
                            hourly = float(ondemand)
                            vcpus = int(inst.get("vCPU", 0))
                            memory_raw = inst.get("memory", 0)
                            # Parse memory - can be string like "16 GiB" or numeric
                            if isinstance(memory_raw, str):
                                memory_gb = float(memory_raw.replace(" GiB", "").replace(",", ""))
                            else:
                                memory_gb = float(memory_raw)
                            
                            logger.info(f"Live AWS pricing for {instance_type} in {region}: ${hourly}/hr")
                            
                            return InstancePricing(
                                provider="aws",
                                instance_type=instance_type,
                                region=region,
                                vcpus=vcpus,
                                memory_gb=memory_gb,
                                hourly_price=round(hourly, 4),
                                monthly_price=round(hourly * self.HOURS_PER_MONTH, 2),
                                yearly_price=round(hourly * self.HOURS_PER_YEAR, 2),
                            )
                
                logger.warning(f"Instance type {instance_type} not found in live AWS pricing data")
                return None
                
        except Exception as e:
            logger.warning(f"Failed to fetch AWS live pricing: {e}")
            return None
    
    def _get_aws_instance_specs(self, instance_type: str) -> Dict[str, Any]:
        """Get AWS instance specs from static data or instance type parsing."""
        if instance_type in AWS_INSTANCE_PRICING:
            return AWS_INSTANCE_PRICING[instance_type]
        
        # Try to infer specs from instance type name
        # Format: family.size (e.g., m5.xlarge, r6i.2xlarge)
        size_vcpu_map = {
            "nano": 1, "micro": 1, "small": 1, "medium": 1,
            "large": 2, "xlarge": 4, "2xlarge": 8, "4xlarge": 16,
            "8xlarge": 32, "12xlarge": 48, "16xlarge": 64, "24xlarge": 96,
            "metal": 96,
        }
        
        parts = instance_type.split(".")
        if len(parts) == 2:
            size = parts[1]
            vcpus = size_vcpu_map.get(size, 4)
            # Memory varies by family, default to 4GB per vCPU
            return {"vcpus": vcpus, "memory_gb": vcpus * 4}
        
        return {"vcpus": 4, "memory_gb": 16}
    
    # =========================================================================
    # AZURE PRICING
    # =========================================================================
    
    async def get_azure_pricing(
        self,
        instance_type: str,
        region: str = "eastus",
    ) -> Optional[InstancePricing]:
        """Get pricing for an Azure VM instance type.
        
        Args:
            instance_type: Azure VM size (e.g., "Standard_D4s_v3")
            region: Azure region (e.g., "eastus")
            
        Returns:
            InstancePricing object or None if not found
        """
        cache_key = f"azure:{instance_type}:{region}"
        
        # Check cache first
        if cache_key in self._azure_cache and self._is_cache_valid():
            return self._azure_cache[cache_key]
        
        # Try live API first, fall back to static
        pricing = await self.fetch_azure_live_pricing(instance_type, region)
        
        if not pricing:
            pricing = self._get_azure_static_pricing(instance_type, region)
        
        if pricing:
            self._azure_cache[cache_key] = pricing
            
        return pricing
    
    def _get_azure_static_pricing(
        self,
        instance_type: str,
        region: str,
    ) -> Optional[InstancePricing]:
        """Get Azure pricing from static data."""
        if instance_type not in AZURE_INSTANCE_PRICING:
            logger.warning(f"Unknown Azure instance type: {instance_type}")
            return None
        
        instance_data = AZURE_INSTANCE_PRICING[instance_type]
        region_data = AZURE_REGIONS.get(region, {"multiplier": 1.0})
        
        hourly = instance_data["hourly"] * region_data["multiplier"]
        
        return InstancePricing(
            provider="azure",
            instance_type=instance_type,
            region=region,
            vcpus=instance_data["vcpus"],
            memory_gb=instance_data["memory_gb"],
            hourly_price=round(hourly, 4),
            monthly_price=round(hourly * self.HOURS_PER_MONTH, 2),
            yearly_price=round(hourly * self.HOURS_PER_YEAR, 2),
        )
    
    async def fetch_azure_live_pricing(
        self,
        instance_type: str,
        region: str = "eastus",
    ) -> Optional[InstancePricing]:
        """Fetch live Azure pricing from the Azure Retail Prices API.
        
        Azure Retail Prices API: https://prices.azure.com/api/retail/prices
        This is a public API that doesn't require authentication.
        """
        base_url = "https://prices.azure.com/api/retail/prices"
        
        # Build OData filter query
        # We need to filter for:
        # - Specific SKU (armSkuName)
        # - Specific region (armRegionName) 
        # - Consumption/PayAsYouGo pricing (not reserved)
        # - Virtual Machines service
        # - Non-Spot, Non-Low Priority
        filter_query = (
            f"armRegionName eq '{region}' and "
            f"armSkuName eq '{instance_type}' and "
            f"priceType eq 'Consumption' and "
            f"serviceFamily eq 'Compute'"
        )
        
        params = {
            "$filter": filter_query,
        }
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(base_url, params=params)
                response.raise_for_status()
                
                data = response.json()
                items = data.get("Items", [])
                
                # Find the Linux hourly price (exclude Windows, Spot, Low Priority)
                for item in items:
                    product_name = item.get("productName", "")
                    meter_name = item.get("meterName", "")
                    
                    # Skip Windows, Spot, and Low Priority
                    if any(skip in product_name for skip in ["Windows", "Spot", "Low Priority"]):
                        continue
                    if any(skip in meter_name for skip in ["Spot", "Low Priority"]):
                        continue
                    
                    # Must be hourly pricing
                    if item.get("unitOfMeasure") != "1 Hour":
                        continue
                    
                    hourly = item.get("retailPrice", 0)
                    if hourly <= 0:
                        continue
                    
                    # Get vCPUs and memory from static data or parse from SKU
                    vcpus, memory_gb = self._get_azure_instance_specs(instance_type)
                    
                    logger.info(f"Live Azure pricing for {instance_type} in {region}: ${hourly}/hr")
                    
                    return InstancePricing(
                        provider="azure",
                        instance_type=instance_type,
                        region=region,
                        vcpus=vcpus,
                        memory_gb=memory_gb,
                        hourly_price=round(hourly, 4),
                        monthly_price=round(hourly * self.HOURS_PER_MONTH, 2),
                        yearly_price=round(hourly * self.HOURS_PER_YEAR, 2),
                    )
                
                logger.debug(f"Instance type {instance_type} not found in Azure API for region {region}")
                return None
                
        except Exception as e:
            logger.warning(f"Failed to fetch Azure live pricing: {e}")
            return None
    
    def _get_azure_instance_specs(self, instance_type: str) -> Tuple[int, float]:
        """Get Azure instance vCPUs and memory from static data or parsing.
        
        Returns:
            Tuple of (vcpus, memory_gb)
        """
        if instance_type in AZURE_INSTANCE_PRICING:
            data = AZURE_INSTANCE_PRICING[instance_type]
            return data["vcpus"], data["memory_gb"]
        
        # Try to parse from instance type name
        # Format: Standard_D4s_v3 -> D4 means ~4 vCPUs (varies by series)
        import re
        match = re.search(r"_([A-Z]+)(\d+)", instance_type)
        if match:
            series = match.group(1)
            size_num = int(match.group(2))
            
            # Memory ratios vary by series
            memory_ratios = {
                "D": 4,   # Dsv3: 4 GB per vCPU
                "E": 8,   # Esv3: 8 GB per vCPU (memory optimized)
                "F": 2,   # Fsv2: 2 GB per vCPU (compute optimized)
                "M": 8,   # M-series: high memory
                "L": 8,   # Lsv2: storage optimized
            }
            ratio = memory_ratios.get(series[0], 4)
            return size_num, size_num * ratio
        
        return 4, 16  # Default fallback
    
    # =========================================================================
    # INSTANCE FAMILY HELPERS
    # =========================================================================
    
    def get_instance_family(self, instance_type: str, provider: str) -> str:
        """Extract the instance family from an instance type.
        
        Examples:
            - m5.xlarge -> m5
            - Standard_D4s_v3 -> Standard_Ds_v3
        """
        if provider == "aws":
            # AWS format: family.size (e.g., m5.xlarge)
            return instance_type.split(".")[0] if "." in instance_type else instance_type
        elif provider == "azure":
            # Azure format: Standard_D4s_v3 -> Standard_Ds_v3
            # Remove the numeric portion
            import re
            match = re.match(r"(Standard_[A-Z]+)\d+(.+)", instance_type)
            if match:
                return f"{match.group(1)}{match.group(2)}"
            return instance_type
        return instance_type
    
    def get_family_instances(
        self,
        family: str,
        provider: str,
    ) -> List[Dict[str, Any]]:
        """Get all instances in a family, sorted by size."""
        if provider == "aws":
            instances = [
                {"type": k, **v}
                for k, v in AWS_INSTANCE_PRICING.items()
                if k.startswith(f"{family}.")
            ]
        elif provider == "azure":
            # For Azure, match the family pattern
            import re
            instances = []
            for k, v in AZURE_INSTANCE_PRICING.items():
                inst_family = self.get_instance_family(k, "azure")
                if inst_family == family:
                    instances.append({"type": k, **v})
        else:
            instances = []
        
        # Sort by vCPUs
        return sorted(instances, key=lambda x: x.get("vcpus", 0))
    
    def get_smaller_instance(
        self,
        instance_type: str,
        provider: str,
    ) -> Optional[str]:
        """Get the next smaller instance in the same family."""
        family = self.get_instance_family(instance_type, provider)
        instances = self.get_family_instances(family, provider)
        
        for i, inst in enumerate(instances):
            if inst["type"] == instance_type and i > 0:
                return instances[i - 1]["type"]
        return None
    
    def get_larger_instance(
        self,
        instance_type: str,
        provider: str,
    ) -> Optional[str]:
        """Get the next larger instance in the same family."""
        family = self.get_instance_family(instance_type, provider)
        instances = self.get_family_instances(family, provider)
        
        for i, inst in enumerate(instances):
            if inst["type"] == instance_type and i < len(instances) - 1:
                return instances[i + 1]["type"]
        return None


# Singleton instance
_pricing_client: Optional[CloudPricingClient] = None


def get_pricing_client() -> CloudPricingClient:
    """Get the singleton pricing client instance."""
    global _pricing_client
    if _pricing_client is None:
        _pricing_client = CloudPricingClient()
    return _pricing_client
