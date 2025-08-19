#!/usr/bin/env python3
"""Cloud Credentials API client implementation."""

import sys
from typing import Dict, Any, List, Optional
from api.base_client import BaseAPIClient
from models.cloud_credential import CloudCredential


class CloudCredentialsAPIClient(BaseAPIClient):
    """Client for interacting with the Cloud Credentials API."""
    
    async def list_credentials(self) -> Dict[str, Any]:
        """Fetch all cloud credentials from the API."""
        print("Fetching cloud credentials from API...", file=sys.stderr)
        
        response = await self.get("/api/v1.2/account/cloud-credentials/")
        
        if "error" not in response:
            items_count = len(response.get("items", []))
            print(f"Successfully retrieved {items_count} cloud credentials", file=sys.stderr)
        
        return response
    
    async def get_credential(self, cred_uuid: str, filer_serial: Optional[str] = None) -> Dict[str, Any]:
        """Get a specific cloud credential by UUID and optionally filer serial."""
        if filer_serial:
            print(f"Fetching credential {cred_uuid} for filer {filer_serial}...", file=sys.stderr)
            return await self.get(f"/api/v1.2/account/cloud-credentials/{cred_uuid}/filers/{filer_serial}/")
        else:
            print(f"Fetching credential {cred_uuid}...", file=sys.stderr)
            return await self.get(f"/api/v1.2/account/cloud-credentials/{cred_uuid}/")
    
    async def get_credentials_as_models(self) -> List[CloudCredential]:
        """Get cloud credentials as model objects."""
        response = await self.list_credentials()
        
        if "error" in response:
            print(f"Error fetching credentials: {response['error']}", file=sys.stderr)
            return []
        
        credentials = []
        for item in response.get("items", []):
            try:
                credential = CloudCredential(item)
                credentials.append(credential)
            except Exception as e:
                print(f"Error parsing credential data: {e}", file=sys.stderr)
                continue
        
        return credentials
    
    async def test_connection(self) -> bool:
        """Test the API connection."""
        try:
            response = await self.get("/api/v1.2/account/cloud-credentials/")
            return "error" not in response
        except Exception:
            return False
    
    async def get_credentials_by_provider(self, provider: str) -> List[CloudCredential]:
        """Get all credentials for a specific cloud provider."""
        credentials = await self.get_credentials_as_models()
        return [c for c in credentials if provider.lower() in c.cloud_provider.lower()]
    
    async def get_credentials_by_filer(self, filer_serial: str) -> List[CloudCredential]:
        """Get all credentials associated with a specific filer."""
        credentials = await self.get_credentials_as_models()
        return [c for c in credentials if c.filer_serial_number == filer_serial]
    
    async def get_credentials_by_name(self, name: str) -> List[CloudCredential]:
        """Get credentials by name (partial match)."""
        credentials = await self.get_credentials_as_models()
        return [c for c in credentials if name.lower() in c.name.lower()]
    
    async def get_active_credentials(self) -> List[CloudCredential]:
        """Get all credentials that are in use."""
        credentials = await self.get_credentials_as_models()
        return [c for c in credentials if c.in_use]
    
    async def get_inactive_credentials(self) -> List[CloudCredential]:
        """Get all credentials that are not in use."""
        credentials = await self.get_credentials_as_models()
        return [c for c in credentials if not c.in_use]
    
    async def get_credential_statistics(self) -> Dict[str, Any]:
        """Get statistics about cloud credentials."""
        credentials = await self.get_credentials_as_models()
        
        if not credentials:
            return {
                "total": 0,
                "unique_credentials": 0,
                "in_use": 0,
                "not_in_use": 0,
                "error": "No credentials found or API error"
            }
        
        # Get unique credential UUIDs
        unique_creds = set(c.cred_uuid for c in credentials)
        
        # Count by provider
        providers = {}
        for cred in credentials:
            provider = cred.cloud_provider
            providers[provider] = providers.get(provider, 0) + 1
        
        # Count by status
        synced_count = sum(1 for c in credentials if c.is_synced)
        in_use_count = sum(1 for c in credentials if c.in_use)
        
        # Group by filer
        filers = {}
        for cred in credentials:
            filer = cred.filer_serial_number
            if filer not in filers:
                filers[filer] = []
            filers[filer].append(cred.name)
        
        # Find credentials deployed to multiple filers
        cred_deployments = {}
        for cred in credentials:
            if cred.cred_uuid not in cred_deployments:
                cred_deployments[cred.cred_uuid] = {
                    "name": cred.name,
                    "provider": cred.cloud_provider,
                    "filers": []
                }
            cred_deployments[cred.cred_uuid]["filers"].append(cred.filer_serial_number)
        
        multi_filer_creds = {
            uuid: info for uuid, info in cred_deployments.items() 
            if len(info["filers"]) > 1
        }
        
        return {
            "total_deployments": len(credentials),
            "unique_credentials": len(unique_creds),
            "in_use": in_use_count,
            "not_in_use": len(credentials) - in_use_count,
            "synced": synced_count,
            "providers": providers,
            "filers_with_credentials": len(filers),
            "multi_filer_credentials": len(multi_filer_creds),
            "multi_filer_details": multi_filer_creds,
            "avg_credentials_per_filer": round(len(credentials) / len(filers), 2) if filers else 0
        }
    
    async def get_credential_usage_analysis(self, volumes_client=None) -> Dict[str, Any]:
        """Analyze credential usage across volumes if volumes client is provided."""
        credentials = await self.get_credentials_as_models()
        
        if not credentials:
            return {"error": "No credentials found"}
        
        analysis = {
            "credentials": {},
            "unused_credentials": []
        }
        
        # Build credential lookup
        for cred in credentials:
            if cred.cred_uuid not in analysis["credentials"]:
                analysis["credentials"][cred.cred_uuid] = {
                    "name": cred.name,
                    "provider": cred.cloud_provider,
                    "in_use": cred.in_use,
                    "filers": [],
                    "volumes": []
                }
            analysis["credentials"][cred.cred_uuid]["filers"].append(cred.filer_serial_number)
        
        # If volumes client is provided, cross-reference with volumes
        if volumes_client:
            try:
                from api.volumes_api import VolumesAPIClient
                volumes = await volumes_client.get_volumes_as_models()
                
                for volume in volumes:
                    if volume.provider.cred_uuid in analysis["credentials"]:
                        analysis["credentials"][volume.provider.cred_uuid]["volumes"].append({
                            "name": volume.name,
                            "guid": volume.guid,
                            "filer": volume.filer_serial_number
                        })
                
                # Find unused credentials
                for uuid, info in analysis["credentials"].items():
                    if not info["volumes"] and not info["in_use"]:
                        analysis["unused_credentials"].append({
                            "uuid": uuid,
                            "name": info["name"],
                            "provider": info["provider"],
                            "filers": info["filers"]
                        })
                        
            except Exception as e:
                print(f"Error analyzing volume usage: {e}", file=sys.stderr)
        
        return analysis