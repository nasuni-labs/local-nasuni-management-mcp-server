#!/usr/bin/env python3
"""Filers API client implementation."""

import sys
from typing import Dict, Any, List
from api.base_client import BaseAPIClient
from models.filer import Filer


class FilersAPIClient(BaseAPIClient):
    """Client for interacting with the Filers API."""
    
    async def list_filers(self) -> Dict[str, Any]:
        """Fetch all filers from the API."""
        print("Fetching filers from API...", file=sys.stderr)
        
        response = await self.get("/api/v1.2/filers/")
        
        if "error" not in response:
            items_count = len(response.get("items", []))
            print(f"Successfully retrieved {items_count} filers", file=sys.stderr)
        
        return response
    
    async def get_filer(self, filer_id: str) -> Dict[str, Any]:
        """Get a specific filer by ID."""
        print(f"Fetching filer {filer_id}...", file=sys.stderr)
        return await self.get(f"/api/v1.2/filers/{filer_id}/")
    
    async def get_filers_as_models(self) -> List[Filer]:
        """Get filers as model objects."""
        response = await self.list_filers()
        
        if "error" in response:
            print(f"Error fetching filers: {response['error']}", file=sys.stderr)
            return []
        
        filers = []
        for item in response.get("items", []):
            try:
                filer = Filer(item)
                filers.append(filer)
            except Exception as e:
                print(f"Error parsing filer data: {e}", file=sys.stderr)
                continue
        
        return filers
    
    async def test_connection(self) -> bool:
        """Test the API connection."""
        try:
            response = await self.get("/api/v1.2/filers/")
            return "error" not in response
        except Exception:
            return False
    
    async def get_filer_statistics(self) -> Dict[str, Any]:
        """Get statistics about all filers."""
        filers = await self.get_filers_as_models()
        
        if not filers:
            return {
                "total": 0,
                "online": 0,
                "offline": 0,
                "error": "No filers found or API error"
            }
        
        online_count = sum(1 for f in filers if f.status.is_online)
        offline_count = len(filers) - online_count
        
        # Calculate aggregate cache usage
        total_cache_size = sum(f.status.platform.cache_status.size for f in filers)
        total_cache_used = sum(f.status.platform.cache_status.used for f in filers)
        avg_cache_usage = (total_cache_used / total_cache_size * 100) if total_cache_size > 0 else 0
        
        return {
            "total": len(filers),
            "online": online_count,
            "offline": offline_count,
            "total_cache_size_gb": round(total_cache_size / (1024**3), 2),
            "total_cache_used_gb": round(total_cache_used / (1024**3), 2),
            "average_cache_usage_percent": round(avg_cache_usage, 2),
            "platforms": list(set(f.status.platform.platform_name for f in filers if f.status.platform.platform_name)),
            "versions": list(set(f.status.current_version for f in filers if f.status.current_version != "Unknown"))
        }