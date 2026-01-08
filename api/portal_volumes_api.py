#!/usr/bin/env python3
"""Portal Volumes API client.

This module provides API client for Portal Volume endpoints.
These endpoints provide volume information including cloud provider,
edge connections, and capacity details.
"""

from __future__ import annotations

from typing import Any, Dict

from api.portal_base_client import PortalBaseAPIClient
from config.logging_setup import get_logger
from models.portal_volume import VolumeDto, VolumesResponseDto

logger = get_logger(__name__)


class PortalVolumesAPIClient(PortalBaseAPIClient):
    """Client for Portal Volumes API endpoints.
    
    The Portal Volumes API provides volume information including:
    - Volume description and ID
    - Cloud provider (AWS, Azure, etc.)
    - Edge connections (master and connected edges)
    - Capacity and usage statistics
    - GFL and GFA mode settings
    - Share features
    """

    async def get_volumes(self) -> VolumesResponseDto:
        """Get list of all volumes for the account.
        
        Returns:
            VolumesResponseDto containing list of volumes with basic info
        """
        response = await self._make_request("GET", "/volumes")
        return VolumesResponseDto.model_validate(response)

    async def get_volume(self, volume_id: str) -> VolumeDto:
        """Get detailed information for a specific volume.
        
        This endpoint provides comprehensive volume details including:
        - Cloud provider information
        - Edge connections (master and connected edges)
        - Capacity and usage statistics
        - GFL and GFA mode settings
        - Share features
        
        Args:
            volume_id: The ID of the volume (GUID format)
            
        Returns:
            VolumeDto with detailed volume information
        """
        response = await self._make_request("GET", f"/volumes/{volume_id}")
        return VolumeDto.model_validate(response)

    async def test_connection(self) -> bool:
        """Test the Portal Volumes API connection.
        
        Returns:
            True if connection is successful, False otherwise
        """
        try:
            await self.get_volumes()
            return True
        except Exception:
            return False