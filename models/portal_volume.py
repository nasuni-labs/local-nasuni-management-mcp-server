#!/usr/bin/env python3
"""Portal Volume API response models.

These models represent the Volume data returned by the Portal API.
The Portal API provides volume information including cloud provider,
edge connections, and capacity details.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class VolumeMasterDto(BaseModel):
    """Master edge information for a volume."""
    id: Optional[str] = None
    description: Optional[str] = None


class VolumeEdgesDto(BaseModel):
    """Edge connection information for a volume."""
    master: Optional[VolumeMasterDto] = None
    connected: List[str] = Field(default_factory=list)
    connected_count: int = 0


class VolumeBaseDto(BaseModel):
    """Basic volume information (from list endpoint)."""
    id: str
    description: Optional[str] = None
    remote_access_enabled: Optional[bool] = None
    provider: Optional[str] = None


class VolumeDto(BaseModel):
    """Detailed volume information.
    
    This model contains comprehensive volume details including:
    - Cloud provider information
    - Edge connections (master and connected edges)
    - Capacity and usage statistics
    - Share features and GFL/GFA settings
    """
    id: str
    description: Optional[str] = None
    remote_access_enabled: Optional[bool] = None
    provider: Optional[str] = None
    edges: Optional[VolumeEdgesDto] = None
    location: Optional[str] = None
    gfl: Optional[bool] = None
    lock_server: Optional[str] = None
    used_capacity: Optional[str] = None
    percent_capacity_used: Optional[int] = None
    compression_data_reduction_percent: Optional[int] = None
    share_features: Optional[str] = None
    gfa_mode: Optional[bool] = None

    def is_gfl_enabled(self) -> bool:
        """Check if Global File Lock is enabled."""
        return bool(self.gfl)
    
    def is_gfa_enabled(self) -> bool:
        """Check if Global File Acceleration is enabled."""
        return bool(self.gfa_mode)
    
    def get_connected_edge_count(self) -> int:
        """Get the number of connected edges."""
        if self.edges:
            return self.edges.connected_count
        return 0


class VolumesResponseDto(BaseModel):
    """Response from GET /volumes endpoint."""
    items: List[VolumeBaseDto] = Field(default_factory=list)
