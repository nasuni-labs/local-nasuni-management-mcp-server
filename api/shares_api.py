#!/usr/bin/env python3
"""Shares API client implementation."""

import sys
from typing import Dict, Any, List
from api.base_client import BaseAPIClient
from models.share import Share


class SharesAPIClient(BaseAPIClient):
    """Client for interacting with the Shares API."""
    
    async def list_shares(self) -> Dict[str, Any]:
        """Fetch all shares from the API."""
        print("Fetching shares from API...", file=sys.stderr)
        
        response = await self.get("/api/v1.2/volumes/filers/shares/")
        
        if "error" not in response:
            items_count = len(response.get("items", []))
            print(f"Successfully retrieved {items_count} shares", file=sys.stderr)
        
        return response
    
    async def get_share(self, share_id: str) -> Dict[str, Any]:
        """Get a specific share by ID."""
        print(f"Fetching share {share_id}...", file=sys.stderr)
        # Note: The exact endpoint would need to be confirmed
        return await self.get(f"/api/v1.2/volumes/filers/shares/{share_id}/")
    
    async def get_shares_as_models(self) -> List[Share]:
        """Get shares as model objects."""
        response = await self.list_shares()
        
        if "error" in response:
            print(f"Error fetching shares: {response['error']}", file=sys.stderr)
            return []
        
        shares = []
        for item in response.get("items", []):
            try:
                share = Share(item)
                shares.append(share)
            except Exception as e:
                print(f"Error parsing share data: {e}", file=sys.stderr)
                continue
        
        return shares
    
    async def test_connection(self) -> bool:
        """Test the API connection."""
        try:
            response = await self.get("/api/v1.2/volumes/filers/shares/")
            return "error" not in response
        except Exception:
            return False
    
    async def get_share_statistics(self) -> Dict[str, Any]:
        """Get statistics about all shares."""
        shares = await self.get_shares_as_models()
        
        if not shares:
            return {
                "total": 0,
                "readonly_shares": 0,
                "readwrite_shares": 0,
                "error": "No shares found or API error"
            }
        
        readonly_count = sum(1 for s in shares if s.is_readonly)
        readwrite_count = sum(1 for s in shares if s.is_readwrite)
        browser_access_count = sum(1 for s in shares if s.has_browser_access)
        mobile_access_count = sum(1 for s in shares if s.has_mobile_access)
        root_shares_count = sum(1 for s in shares if s.is_root_share)
        subfolder_shares_count = sum(1 for s in shares if s.is_subfolder_share)
        
        # Analyze by filer and volume
        filers = set(s.filer_serial_number for s in shares)
        volumes = set(s.volume_guid for s in shares)
        
        # Find most active filers and volumes
        filer_share_counts = {}
        volume_share_counts = {}
        
        for share in shares:
            filer_share_counts[share.filer_serial_number] = filer_share_counts.get(share.filer_serial_number, 0) + 1
            volume_share_counts[share.volume_guid] = volume_share_counts.get(share.volume_guid, 0) + 1
        
        return {
            "total": len(shares),
            "readonly_shares": readonly_count,
            "readwrite_shares": readwrite_count,
            "browser_access_enabled": browser_access_count,
            "mobile_access_enabled": mobile_access_count,
            "root_shares": root_shares_count,
            "subfolder_shares": subfolder_shares_count,
            "unique_filers": len(filers),
            "unique_volumes": len(volumes),
            "avg_shares_per_filer": round(len(shares) / len(filers), 1) if filers else 0,
            "avg_shares_per_volume": round(len(shares) / len(volumes), 1) if volumes else 0,
            "most_active_filer": max(filer_share_counts.items(), key=lambda x: x[1]) if filer_share_counts else None,
            "most_shared_volume": max(volume_share_counts.items(), key=lambda x: x[1]) if volume_share_counts else None
        }
    
    async def get_shares_by_filer(self, filer_serial: str) -> List[Share]:
        """Get all shares for a specific filer."""
        shares = await self.get_shares_as_models()
        return [s for s in shares if s.filer_serial_number == filer_serial]
    
    async def get_shares_by_volume(self, volume_guid: str) -> List[Share]:
        """Get all shares for a specific volume."""
        shares = await self.get_shares_as_models()
        return [s for s in shares if s.volume_guid == volume_guid]
    
    async def get_shares_by_filer_and_volume(self, filer_serial: str, volume_guid: str) -> List[Share]:
        """Get all shares for a specific filer-volume combination."""
        shares = await self.get_shares_as_models()
        return [s for s in shares if s.filer_serial_number == filer_serial and s.volume_guid == volume_guid]
    
    async def get_readonly_shares(self) -> List[Share]:
        """Get all read-only shares."""
        shares = await self.get_shares_as_models()
        return [s for s in shares if s.is_readonly]
    
    async def get_browser_accessible_shares(self) -> List[Share]:
        """Get all shares with browser access enabled."""
        shares = await self.get_shares_as_models()
        return [s for s in shares if s.has_browser_access]
    
    async def get_mobile_accessible_shares(self) -> List[Share]:
        """Get all shares with mobile access enabled."""
        shares = await self.get_shares_as_models()
        return [s for s in shares if s.has_mobile_access]
    
    async def get_shares_by_name_pattern(self, pattern: str) -> List[Share]:
        """Get shares that match a name pattern."""
        shares = await self.get_shares_as_models()
        pattern_lower = pattern.lower()
        return [s for s in shares if pattern_lower in s.name.lower()]