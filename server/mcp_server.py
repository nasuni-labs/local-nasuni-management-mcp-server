#!/usr/bin/env python3
"""MCP Server implementation with consolidated volume-filer tools."""

import sys
from typing import List, Dict, Any
from mcp.server import Server
from mcp.types import Tool, TextContent
from tools.registry import ToolRegistry
from api.filers_api import FilersAPIClient
from config.settings import config
from api.filer_health_api import FilerHealthAPIClient
from api.auth_api import AuthAPIClient


class MCPServer:
    """Main MCP Server class with improved tool management."""
    
    def __init__(self, name: str = "nasuni-management-mcp-server"):
        self.server = Server(name)
        self.tool_registry = ToolRegistry()
        self._setup_tools()
        self._register_handlers()
        self._print_tool_summary()
    
    def _setup_tools(self):
        """Setup and register all tools with improved error handling."""
        print("\n🚀 Setting up MCP Server tools...", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        
        # Setup Filers API client and tools
        filers_client = FilersAPIClient(config.filers_config)
        self.tool_registry.register_filer_tools(filers_client)
        
        # Setup Shares API client and tools
        shares_client = None
        try:
            from api.shares_api import SharesAPIClient
            if hasattr(config, 'shares_config'):
                shares_client = SharesAPIClient(config.shares_config)
            else:
                shares_client = SharesAPIClient(config.filers_config)  # Fallback to filers config
            self.tool_registry.register_share_tools(shares_client)
        except (ImportError, AttributeError) as e:
            print(f"⚠️ Shares tools not available: {e}", file=sys.stderr)
        
        # Setup Volumes API client and tools
        volumes_client = None
        try:
            from api.volumes_api import VolumesAPIClient
            if hasattr(config, 'volumes_config'):
                volumes_client = VolumesAPIClient(config.volumes_config)
            else:
                volumes_client = VolumesAPIClient(config.filers_config)  # Fallback to filers config
            self.tool_registry.register_volume_tools(volumes_client, filers_client)
        except (ImportError, AttributeError) as e:
            print(f"⚠️ Volume tools not available: {e}", file=sys.stderr)
        
        # Setup Filer Health API client and tools
        filer_health_client = FilerHealthAPIClient(config.filers_config)
        self.tool_registry.register_filer_health_tools(filer_health_client)
        
        # Setup Authentication API client and tools
        auth_client = AuthAPIClient(config.filers_config)
        self.tool_registry.register_auth_tools(auth_client)
        
        # Setup Cloud Credentials API client and tools
        try:
            from api.cloud_credentials_api import CloudCredentialsAPIClient
            cloud_creds_client = CloudCredentialsAPIClient(config.filers_config)
            self.tool_registry.register_cloud_credential_tools(cloud_creds_client, volumes_client)
        except (ImportError, AttributeError) as e:
            print(f"⚠️ Cloud credential tools not available: {e}", file=sys.stderr)
        
        # Setup Notifications API client and tools
        try:
            from api.notifications_api import NotificationsAPIClient
            notifications_client = NotificationsAPIClient(config.filers_config)
            self.tool_registry.register_notification_tools(notifications_client)
        except (ImportError, AttributeError) as e:
            print(f"⚠️ Notification tools not available: {e}", file=sys.stderr)
        
        # Setup Volume-Filer Details API client and tools (CONSOLIDATED VERSION)
        try:
            from api.volume_filer_details_api import VolumeFilerDetailsAPIClient
            
            # Create volume-filer details client
            volume_filer_details_client = VolumeFilerDetailsAPIClient(config.filers_config)
            
            # Register consolidated volume-filer details tools
            if volumes_client is not None:
                self.tool_registry.register_volume_filer_details_tools(
                    volume_filer_details_client, 
                    volumes_client
                )
                print("✅ Volume-Filer Details tools registered (consolidated version)", file=sys.stderr)
            else:
                print("⚠️ Volume-Filer Details tools require Volumes API - skipping", file=sys.stderr)
                
        except (ImportError, AttributeError) as e:
            print(f"⚠️ Volume-Filer Details tools not available: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
        
        print("=" * 60, file=sys.stderr)
    
    def _register_handlers(self):
        """Register MCP server handlers."""
        
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List available tools."""
            return self.tool_registry.get_tool_list()
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle tool calls with improved error handling."""
            print(f"\n🔧 Calling tool: {name}", file=sys.stderr)
            print(f"   Arguments: {arguments}", file=sys.stderr)
            
            try:
                result = await self.tool_registry.execute_tool(name, arguments)
                
                # Log result summary
                if result and len(result) > 0:
                    text_length = len(result[0].text) if hasattr(result[0], 'text') else 0
                    if "❌ Error:" in result[0].text:
                        print(f"   Result: ❌ Error in response", file=sys.stderr)
                    else:
                        print(f"   Result: ✅ Success ({text_length} chars)", file=sys.stderr)
                else:
                    print(f"   Result: ⚠️ Empty response", file=sys.stderr)
                
                return result
                
            except Exception as e:
                print(f"   Result: ❌ Exception: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc(file=sys.stderr)
                return [TextContent(
                    type="text",
                    text=f"❌ Error executing tool '{name}': {str(e)}"
                )]
    
    def _print_tool_summary(self):
        """Print a summary of registered tools."""
        stats = self.tool_registry.get_tool_stats()
        
        print("\n📊 Tool Registration Summary", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print(f"Total Tools Registered: {stats['total_tools']}", file=sys.stderr)
        
        if stats.get('categories'):
            print("\nTools by Category:", file=sys.stderr)
            for category, info in stats['categories'].items():
                print(f"\n  {category.upper()} ({info['count']} tools):", file=sys.stderr)
                for tool in info['tools']:
                    print(f"    • {tool}", file=sys.stderr)
        
        # Special note about volume-filer consolidation
        if 'volume_filer' in stats.get('categories', {}):
            vf_tools = stats['categories']['volume_filer']['tools']
            if 'analyze_volume_operations' in vf_tools:
                print("\n📌 Note: Volume-Filer Analysis Consolidation", file=sys.stderr)
                print("  The 'analyze_volume_operations' tool consolidates:", file=sys.stderr)
                print("    • Snapshot analysis (focus='snapshots')", file=sys.stderr)
                print("    • Sync analysis (focus='sync')", file=sys.stderr)
                print("    • Auditing analysis (focus='auditing')", file=sys.stderr)
                print("    • Data protection analysis (focus='data_protection')", file=sys.stderr)
                print("    • Comprehensive analysis (no focus parameter)", file=sys.stderr)
        
        print("\n" + "=" * 60, file=sys.stderr)
        print("✅ MCP Server ready!", file=sys.stderr)
    
    def add_api_tools(self, api_name: str, client_class, config_attr: str):
        """Add tools for a new API dynamically."""
        try:
            api_config = getattr(config, config_attr, config.filers_config)  # Fallback to filers_config
            client = client_class(api_config)
            
            # Register tools based on the API type
            # This would need to be implemented per API
            print(f"✅ Added {api_name} API tools", file=sys.stderr)
            
        except AttributeError as e:
            print(f"⚠️ Configuration for {api_name} not found: {e}", file=sys.stderr)
        except Exception as e:
            print(f"❌ Failed to add {api_name} tools: {e}", file=sys.stderr)
    
    def get_server(self) -> Server:
        """Get the underlying MCP server."""
        return self.server
    
    def get_tool_info(self) -> Dict[str, Any]:
        """Get detailed information about registered tools."""
        return {
            'server_name': self.server.name,
            'tool_count': len(self.tool_registry.tools),
            'tool_names': self.tool_registry.get_tool_names(),
            'statistics': self.tool_registry.get_tool_stats()
        }