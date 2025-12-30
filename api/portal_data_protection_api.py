#!/usr/bin/env python3
"""Portal API client for data protection telemetry."""

import sys
from typing import Dict, Any, List
from api.portal_base_client import PortalBaseAPIClient
from models.data_protection import DataProtectionSnapshot, DataProtectionAnalysis
from config.logging_setup import get_logger

logger = get_logger(__name__)


class PortalDataProtectionAPIClient(PortalBaseAPIClient):
    """Client for Portal data protection telemetry endpoints."""
    
    async def get_volume_data_protection(
        self,
        volume_guid: str,
        serial_numbers: List[str],
        period: str = "PT3H",
        smart_sampling: bool = True,
        chart_width: int = 1000
    ) -> Dict[str, Any]:
        """
        Get data protection telemetry for a volume.
        
        Note: Despite the endpoint name 'data_propagation_raw', this actually provides
        comprehensive data PROTECTION metrics including snapshot timing, file counts,
        protection times, and OUD (Oldest Unprotected Data).
        
        Args:
            volume_guid: Volume GUID (e.g., "cee7d269-e995-4dcf-ade3-5bc6bbffbe5a_29")
            serial_numbers: List of appliance serial numbers (NMC serial numbers)
            period: ISO 8601 duration (default: PT3H = 3 hours)
            smart_sampling: Reduce data points while preserving trends (default: True)
            chart_width: Chart width parameter (default: 1000)
            
        Returns:
            Dict with metadata and items array containing protection snapshots
        """
        logger.info(f"Fetching data protection for volume {volume_guid}")
        logger.debug(f"Serial numbers: {serial_numbers}, Period: {period}")
        
        endpoint = f"/telemetry/volumes/{volume_guid}/data_propagation_raw"
        
        payload = {
            "serial_numbers": serial_numbers,
            "period": period,
            "chart_width": chart_width,
            "smart_sampling": smart_sampling
        }
        
        logger.debug(f"Request payload: {payload}")
        
        response = await self.post(endpoint, json=payload)
        
        if "error" not in response:
            items_count = len(response.get("items", []))
            logger.info(f"Retrieved {items_count} protection snapshots")
        
        return response
    
    async def get_volume_data_protection_analysis(
        self,
        volume_guid: str,
        serial_numbers: List[str],
        period: str = "PT3H",
        smart_sampling: bool = True
    ) -> DataProtectionAnalysis:
        """
        Get data protection with comprehensive analysis.
        
        Returns:
            DataProtectionAnalysis with statistics and insights
        """
        response = await self.get_volume_data_protection(
            volume_guid=volume_guid,
            serial_numbers=serial_numbers,
            period=period,
            smart_sampling=smart_sampling
        )
        
        if "error" in response:
            logger.error(f"Error fetching protection data: {response['error']}")
            return DataProtectionAnalysis([], {})
        
        # Parse snapshots
        snapshots = []
        for item in response.get("items", []):
            try:
                snapshots.append(DataProtectionSnapshot(item))
            except Exception as e:
                logger.warning(f"Failed to parse snapshot: {e}")
        
        metadata = response.get("metadata", {})
        
        logger.info(f"Parsed {len(snapshots)} protection snapshots")
        return DataProtectionAnalysis(snapshots, metadata)
    
    async def test_connection(self) -> bool:
        """Test the Portal API connection."""
        try:
            authenticated = await self._ensure_authenticated()
            return authenticated
        except Exception:
            return False