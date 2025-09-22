# Nasuni Management MCP Server (Local)

A comprehensive Model Context Protocol (MCP) server that provides tools for interacting with your Nasuni environment (Nasuni Management Center (NMC) and Portal) through Claude AI integration. Using this MCP server, you can get granular details about your Nasuni environment, monitor the health of your appliances, summarize notifications, and generate custom reports.

Note: Nasuni Management MCP Server is Claude-specific using Anthropic's MCP framework.

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

### Analytics & Reporting
- **Performance Metrics**: Detailed system performance analytics
- **Usage Statistics**: Comprehensive usage reporting and analysis
- **Notification Management**: Centralized alert and notification handling

## Prerequisites

### Python Requirements
- **Python**: Version 3.11+ or later is required
- **Recommendation**: Install the latest stable Python version for best performance and security

#### Checking Your Python Version
```bash
# Check version (should be 3.11+)
python --version
# or
python3 --version
```

#### Installing the Latest Python Version
Always install the latest stable Python version from the [official Python website](https://www.python.org/downloads/).

**macOS (using Homebrew):**
```bash
# If Python is installed but running a version older than 3.11
brew upgrade python

# Install latest Python (recommended)
brew install python

# Or install latest Python 3
brew install python@3
```

**Windows:**
1. Visit [python.org/downloads](https://www.python.org/downloads/)
2. Download the latest Python version
3. Run the installer and make sure to check "Add Python to PATH"

**Using pyenv (Cross-platform - Recommended for Developers):**
```bash
# Install pyenv first, then:
pyenv install --list | grep "3\." | tail -5  # See latest versions
pyenv install 3.13.1  # Replace with latest version number
pyenv global 3.13.1   # Set as default
pyenv versions        # Verify installation
```

**Linux (Ubuntu/Debian):**
```bash
# Add deadsnakes PPA for latest Python versions
sudo apt update
sudo apt install software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update

# Install latest Python (check python.org for current version number)
sudo apt install python3.13 python3.13-pip python3.13-venv python3.13-dev

# Or use your distribution's latest available version
sudo apt install python3 python3-pip python3-venv

# For other Linux distributions:
# CentOS/RHEL/Fedora:
sudo dnf install python3 python3-pip python3-venv
# Arch Linux:
sudo pacman -S python python-pip
```

### Claude AI Integration Requirements
- **Claude AI Compatibility**: This server is designed exclusively for Claude AI and uses Anthropic's Model Context Protocol (MCP) framework
- **Claude Desktop Client**: Required for local deployment - the MCP server integrates with Claude through the desktop application
  - **Download**: [Get Claude Desktop Client](https://claude.ai/download)
- **Important**: When running locally, MCP server tools are **only accessible through the Claude Desktop Client**, not through Claude's web interface

### NMC API Requirements  
- **NMC Credentials**: Accessing the NMC API requires a user who is a member of an NMC group that has the "Enable NMC API Access" permission enabled
- **API Permissions**: Along with 'Enable NMC API Access', the API users must also have the corresponding NMC permission for each action they perform. For a granular permission set, refer to the [Available Tools](https://github.com/nasuni-labs/local-nasuni-management-mcp-server/?tab=readme-ov-file#available-tools) section.
- **Account Types**: Both native and domain accounts are supported for NMC API authentication (SSO accounts are **not supported** via the NMC API)

## Installation 
There are two options to install and configure the NMC MCP Server:
- **1. Automated Setup (Recommended)**
- **2. Manual Setup**

## Option 1: Automated Setup (Recommended)
The automated installer handles all setup steps including downloading the code, creating virtual environment, installing dependencies, and configuring Claude Desktop.

### 1. Download the Installer Script
Download the [installer.py](https://github.com/nasuni-labs/nasuni-management-mcp-desktop-server/blob/main/installer.py) from the repo. 

### 2. Run the Installer 

**All Platforms:**
```bash
python installer.py
# or
python3 installer.py
```

### Step 3: Provide Required Information

During installation, you'll be prompted for:

1. **Installation directory** 
   - Default: `~/nasuni-management-mcp-server` (Mac/Linux) or `%USERPROFILE%\nasuni-management-mcp-server` (Windows)
   - Press Enter to accept default or specify a custom path

2. **NMC Server URL**
   - Example: `https://nmc.company.com` or `https://192.168.1.100`
   - The installer will add `https://` if not provided

3. **NMC Username**
   - Your NMC login username
   - For domain accounts: `DOMAIN\username` or just `username`

4. **NMC Password**
   - Your NMC login password
   - Input is hidden for security

5. **SSL Certificate Verification**
   - Default: No (recommended for internal servers)
   - Choose 'y' only if your NMC has valid SSL certificates

### Step 4: Restart Claude Desktop and Test

1. **Close Claude Desktop completely** (not just minimize)
2. **Start Claude Desktop** again
3. **Test the integration** by asking Claude:
   - "List all my filers"
   - "Show unhealthy volumes"
   - "Get share statistics"

If Claude Desktop was not installed when you ran the installer:
1. Install Claude Desktop from [claude.ai/download](https://claude.ai/download)
2. Run the configuration script that was created:
   ```bash
   python ~/nasuni-management-mcp-server/configure_claude.py
   ```


## Manual Setup

### 1. Clone the Repository

```bash
git clone https://github.com/nasuni-labs/local-nasuni-management-mcp-server.git nasuni-management-mcp-server
cd nasuni-management-mcp-server
```

### 2. Create Virtual Environment (Recommended)

```bash
# Create virtual environment
python3 -m venv nasuni-management-mcp-server-env

# Activate virtual environment
# On macOS/Linux:
source nasuni-management-mcp-desktop-server-env/bin/activate
# On Windows:
asuni-management-mcp-env\Scripts\activate
```

### 3. Install Dependencies

```bash
# Use pip3 to ensure you're using Python 3.x package manager
pip3 install -r requirements.txt

# Alternative: if pip3 is not available, use pip
pip install -r requirements.txt
```

**Note about pip vs pip3:**
- Use `pip3` if you have both Python 2 and Python 3 installed
- Use `pip` if you only have Python 3 installed or if `pip3` is not available
- When in a virtual environment, both commands typically point to the same Python 3 version

### 4. Verify Installation

```bash
# Check that Python 3.13+ is being used
python --version

# Verify dependencies are installed
pip3 list | grep -E "(mcp-server|httpx|python-dotenv)"
```

### 5. Set Up Environment

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

## Configuration

### Environment Variables

Configure the following environment variables in your `.env` file:

#### Required Configuration
```env
# NMC API Base URL (replace with your actual NMC server)
API_BASE_URL="https://your-nmc-server.com"

# NMC Login Credentials (Ensure the user has adequate permissions)
NMC_USERNAME="username"
NMC_PASSWORD="password"

# SSL Verification (set to true for production)
VERIFY_SSL=false
```

#### Optional Configuration
```env
# API Request Timeout (seconds)
API_TIMEOUT=30.0
```

#### Development/Debugging Configuration
```env
# Uncomment for development
# DEBUG=true
# LOG_LEVEL=DEBUG
```

### Authentication Setup

The Nasuni Management MCP Server uses **username and password authentication** to connect to your NMC instance:

1. **Username**: Your NMC login username
2. **Password**: Your NMC login password
3. **Permissions**: Ensure the user account has:
   - "Enable NMC API Access" permission
   - Appropriate permissions for the operations you want to perform

**Security Note**: The credentials are stored in your local `.env` file and are only used to authenticate with your NMC server.

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

#### Step 1: Find Your Python Executable Path
First, determine the correct Python executable path:

```bash
# Find your Python executable path
which python3
# or
which python

# If using a virtual environment (recommended), activate it first:
source nasuni-management-mcp-server/bin/activate  # macOS/Linux
# nmc-mcp-env\Scripts\activate   # Windows
which python
```

**Common Python paths:**
- **macOS (Homebrew)**: `/opt/homebrew/bin/python3` or `/usr/local/bin/python3`
- **macOS (pyenv)**: `/Users/yourusername/.pyenv/shims/python`
- **Linux**: `/usr/bin/python3` or `/usr/local/bin/python3`
- **Windows**: `C:\Python313\python.exe` or `C:\Users\yourusername\AppData\Local\Programs\Python\Python313\python.exe`
- **Virtual Environment**: `/path/to/nmc-mcp-env/bin/python` (macOS/Linux) or `C:\path\to\nmc-mcp-env\Scripts\python.exe` (Windows)

#### Step 2: Update Claude Desktop Configuration
Add this configuration to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "nasuni-management": {
      "command": "/path/to/your/python/executable",
      "args": ["/full/path/to/nasuni-management-mcp-server/main.py"]
    }
  }
}
```

**Example configurations:**

**Using virtual environment (recommended):**
```json
{
  "mcpServers": {
    "nasuni-management": {
      "command": "/Users/john/Projects/nasuni-management-mcp-server/nasuni-management-mcp-server-env/bin/python",
      "args": ["/Users/john/Projects/nasuni-management-mcp-server/main.py"]
    }
  }
}
```

**Using system Python:**
```json
{
  "mcpServers": {
    "nasuni-management-mcp-server": {
      "command": "/opt/homebrew/bin/python3",
      "args": ["/Users/john/Projects/nasuni-management-mcp-server/main.py"]
    }
  }
}
```

#### Step 3: Locate Claude Desktop Config File
On your Claude Desktop Client -> Settings -> Developer -> Edit Config -> claude_desktop_config.json

<img width="990" height="652" alt="image" src="https://github.com/user-attachments/assets/59609953-b601-4f43-ac86-75d2b13894fd" />


#### Step 4: Restart Claude Desktop
After updating the configuration file, restart the Claude Desktop application to load the new MCP server.

## Setup Complete
Test your Nasuni Management MCP Server, ask Claude "List all my filers withd details"

## Available Tools

**Note:** All tools require 'Enable NMC API Access' permissions. 

### Filer Management
- `list_filers` - List all filer with hardware details
- `get_filer_stats` - Get aggregate statistics about all filers
- `get_filer` - Get detailed information about a specific filer
- `get_volumes_by_filer` - Get all volumes connected to a filer

**Required Permissions:** 
- Manage All Filers or a set of Filers
- Filer Access (Manage All Filers (super user) or intended subset of Filers)
- Manage Volume Settings (Can't add/delete). 

### Volume Operations
- `list_volumes` - List all storage volumes with comprehensive details
- `get_volume_access_summary` - Get volume ownership and access summary
- `find_unprotected_volumes` - Identify volumes with unprotected data
- `analyze_volume_operations` - Comprehensive volume operations analysis

**Required Permissions:** 
- Manage All Filers or a set of Filers
- Filer Access (Manage All Filers (super user) or intended subset of Filers)
- Manage Volume Settings (Can't add/delete). 

### Share Management
- `list_shares` - List all SMB/CIFS Shares
- `get_share_stats` - Get comprehensive Share statistics
- `get_shares_by_filer` - Get Shares on a specific filer
- `get_browser_accessible_shares` - Get shares with web browser access

**Required Permissions:** 
- Manage All Filers or a set of Filers
- Filer Access (Manage All Filers (super user) or intended subset of Filers)
- Manage Shares, Exports, FTP and ISCSI

### Health Monitoring
- `list_filer_health` - Get health status for all filers
- `get_filer_health_stats` - Get health statistics across infrastructure
- `get_unhealthy_filers` - Identify filers requiring attention
- `get_critical_health_issues` - Get prioritized critical health issues

**Required Permissions:** 
- Manage All Filers or a set of Filers
- Filer Access (Manage All Filers (super user) or intended subset of Filers)

### Authentication & Security
- `refresh_auth_token` - Refresh authentication token
- `check_auth_token_status` - Check token validity and expiration
- `ensure_valid_auth_token` - Auto-refresh token if needed

### Cloud Credentials
- `list_cloud_credentials` - List configured cloud credentials
- `get_credential_stats` - Get cloud credential statistics
- `analyze_credential_usage` - Analyze credential usage patterns

**Required Permissions:** 
- Manage all aspects of the Filer (super user)

### 📊 Notifications & Monitoring
- `list_notifications` - List system notifications with filtering
- `get_notification_summary` - Get notification statistics and summaries
- `analyze_notification_patterns` - Identify recurring issues and trends

**Required Permissions:** 
- Manage Notifications (Both NMC and Filer Permissions)

## Development

To foster further colloboartion, here is project structure and details on how to add support for new APIs and tools:

### Project Structure

```
nasuni-management-mcp-server/
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
