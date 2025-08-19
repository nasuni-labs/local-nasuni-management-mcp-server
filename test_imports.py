#!/usr/bin/env python3
try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
    from mcp.server.stdio import stdio_server
    print("✅ MCP imports successful!")
    
    # Test our imports step by step
    try:
        from config.settings import config
        print("✅ Config import successful!")
    except ImportError as e:
        print(f"❌ Config import failed: {e}")
    
    try:
        from models.base import BaseModel
        print("✅ Models base import successful!")
    except ImportError as e:
        print(f"❌ Models base import failed: {e}")
        
    try:
        from api.base_client import BaseAPIClient
        print("✅ API base client import successful!")
    except ImportError as e:
        print(f"❌ API base client import failed: {e}")
    
    try:
        from tools.base_tool import BaseTool
        print("✅ Tools base import successful!")
    except ImportError as e:
        print(f"❌ Tools base import failed: {e}")
    
except ImportError as e:
    print(f"❌ MCP Import error: {e}")
    import traceback
    traceback.print_exc()
