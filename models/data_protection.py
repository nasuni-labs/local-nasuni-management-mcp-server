#!/usr/bin/env python3
"""
Data model for Portal data protection telemetry.
Based on /telemetry/volumes/{guid}/data_propagation_raw endpoint.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from models.base import BaseModel


class DataProtectionSnapshot(BaseModel):
    """
    Model for a single data protection snapshot event.
    
    Represents comprehensive telemetry on when and how data was protected,
    including snapshot phases, file counts, and protection timing metrics.
    """
    
    def _parse_data(self, data: Dict[str, Any]):
        """Parse data protection snapshot data."""
        # Dimension attributes
        self.appliance = data.get("appliance", "")  # Appliance name/description
        self.serial_number = data.get("serial_number", "")  # Appliance serial number
        self.volume = data.get("volume", "")  # Volume GUID
        self.time = data.get("time", 0)  # Metadata snapshot completion time (Unix ms)
        
        # Protection timing metrics
        self.protect_mean = data.get("protect_mean")  # Avg time files remained unprotected (seconds)
        self.protect_max = data.get("protect_max")    # Max time any file remained unprotected (seconds)
        
        # Snapshot phase timestamps (Unix epoch milliseconds)
        self.data_snapshot_start = data.get("data_snapshot_start", 0)
        self.data_snapshot_end = data.get("data_snapshot_end", 0)
        self.metadata_snapshot_start = data.get("metadata_snapshot_start", 0)
        self.metadata_snapshot_end = data.get("metadata_snapshot_end", 0)
        
        # Oldest Unprotected Data
        self.oud = data.get("oud")  # Age in seconds of oldest modified file at snapshot time
        
        # File counts
        self.file_count_ngl = data.get("file_count_ngl")  # Files without Global File Lock
        self.file_count_gl = data.get("file_count_gl")    # Files with Global File Lock
        self.file_count_total = data.get("file_count_total")  # Total files protected
        
        # Directory tracking
        self.dir_count = data.get("dir_count", 0)  # Directory levels impacted
        
        # Restore point version
        self.volume_version = data.get("volume_version", 0)  # Snapshot restore point version number
    
    @property
    def timestamp(self) -> Optional[datetime]:
        """Metadata snapshot completion time as datetime."""
        if self.time:
            try:
                return datetime.fromtimestamp(self.time / 1000.0)
            except:
                return None
        return None
    
    @property
    def timestamp_str(self) -> str:
        """Human-readable completion timestamp."""
        dt = self.timestamp
        return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "Unknown"
    
    @property
    def data_phase_duration_seconds(self) -> Optional[float]:
        """Duration of data snapshot phase in seconds."""
        if self.data_snapshot_start and self.data_snapshot_end:
            return (self.data_snapshot_end - self.data_snapshot_start) / 1000.0
        return None
    
    @property
    def metadata_phase_duration_seconds(self) -> Optional[float]:
        """Duration of metadata snapshot phase in seconds."""
        if self.metadata_snapshot_start and self.metadata_snapshot_end:
            return (self.metadata_snapshot_end - self.metadata_snapshot_start) / 1000.0
        return None
    
    @property
    def total_snapshot_duration_seconds(self) -> Optional[float]:
        """Total snapshot duration from data start to metadata end."""
        if self.data_snapshot_start and self.metadata_snapshot_end:
            return (self.metadata_snapshot_end - self.data_snapshot_start) / 1000.0
        return None
    
    @property
    def protect_mean_seconds(self) -> Optional[float]:
        """Average time files remained unprotected (seconds)."""
        if self.protect_mean:
            try:
                return float(self.protect_mean)
            except:
                return None
        return None
    
    @property
    def protect_max_seconds(self) -> Optional[float]:
        """Maximum time any file remained unprotected (seconds)."""
        if self.protect_max:
            try:
                return float(self.protect_max)
            except:
                return None
        return None
    
    @property
    def oud_seconds(self) -> Optional[int]:
        """Oldest unprotected data age in seconds."""
        return self.oud
    
    @property
    def is_complete(self) -> bool:
        """Check if snapshot has complete data."""
        return (self.protect_mean is not None and 
                self.oud is not None and 
                self.volume_version is not None)
    
    @property
    def has_global_locks(self) -> bool:
        """Check if any files were protected under Global File Lock."""
        return self.file_count_gl is not None and self.file_count_gl > 0
    
    def format_duration(self, seconds: Optional[float]) -> str:
        """Format duration in human-readable way."""
        if seconds is None:
            return "N/A"
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            return f"{seconds / 60:.1f}m"
        else:
            return f"{seconds / 3600:.2f}h"
    
    def get_summary_dict(self) -> Dict[str, Any]:
        """Get summary dictionary with key metrics."""
        return {
            "appliance": self.appliance,
            "serial_number": self.serial_number,
            "volume_version": self.volume_version,
            "timestamp": self.timestamp_str,
            "protect_mean": self.format_duration(self.protect_mean_seconds),
            "protect_max": self.format_duration(self.protect_max_seconds),
            "oud": self.format_duration(self.oud_seconds),
            "data_phase": self.format_duration(self.data_phase_duration_seconds),
            "metadata_phase": self.format_duration(self.metadata_phase_duration_seconds),
            "total_duration": self.format_duration(self.total_snapshot_duration_seconds),
            "files_total": self.file_count_total,
            "files_gfl": self.file_count_gl,
            "files_non_gfl": self.file_count_ngl,
            "directories": self.dir_count,
            "is_complete": self.is_complete
        }


class DataProtectionAnalysis:
    """Comprehensive analysis of data protection snapshots."""
    
    def __init__(self, snapshots: List[DataProtectionSnapshot], metadata: Dict[str, Any] = None):
        self.snapshots = snapshots
        self.complete_snapshots = [s for s in snapshots if s.is_complete]
        self.metadata = metadata or {}
    
    @property
    def latest_snapshot(self) -> Optional[DataProtectionSnapshot]:
        """Get snapshot with highest volume_version (latest restore point)."""
        if self.complete_snapshots:
            return max(self.complete_snapshots, key=lambda s: s.volume_version or 0)
        return None
    
    @property
    def latest_volume_version(self) -> Optional[int]:
        """Get the latest volume version number."""
        if self.latest_snapshot:
            return self.latest_snapshot.volume_version
        return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """Calculate comprehensive statistics across all snapshots."""
        if not self.complete_snapshots:
            return {
                "total_snapshots": len(self.snapshots),
                "complete_snapshots": 0,
                "error": "No complete snapshots available"
            }
        
        latest = self.latest_snapshot
        
        # Group by appliance
        by_appliance = {}
        for snap in self.complete_snapshots:
            if snap.appliance not in by_appliance:
                by_appliance[snap.appliance] = []
            by_appliance[snap.appliance].append(snap)
        
        # Collect metrics
        all_protect_mean = [s.protect_mean_seconds for s in self.complete_snapshots if s.protect_mean_seconds is not None]
        all_protect_max = [s.protect_max_seconds for s in self.complete_snapshots if s.protect_max_seconds is not None]
        all_oud = [s.oud_seconds for s in self.complete_snapshots if s.oud_seconds is not None]
        all_data_phase = [s.data_phase_duration_seconds for s in self.complete_snapshots if s.data_phase_duration_seconds is not None]
        all_metadata_phase = [s.metadata_phase_duration_seconds for s in self.complete_snapshots if s.metadata_phase_duration_seconds is not None]
        all_total_duration = [s.total_snapshot_duration_seconds for s in self.complete_snapshots if s.total_snapshot_duration_seconds is not None]
        all_files = [s.file_count_total for s in self.complete_snapshots if s.file_count_total is not None]
        all_dirs = [s.dir_count for s in self.complete_snapshots if s.dir_count]
        
        stats = {
            "total_snapshots": len(self.snapshots),
            "complete_snapshots": len(self.complete_snapshots),
            "appliances": list(by_appliance.keys()),
            "time_range": {
                "start": self.complete_snapshots[0].timestamp_str,
                "end": self.complete_snapshots[-1].timestamp_str
            }
        }
        
        # Latest snapshot
        if latest:
            stats["latest_snapshot"] = {
                "volume_version": latest.volume_version,
                "appliance": latest.appliance,
                "serial_number": latest.serial_number,
                "completed_at": latest.timestamp_str,
                "protect_mean": latest.format_duration(latest.protect_mean_seconds),
                "protect_max": latest.format_duration(latest.protect_max_seconds),
                "oud": latest.format_duration(latest.oud_seconds),
                "files_protected": latest.file_count_total,
                "has_gfl": latest.has_global_locks
            }
        
        # KEY METRIC: Average data protection time
        if all_protect_mean:
            avg_protection = sum(all_protect_mean) / len(all_protect_mean)
            stats["average_data_protection_time"] = {
                "seconds": avg_protection,
                "human": self._fmt(avg_protection),
                "description": "Average time files remain unprotected before snapshot inclusion"
            }
        
        # Protection anomalies
        if all_protect_max:
            worst_cases = sorted(
                [(s, s.protect_max_seconds) for s in self.complete_snapshots if s.protect_max_seconds],
                key=lambda x: x[1],
                reverse=True
            )[:3]
            
            stats["protection_anomalies"] = {
                "max_unprotected_time_seconds": max(all_protect_max),
                "max_unprotected_time": self._fmt(max(all_protect_max)),
                "worst_cases": [
                    {
                        "appliance": s.appliance,
                        "time": s.timestamp_str,
                        "unprotected_time": self._fmt(duration),
                        "version": s.volume_version
                    }
                    for s, duration in worst_cases
                ]
            }
        
        # OUD statistics
        if all_oud:
            stats["oud_statistics"] = {
                "min": self._fmt(min(all_oud)),
                "max": self._fmt(max(all_oud)),
                "avg": self._fmt(sum(all_oud) / len(all_oud))
            }
        
        # Snapshot phase performance
        if all_data_phase:
            longest_data = max(self.complete_snapshots, key=lambda s: s.data_phase_duration_seconds or 0)
            stats["data_phase_performance"] = {
                "avg": self._fmt(sum(all_data_phase) / len(all_data_phase)),
                "min": self._fmt(min(all_data_phase)),
                "max": self._fmt(max(all_data_phase)),
                "slowest_appliance": longest_data.appliance,
                "slowest_files": longest_data.file_count_total
            }
        
        if all_metadata_phase:
            longest_meta = max(self.complete_snapshots, key=lambda s: s.metadata_phase_duration_seconds or 0)
            stats["metadata_phase_performance"] = {
                "avg": self._fmt(sum(all_metadata_phase) / len(all_metadata_phase)),
                "min": self._fmt(min(all_metadata_phase)),
                "max": self._fmt(max(all_metadata_phase)),
                "slowest_appliance": longest_meta.appliance
            }
        
        # File statistics
        if all_files:
            stats["file_statistics"] = {
                "total_protected": sum(all_files),
                "avg_per_snapshot": sum(all_files) / len(all_files),
                "max_in_snapshot": max(all_files),
                "min_in_snapshot": min(all_files)
            }
        
        # Most active appliance
        snapshot_counts = {app: len(snaps) for app, snaps in by_appliance.items()}
        most_active = max(snapshot_counts.items(), key=lambda x: x[1])
        stats["most_active_appliance"] = {
            "name": most_active[0],
            "snapshots": most_active[1],
            "percentage": (most_active[1] / len(self.complete_snapshots)) * 100
        }
        
        # Per-appliance statistics
        stats["by_appliance"] = {}
        for appliance, snaps in by_appliance.items():
            latest_app = max(snaps, key=lambda s: s.volume_version or 0)
            
            protect_means = [s.protect_mean_seconds for s in snaps if s.protect_mean_seconds]
            protect_maxs = [s.protect_max_seconds for s in snaps if s.protect_max_seconds]
            ouds = [s.oud_seconds for s in snaps if s.oud_seconds]
            files = [s.file_count_total for s in snaps if s.file_count_total]
            
            stats["by_appliance"][appliance] = {
                "serial_number": latest_app.serial_number,
                "snapshots": len(snaps),
                "latest_version": latest_app.volume_version,
                "latest_time": latest_app.timestamp_str,
                "avg_protect_time": self._fmt(sum(protect_means) / len(protect_means)) if protect_means else "N/A",
                "worst_protect_time": self._fmt(max(protect_maxs)) if protect_maxs else "N/A",
                "avg_oud": self._fmt(sum(ouds) / len(ouds)) if ouds else "N/A",
                "total_files": sum(files) if files else 0
            }
        
        return stats
    
    def get_insights(self) -> List[str]:
        """Generate actionable insights."""
        insights = []
        
        if not self.complete_snapshots:
            insights.append("⚠️ No complete snapshot data available")
            return insights
        
        stats = self.get_statistics()
        
        # Latest snapshot
        if stats.get("latest_snapshot"):
            latest = stats["latest_snapshot"]
            insights.append(f"📌 Latest: Version {latest['volume_version']} by {latest['appliance']} at {latest['completed_at']}")
        
        # Average protection time (KEY METRIC)
        if stats.get("average_data_protection_time"):
            avg = stats["average_data_protection_time"]
            if avg["seconds"] > 180:
                insights.append(f"🚨 Files unprotected avg {avg['human']} - consider more frequent snapshots")
            elif avg["seconds"] > 90:
                insights.append(f"⚠️ Files unprotected avg {avg['human']}")
            else:
                insights.append(f"✅ Good protection time: avg {avg['human']}")
        
        # Anomalies
        if stats.get("protection_anomalies"):
            anom = stats["protection_anomalies"]
            worst = anom["worst_cases"][0]
            insights.append(f"⚠️ Worst case: {worst['appliance']} had files unprotected for {worst['unprotected_time']}")
        
        # Performance
        if stats.get("data_phase_performance"):
            data = stats["data_phase_performance"]
            if data.get("slowest_files") and int(data.get("slowest_files", 0)) > 50:
                insights.append(f"📊 Largest snapshot: {data['slowest_files']} files on {data['slowest_appliance']} ({data['max']})")
        
        # Activity
        if stats.get("most_active_appliance"):
            active = stats["most_active_appliance"]
            if active["percentage"] > 60:
                insights.append(f"📈 {active['name']} created {active['percentage']:.0f}% of snapshots ({active['snapshots']} versions)")
        
        # Comparison
        if len(stats.get("by_appliance", {})) > 1:
            apps = stats["by_appliance"]
            protect_times = {k: v.get("avg_protect_time") for k, v in apps.items() if v.get("avg_protect_time") != "N/A"}
            
            if len(protect_times) > 1:
                # Find slowest
                slowest_app = max(
                    [(k, v) for k, v in apps.items() if v.get("avg_protect_time") != "N/A"],
                    key=lambda x: self._parse_duration(x[1].get("avg_protect_time", "0s"))
                )
                insights.append(f"🔍 Slowest appliance: {slowest_app[0]} (avg {slowest_app[1]['avg_protect_time']})")
        
        return insights
    
    def _fmt(self, seconds: Optional[float]) -> str:
        """Format duration."""
        if seconds is None:
            return "N/A"
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            return f"{seconds / 60:.1f}m"
        else:
            return f"{seconds / 3600:.2f}h"
    
    def _parse_duration(self, duration_str: str) -> float:
        """Parse duration string back to seconds for comparison."""
        if duration_str == "N/A":
            return 0
        try:
            if 's' in duration_str:
                return float(duration_str.replace('s', ''))
            elif 'm' in duration_str:
                return float(duration_str.replace('m', '')) * 60
            elif 'h' in duration_str:
                return float(duration_str.replace('h', '')) * 3600
        except:
            return 0
        return 0