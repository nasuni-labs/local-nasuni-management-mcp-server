#!/usr/bin/env python3
"""Enhanced main entry point with better error handling and diagnostics."""

import asyncio
import sys
from mcp.server.stdio import stdio_server
from api.auth_api import AuthAPIClient
from server.mcp_server import MCPServer
from api.filers_api import FilersAPIClient
from api.volumes_api import VolumesAPIClient
from config.settings import config
from config.logging_setup import setup_logging, get_logger

logger = get_logger(__name__)

async def main():
    """Main entry point for the MCP server."""
    print("🚀 Starting NMC MCP server...", file=sys.stderr)
    setup_logging()

    logger.debug("check")
    try:
        # Create and configure the server
        mcp_server = MCPServer("nasuni-management-mcp-server")
        server = mcp_server.get_server()
        
        print(f"✅ Server initialized with {len(mcp_server.tool_registry.get_tool_names())} tools", file=sys.stderr)
        
        # Start the server
        async with stdio_server() as streams:
            print("🔌 MCP server connected via stdio", file=sys.stderr)
            await server.run(
                streams[0], 
                streams[1], 
                server.create_initialization_options()
            )
    except KeyboardInterrupt:
        print("Server stopped by user", file=sys.stderr)
    except Exception as e:
        print(f"MCP server error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        raise


async def diagnose_system():
    """Comprehensive system diagnosis."""
    print("🔍 SYSTEM DIAGNOSIS", file=sys.stderr)
    print("=" * 50, file=sys.stderr)
    
    # 1. Configuration check
    print("📋 Configuration Check:", file=sys.stderr)
    try:
        print(f"   Filers API URL: {config.filers_config.base_url}", file=sys.stderr)
        print(f"   API Token: {'✅ Present' if config.filers_config.token else '❌ Missing'}", file=sys.stderr)
        print(f"   SSL Verification: {config.filers_config.verify_ssl}", file=sys.stderr)
        print(f"   Timeout: {config.filers_config.timeout}s", file=sys.stderr)
        
        # Check if shares and volumes configs exist
        if hasattr(config, 'shares_config'):
            print("   Shares Config: ✅ Available", file=sys.stderr)
        else:
            print("   Shares Config: ❌ Missing", file=sys.stderr)
            
        if hasattr(config, 'volumes_config'):
            print("   Volumes Config: ✅ Available", file=sys.stderr)
        else:
            print("   Volumes Config: ❌ Missing", file=sys.stderr)
            
    except Exception as e:
        print(f"   ❌ Configuration error: {e}", file=sys.stderr)
    
    # 2. API connectivity test
    print("\n🌐 API Connectivity:", file=sys.stderr)
    
    # Test Filers API
    try:
        filers_client = FilersAPIClient(config.filers_config)
        filers_success = await filers_client.test_connection()
        if filers_success:
            print("   Filers API: ✅ Connected", file=sys.stderr)
            try:
                stats = await filers_client.get_filer_statistics()
                print(f"   Filers Found: {stats.get('total', 0)}", file=sys.stderr)
            except Exception as e:
                print(f"   Filers Data: ❌ {e}", file=sys.stderr)
        else:
            print("   Filers API: ❌ Connection failed", file=sys.stderr)
    except Exception as e:
        print(f"   Filers API: ❌ {e}", file=sys.stderr)
    
    # Test Volumes API
    try:
        volumes_client = VolumesAPIClient(config.filers_config)  # Assuming same config
        volumes_success = await volumes_client.test_connection()
        if volumes_success:
            print("   Volumes API: ✅ Connected", file=sys.stderr)
            try:
                stats = await volumes_client.get_volume_statistics()
                print(f"   Volumes Found: {stats.get('total', 0)}", file=sys.stderr)
            except Exception as e:
                print(f"   Volumes Data: ❌ {e}", file=sys.stderr)
        else:
            print("   Volumes API: ❌ Connection failed", file=sys.stderr)
    except Exception as e:
        print(f"   Volumes API: ❌ {e}", file=sys.stderr)
    
    # 3. Tool registration test
    print("\n🛠️  Tool Registration:", file=sys.stderr)
    try:
        mcp_server = MCPServer("nmc-diagnosis-server")
        tools = mcp_server.tool_registry.get_tool_names()
        print(f"   Total Tools: {len(tools)}", file=sys.stderr)
        for tool in tools:
            print(f"   - {tool}", file=sys.stderr)
    except Exception as e:
        print(f"   ❌ Tool registration error: {e}", file=sys.stderr)
    
    print("\n" + "=" * 50, file=sys.stderr)
    print("🏁 Diagnosis Complete", file=sys.stderr)


    # Add to the diagnose_system function in main.py

    # Test Cloud Credentials API
    try:
        from api.cloud_credentials_api import CloudCredentialsAPIClient
        cloud_creds_client = CloudCredentialsAPIClient(config.filers_config)
        creds_success = await cloud_creds_client.test_connection()
        if creds_success:
            print("   Cloud Credentials API: ✅ Connected", file=sys.stderr)
            try:
                stats = await cloud_creds_client.get_credential_statistics()
                print(f"   Credentials Found: {stats.get('total_deployments', 0)} deployments", file=sys.stderr)
                print(f"   Unique Credentials: {stats.get('unique_credentials', 0)}", file=sys.stderr)
                print(f"   In Use: {stats.get('in_use', 0)}", file=sys.stderr)
            except Exception as e:
                print(f"   Credentials Data: ❌ {e}", file=sys.stderr)
        else:
            print("   Cloud Credentials API: ❌ Connection failed", file=sys.stderr)
    except Exception as e:
        print(f"   Cloud Credentials API: ❌ {e}", file=sys.stderr)

    if config.portal_enabled:
        print("   Portal Integration: ✅ Enabled", file=sys.stderr)
        print(f"   Portal URL: {config.portal_config.base_url}", file=sys.stderr)
        print(f"   Service Key: {'✅ Present' if config.portal_config.service_key else '❌ Missing'}", file=sys.stderr)
        print(f"   Service Secret: {'✅ Present' if config.portal_config.service_secret else '❌ Missing'}", file=sys.stderr)
        
        try:
            from api.portal_auth_api import PortalAuthAPIClient
            portal_auth_client = PortalAuthAPIClient(config.portal_config)
            
            # Check current token status
            token_info = portal_auth_client.get_token_info()
            print(f"   Access Token: {'✅ Present' if token_info['has_token'] else '❌ Missing'}", file=sys.stderr)
            
            if token_info['has_token']:
                if token_info['is_expired']:
                    print(f"   Token Status: ⚠️ Expired", file=sys.stderr)
                else:
                    print(f"   Token Status: ✅ Valid ({token_info.get('time_until_expiry', 'unknown')} remaining)", file=sys.stderr)
            
            # Test authentication
            print("   Testing Portal authentication...", file=sys.stderr)
            portal_success = await portal_auth_client.test_connection()
            
            if portal_success:
                print("   Portal API: ✅ Connected", file=sys.stderr)
                # Show token info after successful auth
                new_token_info = portal_auth_client.get_token_info()
                if not new_token_info['is_expired']:
                    print(f"   Token expires in: {new_token_info.get('time_until_expiry', 'unknown')}", file=sys.stderr)
            else:
                print("   Portal API: ❌ Connection failed", file=sys.stderr)
                print("   Check service key and secret in .env file", file=sys.stderr)
                
        except Exception as e:
            print(f"   Portal API: ❌ {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
    else:
        print("   Portal Integration: ⚪ Disabled (optional)", file=sys.stderr)
        print("   To enable: Add PORTAL_SERVICE_KEY and PORTAL_SERVICE_SECRET to .env", file=sys.stderr)



async def test_all_tools():
    """Test all registered tools."""
    print("🧪 TESTING ALL TOOLS", file=sys.stderr)
    print("=" * 50, file=sys.stderr)
    
    try:
        mcp_server = MCPServer("nmc-test-server")
        tools = mcp_server.tool_registry.get_tool_names()
        
        print(f"📋 Testing {len(tools)} tools...", file=sys.stderr)
        
        test_results = {}
        
        for tool_name in tools:
            print(f"\n🔧 Testing: {tool_name}", file=sys.stderr)
            try:
                # Test with minimal/empty arguments
                result = await mcp_server.tool_registry.execute_tool(tool_name, {})
                
                if result and len(result) > 0:
                    text_length = len(result[0].text) if hasattr(result[0], 'text') else 0
                    if "❌ Error:" in result[0].text:
                        test_results[tool_name] = "❌ Error"
                        print(f"   Result: ❌ Error in response", file=sys.stderr)
                    else:
                        test_results[tool_name] = "✅ Success"
                        print(f"   Result: ✅ Success ({text_length} chars)", file=sys.stderr)
                else:
                    test_results[tool_name] = "⚠️ Empty"
                    print(f"   Result: ⚠️ Empty response", file=sys.stderr)
                    
            except Exception as e:
                test_results[tool_name] = f"❌ {str(e)}"
                print(f"   Result: ❌ Exception: {e}", file=sys.stderr)
        
        # Summary
        print(f"\n📊 TEST SUMMARY", file=sys.stderr)
        print("=" * 30, file=sys.stderr)
        
        success_count = sum(1 for result in test_results.values() if result == "✅ Success")
        error_count = sum(1 for result in test_results.values() if "❌" in result)
        
        print(f"✅ Successful: {success_count}/{len(tools)}", file=sys.stderr)
        print(f"❌ Failed: {error_count}/{len(tools)}", file=sys.stderr)
        
        if error_count > 0:
            print("\n❌ Failed Tools:", file=sys.stderr)
            for tool_name, result in test_results.items():
                if "❌" in result:
                    print(f"   - {tool_name}: {result}", file=sys.stderr)
        
    except Exception as e:
        print(f"❌ Tool testing failed: {e}", file=sys.stderr)


async def quick_share_test():
    """Quick test of shares functionality."""
    print("Quick Share Test\n", file=sys.stderr)
    
    try:
        # Test 1: Can we import the shares API?
        print("1. Testing shares API import...", file=sys.stderr)
        from api.shares_api import SharesAPIClient
        print("   ✅ SharesAPIClient imported", file=sys.stderr)
        
        # Test 2: Can we connect to the API?
        print("\n2. Testing API connection...", file=sys.stderr)
        client = SharesAPIClient(config.filers_config)
        response = await client.list_shares()
        
        if "error" in response:
            print(f"   ❌ API Error: {response['error']}", file=sys.stderr)
            return
        
        items = response.get("items", [])
        print(f"   ✅ Connected! Found {len(items)} shares", file=sys.stderr)
        
        # Test 3: Show sample share data
        if items:
            print("\n3. Sample share data:", file=sys.stderr)
            first = items[0]
            print(f"   Name: {first.get('share_name')}", file=sys.stderr)
            print(f"   Path: {first.get('path')}", file=sys.stderr)
            print(f"   Filer: {first.get('filer_serial_number')[:8]}...", file=sys.stderr)
            print(f"   Previous Versions: {first.get('enable_previous_vers', 'N/A')}", file=sys.stderr)
            print(f"   Fruit Enabled: {first.get('fruit_enabled', 'N/A')}", file=sys.stderr)
        
        # Test 4: Try to import share tools one by one
        print("\n4. Testing tool imports:", file=sys.stderr)
        
        tools_to_test = [
            "ListSharesTool",
            "GetShareStatsTool", 
            "GetSharesByFilerTool",
            "GetBrowserAccessibleSharesTool",
            "GetSharesByVolumeTool"
        ]
        
        working_tools = []
        for tool_name in tools_to_test:
            try:
                exec(f"from tools.share_tools import {tool_name}")
                print(f"   ✅ {tool_name}", file=sys.stderr)
                working_tools.append(tool_name)
            except ImportError as e:
                print(f"   ❌ {tool_name}: {e}", file=sys.stderr)
        
        print(f"\n✅ Summary: {len(working_tools)}/{len(tools_to_test)} tools working", file=sys.stderr)
        print(f"   Working tools: {', '.join(working_tools)}", file=sys.stderr)
        
    except ImportError as e:
        print(f"❌ Import failed: {e}", file=sys.stderr)
    except Exception as e:
        print(f"❌ Test failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)


if __name__ == "__main__":

    #Getting a new NMC API Token
    auth_client = AuthAPIClient(config.filers_config)
    asyncio.run(auth_client.login())

    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "diagnose":
            print("🔍 Running system diagnosis...", file=sys.stderr)
            asyncio.run(diagnose_system())
            
        elif command == "test-tools":
            print("🧪 Running tool tests...", file=sys.stderr)
            asyncio.run(test_all_tools())
            
        elif command == "test-api":
            print("🌐 Running API test...", file=sys.stderr)
            asyncio.run(quick_share_test())  # Your existing function
            
        elif command == "test":
            print("🔄 Running all tests...", file=sys.stderr)
            asyncio.run(diagnose_system())
            asyncio.run(test_all_tools())
            
        else:
            print(f"❌ Unknown command: {command}", file=sys.stderr)
            print("Available commands:", file=sys.stderr)
            print("  diagnose    - Full system diagnosis", file=sys.stderr)
            print("  test-api    - Test API connectivity", file=sys.stderr)
            print("  test-tools  - Test all registered tools", file=sys.stderr)
            print("  test        - Run all tests", file=sys.stderr)
    else:
        print("🚀 MCP Server starting up...", file=sys.stderr)
        asyncio.run(main())