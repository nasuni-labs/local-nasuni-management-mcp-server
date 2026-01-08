#!/usr/bin/env python3
"""Portal Edge API response models.

These models represent the Edge appliance data returned by the Portal API.
The Portal API provides authoritative and detailed hardware information
for Edge appliances.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class EdgeServicesDto(BaseModel):
    """Edge appliance services status."""
    s3_edge: Optional[bool] = None
    file_iq: Optional[bool] = None


class EdgeVolumes(BaseModel):
    """Edge appliance volume statistics."""
    owned: int = 0
    remotely_connected: int = 0
    
    def total_volumes(self) -> int:
        """Return total number of volumes (owned + remote)."""
        return self.owned + self.remotely_connected


class EdgeBuild(BaseModel):
    """Edge appliance build/version information."""
    current: Optional[str] = None
    available: Optional[str] = None
    platform: Optional[str] = None
    
    def is_update_available(self) -> bool:
        """Check if an update is available."""
        return bool(self.available)


class EdgeMachine(BaseModel):
    """Edge appliance hardware specifications.
    
    This is the authoritative source for Edge hardware details including:
    - CPU model and core count
    - RAM capacity
    - Disk sizes for cache, OS, File IQ, and CoW storage
    """
    cpu: Optional[str] = None
    ram: Optional[str] = None
    cache_disk: Optional[str] = None
    os_disk: Optional[str] = None
    fiq_disk: Optional[str] = None
    cow_disk: Optional[str] = None
    cpu_cores: Optional[int] = None


class SimpleEdgeDto(BaseModel):
    """Basic Edge appliance info (from list endpoint)."""
    id: Optional[str] = None
    description: Optional[str] = None
    serial: Optional[str] = None
    build: Optional[str] = None
    services: Optional[EdgeServicesDto] = None


class EdgesDto(BaseModel):
    """Response from GET /edges endpoint."""
    items: List[SimpleEdgeDto] = Field(default_factory=list)


class EdgeDto(BaseModel):
    """Detailed Edge appliance information.
    
    This model contains comprehensive hardware and configuration details
    for an Edge appliance, including machine specs, build info, volume stats,
    and service configurations.
    """
    id: Optional[str] = None
    description: Optional[str] = None
    serial: Optional[str] = None
    ipaddress: Optional[str] = None
    location: Optional[str] = None
    last_config_backup_date: Optional[str] = None
    
    # Nested objects
    services: Optional[EdgeServicesDto] = None
    volumes: Optional[EdgeVolumes] = None
    build: Optional[EdgeBuild] = None
    machine: Optional[EdgeMachine] = None
    
    # Legacy fields (also available at top level in some responses)
    owned_volumes: Optional[int] = None
    remotely_connected_volumes: Optional[int] = None

    def get_version_tuple(self) -> tuple:
        """Parse the current build version into a tuple for comparison.
        
        Returns:
            Tuple of (major, minor, patch) or empty tuple if parsing fails.
        """
        try:
            if not self.build or not self.build.current:
                return ()
            parts = self.build.current.split(".")
            return tuple(int(p) for p in parts[:3])
        except (ValueError, IndexError):
            return ()
