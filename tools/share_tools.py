#!/usr/bin/env python3
"""Share-related MCP tools."""

import json
from typing import Dict, Any, List
from mcp.types import TextContent
from tools.base_tool import BaseTool
from api.shares_api import SharesAPIClient



class ListSharesTool(BaseTool):
    """Tool to list all SMB/CIFS shares."""
    
    def __init__(self, api_client: SharesAPIClient):
        super().__init__(
            name="list_shares",
            description="Lists all SMB/CIFS network shares (NOT volumes). Returns SMB shares and CIFS Shares across all filers and volumes. Shows share names, paths, permissions, and access settings. Use this when asked about 'shares', 'network shares', 'SMB shares', 'CIFS shares', or 'Windows shares'." \
            "Contains share details such as readonly shares, browseable (Visible Share), comments, Allowed Hosts (hosts_allow), Hide Unreadable Files (hide_unreadable), Previous Versions (enable_previous_vers), Case-Sensitive Paths (case_sensitive), Snapshot Directories (enable_snapshot_dirs)," \
            "Sync and Mobile Access (mobile), Web Access(browser_access), Asynchronous I/O (aio_enabled), Block files (veto_files), Support for Mac OS X (fruit_enabled), and SMB Encryption (smb_encrypt)"
        )
        self.api_client = api_client
        
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the list shares tool."""
        try:
            shares = await self.api_client.get_shares_as_models()
            
            if not shares:
                raw_response = await self.api_client.list_shares()
                if "error" in raw_response:
                    return self.format_error(f"Failed to fetch shares: {raw_response['error']}")
                else:
                    return [TextContent(type="text", text="No shares found.")]
            
            output = self._format_shares_output(shares)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _format_shares_output(self, shares: List) -> str:
        """Format shares output."""
        
        # Get statistics
        total_shares = len(shares)
        readonly_shares = sum(1 for s in shares if s.is_readonly)
        readwrite_shares = sum(1 for s in shares if s.is_readwrite)
        browser_enabled = sum(1 for s in shares if s.has_browser_access)
        mobile_enabled = sum(1 for s in shares if s.has_mobile_access)
        
        output = f"""SMB/CIFS SHARES INFORMATION

=== SUMMARY ===
Total Shares: {total_shares}
Read-Only Shares: {readonly_shares}
Read-Write Shares: {readwrite_shares}
Browser Access Enabled: {browser_enabled}
Mobile Access Enabled: {mobile_enabled}

=== DETAILED SHARE DATA ===
"""
        
        # Group shares by filer for better organization
        shares_by_filer = {}
        for share in shares:
            filer_serial = share.filer_serial_number
            if filer_serial not in shares_by_filer:
                shares_by_filer[filer_serial] = []
            shares_by_filer[filer_serial].append(share)
        
        for filer_serial, filer_shares in shares_by_filer.items():
            output += f"\n📁 FILER: {filer_serial} ({len(filer_shares)} shares)\n"
            
            for i, share in enumerate(filer_shares, 1):
                summary = share.get_summary_dict()
                
                # Access indicators
                permission_icon = "📖" if summary['readonly'] else "✏️"
                browser_icon = "🌐" if summary['browser_access'] else ""
                mobile_icon = "📱" if summary['mobile_access'] else ""
                path_type = "🏠 Root" if summary['is_root_share'] else f"📂 {summary['path']}"
                
                output += f"""
  {permission_icon} {summary['name']} {browser_icon}{mobile_icon}
     Path: {path_type}
     Volume: {summary['volume_guid']}
     Permission: {summary['permission']}
     Access Methods: {', '.join(summary['access_methods'])}
     Browseable: {'Yes' if summary['browseable'] else 'No'}
"""
                
                if summary['comment']:
                    output += f"     Comment: {summary['comment']}\n"
                
                if summary['veto_files']:
                    output += f"     Vetoed Files: {summary['veto_files']}\n"
        
        return output



class ListSharesRawTool(BaseTool):
    """Tool to list shares with complete raw API data."""
    
    def __init__(self, api_client: SharesAPIClient):
        super().__init__(
            name="list_shares_raw",
            description="Returns raw API data for all shares including all fields like enable_previous_vers, fruit_enabled, audit_enabled, etc. Use this to see complete share configuration details."
        )
        self.api_client = api_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "filer_serial": {
                    "type": "string",
                    "description": "Optional: Filter by filer serial number"
                },
                "fields_filter": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional: List of specific fields to include (e.g., ['share_name', 'enable_previous_vers', 'fruit_enabled'])"
                },
                "format": {
                    "type": "string",
                    "enum": ["json", "table"],
                    "description": "Output format: 'json' for full JSON or 'table' for tabular view (default: json)"
                }
            },
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the raw shares list tool."""
        try:
            # Get raw API response
            raw_response = await self.api_client.list_shares()
            
            if "error" in raw_response:
                return self.format_error(f"Failed to fetch shares: {raw_response['error']}")
            
            shares_data = raw_response.get("items", [])
            if not shares_data:
                return [TextContent(type="text", text="No shares found.")]
            
            # Filter by filer if requested
            filer_filter = arguments.get("filer_serial", "").strip()
            if filer_filter:
                shares_data = [s for s in shares_data if s.get("filer_serial_number") == filer_filter]
                if not shares_data:
                    return [TextContent(type="text", text=f"No shares found for filer: {filer_filter}")]
            
            # Filter fields if requested
            fields_filter = arguments.get("fields_filter", [])
            if fields_filter:
                filtered_data = []
                for share in shares_data:
                    filtered_share = {field: share.get(field) for field in fields_filter if field in share}
                    # Always include share_name for identification
                    if "share_name" not in filtered_share:
                        filtered_share["share_name"] = share.get("share_name", "Unknown")
                    filtered_data.append(filtered_share)
                shares_data = filtered_data
            
            # Format output
            output_format = arguments.get("format", "json").lower()
            
            if output_format == "table":
                output = self._format_as_table(shares_data, fields_filter)
            else:
                output = self._format_as_json(shares_data, filer_filter)
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _format_as_json(self, shares_data: List[Dict], filer_filter: str) -> str:
        """Format output as JSON."""
        title = f"RAW SHARE DATA FOR FILER {filer_filter}" if filer_filter else "RAW SHARE DATA FOR ALL FILERS"
        
        output = f"{title}\n\n"
        output += f"Total Shares: {len(shares_data)}\n\n"
        
        # Show some key fields summary if they exist
        if shares_data and not any("fields_filter" in s for s in shares_data):
            sample = shares_data[0]
            output += "=== AVAILABLE FIELDS ===\n"
            output += f"Total fields per share: {len(sample)}\n"
            
            # Check for interesting boolean fields
            boolean_fields = []
            for key, value in sample.items():
                if isinstance(value, bool):
                    boolean_fields.append(key)
            
            if boolean_fields:
                output += f"Boolean fields: {', '.join(boolean_fields[:10])}\n"
                if len(boolean_fields) > 10:
                    output += f"  ... and {len(boolean_fields) - 10} more\n"
            
            output += "\n"
        
        output += "=== COMPLETE JSON DATA ===\n"
        output += json.dumps(shares_data, indent=2)
        
        return output
    
    def _format_as_table(self, shares_data: List[Dict], fields_filter: List[str]) -> str:
        """Format output as a table."""
        if not shares_data:
            return "No data to display."
        
        # Determine columns to show
        if fields_filter:
            columns = fields_filter
            if "share_name" not in columns:
                columns = ["share_name"] + columns
        else:
            # Default important columns
            columns = [
                "share_name",
                "filer_serial_number",
                "path",
                "readonly",
                "enable_previous_vers",
                "fruit_enabled",
                "enable_browser_access",
                "enable_mobile_access",
                "audit_enabled"
            ]
            # Only include columns that exist
            columns = [c for c in columns if c in shares_data[0]]
        
        output = "SHARES DATA TABLE VIEW\n\n"
        output += f"Showing {len(shares_data)} shares with {len(columns)} fields\n\n"
        
        # Create table header
        header = " | ".join(self._truncate(col, 20) for col in columns)
        output += header + "\n"
        output += "-" * len(header) + "\n"
        
        # Add data rows
        for share in shares_data:
            row = []
            for col in columns:
                value = share.get(col, "N/A")
                if isinstance(value, bool):
                    value = "✔" if value else "✗"
                elif value is None:
                    value = "N/A"
                else:
                    value = str(value)
                row.append(self._truncate(value, 20))
            output += " | ".join(row) + "\n"
        
        # Add summary of boolean fields
        output += "\n=== BOOLEAN FIELDS SUMMARY ===\n"
        for col in columns:
            if all(isinstance(s.get(col), bool) for s in shares_data if col in s):
                true_count = sum(1 for s in shares_data if s.get(col) == True)
                false_count = sum(1 for s in shares_data if s.get(col) == False)
                output += f"{col}: {true_count} ✔, {false_count} ✗\n"
        
        return output
    
    def _truncate(self, text: str, max_length: int) -> str:
        """Truncate text to max length."""
        text = str(text)
        if len(text) <= max_length:
            return text.ljust(max_length)
        return text[:max_length-3] + "...".ljust(3)


class AnalyzeShareFieldTool(BaseTool):
    """Tool to analyze any field in share configurations."""
    
    def __init__(self, api_client: SharesAPIClient):
        super().__init__(
            name="analyze_share_field",
            description="Analyze shares based on any field in the API data. Can check for enable_previous_vers, fruit_enabled, or any other field. Shows which shares have specific field values."
        )
        self.api_client = api_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "field_name": {
                    "type": "string",
                    "description": "The field name to analyze (e.g., 'enable_previous_vers', 'fruit_enabled', 'audit_enabled')"
                },
                "field_value": {
                    "description": "Optional: The specific value to look for. If not provided, shows all values for the field"
                },
                "filer_serial": {
                    "type": "string",
                    "description": "Optional: Filter by filer serial number"
                },
                "show_fields": {
                    "type": "boolean",
                    "description": "Optional: Show all available fields in the first share as reference"
                }
            },
            "required": ["field_name"],
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the field analysis."""
        try:
            # Get raw API response
            raw_response = await self.api_client.list_shares()
            
            if "error" in raw_response:
                return self.format_error(f"Failed to fetch shares: {raw_response['error']}")
            
            shares_data = raw_response.get("items", [])
            if not shares_data:
                return [TextContent(type="text", text="No shares found.")]
            
            # Show available fields if requested
            if arguments.get("show_fields", False):
                return self._show_available_fields(shares_data)
            
            field_name = arguments.get("field_name", "").strip()
            if not field_name:
                return self.format_error("field_name is required")
            
            # Filter by filer if requested
            filer_filter = arguments.get("filer_serial", "").strip()
            if filer_filter:
                shares_data = [s for s in shares_data if s.get("filer_serial_number") == filer_filter]
                if not shares_data:
                    return [TextContent(type="text", text=f"No shares found for filer: {filer_filter}")]
            
            # Analyze the specified field
            output = self._analyze_field(shares_data, field_name, arguments.get("field_value"), filer_filter)
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _show_available_fields(self, shares_data: List[Dict]) -> List[TextContent]:
        """Show all available fields from the first share."""
        if not shares_data:
            return [TextContent(type="text", text="No shares available to show fields.")]
        
        first_share = shares_data[0]
        
        output = "AVAILABLE FIELDS IN SHARE DATA\n\n"
        output += f"Sample from share: {first_share.get('share_name', 'Unknown')}\n\n"
        output += "=== ALL FIELDS ===\n"
        
        # Group fields by type
        boolean_fields = []
        string_fields = []
        other_fields = []
        
        for key, value in sorted(first_share.items()):
            if isinstance(value, bool):
                boolean_fields.append(f"  {key}: {value}")
            elif isinstance(value, str):
                value_display = f"'{value[:50]}...'" if len(value) > 50 else f"'{value}'"
                string_fields.append(f"  {key}: {value_display}")
            else:
                other_fields.append(f"  {key}: {type(value).__name__}")
        
        if boolean_fields:
            output += "\nBoolean Fields:\n" + "\n".join(boolean_fields) + "\n"
        if string_fields:
            output += "\nString Fields:\n" + "\n".join(string_fields) + "\n"
        if other_fields:
            output += "\nOther Fields:\n" + "\n".join(other_fields) + "\n"
        
        output += "\n=== COMMON ANALYSIS FIELDS ===\n"
        output += "  enable_previous_vers - Previous versions/snapshots enabled\n"
        output += "  fruit_enabled - macOS/AFP compatibility features\n"
        output += "  audit_enabled - Audit logging enabled\n"
        output += "  readonly - Share is read-only\n"
        output += "  browseable - Share is visible when browsing\n"
        output += "  enable_browser_access - Web browser access enabled\n"
        output += "  enable_mobile_access - Mobile access enabled\n"
        output += "  hidden - Share is hidden\n"
        
        return [TextContent(type="text", text=output)]
    
    def _analyze_field(self, shares_data: List[Dict], field_name: str, field_value: Any, filer_filter: str) -> str:
        """Analyze a specific field across all shares."""
        # Check if field exists in any share
        field_exists = any(field_name in share for share in shares_data)
        
        if not field_exists:
            # Try to find similar fields
            all_fields = set()
            for share in shares_data:
                all_fields.update(share.keys())
            
            similar = [f for f in all_fields if field_name.lower() in f.lower() or f.lower() in field_name.lower()]
            
            output = f"Field '{field_name}' not found in share data.\n\n"
            if similar:
                output += f"Did you mean one of these?\n"
                for field in similar[:5]:
                    output += f"  - {field}\n"
            else:
                output += "Use 'show_fields: true' to see all available fields.\n"
            return output
        
        # Analyze the field
        title = f"ANALYSIS OF FIELD: {field_name}"
        if filer_filter:
            title += f" (Filer: {filer_filter})"
        
        # Group shares by field value
        by_value = {}
        for share in shares_data:
            value = share.get(field_name, "NOT_SET")
            if value not in by_value:
                by_value[value] = []
            by_value[value].append(share)
        
        # If looking for specific value
        if field_value is not None:
            matching = by_value.get(field_value, [])
            
            output = f"{title}\n\n"
            output += f"Looking for: {field_name} = {field_value}\n\n"
            output += f"=== RESULTS ===\n"
            output += f"Matching Shares: {len(matching)}/{len(shares_data)}\n\n"
            
            if matching:
                output += f"=== SHARES WITH {field_name} = {field_value} ===\n\n"
                
                # Group by filer
                by_filer = {}
                for share in matching:
                    filer = share.get("filer_serial_number", "unknown")
                    if filer not in by_filer:
                        by_filer[filer] = []
                    by_filer[filer].append(share)
                
                for filer, shares in sorted(by_filer.items()):
                    output += f"📁 FILER: {filer} ({len(shares)} shares)\n\n"
                    for share in sorted(shares, key=lambda x: x.get("share_name", "")):
                        output += self._format_share_details(share, field_name)
            else:
                output += f"No shares found with {field_name} = {field_value}\n"
        
        else:
            # Show distribution of all values
            output = f"{title}\n\n"
            output += f"=== VALUE DISTRIBUTION ===\n"
            output += f"Total Shares: {len(shares_data)}\n\n"
            
            for value, shares in sorted(by_value.items(), key=lambda x: len(x[1]), reverse=True):
                percentage = len(shares) / len(shares_data) * 100
                output += f"{value}: {len(shares)} shares ({percentage:.1f}%)\n"
            
            output += f"\n=== DETAILED BREAKDOWN ===\n"
            
            for value, shares in sorted(by_value.items()):
                output += f"\n{field_name} = {value} ({len(shares)} shares):\n"
                output += "-" * 40 + "\n"
                
                # Show first few shares as examples
                for share in shares[:3]:
                    name = share.get("share_name", "Unknown")
                    filer = share.get("filer_serial_number", "unknown")
                    path = share.get("path", "/")
                    output += f"  • {name} (Filer: {filer[:8]}..., Path: {path})\n"
                
                if len(shares) > 3:
                    output += f"  ... and {len(shares) - 3} more\n"
        
        # Add insights based on the field
        output += self._add_field_insights(field_name, by_value, len(shares_data))
        
        return output
    
    def _format_share_details(self, share: Dict, highlight_field: str) -> str:
        """Format share details with highlighted field."""
        name = share.get("share_name", "Unknown")
        path = share.get("path", "/")
        volume = share.get("volume_guid", "unknown")[:8] + "..."
        
        # Handle Windows backslash paths
        if path in ["/", "\\", ""]:
            path_display = "🏠 Root"
        else:
            path_display = f"📂 {path}"
        
        output = f"  ✓ {name}\n"
        output += f"     Path: {path_display}\n"
        output += f"     Volume: {volume}\n"
        output += f"     {highlight_field}: {share.get(highlight_field, 'NOT_SET')}\n"
        
        # Add other relevant fields
        if share.get("enable_browser_access"):
            output += f"     Browser Access: Yes\n"
        if share.get("enable_mobile_access"):
            output += f"     Mobile Access: Yes\n"
        if share.get("readonly"):
            output += f"     Permission: Read-Only\n"
        
        output += "\n"
        return output
    
    def _add_field_insights(self, field_name: str, by_value: Dict, total: int) -> str:
        """Add insights based on the field being analyzed."""
        output = "\n=== INSIGHTS ===\n"
        
        if field_name == "enable_previous_vers":
            enabled = len(by_value.get(True, []))
            if enabled == 0:
                output += "⚠️ No shares have previous versions enabled - users cannot restore files from snapshots\n"
            elif enabled < total * 0.5:
                output += f"⚠️ Only {enabled}/{total} shares have previous versions enabled\n"
            else:
                output += f"✅ {enabled}/{total} shares have previous versions enabled for file recovery\n"
        
        elif field_name == "fruit_enabled":
            enabled = len(by_value.get(True, []))
            if enabled > 0:
                output += f"🍎 {enabled} shares have macOS/AFP compatibility features enabled\n"
                output += "   This improves compatibility for Mac clients accessing these shares\n"
            else:
                output += "ℹ️ No shares have macOS/AFP features enabled\n"
        
        elif field_name == "audit_enabled":
            enabled = len(by_value.get(True, []))
            if enabled == 0:
                output += "⚠️ No shares have audit logging enabled - file access is not being tracked\n"
            else:
                output += f"📝 {enabled}/{total} shares have audit logging enabled\n"
        
        elif field_name == "readonly":
            readonly = len(by_value.get(True, []))
            output += f"🔒 {readonly} read-only shares, {total - readonly} read-write shares\n"
        
        elif field_name == "hidden":
            hidden = len(by_value.get(True, []))
            if hidden > 0:
                output += f"👻 {hidden} shares are hidden from browse lists\n"
        
        return output


class GetShareStatsTool(BaseTool):
    """Tool to get share statistics."""
    
    def __init__(self, api_client: SharesAPIClient):
        super().__init__(
            name="get_share_stats",
            description="Get comprehensive statistics about SMB/CIFS shares including permission distribution, access methods, and usage patterns across filers and volumes."
        )
        self.api_client = api_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the share statistics tool."""
        try:
            stats = await self.api_client.get_share_statistics()
            
            if "error" in stats:
                return self.format_error(stats["error"])
            
            output = self._format_share_statistics(stats)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _format_share_statistics(self, stats: Dict[str, Any]) -> str:
        """Format share statistics output."""
        
        total = stats['total']
        
        output = f"""SMB/CIFS SHARE STATISTICS

=== OVERVIEW ===
Total Shares: {total}
Read-Only Shares: {stats['readonly_shares']} ({stats['readonly_shares']/total*100:.1f}%)
Read-Write Shares: {stats['readwrite_shares']} ({stats['readwrite_shares']/total*100:.1f}%)

=== ACCESS METHODS ===
Browser Access Enabled: {stats['browser_access_enabled']} ({stats['browser_access_enabled']/total*100:.1f}%)
Mobile Access Enabled: {stats['mobile_access_enabled']} ({stats['mobile_access_enabled']/total*100:.1f}%)

=== SHARE TYPES ===
Root Volume Shares: {stats['root_shares']} ({stats['root_shares']/total*100:.1f}%)
Subfolder Shares: {stats['subfolder_shares']} ({stats['subfolder_shares']/total*100:.1f}%)

=== DISTRIBUTION ===
Unique Filers with Shares: {stats['unique_filers']}
Unique Volumes with Shares: {stats['unique_volumes']}
Average Shares per Filer: {stats['avg_shares_per_filer']}
Average Shares per Volume: {stats['avg_shares_per_volume']}

=== TOP ACTIVITY ===
"""
        
        if stats['most_active_filer']:
            filer_serial, share_count = stats['most_active_filer']
            output += f"Most Active Filer: {filer_serial} ({share_count} shares)\n"
        
        if stats['most_shared_volume']:
            volume_guid, share_count = stats['most_shared_volume']
            output += f"Most Shared Volume: {volume_guid} ({share_count} shares)\n"
        
        return output


class GetSharesByFilerTool(BaseTool):
    """Tool to get shares for a specific filer."""
    
    def __init__(self, api_client: SharesAPIClient):
        super().__init__(
            name="get_shares_by_filer",
            description="Get all SMB/CIFS shares hosted on a specific filer/appliance by serial number. This shows the actual network shares that users can connect to (like \\\\server\\sharename). Use this when someone asks 'what shares exist on [filer]' or 'what can users access from [appliance]'."
        )
        self.api_client = api_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "filer_serial": {
                    "type": "string",
                    "description": "The serial number of the filer/appliance"
                }
            },
            "required": ["filer_serial"],
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the filer shares tool."""
        try:
            filer_serial = arguments.get("filer_serial", "").strip()
            if not filer_serial:
                return self.format_error("Filer serial number is required")
            
            shares = await self.api_client.get_shares_by_filer(filer_serial)
            
            if not shares:
                return [TextContent(
                    type="text", 
                    text=f"No shares found for filer: {filer_serial}"
                )]
            
            output = f"SMB/CIFS SHARES FOR FILER: {filer_serial}\n\n"
            output += f"Total Shares: {len(shares)}\n\n"
            
            # Group by volume
            shares_by_volume = {}
            for share in shares:
                vol_guid = share.volume_guid
                if vol_guid not in shares_by_volume:
                    shares_by_volume[vol_guid] = []
                shares_by_volume[vol_guid].append(share)
            
            for volume_guid, vol_shares in shares_by_volume.items():
                output += f"📂 VOLUME: {volume_guid} ({len(vol_shares)} shares)\n"
                
                for share in vol_shares:
                    summary = share.get_summary_dict()
                    permission_icon = "📖" if summary['readonly'] else "✏️"
                    access_icons = ""
                    if summary['browser_access']:
                        access_icons += "🌐"
                    if summary['mobile_access']:
                        access_icons += "📱"
                    
                    # Handle Windows backslash paths properly
                    path = summary['path']
                    if path == "\\":
                        path_display = "/ (Root)"
                    else:
                        path_display = path
                    
                    output += f"""
  {permission_icon} {summary['name']} {access_icons}
     Path: {path_display}
     Permission: {summary['permission']}
     Browseable: {'Yes' if summary['browseable'] else 'No'}
     Access: {', '.join(summary['access_methods'])}
"""
                output += "\n"
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")


class GetBrowserAccessibleSharesTool(BaseTool):
    """Tool to get shares with browser access enabled."""
    
    def __init__(self, api_client: SharesAPIClient):
        super().__init__(
            name="get_browser_accessible_shares",
            description="Get all SMB/CIFS shares that have browser access enabled. These shares can be accessed via web browser in addition to traditional file sharing protocols."
        )
        self.api_client = api_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the browser accessible shares tool."""
        try:
            shares = await self.api_client.get_browser_accessible_shares()
            
            if not shares:
                return [TextContent(
                    type="text", 
                    text="No shares with browser access enabled found."
                )]
            
            output = f"BROWSER-ACCESSIBLE SHARES ({len(shares)} found)\n\n"
            output += "These shares can be accessed via web browser:\n\n"
            
            for i, share in enumerate(shares, 1):
                summary = share.get_summary_dict()
                permission_icon = "📖" if summary['readonly'] else "✏️"
                mobile_icon = "📱" if summary['mobile_access'] else ""
                
                # Handle Windows backslash paths properly
                path = summary['path']
                if path == '\\':
                    path_display = '/ (Root)'
                else:
                    path_display = path
                
                output += f"""🌐 {summary['name']} {permission_icon}{mobile_icon}
   Filer: {summary['filer_serial_number']}
   Volume: {summary['volume_guid']}
   Path: {path_display}
   Permission: {summary['permission']}
   Access Methods: {', '.join(summary['access_methods'])}

"""
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")


class GetSharesByVolumeTool(BaseTool):
    """Tool to get all shares for a specific volume."""
    
    def __init__(self, api_client: SharesAPIClient):
        super().__init__(
            name="get_shares_by_volume",
            description="Get all SMB/CIFS shares created on a specific volume across all filers. Shows how a volume is exposed through different network shares."
        )
        self.api_client = api_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "volume_guid": {
                    "type": "string",
                    "description": "The GUID of the volume"
                }
            },
            "required": ["volume_guid"],
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the volume shares tool."""
        try:
            volume_guid = arguments.get("volume_guid", "").strip()
            if not volume_guid:
                return self.format_error("Volume GUID is required")
            
            shares = await self.api_client.get_shares_by_volume(volume_guid)
            
            if not shares:
                return [TextContent(
                    type="text", 
                    text=f"No shares found for volume: {volume_guid}"
                )]
            
            output = f"SHARES FOR VOLUME: {volume_guid}\n\n"
            output += f"Total Shares: {len(shares)}\n\n"
            
            # Group by filer
            shares_by_filer = {}
            for share in shares:
                filer_serial = share.filer_serial_number
                if filer_serial not in shares_by_filer:
                    shares_by_filer[filer_serial] = []
                shares_by_filer[filer_serial].append(share)
            
            for filer_serial, filer_shares in shares_by_filer.items():
                output += f"🖥️ FILER: {filer_serial} ({len(filer_shares)} shares)\n"
                
                for share in filer_shares:
                    summary = share.get_summary_dict()
                    permission_icon = "📖" if summary['readonly'] else "✏️"
                    access_icons = ""
                    if summary['browser_access']:
                        access_icons += "🌐"
                    if summary['mobile_access']:
                        access_icons += "📱"
                    
                    # Handle Windows backslash paths properly
                    path = summary['path']
                    if path == "\\":
                        path_display = "/ (Root)"
                    else:
                        path_display = path
                    
                    output += f"""
  {permission_icon} {summary['name']} {access_icons}
     Path: {path_display}
     Permission: {summary['permission']}
     Access: {', '.join(summary['access_methods'])}
"""
                output += "\n"
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
        
class GetSharesPreviousVersionsTool(BaseTool):
    """Tool to check which shares have previous versions enabled."""
    
    def __init__(self, api_client: SharesAPIClient):
        super().__init__(
            name="get_shares_previous_versions",
            description="Check which shares have previous versions (snapshots) enabled. Shows the enable_previous_vers field for all shares."
        )
        self.api_client = api_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "filer_serial": {
                    "type": "string",
                    "description": "Optional: Filter by filer serial number"
                },
                "show_raw": {
                    "type": "boolean",
                    "description": "Optional: Show raw API data with all fields"
                }
            },
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the previous versions check."""
        try:
            # Get raw API response first
            raw_response = await self.api_client.list_shares()
            
            if "error" in raw_response:
                return self.format_error(f"Failed to fetch shares: {raw_response['error']}")
            
            shares_data = raw_response.get("items", [])
            if not shares_data:
                return [TextContent(type="text", text="No shares found.")]
            
            # Filter by filer if requested
            filer_filter = arguments.get("filer_serial", "").strip()
            if filer_filter:
                shares_data = [s for s in shares_data if s.get("filer_serial_number") == filer_filter]
                if not shares_data:
                    return [TextContent(type="text", text=f"No shares found for filer: {filer_filter}")]
            
            # Analyze previous versions settings
            output = self._analyze_previous_versions(shares_data, filer_filter)
            
            # Add raw data if requested
            if arguments.get("show_raw", False):
                output += "\n\n=== RAW API DATA ===\n"
                # Show only relevant fields for first few shares as example
                sample_data = []
                for share in shares_data[:3]:
                    sample_data.append({
                        "share_name": share.get("share_name"),
                        "enable_previous_vers": share.get("enable_previous_vers"),
                        "path": share.get("path"),
                        "volume_guid": share.get("volume_guid"),
                        "filer_serial_number": share.get("filer_serial_number")
                    })
                output += json.dumps(sample_data, indent=2)
                output += f"\n... and {len(shares_data) - 3} more shares"
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _analyze_previous_versions(self, shares_data: List[Dict], filer_filter: str = "") -> str:
        """Analyze previous versions settings for shares."""
        # Group shares by filer
        by_filer = {}
        for share in shares_data:
            filer = share.get("filer_serial_number", "unknown")
            if filer not in by_filer:
                by_filer[filer] = []
            by_filer[filer].append(share)
        
        # Count statistics
        total_shares = len(shares_data)
        prev_vers_enabled = sum(1 for s in shares_data if s.get("enable_previous_vers", False))
        prev_vers_disabled = total_shares - prev_vers_enabled
        
        # Build output
        title = f"PREVIOUS VERSIONS STATUS FOR FILER {filer_filter}" if filer_filter else "PREVIOUS VERSIONS STATUS FOR ALL SHARES"
        
        output = f"""{title}

=== SUMMARY ===
Total Shares: {total_shares}
Previous Versions Enabled: {prev_vers_enabled} ({prev_vers_enabled/total_shares*100:.1f}%)
Previous Versions Disabled: {prev_vers_disabled} ({prev_vers_disabled/total_shares*100:.1f}%)

=== DETAILED STATUS BY FILER ===
"""
        
        for filer, shares in sorted(by_filer.items()):
            filer_enabled = sum(1 for s in shares if s.get("enable_previous_vers", False))
            filer_total = len(shares)
            
            output += f"\n📁 FILER: {filer}\n"
            output += f"   Total Shares: {filer_total}\n"
            output += f"   Previous Versions Enabled: {filer_enabled}/{filer_total}\n\n"
            
            # List shares with their status
            for share in sorted(shares, key=lambda x: x.get("share_name", "")):
                name = share.get("share_name", "Unknown")
                path = share.get("path", "/")
                volume = share.get("volume_guid", "unknown")[:8] + "..."
                prev_vers = share.get("enable_previous_vers", False)
                
                status_icon = "✅" if prev_vers else "❌"
                
                # Handle Windows backslash paths properly
                if path in ["/", "\\", ""]:
                    path_display = "🏠 Root"
                else:
                    path_display = f"📂 {path}"
                
                output += f"   {status_icon} {name}\n"
                output += f"      Path: {path_display}\n"
                output += f"      Volume: {volume}\n"
                output += f"      Previous Versions: {'ENABLED' if prev_vers else 'DISABLED'}\n"
                
                # Add additional relevant fields if present
                if share.get("enable_browser_access"):
                    output += f"      Browser Access: Yes\n"
                if share.get("enable_mobile_access"):
                    output += f"      Mobile Access: Yes\n"
                if share.get("readonly"):
                    output += f"      Permission: Read-Only\n"
                
                output += "\n"
        
        # Add insights
        output += "=== INSIGHTS ===\n"
        
        if prev_vers_enabled == 0:
            output += "⚠️ No shares have previous versions enabled - users cannot restore files from snapshots\n"
        elif prev_vers_enabled < total_shares * 0.5:
            output += f"⚠️ Only {prev_vers_enabled}/{total_shares} shares have previous versions enabled\n"
        else:
            output += f"✅ {prev_vers_enabled}/{total_shares} shares have previous versions enabled for file recovery\n"
        
        # Find shares that might benefit from previous versions
        important_shares = []
        for share in shares_data:
            if not share.get("enable_previous_vers", False):
                # Check if it's a root share or has browser/mobile access (likely important)
                if (share.get("path", "/") in ["/", "\\", ""] or 
                    share.get("enable_browser_access") or 
                    share.get("enable_mobile_access")):
                    important_shares.append(share.get("share_name", "Unknown"))
        
        if important_shares:
            output += f"\n💡 Consider enabling previous versions for these shares:\n"
            for name in important_shares[:5]:
                output += f"   - {name}\n"
            if len(important_shares) > 5:
                output += f"   ... and {len(important_shares) - 5} more\n"
        
        return output