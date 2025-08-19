#!/usr/bin/env python3
"""Filer Health API client implementation."""

import sys
from typing import Dict, Any, List
from api.base_client import BaseAPIClient
from models.filer_health import FilerHealth


class FilerHealthAPIClient(BaseAPIClient):
    """Client for interacting with the Filer Health API."""
    
    async def list_filer_health(self) -> Dict[str, Any]:
        """Fetch health status for all filers from the API."""
        print("Fetching filer health data from API...", file=sys.stderr)
        
        response = await self.get("/api/v1.2/filers/health/")
        
        if "error" not in response:
            items_count = len(response.get("items", []))
            print(f"Successfully retrieved health data for {items_count} filers", file=sys.stderr)
        
        return response
    
    async def get_filer_health(self, filer_serial: str) -> Dict[str, Any]:
        """Get health status for a specific filer by serial number."""
        print(f"Fetching health for filer {filer_serial}...", file=sys.stderr)
        return await self.get(f"/api/v1.2/filers/{filer_serial}/health/")
    
    async def get_filer_health_as_models(self) -> List[FilerHealth]:
        """Get filer health data as model objects."""
        response = await self.list_filer_health()
        
        if "error" in response:
            print(f"Error fetching filer health: {response['error']}", file=sys.stderr)
            return []
        
        health_records = []
        for item in response.get("items", []):
            try:
                health = FilerHealth(item)
                health_records.append(health)
            except Exception as e:
                print(f"Error parsing filer health data: {e}", file=sys.stderr)
                continue
        
        return health_records
    
    async def test_connection(self) -> bool:
        """Test the API connection."""
        try:
            response = await self.get("/api/v1.2/filers/health/")
            return "error" not in response
        except Exception:
            return False
    
    async def get_health_statistics(self) -> Dict[str, Any]:
        """Get statistics about filer health across the infrastructure."""
        health_records = await self.get_filer_health_as_models()
        
        if not health_records:
            return {
                "total_filers": 0,
                "healthy_filers": 0,
                "unhealthy_filers": 0,
                "error": "No filer health data found or API error"
            }
        
        # Overall health statistics
        healthy_filers = sum(1 for h in health_records if h.is_healthy)
        unhealthy_filers = sum(1 for h in health_records if h.is_unhealthy)
        warning_filers = sum(1 for h in health_records if h.has_warnings)
        
        # Component-specific statistics
        component_stats = {}
        all_components = [
            "network", "memory", "cpu", "disk", "filesystem", "services",
            "nfs", "smb", "directoryservices", "cyberresilience", 
            "fileaccelerator", "agfl", "nasuni_iq"
        ]
        
        for component in all_components:
            healthy_count = 0
            unhealthy_count = 0
            no_results_count = 0
            
            for health in health_records:
                status = getattr(health, component, "")
                if status == "Healthy":
                    healthy_count += 1
                elif status == "Unhealthy":
                    unhealthy_count += 1
                elif status == "No Results":
                    no_results_count += 1
            
            component_stats[component] = {
                "healthy": healthy_count,
                "unhealthy": unhealthy_count,
                "no_results": no_results_count,
                "monitored": healthy_count + unhealthy_count
            }
        
        # Calculate average health score
        health_scores = [h.health_score for h in health_records if h.health_score > 0]
        avg_health_score = round(sum(health_scores) / len(health_scores), 1) if health_scores else 0
        
        # Find most problematic components
        problematic_components = [
            (comp, stats["unhealthy"]) 
            for comp, stats in component_stats.items() 
            if stats["unhealthy"] > 0
        ]
        problematic_components.sort(key=lambda x: x[1], reverse=True)
        
        return {
            "total_filers": len(health_records),
            "healthy_filers": healthy_filers,
            "unhealthy_filers": unhealthy_filers,
            "warning_filers": warning_filers,
            "avg_health_score": avg_health_score,
            "component_stats": component_stats,
            "most_problematic_components": problematic_components[:5],
            "infrastructure_health": "Healthy" if unhealthy_filers == 0 else "Issues Detected"
        }
    
    async def get_unhealthy_filers(self) -> List[FilerHealth]:
        """Get all filers with unhealthy components."""
        health_records = await self.get_filer_health_as_models()
        return [h for h in health_records if h.is_unhealthy]
    
    async def get_healthy_filers(self) -> List[FilerHealth]:
        """Get all completely healthy filers."""
        health_records = await self.get_filer_health_as_models()
        return [h for h in health_records if h.is_healthy]
    
    async def get_filers_with_warnings(self) -> List[FilerHealth]:
        """Get all filers with warning conditions."""
        health_records = await self.get_filer_health_as_models()
        return [h for h in health_records if h.has_warnings]
    
    async def get_filers_by_component_health(self, component: str, status: str) -> List[FilerHealth]:
        """Get filers filtered by specific component health status."""
        health_records = await self.get_filer_health_as_models()
        
        valid_components = [
            "network", "memory", "cpu", "disk", "filesystem", "services",
            "nfs", "smb", "directoryservices", "cyberresilience", 
            "fileaccelerator", "agfl", "nasuni_iq"
        ]
        
        if component not in valid_components:
            return []
        
        return [
            h for h in health_records 
            if getattr(h, component, "") == status
        ]
    
    async def get_critical_issues(self) -> Dict[str, Any]:
        """Identify critical health issues across the infrastructure."""
        health_records = await self.get_filer_health_as_models()
        
        critical_issues = {
            "unhealthy_filers": [],
            "disk_issues": [],
            "memory_issues": [],
            "network_issues": [],
            "service_issues": [],
            "file_iq_issues": []
        }
        
        for health in health_records:
            if health.is_unhealthy:
                critical_issues["unhealthy_filers"].append(health.filer_serial_number)
            
            if health.disk == "Unhealthy":
                critical_issues["disk_issues"].append(health.filer_serial_number)
            
            if health.memory == "Unhealthy":
                critical_issues["memory_issues"].append(health.filer_serial_number)
            
            if health.network == "Unhealthy":
                critical_issues["network_issues"].append(health.filer_serial_number)
            
            if health.services == "Unhealthy":
                critical_issues["service_issues"].append(health.filer_serial_number)
            
            if health.nasuni_iq == "Unhealthy":
                critical_issues["file_iq_issues"].append(health.filer_serial_number)
        
        return critical_issues