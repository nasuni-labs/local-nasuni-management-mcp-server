# NMC MCP Server

A comprehensive Model Context Protocol (MCP) server that provides tools for interacting with the Nasuni Management Center (NMC) through Claude AI integration. Using this MCP server, you can get granular details about your Nasuni enviornment, monitor the health of your appliances, summarize notifications, and generate custom reports.  

Note: NMC MCP Server is Claude-specific using Anthropic's MCP framework.

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Available Tools](#available-tools)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)



## Features

### Infrastructure Management
- **Filer(Edge) Management**: List, monitor, and manage Edge Appliances
- **Volume Operations**: Comprehensive volume detail reporting
- **Share Administration**: SMB/CIFS Share management
- **Health Monitoring**: Real-time system health and performance monitoring

### 📊 Analytics & Reporting
- **Performance Metrics**: Detailed system performance analytics
- **Usage Statistics**: Comprehensive usage reporting and analysis
- **Notification Management**: Centralized alert and notification handling

## Prerequisites

- **Python**: 3.8 or higher
- **NMC Credentials**: Accessing the NMC API requires a user who is a member of an NMC group that has the "Enable NMC API Access" permission enabled. API users must also have the corresponding NMC permission for the action that they are performing. Both native and domain accounts are supported for NMC API authentication (SSO accounts are not supported using the NMC API).
- **Claude AI**: Compatible with Anthropic's Claude AI platform

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd nmc-mcp-server
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Set Up Environment

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

## Configuration

### Environment Variables

Configure the following environment variables in your `.env` file:

#### Required Configuration
```env
# API Configuration
API_BASE_URL=https://your-nmc-server.com
API_TOKEN=your_api_token_here

# Alternative token file method
API_TOKEN_FILE=/path/to/your/token.txt
```

#### Optional Configuration
```env
# SSL Configuration
VERIFY_SSL=false

# Timeout Settings
API_TIMEOUT=30.0

### API Token Setup

You can provide your API token in two ways:

#### Method 1: Environment Variable
```env
API_TOKEN=your_actual_token_here
```

#### Method 2: Token File
```env
API_TOKEN_FILE=/secure/path/to/token.txt
```

Create the token file:
```bash
echo "your_actual_token_here" > /secure/path/to/token.txt
chmod 600 /secure/path/to/token.txt
```

### Verification

Test your configuration:

```bash
python -c "
import asyncio
from main import diagnose_system
asyncio.run(diagnose_system())
"
```

## Usage

### Starting the Server

#### For Claude Integration
```bash
python main.py
```

#### Diagnostic Mode
```bash
python -c "
import asyncio
from main import diagnose_system
asyncio.run(diagnose_system())
"
```

#### Tool Testing
```bash
python -c "
import asyncio
from main import test_all_tools
asyncio.run(test_all_tools())
"
```

### Claude Desktop Integration

Configure your `.env` file as described above, then add the JSON config to your Claude configuration file (usually `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "nmc-mcp-server": {
      "command": "python",
      "args": ["/path/to/nmc-mcp-server/main.py"]
    }
  }
}
```
On your Claude Desktop Client -> Settings -> Developer -> Edit Config

<img width="990" height="652" alt="image" src="https://github.com/user-attachments/assets/59609953-b601-4f43-ac86-75d2b13894fd" />

## Available Tools

### Filer Management
- `list_filers` - List all filer with hardware details
- `get_filer_stats` - Get aggregate statistics about all filers
- `get_filer` - Get detailed information about a specific filer
- `get_volumes_by_filer` - Get all volumes connected to a filer

### Volume Operations
- `list_volumes` - List all storage volumes with comprehensive details
- `get_volume_access_summary` - Get volume ownership and access summary
- `find_unprotected_volumes` - Identify volumes with unprotected data
- `analyze_volume_operations` - Comprehensive volume operations analysis

### Share Management
- `list_shares` - List all SMB/CIFS Shares
- `get_share_stats` - Get comprehensive Share statistics
- `get_shares_by_filer` - Get Shares on a specific filer
- `get_browser_accessible_shares` - Get shares with web browser access

### Health Monitoring
- `list_filer_health` - Get health status for all filers
- `get_filer_health_stats` - Get health statistics across infrastructure
- `get_unhealthy_filers` - Identify filers requiring attention
- `get_critical_health_issues` - Get prioritized critical health issues

### Authentication & Security
- `refresh_auth_token` - Refresh authentication token
- `check_auth_token_status` - Check token validity and expiration
- `ensure_valid_auth_token` - Auto-refresh token if needed

### Cloud Credentials
- `list_cloud_credentials` - List configured cloud credentials
- `get_credential_stats` - Get cloud credential statistics
- `analyze_credential_usage` - Analyze credential usage patterns

### 📊 Notifications & Monitoring
- `list_notifications` - List system notifications with filtering
- `get_notification_summary` - Get notification statistics and summaries
- `analyze_notification_patterns` - Identify recurring issues and trends

## Development

To foster further colloboartion, here is project structure and details on how to add support for new APIs and tools:

### Project Structure

```
nmc-mcp-server/
├── main.py                 # Main entry point and diagnostics
├── requirements.txt        # Python dependencies
├── .env.example           # Environment configuration template
├── server/
│   └── mcp_server.py      # Main MCP server implementation
├── api/                   # API client implementations
│   ├── base_client.py     # Base API client class
│   ├── filers_api.py      # Filer management API
│   ├── volumes_api.py     # Volume management API
│   ├── shares_api.py      # Share management API
│   └── ...
├── tools/                 # MCP tool implementations
│   ├── base_tool.py       # Base tool class
│   ├── filer_tools.py     # Filer-related tools
│   ├── volume_tools.py    # Volume-related tools
│   └── registry.py        # Tool registration system
├── models/                # Data model classes
│   ├── base.py           # Base model classes
│   ├── filer.py          # Filer data models
│   └── volume.py         # Volume data models
├── config/                # Configuration management
│   └── settings.py       # Configuration loader
└── utils/                 # Utility functions
    └── formatting.py     # Output formatting utilities
```

### Adding New Tools

1. Create a new tool class inheriting from `BaseTool`:

```python
from tools.base_tool import BaseTool

class MyCustomTool(BaseTool):
    def __init__(self, api_client):
        super().__init__(
            name="my_custom_tool",
            description="Description of what this tool does"
        )
        self.api_client = api_client
    
    def get_schema(self):
        return {
            "type": "object",
            "properties": {
                "parameter": {
                    "type": "string",
                    "description": "Parameter description"
                }
            }
        }
    
    async def execute(self, arguments):
        # Tool implementation
        pass
```

2. Register the tool in `tools/registry.py`:

```python
def register_custom_tools(self, api_client):
    self.register_tool(MyCustomTool(api_client))
```

### Adding New API Clients

1. Create an API client inheriting from `BaseAPIClient`:

```python
from api.base_client import BaseAPIClient

class MyAPIClient(BaseAPIClient):
    async def get_data(self):
        return await self.get("/api/v1.2/my-endpoint/")
```

2. Register in `server/mcp_server.py`:

```python
def _setup_tools(self):
    # ... existing setup ...
    my_client = MyAPIClient(config.api_config)
    self.tool_registry.register_custom_tools(my_client)
```

## Troubleshooting

### Common Issues

#### Connection Errors
```bash
# Test API connectivity
python -c "
import asyncio
from api.filers_api import FilersAPIClient
from config.settings import config

async def test():
    client = FilersAPIClient(config.filers_config)
    result = await client.test_connection()
    print('Connection:', 'Success' if result else 'Failed')

asyncio.run(test())
"
```

#### Authentication Issues
```bash
# Check token status
python -c "
import asyncio
from main import diagnose_system
asyncio.run(diagnose_system())
"
```

#### Tool Registration Problems
```bash
# List available tools
python -c "
from server.mcp_server import MCPServer
server = MCPServer()
print('Available tools:', server.tool_registry.get_tool_names())
"
```

### Debugging

Enable detailed logging by setting:

```env
DEBUG=true
LOG_LEVEL=DEBUG
```

### Performance Optimization

- **Connection Pooling**: The server uses HTTP connection pooling for optimal performance
- **Token Caching**: Authentication tokens are cached and auto-refreshed
- **Concurrent Requests**: NMC API calls are throlled at 5 requests per second. [Learn More](https://docs.api.nasuni.com/api/nmc/v120/introduction#rate-limit)

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request


### Testing

Run the comprehensive test suite:

```bash
python -c "
import asyncio
from main import test_all_tools, diagnose_system

async def full_test():
    await diagnose_system()
    await test_all_tools()

asyncio.run(full_test())
"
```


---

**Note**: This server is designed for Nasuni environments and requires proper network access and authentication to your NMC infrastructure.
