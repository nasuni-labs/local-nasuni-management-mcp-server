#!/usr/bin/env python3
"""Volumes API client implementation."""

import sys
from typing import Dict, Any, List
from api.base_client import BaseAPIClient
from models.volume import Volume
from models.volume_connection import VolumeConnection


class VolumesAPIClient(BaseAPIClient):
    """Client for interacting with the Volumes API."""
    
    async def list_volumes(self) -> Dict[str, Any]:
        """Fetch all volumes from the API."""
        print("Fetching volumes from API...", file=sys.stderr)
        
        response = await self.get("/api/v1.2/volumes/")
        
        if "error" not in response:
            items_count = len(response.get("items", []))
            print(f"Successfully retrieved {items_count} volumes", file=sys.stderr)
        
        return response
    
    async def list_volume_connections(self) -> Dict[str, Any]:
        """Fetch all volume-filer connections from the API."""
        print("Fetching volume connections from API...", file=sys.stderr)
        
        response = await self.get("/api/v1.2/volumes/filer-connections/")
        
        if "error" not in response:
            items_count = len(response.get("items", []))
            print(f"Successfully retrieved {items_count} volume connections", file=sys.stderr)
        
        return response
    
    async def get_volume(self, volume_id: str) -> Dict[str, Any]:
        """Get a specific volume by ID."""
        print(f"Fetching volume {volume_id}...", file=sys.stderr)
        return await self.get(f"/api/v1.2/volumes/{volume_id}/")
    
    async def get_volumes_as_models(self) -> List[Volume]:
        """Get volumes as model objects."""
        response = await self.list_volumes()
        
        if "error" in response:
            print(f"Error fetching volumes: {response['error']}", file=sys.stderr)
            return []
        
        volumes = []
        for item in response.get("items", []):
            try:
                volume = Volume(item)
                volumes.append(volume)
            except Exception as e:
                print(f"Error parsing volume data: {e}", file=sys.stderr)
                continue
        
        return volumes
    
    async def get_volume_connections_as_models(self) -> List[VolumeConnection]:
        """Get volume connections as model objects."""
        response = await self.list_volume_connections()
        
        if "error" in response:
            print(f"Error fetching volume connections: {response['error']}", file=sys.stderr)
            return []
        
        connections = []
        for item in response.get("items", []):
            try:
                connection = VolumeConnection(item)
                connections.append(connection)
            except Exception as e:
                print(f"Error parsing volume connection data: {e}", file=sys.stderr)
                continue
        
        return connections
    
    async def test_connection(self) -> bool:
        """Test the API connection."""
        try:
            response = await self.get("/api/v1.2/volumes/")
            return "error" not in response
        except Exception:
            return False
    
    async def get_volume_statistics(self) -> Dict[str, Any]:
        """Get statistics about all volumes."""
        volumes = await self.get_volumes_as_models()
        
        if not volumes:
            return {
                "total": 0,
                "cifs_volumes": 0,
                "nfs_volumes": 0,
                "error": "No volumes found or API error"
            }
        
        # Calculate statistics
        cifs_count = sum(1 for v in volumes if v.is_cifs)
        nfs_count = sum(1 for v in volumes if v.is_nfs)
        antivirus_enabled = sum(1 for v in volumes if v.antivirus_enabled)
        public_volumes = sum(1 for v in volumes if v.auth and v.auth.is_public)
        quoted_volumes = sum(1 for v in volumes if v.has_quota)
        
        # Provider statistics
        providers = {}
        locations = {}
        for volume in volumes:
            provider = volume.provider.name
            location = volume.provider.location
            providers[provider] = providers.get(provider, 0) + 1
            if location:
                locations[location] = locations.get(location, 0) + 1
        
        # Calculate total quota
        total_quota = sum(v.quota for v in volumes if v.has_quota)
        
        return {
            "total": len(volumes),
            "cifs_volumes": cifs_count,
            "nfs_volumes": nfs_count,
            "antivirus_enabled": antivirus_enabled,
            "public_volumes": public_volumes,
            "quoted_volumes": quoted_volumes,
            "total_quota_gb": round(total_quota / 1024, 2) if total_quota > 0 else 0,
            "providers": providers,
            "locations": locations,
            "nmc_managed": sum(1 for v in volumes if v.nmc_managed),
            "case_sensitive": sum(1 for v in volumes if v.case_sensitive),
            "compression_enabled": sum(1 for v in volumes if v.cloud_io.compression),
            "remote_access_enabled": sum(1 for v in volumes if v.remote_access.enabled)
        }
    
    async def get_connection_statistics(self) -> Dict[str, Any]:
        """Get statistics about volume-filer connections."""
        connections = await self.get_volume_connections_as_models()
        
        if not connections:
            return {
                "total": 0,
                "connected": 0,
                "disconnected": 0,
                "error": "No connections found or API error"
            }
        
        connected_count = sum(1 for c in connections if c.is_connected)
        disconnected_count = sum(1 for c in connections if c.is_disconnected)
        
        # Group by volume and filer
        volumes = set(c.volume_guid for c in connections)
        filers = set(c.filer_serial_number for c in connections)
        
        # Find volumes with connection issues
        disconnected_volumes = set(c.volume_guid for c in connections if c.is_disconnected)
        
        return {
            "total": len(connections),
            "connected": connected_count,
            "disconnected": disconnected_count,
            "unique_volumes": len(volumes),
            "unique_filers": len(filers),
            "volumes_with_issues": len(disconnected_volumes),
            "connection_health": round((connected_count / len(connections)) * 100, 1) if connections else 0
        }
    
    async def get_volumes_by_filer(self, filer_serial: str) -> List[Volume]:
        """Get all volumes for a specific filer."""
        volumes = await self.get_volumes_as_models()
        return [v for v in volumes if v.filer_serial_number == filer_serial]
    
    async def get_connections_by_filer(self, filer_serial: str) -> List[VolumeConnection]:
        """Get all volume connections for a specific filer."""
        connections = await self.get_volume_connections_as_models()
        return [c for c in connections if c.filer_serial_number == filer_serial]
    
    async def get_connections_by_volume(self, volume_guid: str) -> List[VolumeConnection]:
        """Get all filer connections for a specific volume."""
        connections = await self.get_volume_connections_as_models()
        return [c for c in connections if c.volume_guid == volume_guid]
    
    async def get_disconnected_connections(self) -> List[VolumeConnection]:
        """Get all disconnected volume-filer connections."""
        connections = await self.get_volume_connections_as_models()
        return [c for c in connections if c.is_disconnected]
    
    async def get_volumes_by_provider(self, provider_name: str) -> List[Volume]:
        """Get all volumes for a specific provider."""
        volumes = await self.get_volumes_as_models()
        return [v for v in volumes if provider_name.lower() in v.provider.name.lower()]
    
    async def get_public_volumes(self) -> List[Volume]:
        """Get all public volumes."""
        volumes = await self.get_volumes_as_models()
        return [v for v in volumes if v.auth and v.auth.is_public]
    
    async def get_volumes_by_filer(self, filer_serial: str, include_disconnected: bool = False) -> Dict[str, Any]:
        """Get all volumes connected to a specific filer."""
        from tools.filer_volumes_tool import GetVolumesByFilerTool
        tool = GetVolumesByFilerTool(self)
        return await tool.get_filer_volumes(filer_serial, include_disconnected)