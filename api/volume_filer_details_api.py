#!/usr/bin/env python3
"""Volume-Filer Details API client using the improved /volumes/:volume_guid/filers/ endpoint."""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from api.base_client import BaseAPIClient


class VolumeFilerDetailsAPIClient(BaseAPIClient):
    """API client for volume-filer connection details using the consolidated endpoint."""
    
    async def get(self, endpoint: str) -> Dict[str, Any]:
        """Make a GET request to the API."""
        return await self._make_request("GET", endpoint)
    
    async def get_volume_filers(self, volume_guid: str) -> Dict[str, Any]:
        """
        Get all filers connected to a specific volume.
        Uses the /volumes/:volume_guid/filers/ endpoint which returns both master and remote connections.
        
        Args:
            volume_guid: The GUID of the volume
            
        Returns:
            Dict containing all filer connections for the volume
        """
        try:
            endpoint = f"/api/v1.2/volumes/{volume_guid}/filers/"
            response = await self.get(endpoint)
            return response
        except Exception as e:
            return {"error": f"Failed to fetch volume filers: {str(e)}"}
    
    async def get_volume_filer_details(self, volume_guid: str, filer_serial: Optional[str] = None) -> Dict[str, Any]:
        """
        Get comprehensive details for volume-filer connections.
        If filer_serial is provided, returns details for that specific filer.
        Otherwise returns all filer connections for the volume.
        
        Args:
            volume_guid: The GUID of the volume
            filer_serial: Optional serial number of a specific filer
            
        Returns:
            Dict with detailed filer connection information
        """
        try:
            data = await self.get_volume_filers(volume_guid)
            
            if "error" in data:
                return data
            
            filers = data.get("items", [])
            
            if filer_serial:
                # Filter for specific filer
                filer = next((f for f in filers if f["filer_serial_number"] == filer_serial), None)
                if not filer:
                    return {"error": f"Filer {filer_serial} not found for volume {volume_guid}"}
                return self._extract_filer_details(filer)
            
            # Return all filers with enhanced details
            master_filer = next((f for f in filers if f["type"] == "master"), None)
            remote_filers = [f for f in filers if f["type"] == "remote"]
            
            return {
                "volume_guid": volume_guid,
                "volume_name": filers[0]["name"] if filers else "Unknown",
                "total_filers": len(filers),
                "owner": {
                    "exists": master_filer is not None,
                    "filer_serial": master_filer["filer_serial_number"] if master_filer else None,
                    "details": self._extract_filer_details(master_filer) if master_filer else None
                },
                "remote_connections": {
                    "count": len(remote_filers),
                    "filers": [self._extract_filer_details(f) for f in remote_filers]
                },
                "all_filers": [self._extract_filer_details(f) for f in filers]
            }
            
        except Exception as e:
            return {"error": f"Failed to get volume filer details: {str(e)}"}
    
    def _extract_filer_details(self, filer: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract and enrich key details from a filer connection.
        
        Args:
            filer: Raw filer data from API
            
        Returns:
            Dict with extracted and calculated metrics
        """
        status = filer.get("status", {})
        sync_schedule = filer.get("sync_schedule", {})
        snapshot_schedule = filer.get("snapshot_schedule", {})
        auditing = filer.get("auditing", {})
        
        # Calculate data protection metrics
        accessible_data = status.get("accessible_data", 0)
        unprotected_data = status.get("data_not_yet_protected", 0)
        protection_pct = ((accessible_data - unprotected_data) / accessible_data * 100) if accessible_data > 0 else 100
        
        # Parse snapshot timestamps
        last_snapshot = status.get("last_snapshot", "")
        last_snapshot_dt = None
        hours_since_snapshot = None
        
        if last_snapshot:
            try:
                last_snapshot_dt = datetime.strptime(last_snapshot.replace("UTC", "+0000"), "%Y-%m-%dT%H:%M:%S%z")
                hours_since_snapshot = (datetime.now(last_snapshot_dt.tzinfo) - last_snapshot_dt).total_seconds() / 3600
            except:
                pass
        
        # Determine if sync/snapshot schedules are active
        sync_enabled = any(sync_schedule.get("days", {}).values())
        snapshot_enabled = any(snapshot_schedule.get("days", {}).values())
        
        return {
            # Basic Information
            "filer_serial": filer["filer_serial_number"],
            "volume_name": filer["name"],
            "connection_type": filer["type"],  # "master" or "remote"
            "is_owner": filer["type"] == "master",
            
            # Data Protection Status
            "data_protection": {
                "accessible_data_bytes": accessible_data,
                "accessible_data_gb": round(accessible_data / (1024**3), 2) if accessible_data else 0,
                "unprotected_data_bytes": unprotected_data,
                "unprotected_data_gb": round(unprotected_data / (1024**3), 2) if unprotected_data else 0,
                "protection_percentage": round(protection_pct, 2),
                "fully_protected": unprotected_data == 0,
                "at_risk": unprotected_data > 0
            },
            
            # Snapshot Configuration and Status
            "snapshot": {
                "enabled": snapshot_enabled,
                "frequency_minutes": snapshot_schedule.get("frequency", 0),
                "frequency_hours": snapshot_schedule.get("frequency", 0) / 60 if snapshot_schedule.get("frequency") else 0,
                "active_days": [day for day, active in snapshot_schedule.get("days", {}).items() if active],
                "schedule_type": "all_day" if snapshot_schedule.get("allday", False) else "scheduled",
                "snapshot_access": filer.get("snapshot_access", False),
                
                # Status
                "last_snapshot": last_snapshot,
                "last_snapshot_version": status.get("last_snapshot_version"),
                "last_snapshot_start": status.get("last_snapshot_start"),
                "last_snapshot_end": status.get("last_snapshot_end"),
                "snapshot_status": status.get("snapshot_status", "unknown"),
                "snapshot_progress": status.get("snapshot_percent", 0),
                
                # Health indicators
                "hours_since_last_snapshot": round(hours_since_snapshot, 1) if hours_since_snapshot else None,
                "is_stale": hours_since_snapshot > 24 if hours_since_snapshot else False,
                "is_critical": hours_since_snapshot > 48 if hours_since_snapshot else False
            },
            
            # Sync Configuration
            "sync": {
                "enabled": sync_enabled,
                "frequency_minutes": sync_schedule.get("frequency", 0),
                "frequency_hours": sync_schedule.get("frequency", 0) / 60 if sync_schedule.get("frequency") else 0,
                "active_days": [day for day, active in sync_schedule.get("days", {}).items() if active],
                "schedule_type": "all_day" if sync_schedule.get("allday", False) else "scheduled",
                "auto_cache_allowed": sync_schedule.get("auto_cache_allowed", False),
                "auto_cache_min_file_size": sync_schedule.get("auto_cache_min_file_size", 0)
            },
            
            # Auditing Configuration
            "auditing": {
                "enabled": auditing.get("enabled", False),
                "collapse_events": auditing.get("collapse", False),
                "events": {
                    event: enabled 
                    for event, enabled in auditing.get("events", {}).items()
                },
                "events_tracked": [
                    event for event, enabled in auditing.get("events", {}).items() if enabled
                ],
                "logs": {
                    "retention_enabled": auditing.get("logs", {}).get("prune_audit_logs", False),
                    "retention_days": auditing.get("logs", {}).get("days_to_keep", 0),
                    "exclude_by_default": auditing.get("logs", {}).get("exclude_by_default", False),
                    "include_priority": auditing.get("logs", {}).get("include_takes_priority", True)
                },
                "syslog_export": auditing.get("syslog_export", False),
                "output_type": auditing.get("output_type", "csv"),
                "destination": auditing.get("destination", "")
            },
            
            # Access Methods
            "access": {
                "share_count": status.get("share_count", 0),
                "export_count": status.get("export_count", 0),
                "ftp_dir_count": status.get("ftp_dir_count", 0),
                "total_access_points": (
                    status.get("share_count", 0) + 
                    status.get("export_count", 0) + 
                    status.get("ftp_dir_count", 0)
                )
            },
            
            # File Alerts
            "file_alerts": {
                "enabled": filer.get("file_alerts_service", {}).get("enabled", False)
            },
            
            # API Links
            "links": filer.get("links", {})
        }
    
    async def analyze_volume_operations(self, 
                                       focus: Optional[str] = None,
                                       include_protected: bool = False,
                                       min_unprotected_gb: float = 0) -> Dict[str, Any]:
        """
        Analyze volume-filer operations across all volumes.
        
        Args:
            focus: Focus area - 'snapshots', 'sync', 'auditing', 'data_protection', or None for all
            include_protected: Include fully protected volumes in results
            min_unprotected_gb: Minimum unprotected data threshold in GB
            
        Returns:
            Dict with comprehensive operational analysis
        """
        try:
            # Get all volumes first
            volumes_response = await self.get("/api/v1.2/volumes/")
            if "error" in volumes_response:
                return volumes_response
            
            volumes = volumes_response.get("items", [])
            
            analysis = {
                "timestamp": datetime.utcnow().isoformat(),
                "focus_area": focus or "all",
                "filters_applied": {
                    "include_protected": include_protected,
                    "min_unprotected_gb": min_unprotected_gb
                },
                "summary": {
                    "total_volumes_analyzed": len(volumes),
                    "volumes_with_connections": 0,
                    "total_connections": 0,
                    "master_connections": 0,
                    "remote_connections": 0,
                    "volumes_with_unprotected_data": 0,
                    "total_unprotected_data_gb": 0,
                    "total_accessible_data_gb": 0
                },
                "volumes": []
            }
            
            for volume in volumes:
                volume_guid = volume["guid"]
                volume_name = volume.get("name", "Unknown")
                
                # Get filers for this volume
                filer_data = await self.get_volume_filers(volume_guid)
                if "error" in filer_data:
                    continue
                
                filers = filer_data.get("items", [])
                if not filers:
                    continue
                
                volume_analysis = {
                    "volume_guid": volume_guid,
                    "volume_name": volume_name,
                    "filer_connections": []
                }
                
                volume_has_unprotected = False
                volume_unprotected_total = 0
                
                for filer in filers:
                    filer_details = self._extract_filer_details(filer)
                    
                    # Apply filters
                    if not include_protected and filer_details["data_protection"]["fully_protected"]:
                        continue
                    
                    if filer_details["data_protection"]["unprotected_data_gb"] < min_unprotected_gb:
                        continue
                    
                    # Apply focus area filtering
                    if focus:
                        if focus == "snapshots" and not filer_details["snapshot"]["enabled"]:
                            continue
                        elif focus == "sync" and not filer_details["sync"]["enabled"]:
                            continue
                        elif focus == "auditing":
                            # For auditing, include ALL filers to show both enabled and disabled
                            pass
                        elif focus == "data_protection" and filer_details["data_protection"]["fully_protected"]:
                            continue
                    
                    volume_analysis["filer_connections"].append(filer_details)
                    
                    # Update summary statistics
                    analysis["summary"]["total_connections"] += 1
                    if filer_details["is_owner"]:
                        analysis["summary"]["master_connections"] += 1
                    else:
                        analysis["summary"]["remote_connections"] += 1
                    
                    analysis["summary"]["total_accessible_data_gb"] += filer_details["data_protection"]["accessible_data_gb"]
                    
                    if not filer_details["data_protection"]["fully_protected"]:
                        volume_has_unprotected = True
                        volume_unprotected_total += filer_details["data_protection"]["unprotected_data_gb"]
                        analysis["summary"]["total_unprotected_data_gb"] += filer_details["data_protection"]["unprotected_data_gb"]
                
                if volume_analysis["filer_connections"]:
                    if volume_has_unprotected:
                        analysis["summary"]["volumes_with_unprotected_data"] += 1
                        volume_analysis["total_unprotected_gb"] = round(volume_unprotected_total, 2)
                    
                    analysis["summary"]["volumes_with_connections"] += 1
                    analysis["volumes"].append(volume_analysis)
            
            # Round summary values
            analysis["summary"]["total_unprotected_data_gb"] = round(analysis["summary"]["total_unprotected_data_gb"], 2)
            analysis["summary"]["total_accessible_data_gb"] = round(analysis["summary"]["total_accessible_data_gb"], 2)
            
            # Add focus-specific summaries
            if focus == "snapshots":
                analysis["snapshot_analysis"] = self._analyze_snapshots(analysis["volumes"])
            elif focus == "sync":
                analysis["sync_analysis"] = self._analyze_sync(analysis["volumes"])
            elif focus == "auditing":
                analysis["auditing_analysis"] = self._analyze_auditing(analysis["volumes"])
            elif focus == "data_protection":
                analysis["protection_analysis"] = self._analyze_protection(analysis["volumes"])
            
            return analysis
            
        except Exception as e:
            return {"error": f"Failed to analyze volume operations: {str(e)}"}


    def _analyze_snapshots(self, volumes: List[Dict]) -> Dict[str, Any]:
        """Analyze snapshot configurations and health."""
        snapshot_analysis = {
            "enabled_count": 0,
            "disabled_count": 0,
            "stale_snapshots": [],
            "critical_snapshots": [],
            "frequency_distribution": {},
            "never_snapshotted": []
        }
        
        for volume in volumes:
            for filer in volume["filer_connections"]:
                snapshot_info = filer["snapshot"]
                
                if snapshot_info["enabled"]:
                    snapshot_analysis["enabled_count"] += 1
                    
                    # Track frequency distribution
                    freq_hours = snapshot_info["frequency_hours"]
                    freq_key = f"{freq_hours:.1f}h" if freq_hours else "0h"
                    snapshot_analysis["frequency_distribution"][freq_key] = \
                        snapshot_analysis["frequency_distribution"].get(freq_key, 0) + 1
                    
                    # Check for stale snapshots
                    if snapshot_info.get("is_stale"):
                        snapshot_analysis["stale_snapshots"].append({
                            "volume": volume["volume_name"],
                            "filer": filer["filer_serial"],
                            "hours_since": snapshot_info.get("hours_since_last_snapshot"),
                            "last_snapshot": snapshot_info.get("last_snapshot")
                        })
                    
                    # Check for critical snapshots
                    if snapshot_info.get("is_critical"):
                        snapshot_analysis["critical_snapshots"].append({
                            "volume": volume["volume_name"],
                            "filer": filer["filer_serial"],
                            "hours_since": snapshot_info.get("hours_since_last_snapshot"),
                            "last_snapshot": snapshot_info.get("last_snapshot")
                        })
                    
                    # Check if never snapshotted
                    if not snapshot_info.get("last_snapshot"):
                        snapshot_analysis["never_snapshotted"].append({
                            "volume": volume["volume_name"],
                            "filer": filer["filer_serial"]
                        })
                else:
                    snapshot_analysis["disabled_count"] += 1
        
        snapshot_analysis["health_summary"] = {
            "healthy": snapshot_analysis["enabled_count"] - len(snapshot_analysis["stale_snapshots"]),
            "warning": len(snapshot_analysis["stale_snapshots"]) - len(snapshot_analysis["critical_snapshots"]),
            "critical": len(snapshot_analysis["critical_snapshots"])
        }
        
        return snapshot_analysis
    
    def _analyze_sync(self, volumes: List[Dict]) -> Dict[str, Any]:
        """Analyze sync configurations."""
        sync_analysis = {
            "enabled_count": 0,
            "disabled_count": 0,
            "auto_cache_enabled": 0,
            "frequency_distribution": {},
            "daily_sync_count": 0,
            "continuous_sync_count": 0  # frequency <= 5 minutes
        }
        
        for volume in volumes:
            for filer in volume["filer_connections"]:
                sync_info = filer["sync"]
                
                if sync_info["enabled"]:
                    sync_analysis["enabled_count"] += 1
                    
                    if sync_info["auto_cache_allowed"]:
                        sync_analysis["auto_cache_enabled"] += 1
                    
                    # Track frequency
                    freq_minutes = sync_info["frequency_minutes"]
                    if freq_minutes <= 5:
                        sync_analysis["continuous_sync_count"] += 1
                    
                    # Check if daily sync
                    if len(sync_info["active_days"]) == 7:
                        sync_analysis["daily_sync_count"] += 1
                    
                    # Frequency distribution
                    if freq_minutes < 60:
                        freq_key = f"{freq_minutes}min"
                    else:
                        freq_key = f"{freq_minutes/60:.1f}h"
                    
                    sync_analysis["frequency_distribution"][freq_key] = \
                        sync_analysis["frequency_distribution"].get(freq_key, 0) + 1
                else:
                    sync_analysis["disabled_count"] += 1
        
        return sync_analysis
    
    def _analyze_auditing(self, volumes: List[Dict]) -> Dict[str, Any]:
        """Analyze auditing configurations."""
        auditing_analysis = {
            "enabled_count": 0,
            "disabled_count": 0,
            "syslog_export_count": 0,
            "event_coverage": {},
            "retention_distribution": {},
            "comprehensive_auditing": 0  # All events tracked
        }
        
        all_possible_events = ["create", "delete", "rename", "close", "security", "metadata", "write", "read"]
        
        for volume in volumes:
            for filer in volume["filer_connections"]:
                audit_info = filer["auditing"]
                
                if audit_info["enabled"]:
                    auditing_analysis["enabled_count"] += 1
                    
                    if audit_info["syslog_export"]:
                        auditing_analysis["syslog_export_count"] += 1
                    
                    # Check event coverage
                    tracked_events = audit_info["events_tracked"]
                    for event in tracked_events:
                        auditing_analysis["event_coverage"][event] = \
                            auditing_analysis["event_coverage"].get(event, 0) + 1
                    
                    # Check if comprehensive
                    if len(tracked_events) == len(all_possible_events):
                        auditing_analysis["comprehensive_auditing"] += 1
                    
                    # Retention distribution
                    retention_days = audit_info["logs"]["retention_days"]
                    retention_key = f"{retention_days}d"
                    auditing_analysis["retention_distribution"][retention_key] = \
                        auditing_analysis["retention_distribution"].get(retention_key, 0) + 1
                else:
                    auditing_analysis["disabled_count"] += 1
        
        # Calculate compliance percentage
        total = auditing_analysis["enabled_count"] + auditing_analysis["disabled_count"]
        auditing_analysis["compliance_percentage"] = round(
            (auditing_analysis["enabled_count"] / total * 100) if total > 0 else 0, 2
        )
        
        return auditing_analysis
    
    def _analyze_protection(self, volumes: List[Dict]) -> Dict[str, Any]:
        """Analyze data protection status."""
        protection_analysis = {
            "fully_protected_count": 0,
            "at_risk_count": 0,
            "high_risk_connections": [],  # > 100GB unprotected
            "critical_risk_connections": [],  # > 500GB unprotected
            "protection_distribution": {
                "100%": 0,
                "90-99%": 0,
                "75-90%": 0,
                "50-75%": 0,
                "<50%": 0
            },
            "total_accessible_gb": 0,
            "total_unprotected_gb": 0
        }
        
        for volume in volumes:
            for filer in volume["filer_connections"]:
                protection = filer["data_protection"]
                
                protection_analysis["total_accessible_gb"] += protection["accessible_data_gb"]
                protection_analysis["total_unprotected_gb"] += protection["unprotected_data_gb"]
                
                if protection["fully_protected"]:
                    protection_analysis["fully_protected_count"] += 1
                    protection_analysis["protection_distribution"]["100%"] += 1
                else:
                    protection_analysis["at_risk_count"] += 1
                    
                    # Categorize protection level
                    pct = protection["protection_percentage"]
                    if pct >= 90:
                        protection_analysis["protection_distribution"]["90-99%"] += 1
                    elif pct >= 75:
                        protection_analysis["protection_distribution"]["75-90%"] += 1
                    elif pct >= 50:
                        protection_analysis["protection_distribution"]["50-75%"] += 1
                    else:
                        protection_analysis["protection_distribution"]["<50%"] += 1
                    
                    # Identify high risk
                    if protection["unprotected_data_gb"] > 100:
                        risk_entry = {
                            "volume": volume["volume_name"],
                            "filer": filer["filer_serial"],
                            "unprotected_gb": protection["unprotected_data_gb"],
                            "protection_percentage": protection["protection_percentage"]
                        }
                        
                        protection_analysis["high_risk_connections"].append(risk_entry)
                        
                        if protection["unprotected_data_gb"] > 500:
                            protection_analysis["critical_risk_connections"].append(risk_entry)
        
        # Calculate overall protection
        if protection_analysis["total_accessible_gb"] > 0:
            protection_analysis["overall_protection_percentage"] = round(
                (protection_analysis["total_accessible_gb"] - protection_analysis["total_unprotected_gb"]) /
                protection_analysis["total_accessible_gb"] * 100, 2
            )
        else:
            protection_analysis["overall_protection_percentage"] = 100
        
        # Round totals
        protection_analysis["total_accessible_gb"] = round(protection_analysis["total_accessible_gb"], 2)
        protection_analysis["total_unprotected_gb"] = round(protection_analysis["total_unprotected_gb"], 2)
        
        return protection_analysis
    
    async def get_volume_access_summary(self, volume_guid: str) -> Dict[str, Any]:
        """
        Get a clear summary of which filers can access a volume and their roles.
        
        Args:
            volume_guid: The GUID of the volume
            
        Returns:
            Dict with clear ownership and access information
        """
        try:
            data = await self.get_volume_filers(volume_guid)
            
            if "error" in data:
                return data
            
            filers = data.get("items", [])
            
            master_filer = next((f for f in filers if f["type"] == "master"), None)
            remote_filers = [f for f in filers if f["type"] == "remote"]
            
            summary = {
                "volume_guid": volume_guid,
                "volume_name": filers[0]["name"] if filers else "Unknown",
                "ownership": {
                    "has_owner": master_filer is not None,
                    "owner_serial": master_filer["filer_serial_number"] if master_filer else None,
                    "owner_details": {
                        "share_count": master_filer.get("status", {}).get("share_count", 0),
                        "accessible_data_gb": round(
                            master_filer.get("status", {}).get("accessible_data", 0) / (1024**3), 2
                        ) if master_filer else 0,
                        "snapshot_enabled": any(
                            master_filer.get("snapshot_schedule", {}).get("days", {}).values()
                        ) if master_filer else False,
                        "sync_enabled": any(
                            master_filer.get("sync_schedule", {}).get("days", {}).values()
                        ) if master_filer else False
                    } if master_filer else None
                },
                "remote_access": {
                    "enabled": len(remote_filers) > 0,
                    "connection_count": len(remote_filers),
                    "connections": [
                        {
                            "filer_serial": f["filer_serial_number"],
                            "sync_enabled": any(f.get("sync_schedule", {}).get("days", {}).values()),
                            "snapshot_enabled": any(f.get("snapshot_schedule", {}).get("days", {}).values()),
                            "share_count": f.get("status", {}).get("share_count", 0),
                            "accessible_data_gb": round(
                                f.get("status", {}).get("accessible_data", 0) / (1024**3), 2
                            )
                        }
                        for f in remote_filers
                    ]
                },
                "summary": {
                    "total_connections": len(filers),
                    "has_redundancy": len(remote_filers) > 0,
                    "total_shares": sum(f.get("status", {}).get("share_count", 0) for f in filers),
                    "total_accessible_data_gb": round(
                        sum(f.get("status", {}).get("accessible_data", 0) for f in filers) / (1024**3), 2
                    )
                }
            }
            
            return summary
            
        except Exception as e:
            return {"error": f"Failed to get volume access summary: {str(e)}"}
        

    async def test_connection(self) -> bool:
        """Test the API connection."""
        try:
            response = await self.get("/api/v1.2/volumes/")
            return "error" not in response
        except Exception:
            return False