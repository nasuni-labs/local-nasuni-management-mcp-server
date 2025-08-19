#!/usr/bin/env python3
"""Output formatting utilities."""

from typing import List, Dict, Any
from models.cloud_credential import CloudCredential
from models.filer import Filer
from models.volume import Volume


def format_filers_output(filers: List[Filer], detailed: bool = False) -> str:
    """Format filers data for output."""
    if not filers:
        return "No filers found."
    
    total_filers = len(filers)
    online_filers = sum(1 for f in filers if f.status.is_online)
    offline_filers = total_filers - online_filers
    
    output = f"""FILERS INFORMATION

=== SUMMARY ===
Total Filers: {total_filers}
Online Filers: {online_filers}
Offline Filers: {offline_filers}

=== DETAILED FILER DATA ===
"""
    
    for i, filer in enumerate(filers, 1):
        status_icon = "🟢 Online" if filer.status.is_online else "🔴 Offline"
        summary = filer.get_summary_dict()
        
        output += f"""
--- Filer {i}: {summary['description']} ---
Status: {status_icon}
Serial Number: {summary['serial_number']}
GUID: {summary['guid']}
Build Version: {summary['build']}
OS Version: {summary['osversion']}
Current Version: {summary['current_version']}
Platform: {summary['platform']}
Management State: {summary['management_state']}

Network:
  - Hostname: {summary['hostname']}
  - IP Addresses: {', '.join(summary['ip_addresses'])}
  - Timezone: {summary['timezone']}

Hardware:
  - CPU: {summary['cpu_cores']} cores, {summary['cpu_model']}
  - Memory: {summary['memory_mb']} MB
  - Cache Size: {summary['cache_size_gb']} GB
  - Cache Used: {summary['cache_used_gb']} GB ({summary['cache_used_percent']:.1f}%)

System:
  - Uptime: {summary['uptime']} seconds ({summary['uptime_days']} days)

"""
        
        if detailed:
            # Add more detailed information for single filer view
            output += f"""Advanced Details:
  - Links: {filer.links}
  - CIFS Settings: {filer.settings.cifs}
  - FTP Settings: {filer.settings.ftp}
  - QoS Settings: {filer.settings.qos}
  - SNMP Settings: {filer.settings.snmp}
  - Remote Support: {filer.settings.remote_support}

"""
    
    return output


def format_filer_statistics(stats: Dict[str, Any]) -> str:
    """Format filer statistics for output."""
    output = f"""FILER STATISTICS

=== OVERVIEW ===
Total Filers: {stats['total']}
Online: {stats['online']} ({stats['online']/stats['total']*100:.1f}%)
Offline: {stats['offline']} ({stats['offline']/stats['total']*100:.1f}%)

=== CACHE USAGE ===
Total Cache Size: {stats['total_cache_size_gb']} GB
Total Cache Used: {stats['total_cache_used_gb']} GB
Average Usage: {stats['average_cache_usage_percent']}%

=== PLATFORMS ===
"""
    
    for platform in stats.get('platforms', []):
        output += f"  - {platform}\n"
    
    output += "\n=== SOFTWARE VERSIONS ===\n"
    for version in stats.get('versions', []):
        output += f"  - {version}\n"
    
    return output


def format_volumes_output(volumes: List[Volume], show_filer_serial: bool = True) -> str:
    """Format volumes data for output."""
    if not volumes:
        return "No volumes found."
    
    total_volumes = len(volumes)
    cifs_volumes = sum(1 for v in volumes if v.is_cifs)
    nfs_volumes = sum(1 for v in volumes if v.is_nfs)
    public_volumes = sum(1 for v in volumes if v.auth and v.auth.is_public)
    
    output = f"""VOLUMES INFORMATION

=== SUMMARY ===
Total Volumes: {total_volumes}
CIFS Volumes: {cifs_volumes}
NFS Volumes: {nfs_volumes}
Public Volumes: {public_volumes}

=== DETAILED VOLUME DATA ===
"""
    
    for i, volume in enumerate(volumes, 1):
        summary = volume.get_summary_dict()
        
        # Access indicators
        access_icon = "🌐 Public" if summary['is_public'] else "🔒 Private"
        antivirus_icon = "🛡️ Protected" if summary['antivirus_enabled'] else "⚠️ Unprotected"
        quota_info = f"{summary['quota_gb']} GB" if summary['has_quota'] else "No Limit"
        
        output += f"""
--- Volume {i}: {summary['name']} ---
Access: {access_icon}
Antivirus: {antivirus_icon}
GUID: {summary['guid']}
"""
        
        if show_filer_serial:
            output += f"Filer Serial: {summary['filer_serial_number']}\n"
        
        output += f"""Protocols: {summary['protocols']}
Provider: {summary['provider_name']} ({summary['provider_location']})
Quota: {quota_info}
NMC Managed: {'Yes' if summary['nmc_managed'] else 'No'}

Configuration:
  - Case Sensitive: {'Yes' if summary['case_sensitive'] else 'No'}
  - Compression: {'Enabled' if summary['compression_enabled'] else 'Disabled'}
  - Remote Access: {'Enabled' if summary['remote_access_enabled'] else 'Disabled'}
  - Retention: {'Infinite' if summary['retention_infinite'] else 'Limited'}

Filer Access:
  - Enabled Filers: {summary['enabled_filers_count']}
  - Read-Only: {summary['readonly_filers_count']}
  - Read-Write: {summary['readwrite_filers_count']}

"""
    
    return output


def format_volume_statistics(stats: Dict[str, Any]) -> str:
    """Format volume statistics for output."""
    output = f"""VOLUME STATISTICS

=== OVERVIEW ===
Total Volumes: {stats['total']}
CIFS Volumes: {stats['cifs_volumes']} ({stats['cifs_volumes']/stats['total']*100:.1f}%)
NFS Volumes: {stats['nfs_volumes']} ({stats['nfs_volumes']/stats['total']*100:.1f}%)
Public Volumes: {stats['public_volumes']} ({stats['public_volumes']/stats['total']*100:.1f}%)

=== SECURITY & MANAGEMENT ===
Antivirus Enabled: {stats['antivirus_enabled']} ({stats['antivirus_enabled']/stats['total']*100:.1f}%)
NMC Managed: {stats['nmc_managed']} ({stats['nmc_managed']/stats['total']*100:.1f}%)
Case Sensitive: {stats['case_sensitive']} ({stats['case_sensitive']/stats['total']*100:.1f}%)

=== FEATURES ===
Compression Enabled: {stats['compression_enabled']} ({stats['compression_enabled']/stats['total']*100:.1f}%)
Remote Access Enabled: {stats['remote_access_enabled']} ({stats['remote_access_enabled']/stats['total']*100:.1f}%)
Quoted Volumes: {stats['quoted_volumes']} ({stats['quoted_volumes']/stats['total']*100:.1f}%)
Total Quota: {stats['total_quota_gb']} GB

=== CLOUD PROVIDERS ===
"""
    
    for provider, count in stats.get('providers', {}).items():
        percentage = count / stats['total'] * 100
        output += f"  - {provider}: {count} volumes ({percentage:.1f}%)\n"
    
    output += "\n=== LOCATIONS ===\n"
    for location, count in stats.get('locations', {}).items():
        percentage = count / stats['total'] * 100
        output += f"  - {location}: {count} volumes ({percentage:.1f}%)\n"
    
    return output


def format_health_status(filers: List[Filer]) -> str:
    """Format health status overview."""
    if not filers:
        return "No filers to analyze."
    
    # Analyze health metrics
    high_cache_usage = [f for f in filers if f.status.platform.cache_status.percent_used > 80]
    offline_filers = [f for f in filers if not f.status.is_online]
    low_uptime = [f for f in filers if f.status.uptime_days < 1]
    
    output = "FILER HEALTH STATUS\n\n"
    
    if not any([high_cache_usage, offline_filers, low_uptime]):
        output += "✅ All filers appear healthy!\n"
    else:
        output += "⚠️ Issues detected:\n\n"
        
        if offline_filers:
            output += f"🔴 OFFLINE FILERS ({len(offline_filers)}):\n"
            for filer in offline_filers:
                output += f"  - {filer.description} ({filer.settings.network_settings.hostname})\n"
            output += "\n"
        
        if high_cache_usage:
            output += f"🟡 HIGH CACHE USAGE ({len(high_cache_usage)}):\n"
            for filer in high_cache_usage:
                output += f"  - {filer.description}: {filer.status.platform.cache_status.percent_used:.1f}%\n"
            output += "\n"
        
        if low_uptime:
            output += f"🟡 RECENTLY RESTARTED ({len(low_uptime)}):\n"
            for filer in low_uptime:
                output += f"  - {filer.description}: {filer.status.uptime_days} days uptime\n"
    
    return output


def format_volume_security_analysis(volumes: List[Volume]) -> str:
    """Format volume security analysis."""
    if not volumes:
        return "No volumes to analyze."
    
    # Security analysis
    public_volumes = [v for v in volumes if v.auth and v.auth.is_public]
    unprotected_volumes = [v for v in volumes if not v.antivirus_enabled]
    unlimited_volumes = [v for v in volumes if not v.has_quota]
    
    output = "VOLUME SECURITY ANALYSIS\n\n"
    
    if not any([public_volumes, unprotected_volumes]):
        output += "✅ No security issues detected!\n"
    else:
        output += "⚠️ Security considerations:\n\n"
        
        if public_volumes:
            output += f"🌐 PUBLIC VOLUMES ({len(public_volumes)}):\n"
            for volume in public_volumes:
                output += f"  - {volume.name} ({volume.protocols.protocol_list})\n"
            output += "\n"
        
        if unprotected_volumes:
            output += f"🛡️ UNPROTECTED VOLUMES ({len(unprotected_volumes)}):\n"
            for volume in unprotected_volumes:
                output += f"  - {volume.name} (No antivirus)\n"
            output += "\n"
        
        if unlimited_volumes:
            output += f"💾 UNLIMITED VOLUMES ({len(unlimited_volumes)}):\n"
            for volume in unlimited_volumes:
                output += f"  - {volume.name} (No quota set)\n"
    
    return output#!/usr/bin/env python3
"""Output formatting utilities."""

from typing import List, Dict, Any
from models.filer import Filer


def format_filers_output(filers: List[Filer], detailed: bool = False) -> str:
    """Format filers data for output."""
    if not filers:
        return "No filers found."
    
    total_filers = len(filers)
    online_filers = sum(1 for f in filers if f.status.is_online)
    offline_filers = total_filers - online_filers
    
    output = f"""FILERS INFORMATION

=== SUMMARY ===
Total Filers: {total_filers}
Online Filers: {online_filers}
Offline Filers: {offline_filers}

=== DETAILED FILER DATA ===
"""
    
    for i, filer in enumerate(filers, 1):
        status_icon = "🟢 Online" if filer.status.is_online else "🔴 Offline"
        summary = filer.get_summary_dict()
        
        output += f"""
--- Filer {i}: {summary['description']} ---
Status: {status_icon}
Serial Number: {summary['serial_number']}
GUID: {summary['guid']}
Build Version: {summary['build']}
OS Version: {summary['osversion']}
Current Version: {summary['current_version']}
Platform: {summary['platform']}
Management State: {summary['management_state']}

Network:
  - Hostname: {summary['hostname']}
  - IP Addresses: {', '.join(summary['ip_addresses'])}
  - Timezone: {summary['timezone']}

Hardware:
  - CPU: {summary['cpu_cores']} cores, {summary['cpu_model']}
  - Memory: {summary['memory_mb']} MB
  - Cache Size: {summary['cache_size_gb']} GB
  - Cache Used: {summary['cache_used_gb']} GB ({summary['cache_used_percent']:.1f}%)

System:
  - Uptime: {summary['uptime']} seconds ({summary['uptime_days']} days)

"""
        
        if detailed:
            # Add more detailed information for single filer view
            output += f"""Advanced Details:
  - Links: {filer.links}
  - CIFS Settings: {filer.settings.cifs}
  - FTP Settings: {filer.settings.ftp}
  - QoS Settings: {filer.settings.qos}
  - SNMP Settings: {filer.settings.snmp}
  - Remote Support: {filer.settings.remote_support}

"""
    
    return output


def format_filer_statistics(stats: Dict[str, Any]) -> str:
    """Format filer statistics for output."""
    output = f"""FILER STATISTICS

=== OVERVIEW ===
Total Filers: {stats['total']}
Online: {stats['online']} ({stats['online']/stats['total']*100:.1f}%)
Offline: {stats['offline']} ({stats['offline']/stats['total']*100:.1f}%)

=== CACHE USAGE ===
Total Cache Size: {stats['total_cache_size_gb']} GB
Total Cache Used: {stats['total_cache_used_gb']} GB
Average Usage: {stats['average_cache_usage_percent']}%

=== PLATFORMS ===
"""
    
    for platform in stats.get('platforms', []):
        output += f"  - {platform}\n"
    
    output += "\n=== SOFTWARE VERSIONS ===\n"
    for version in stats.get('versions', []):
        output += f"  - {version}\n"
    
    return output


def format_health_status(filers: List[Filer]) -> str:
    """Format health status overview."""
    if not filers:
        return "No filers to analyze."
    
    # Analyze health metrics
    high_cache_usage = [f for f in filers if f.status.platform.cache_status.percent_used > 80]
    offline_filers = [f for f in filers if not f.status.is_online]
    low_uptime = [f for f in filers if f.status.uptime_days < 1]
    
    output = "FILER HEALTH STATUS\n\n"
    
    if not any([high_cache_usage, offline_filers, low_uptime]):
        output += "✅ All filers appear healthy!\n"
    else:
        output += "⚠️ Issues detected:\n\n"
        
        if offline_filers:
            output += f"🔴 OFFLINE FILERS ({len(offline_filers)}):\n"
            for filer in offline_filers:
                output += f"  - {filer.description} ({filer.settings.network_settings.hostname})\n"
            output += "\n"
        
        if high_cache_usage:
            output += f"🟡 HIGH CACHE USAGE ({len(high_cache_usage)}):\n"
            for filer in high_cache_usage:
                output += f"  - {filer.description}: {filer.status.platform.cache_status.percent_used:.1f}%\n"
            output += "\n"
        
        if low_uptime:
            output += f"🟡 RECENTLY RESTARTED ({len(low_uptime)}):\n"
            for filer in low_uptime:
                output += f"  - {filer.description}: {filer.status.uptime_days} days uptime\n"
    
    return output

def format_cloud_credentials_output(credentials: List['CloudCredential']) -> str:
    """Format cloud credentials data for output."""
    if not credentials:
        return "No cloud credentials found."
    
    # Group credentials by unique UUID
    unique_creds = {}
    for cred in credentials:
        if cred.cred_uuid not in unique_creds:
            unique_creds[cred.cred_uuid] = {
                "name": cred.name,
                "provider": cred.cloud_provider,
                "account": cred.account,
                "hostname": cred.hostname,
                "deployments": []
            }
        unique_creds[cred.cred_uuid]["deployments"].append({
            "filer": cred.filer_serial_number,
            "status": cred.status,
            "in_use": cred.in_use
        })
    
    total_deployments = len(credentials)
    unique_count = len(unique_creds)
    in_use_count = sum(1 for c in credentials if c.in_use)
    
    output = f"""CLOUD CREDENTIALS INFORMATION

=== SUMMARY ===
Total Deployments: {total_deployments}
Unique Credentials: {unique_count}
In Use: {in_use_count}
Not In Use: {total_deployments - in_use_count}

=== DETAILED CREDENTIAL DATA ===
"""
    
    for i, (uuid, info) in enumerate(unique_creds.items(), 1):
        deployment_count = len(info["deployments"])
        in_use_deployments = sum(1 for d in info["deployments"] if d["in_use"])
        
        output += f"""
--- Credential {i}: {info['name']} ---
UUID: {uuid}
Provider: {info['provider']}
Account: {info['account']}
Hostname: {info['hostname']}
Deployments: {deployment_count} filer(s)
In Use: {in_use_deployments}/{deployment_count} deployment(s)

Filer Deployments:
"""
        for dep in info["deployments"]:
            status_icon = "✓" if dep["in_use"] else "✗"
            output += f"  {status_icon} Filer: {dep['filer']}\n"
            output += f"     Status: {dep['status']}, In Use: {dep['in_use']}\n"
    
    return output


def format_credential_statistics(stats: Dict[str, Any]) -> str:
    """Format cloud credential statistics for output."""
    output = f"""CLOUD CREDENTIAL STATISTICS

=== OVERVIEW ===
Total Deployments: {stats['total_deployments']}
Unique Credentials: {stats['unique_credentials']}
In Use: {stats['in_use']} ({stats['in_use']/stats['total_deployments']*100:.1f}%)
Not In Use: {stats['not_in_use']} ({stats['not_in_use']/stats['total_deployments']*100:.1f}%)
Synced: {stats['synced']} ({stats['synced']/stats['total_deployments']*100:.1f}%)

=== DEPLOYMENT ===
Filers with Credentials: {stats['filers_with_credentials']}
Average Credentials per Filer: {stats['avg_credentials_per_filer']}
Multi-Filer Credentials: {stats['multi_filer_credentials']}

=== CLOUD PROVIDERS ===
"""
    
    for provider, count in stats.get('providers', {}).items():
        percentage = count / stats['total_deployments'] * 100
        output += f"  - {provider}: {count} deployments ({percentage:.1f}%)\n"
    
    if stats.get('multi_filer_details'):
        output += "\n=== MULTI-FILER CREDENTIALS ===\n"
        for uuid, info in stats['multi_filer_details'].items():
            output += f"\n{info['name']} ({uuid[:8]}...)\n"
            output += f"  Provider: {info['provider']}\n"
            output += f"  Deployed to {len(info['filers'])} filers\n"
    
    return output


def format_credential_security_analysis(credentials: List['CloudCredential']) -> str:
    """Format cloud credential security analysis."""
    if not credentials:
        return "No credentials to analyze."
    
    # Security analysis
    not_synced = [c for c in credentials if not c.is_synced]
    not_in_use = [c for c in credentials if not c.in_use]
    skip_validation = [c for c in credentials if c.skip_validation]
    
    # Group by provider
    providers = {}
    for cred in credentials:
        if cred.cloud_provider not in providers:
            providers[cred.cloud_provider] = []
        providers[cred.cloud_provider].append(cred.name)
    
    output = "CLOUD CREDENTIAL SECURITY ANALYSIS\n\n"
    
    if not any([not_synced, not_in_use]):
        output += "✓ All credentials appear properly configured!\n"
    else:
        output += "Issues detected:\n\n"
        
        if not_synced:
            output += f"NOT SYNCED ({len(not_synced)}):\n"
            for cred in not_synced:
                output += f"  - {cred.name} on filer {cred.filer_serial_number}\n"
            output += "\n"
        
        if not_in_use:
            output += f"NOT IN USE ({len(not_in_use)}):\n"
            unique_unused = {}
            for cred in not_in_use:
                if cred.name not in unique_unused:
                    unique_unused[cred.name] = []
                unique_unused[cred.name].append(cred.filer_serial_number)
            
            for name, filers in unique_unused.items():
                output += f"  - {name} (on {len(filers)} filer(s))\n"
            output += "\n"
        
        if skip_validation:
            output += f"VALIDATION SKIPPED ({len(skip_validation)}):\n"
            unique_skip = set(c.name for c in skip_validation)
            for name in unique_skip:
                output += f"  - {name}\n"
    
    output += "\n=== PROVIDER DISTRIBUTION ===\n"
    for provider, creds in providers.items():
        unique_creds = set(creds)
        output += f"  {provider}: {len(unique_creds)} unique credential(s)\n"
    
    return output

# Add these functions to utils/formatting.py

def format_notifications_output(notifications: List) -> str:
    """Format notifications data for output."""
    if not notifications:
        return "No notifications found."
    
    total = len(notifications)
    
    # Group by priority
    by_priority = {"error": 0, "warning": 0, "info": 0, "other": 0}
    for notif in notifications:
        if notif.is_error:
            by_priority["error"] += 1
        elif notif.is_warning:
            by_priority["warning"] += 1
        elif notif.is_info:
            by_priority["info"] += 1
        else:
            by_priority["other"] += 1
    
    output = f"""NOTIFICATIONS

=== SUMMARY ===
Total: {total}
🔴 Errors: {by_priority['error']}
🟡 Warnings: {by_priority['warning']}
🔵 Info: {by_priority['info']}

=== RECENT NOTIFICATIONS ===
"""
    
    # Show first 20 notifications
    for notif in notifications[:20]:
        icon = "🔴" if notif.is_error else "🟡" if notif.is_warning else "🔵"
        urgent = "🚨" if notif.urgent else ""
        ack = "✓" if notif.acknowledged else "○"
        
        output += f"\n{icon} [{notif.date}] {urgent}\n"
        output += f"   {ack} {notif.name}: {notif.message}\n"
        output += f"   Origin: {notif.origin}\n"
        
        if notif.volume_name:
            output += f"   Volume: {notif.volume_name}\n"
    
    if total > 20:
        output += f"\n... and {total - 20} more notifications\n"
    
    return output


def format_notification_statistics(stats: Dict[str, Any]) -> str:
    """Format notification statistics for output."""
    total = stats.get('total', 0)
    
    output = f"""NOTIFICATION STATISTICS

=== OVERVIEW ===
Total Notifications: {total}
Acknowledged: {stats.get('acknowledged', 0)}
Unacknowledged: {stats.get('unacknowledged', 0)}
Urgent: {stats.get('urgent', 0)}

=== RECENT ACTIVITY ===
Last Hour: {stats.get('recent_1h', 0)}
Last 24 Hours: {stats.get('recent_24h', 0)}

=== BY PRIORITY ===
"""
    
    for priority, count in stats.get('by_priority', {}).items():
        percentage = (count / total * 100) if total > 0 else 0
        output += f"  {priority.capitalize()}: {count} ({percentage:.1f}%)\n"
    
    output += "\n=== TOP ORIGINS ===\n"
    origins = sorted(stats.get('by_origin', {}).items(), key=lambda x: x[1], reverse=True)[:5]
    for origin, count in origins:
        percentage = (count / total * 100) if total > 0 else 0
        output += f"  {origin}: {count} ({percentage:.1f}%)\n"
    
    output += "\n=== MOST FREQUENT NOTIFICATIONS ===\n"
    for msg_type, count in list(stats.get('top_messages', {}).items())[:5]:
        output += f"  {msg_type}: {count} occurrences\n"
    
    return output