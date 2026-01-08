#!/usr/bin/env python3
"""Portal Edges API client.

This module provides API client for Portal Edge appliance endpoints.
These endpoints provide detailed hardware information about Edge appliances
that is more accurate than NMC data.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from api.portal_base_client import PortalBaseAPIClient
from config.logging_setup import get_logger
from models.portal_edge import EdgeDto, EdgesDto, EdgeServicesDto

logger = get_logger(__name__)


class PortalEdgesAPIClient(PortalBaseAPIClient):
    """Client for Portal Edges API endpoints.
    
    The Portal Edges API provides detailed and accurate hardware information
    about Edge appliances, including:
    - CPU details and core count
    - RAM capacity
    - Disk configurations (cache, OS, FIQ, COW)
    - Build/version information
    - Platform type
    - Network configuration
    - Volume ownership statistics
    """

    async def get_edges(
        self,
        s3_edge_enabled: Optional[bool] = None,
        file_iq_enabled: Optional[bool] = None,
    ) -> EdgesDto:
        """Get list of all Edge appliances.
        
        Args:
            s3_edge_enabled: Filter by S3 Edge service status (None for no filter)
            file_iq_enabled: Filter by File IQ service status (None for no filter)
            
        Returns:
            EdgesDto containing list of edges with basic info
        """
        params: Dict[str, Any] = {}
        if s3_edge_enabled is not None:
            params["s3_edge_enabled"] = str(s3_edge_enabled).lower()
        if file_iq_enabled is not None:
            params["file_iq_enabled"] = str(file_iq_enabled).lower()

        response = await self._make_request("GET", "/edges", params=params if params else None)
        return EdgesDto.model_validate(response)

    async def get_edge(self, edge_id: str | UUID) -> EdgeDto:
        """Get detailed information for a specific Edge appliance.
        
        This endpoint provides comprehensive hardware details including:
        - Machine specs (CPU, RAM, disk sizes, core count)
        - Build information (current version, available update, platform)
        - Volume statistics (owned vs remotely connected)
        - Network information (IP address, location)
        - Service status (S3 Edge, File IQ)
        
        Args:
            edge_id: The UUID of the Edge appliance (same as serial number)
            
        Returns:
            EdgeDto with detailed edge information
        """
        response = await self._make_request("GET", f"/edges/{edge_id}")
        return EdgeDto.model_validate(response)

    async def get_edge_by_serial(self, serial_number: str) -> EdgeDto:
        """Get detailed information for an Edge by serial number.
        
        Convenience method that treats serial_number as the edge_id.
        
        Args:
            serial_number: The serial number (UUID) of the Edge appliance
            
        Returns:
            EdgeDto with detailed edge information
        """
        return await self.get_edge(serial_number)

    async def get_edge_event_forwarder(self, edge_id: str | UUID) -> EdgeServicesDto:
        """Get Event Forwarder service configuration for an Edge.
        
        Args:
            edge_id: The UUID of the Edge appliance
            
        Returns:
            EdgeServicesDto with event forwarder configuration
        """
        response = await self._make_request("GET", f"/edges/{edge_id}/services/event_forwarder")
        return EdgeServicesDto.model_validate(response)

    async def get_edge_s3_edge_config(self, edge_id: str | UUID) -> EdgeServicesDto:
        """Get S3 Edge service configuration for an Edge.
        
        Args:
            edge_id: The UUID of the Edge appliance
            
        Returns:
            EdgeServicesDto with S3 Edge configuration
        """
        response = await self._make_request("GET", f"/edges/{edge_id}/services/s3_edge")
        return EdgeServicesDto.model_validate(response)

    async def test_connection(self) -> bool:
        """Test the Portal Edges API connection.
        
        Returns:
            True if connection is successful, False otherwise
        """
        try:
            await self.get_edges()
            return True
        except Exception:
            return False