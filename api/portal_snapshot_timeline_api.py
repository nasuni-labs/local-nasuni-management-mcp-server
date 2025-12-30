#!/usr/bin/env python3
"""Portal API client for snapshot timeline (protection) telemetry."""

import sys
from typing import Dict, Any, List
from api.portal_base_client import PortalBaseAPIClient
from models.snapshot_timeline import DataSnapshotEvent, MetadataSnapshotEvent, SnapshotTimelineAnalysis
from config.logging_setup import get_logger

logger = get_logger(__name__)


class PortalSnapshotTimelineAPIClient(PortalBaseAPIClient):
    """Client for Portal snapshot timeline (protection) endpoints."""
    
    async def get_volume_snapshot_timeline(
        self,
        volume_guid: str,
        serial_numbers: List[str],
        period: str = "PT3H",
        smart_sampling: bool = True,
        chart_width: int = 1000
    ) -> Dict[str, Any]:
        """
        Get snapshot timeline (protection events) for a volume.
        
        Args:
            volume_guid: Volume GUID (e.g., "cee7d269-e995-4dcf-ade3-5bc6bbffbe5a_29")
            serial_numbers: List of appliance serial numbers (NMC serial numbers)
            period: ISO 8601 duration (default: PT3H = 3 hours)
                   Examples: PT1H (1 hour), PT6H (6 hours), PT24H (24 hours), P7D (7 days)
            smart_sampling: Reduce data points while preserving trends (default: True)
            chart_width: Chart width parameter (default: 1000)
            
        Returns:
            Dict with separate data_events and metadata_events arrays
        """
        logger.info(f"Fetching snapshot timeline for volume {volume_guid}")
        logger.debug(f"Serial numbers: {serial_numbers}, Period: {period}, Smart sampling: {smart_sampling}")
        
        endpoint = f"/telemetry/volumes/{volume_guid}/snapshot_timeline"
        
        payload = {
            "serial_numbers": serial_numbers,
            "period": period,
            "chart_width": chart_width,
            "smart_sampling": smart_sampling
        }
        
        logger.debug(f"Request payload: {payload}")
        
        response = await self.post(endpoint, json=payload)
        
        if "error" not in response:
            data_count = len(response.get("data_events", []))
            metadata_count = len(response.get("metadata_events", []))
            logger.info(f"Retrieved {data_count} data events, {metadata_count} metadata events")
        
        return response
    
    async def get_volume_snapshot_timeline_analysis(
        self,
        volume_guid: str,
        serial_numbers: List[str],
        period: str = "PT3H",
        smart_sampling: bool = True
    ) -> SnapshotTimelineAnalysis:
        """
        Get snapshot timeline with analysis.
        
        Args:
            volume_guid: Volume GUID
            serial_numbers: List of appliance serial numbers
            period: ISO 8601 duration
            smart_sampling: Reduce data points while preserving trends
            
        Returns:
            SnapshotTimelineAnalysis object with statistics and insights
        """
        response = await self.get_volume_snapshot_timeline(
            volume_guid=volume_guid,
            serial_numbers=serial_numbers,
            period=period,
            smart_sampling=smart_sampling
        )
        
        if "error" in response:
            logger.error(f"Error fetching snapshot timeline: {response['error']}")
            return SnapshotTimelineAnalysis([], [], {})
        
        # Parse data events
        data_events = []
        for event_data in response.get("data_events", []):
            try:
                data_events.append(DataSnapshotEvent(event_data))
            except Exception as e:
                logger.warning(f"Failed to parse data event: {e}")
        
        # Parse metadata events
        metadata_events = []
        for event_data in response.get("metadata_events", []):
            try:
                metadata_events.append(MetadataSnapshotEvent(event_data))
            except Exception as e:
                logger.warning(f"Failed to parse metadata event: {e}")
        
        # Extract metadata
        metadata = {
            "appliance_count": response.get("appliance_count", 0),
            "min_time": response.get("min_time", 0),
            "max_time": response.get("max_time", 0)
        }
        
        logger.info(f"Parsed {len(data_events)} data events, {len(metadata_events)} metadata events")
        
        return SnapshotTimelineAnalysis(data_events, metadata_events, metadata)
    
    async def test_connection(self) -> bool:
        """Test the Portal API connection."""
        try:
            authenticated = await self._ensure_authenticated()
            return authenticated
        except Exception:
            return False