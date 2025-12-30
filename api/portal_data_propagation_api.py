#!/usr/bin/env python3
"""Portal API client for data propagation (sync timing) telemetry."""

import sys
from typing import Dict, Any, List
from api.portal_base_client import PortalBaseAPIClient
from models.data_propagation import DataPropagationEvent, DataPropagationAnalysis
from config.logging_setup import get_logger

logger = get_logger(__name__)


class PortalDataPropagationAPIClient(PortalBaseAPIClient):
    """Client for Portal data propagation (sync timing) endpoints."""
    
    async def get_volume_data_propagation(
        self,
        volume_guid: str,
        serial_numbers: List[str],
        period: str = "PT3H",
        smart_sampling: bool = True,
        chart_width: int = 1000
    ) -> Dict[str, Any]:
        """
        Get data propagation (sync timing) telemetry for a volume.
        
        Shows when each connected appliance synced snapshots after creation,
        including propagation duration and statistical outlier detection.
        
        Args:
            volume_guid: Volume GUID
            serial_numbers: List of appliance serial numbers
            period: ISO 8601 duration (default: PT3H)
            smart_sampling: Reduce data points while preserving trends
            chart_width: Chart width parameter
            
        Returns:
            Dict with metadata and items array containing propagation events
        """
        logger.info(f"Fetching data propagation for volume {volume_guid}")
        logger.debug(f"Serial numbers: {serial_numbers}, Period: {period}")
        
        # Note: This uses the data_propagation endpoint (correctly named for propagation)
        endpoint = f"/telemetry/volumes/{volume_guid}/snapshot_propagation_by_appliance"
        
        payload = {
            "serial_numbers": serial_numbers,
            "period": period,
            "chart_width": chart_width,
            "smart_sampling": smart_sampling
        }
        
        response = await self.post(endpoint, json=payload)
        
        if "error" not in response:
            items_count = len(response.get("items", []))
            logger.info(f"Retrieved {items_count} propagation events")
        
        return response
    
    async def get_volume_data_propagation_analysis(
        self,
        volume_guid: str,
        serial_numbers: List[str],
        period: str = "PT3H",
        smart_sampling: bool = True
    ) -> DataPropagationAnalysis:
        """
        Get data propagation with analysis.
        
        Returns:
            DataPropagationAnalysis with statistics and insights
        """
        response = await self.get_volume_data_propagation(
            volume_guid=volume_guid,
            serial_numbers=serial_numbers,
            period=period,
            smart_sampling=smart_sampling
        )
        
        if "error" in response:
            logger.error(f"Error fetching propagation data: {response['error']}")
            return DataPropagationAnalysis([], {})
        
        # Parse events
        events = []
        for item in response.get("items", []):
            try:
                events.append(DataPropagationEvent(item))
            except Exception as e:
                logger.warning(f"Failed to parse event: {e}")
        
        metadata = {
            "snapshot_appliances": response.get("snapshot_appliances", []),
            "sync_appliances": response.get("sync_appliances", [])
        }
        
        logger.info(f"Parsed {len(events)} propagation events")
        return DataPropagationAnalysis(events, metadata)
    
    async def test_connection(self) -> bool:
        """Test the Portal API connection."""
        try:
            authenticated = await self._ensure_authenticated()
            return authenticated
        except Exception:
            return False