#!/usr/bin/env python3
"""
NMC MCP Server Universal Installer
Works on Windows, macOS, and Linux
Downloads latest code from GitHub
"""

import os
import sys
import json
import platform
import subprocess
import shutil
import getpass
import urllib.request
import urllib.error
import ssl
import zipfile
import tarfile
from pathlib import Path
from typing import Optional, Dict, Tuple
import tempfile
import time

# GitHub repository URL
GITHUB_REPO = "https://github.com/nasuni-labs/nasuni-nmc-mcp-desktop-server"
GITHUB_ARCHIVE = "https://github.com/nasuni-labs/nasuni-nmc-mcp-desktop-server/archive/refs/heads/main.zip"

# ANSI color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

    @staticmethod
    def disable():
        Colors.HEADER = ''
        Colors.BLUE = ''
        Colors.CYAN = ''
        Colors.GREEN = ''
        Colors.WARNING = ''
        Colors.RED = ''
        Colors.ENDC = ''
        Colors.BOLD = ''

# Disable colors on Windows if not supported
if platform.system() == 'Windows':
    try:
        import colorama
        colorama.init()
    except ImportError:
        Colors.disable()

class Installer:
    def __init__(self):
        self.os_type = platform.system()
        self.arch = platform.machine()
        self.home = Path.home()
        self.install_dir = None
        self.python_cmd = None
        self.pip_cmd = None
        self.venv_path = None
        self.config = {}
        
    def print_header(self):
        """Print welcome header"""
        print(f"\n{Colors.CYAN}{'='*60}{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.HEADER}🚀 NMC MCP Server Universal Installer{Colors.ENDC}")
        print(f"{Colors.CYAN}{'='*60}{Colors.ENDC}")
        print(f"OS: {Colors.GREEN}{self.os_type}{Colors.ENDC}")
        print(f"Architecture: {Colors.GREEN}{self.arch}{Colors.ENDC}")
        print(f"Python: {Colors.GREEN}{sys.version.split()[0]}{Colors.ENDC}")
        print(f"Repository: {Colors.GREEN}{GITHUB_REPO}{Colors.ENDC}")
        print(f"{Colors.CYAN}{'='*60}{Colors.ENDC}\n")
    
    def check_python(self) -> bool:
        """Check if Python 3.10+ is installed"""
        print(f"{Colors.BLUE}📋 Checking Python version...{Colors.ENDC}")
        
        if sys.version_info < (3, 10):
            print(f"{Colors.RED}❌ Python 3.10+ required (you have {sys.version}){Colors.ENDC}")
            self.offer_python_install()
            return False
        
        print(f"{Colors.GREEN}✅ Python {sys.version.split()[0]} is compatible{Colors.ENDC}")
        
        # Find the right Python command
        for cmd in ['python3', 'python', sys.executable]:
            try:
                result = subprocess.run([cmd, '--version'], capture_output=True, text=True)
                if result.returncode == 0:
                    self.python_cmd = cmd
                    break
            except:
                continue
        
        # Find pip command
        for cmd in ['pip3', 'pip', f'{self.python_cmd} -m pip']:
            try:
                result = subprocess.run(cmd.split() + ['--version'], capture_output=True, text=True)
                if result.returncode == 0:
                    self.pip_cmd = cmd
                    break
            except:
                continue
        
        if not self.pip_cmd:
            print(f"{Colors.WARNING}⚠️  pip not found, will use {self.python_cmd} -m pip{Colors.ENDC}")
            self.pip_cmd = f"{self.python_cmd} -m pip"
        
        return True
    
    def offer_python_install(self):
        """Provide instructions for installing Python"""
        print(f"\n{Colors.HEADER}📦 Python Installation Instructions:{Colors.ENDC}\n")
        
        if self.os_type == "Windows":
            print("1. Download Python from: https://www.python.org/downloads/")
            print("2. Run the installer and CHECK 'Add Python to PATH'")
            print("3. Restart this installer after Python is installed")
            
        elif self.os_type == "Darwin":  # macOS
            print("Option 1: Using Homebrew (recommended)")
            print("  brew install python@3.13")
            print("\nOption 2: Download from python.org")
            print("  https://www.python.org/downloads/")
            
        else:  # Linux
            print("Ubuntu/Debian:")
            print("  sudo apt update && sudo apt install python3.13 python3-pip python3-venv")
            print("\nFedora:")
            print("  sudo dnf install python3.13 python3-pip")
            print("\nArch:")
            print("  sudo pacman -S python python-pip")
    
    def download_from_github(self) -> bool:
        """Download latest code from GitHub"""
        print(f"\n{Colors.BLUE}📥 Downloading latest version from GitHub...{Colors.ENDC}")
        
        # Choose installation directory
        default_dir = self.home / "nmc-mcp-server"
        install_path = input(f"Installation directory [{default_dir}]: ").strip()
        
        if not install_path:
            self.install_dir = default_dir
        else:
            self.install_dir = Path(install_path).expanduser().resolve()
        
        # Check if directory exists
        if self.install_dir.exists():
            response = input(f"{Colors.WARNING}Directory exists. Overwrite? (y/n): {Colors.ENDC}").lower()
            if response != 'y':
                print(f"{Colors.RED}Installation cancelled{Colors.ENDC}")
                return False
            shutil.rmtree(self.install_dir, ignore_errors=True)
        
        # Create directory
        self.install_dir.mkdir(parents=True, exist_ok=True)
        
        # Download from GitHub
        try:
            # Create SSL context that doesn't verify certificates (for simplicity)
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                zip_path = temp_path / "nmc-mcp-server.zip"
                
                # Download with progress indicator
                def download_progress(block_num, block_size, total_size):
                    downloaded = block_num * block_size
                    percent = min(downloaded * 100 / total_size, 100)
                    bar_length = 40
                    filled = int(bar_length * percent / 100)
                    bar = '█' * filled + '-' * (bar_length - filled)
                    print(f'\rDownloading: |{bar}| {percent:.1f}%', end='', flush=True)
                
                print(f"Downloading from: {GITHUB_ARCHIVE}")
                urllib.request.urlretrieve(
                    GITHUB_ARCHIVE, 
                    zip_path,
                    reporthook=download_progress
                )
                print()  # New line after progress bar
                
                # Extract zip file
                print(f"{Colors.BLUE}📦 Extracting files...{Colors.ENDC}")
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_path)
                
                # Find the extracted directory (GitHub adds -main suffix)
                extracted_dirs = [d for d in temp_path.iterdir() if d.is_dir()]
                if not extracted_dirs:
                    raise Exception("No directory found in archive")
                
                source_dir = extracted_dirs[0]
                
                # Move files to installation directory
                for item in source_dir.iterdir():
                    dest = self.install_dir / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, dest)
                
                print(f"{Colors.GREEN}✅ Downloaded to: {self.install_dir}{Colors.ENDC}")
                return True
                
        except Exception as e:
            print(f"{Colors.RED}❌ Download failed: {e}{Colors.ENDC}")
            print(f"\n{Colors.WARNING}Alternative: Clone manually using git:{Colors.ENDC}")
            print(f"  git clone {GITHUB_REPO}.git {self.install_dir}")
            return False
    
    def setup_virtual_environment(self) -> bool:
        """Create and setup virtual environment"""
        print(f"\n{Colors.BLUE}🔧 Setting up virtual environment...{Colors.ENDC}")
        
        self.venv_path = self.install_dir / "venv"
        
        try:
            # Create virtual environment
            subprocess.run(
                [self.python_cmd, "-m", "venv", str(self.venv_path)],
                check=True,
                capture_output=True
            )
            
            # Get venv Python and pip paths
            if self.os_type == "Windows":
                venv_python = self.venv_path / "Scripts" / "python.exe"
                venv_pip = self.venv_path / "Scripts" / "pip.exe"
            else:
                venv_python = self.venv_path / "bin" / "python"
                venv_pip = self.venv_path / "bin" / "pip"
            
            # Upgrade pip
            print(f"{Colors.BLUE}📦 Upgrading pip...{Colors.ENDC}")
            subprocess.run(
                [str(venv_python), "-m", "pip", "install", "--upgrade", "pip"],
                check=True,
                capture_output=True
            )
            
            # Install requirements
            requirements_file = self.install_dir / "requirements.txt"
            if requirements_file.exists():
                print(f"{Colors.BLUE}📦 Installing dependencies...{Colors.ENDC}")
                subprocess.run(
                    [str(venv_pip), "install", "-r", str(requirements_file)],
                    check=True,
                    capture_output=True
                )
                print(f"{Colors.GREEN}✅ Dependencies installed{Colors.ENDC}")
            else:
                print(f"{Colors.WARNING}⚠️  No requirements.txt found{Colors.ENDC}")
            
            self.python_cmd = str(venv_python)
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"{Colors.RED}❌ Failed to setup virtual environment: {e}{Colors.ENDC}")
            return False
    
    def configure_nmc(self) -> bool:
        """Configure NMC connection settings"""
        print(f"\n{Colors.HEADER}🔐 NMC Configuration{Colors.ENDC}")
        print("Enter your NMC connection details:\n")
        
        # Get NMC URL
        nmc_url = input("NMC Server URL (e.g., https://nmc.company.com): ").strip()
        if not nmc_url:
            print(f"{Colors.RED}❌ NMC URL is required{Colors.ENDC}")
            return False
        
        # Ensure URL has protocol
        if not nmc_url.startswith(('http://', 'https://')):
            nmc_url = f"https://{nmc_url}"
        
        # Get credentials
        username = input("NMC Username: ").strip()
        if not username:
            print(f"{Colors.RED}❌ Username is required{Colors.ENDC}")
            return False
        
        password = getpass.getpass("NMC Password: ")
        if not password:
            print(f"{Colors.RED}❌ Password is required{Colors.ENDC}")
            return False
        
        # SSL verification
        verify_ssl = input("Verify SSL certificate? (y/n) [n]: ").lower() == 'y'
        
        # Create .env file
        env_file = self.install_dir / ".env"
        env_content = f"""# NMC API Configuration
API_BASE_URL="{nmc_url}"
NMC_USERNAME="{username}"
NMC_PASSWORD="{password}"
VERIFY_SSL={str(verify_ssl).lower()}
API_TIMEOUT=30.0
"""
        
        try:
            env_file.write_text(env_content)
            print(f"{Colors.GREEN}✅ Configuration saved to .env file{Colors.ENDC}")
            
            # Store config for Claude setup
            self.config = {
                'url': nmc_url,
                'username': username,
                'install_dir': str(self.install_dir)
            }
            
            return True
            
        except Exception as e:
            print(f"{Colors.RED}❌ Failed to save configuration: {e}{Colors.ENDC}")
            return False
    
    def test_connection(self) -> bool:
        """Test NMC connection"""
        print(f"\n{Colors.BLUE}🔍 Testing NMC connection...{Colors.ENDC}")
        
        test_script = self.install_dir / "test_connection.py"
        if not test_script.exists():
            # Create a simple test script
            test_code = '''
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import asyncio
from dotenv import load_dotenv
load_dotenv()

async def test():
    try:
        from api.base_client import BaseAPIClient
        from config.settings import config
        
        client = BaseAPIClient(config.api_config)
        # Try a simple API call
        response = await client.get("/api/v1.2/auth/")
        print("✅ Connection successful!")
        return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

asyncio.run(test())
'''
            test_script.write_text(test_code)
        
        try:
            result = subprocess.run(
                [self.python_cmd, str(test_script)],
                capture_output=True,
                text=True,
                cwd=self.install_dir
            )
            
            print(result.stdout)
            if result.stderr:
                print(f"{Colors.WARNING}{result.stderr}{Colors.ENDC}")
            
            return "successful" in result.stdout
            
        except Exception as e:
            print(f"{Colors.WARNING}⚠️  Could not test connection: {e}{Colors.ENDC}")
            print("You can test manually after installation")
            return True  # Continue anyway
    
    def configure_claude_desktop(self) -> bool:
        """Configure Claude Desktop to use the MCP server"""
        print(f"\n{Colors.BLUE}🤖 Configuring Claude Desktop...{Colors.ENDC}")
        
        # Find Claude Desktop config file
        if self.os_type == "Darwin":  # macOS
            config_paths = [
                self.home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
                self.home / ".claude" / "claude_desktop_config.json"
            ]
        elif self.os_type == "Windows":
            config_paths = [
                self.home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json",
                Path(os.getenv("APPDATA", "")) / "Claude" / "claude_desktop_config.json"
            ]
        else:  # Linux
            config_paths = [
                self.home / ".config" / "Claude" / "claude_desktop_config.json",
                self.home / ".claude" / "claude_desktop_config.json"
            ]
        
        config_file = None
        for path in config_paths:
            if path.parent.exists():
                config_file = path
                break
        
        if not config_file:
            print(f"{Colors.WARNING}⚠️  Claude Desktop config directory not found{Colors.ENDC}")
            print(f"\nPlease add this to your Claude Desktop config manually:")
            self.print_manual_config()
            return False
        
        # Create config directory if it doesn't exist
        config_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing config or create new
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
            except:
                config = {}
        else:
            config = {}
        
        # Add our MCP server
        if "mcpServers" not in config:
            config["mcpServers"] = {}
        
        # Determine main.py path
        main_py = self.install_dir / "main.py"
        
        config["mcpServers"]["nmc-mcp-server"] = {
            "command": self.python_cmd,
            "args": [str(main_py)]
        }
        
        # Save config
        try:
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            
            print(f"{Colors.GREEN}✅ Claude Desktop configured successfully{Colors.ENDC}")
            print(f"   Config file: {config_file}")
            return True
            
        except Exception as e:
            print(f"{Colors.RED}❌ Failed to update Claude config: {e}{Colors.ENDC}")
            print(f"\nPlease add this to your Claude Desktop config manually:")
            self.print_manual_config()
            return False
    
    def print_manual_config(self):
        """Print manual configuration instructions"""
        main_py = self.install_dir / "main.py"
        
        config_json = {
            "mcpServers": {
                "nmc-mcp-server": {
                    "command": self.python_cmd,
                    "args": [str(main_py)]
                }
            }
        }
        
        print(f"\n{Colors.CYAN}{'='*60}{Colors.ENDC}")
        print(json.dumps(config_json, indent=2))
        print(f"{Colors.CYAN}{'='*60}{Colors.ENDC}")
    
    def create_shortcuts(self):
        """Create convenient shortcuts/commands"""
        print(f"\n{Colors.BLUE}🔗 Creating shortcuts...{Colors.ENDC}")
        
        if self.os_type == "Windows":
            # Create batch file
            batch_file = self.install_dir / "nmc-mcp.bat"
            batch_content = f'''@echo off
"{self.python_cmd}" "{self.install_dir}\\main.py" %*
'''
            batch_file.write_text(batch_content)
            print(f"  Created: {batch_file}")
            
        else:
            # Create shell script
            shell_file = self.install_dir / "nmc-mcp"
            shell_content = f'''#!/bin/bash
{self.python_cmd} {self.install_dir}/main.py "$@"
'''
            shell_file.write_text(shell_content)
            shell_file.chmod(0o755)
            print(f"  Created: {shell_file}")
    
    def print_success(self):
        """Print success message and next steps"""
        print(f"\n{Colors.GREEN}{'='*60}{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.GREEN}✨ Installation Complete!{Colors.ENDC}")
        print(f"{Colors.GREEN}{'='*60}{Colors.ENDC}\n")
        
        print(f"{Colors.HEADER}📍 Installation Details:{Colors.ENDC}")
        print(f"  • Location: {self.install_dir}")
        print(f"  • Python: {self.python_cmd}")
        print(f"  • NMC URL: {self.config.get('url', 'configured')}")
        
        # Check Claude Desktop status
        claude_installed, _ = self.check_claude_desktop()
        
        if claude_installed:
            print(f"\n{Colors.HEADER}🚀 Next Steps:{Colors.ENDC}")
            print(f"  1. {Colors.BOLD}Restart Claude Desktop{Colors.ENDC}")
            print(f"  2. Look for 'nmc-mcp-server' in Claude's tools menu")
            print(f"  3. Try asking Claude: 'List all my filers'")
        else:
            print(f"\n{Colors.WARNING}⚠️  Claude Desktop Not Installed{Colors.ENDC}")
            print(f"\n{Colors.HEADER}📥 To Complete Setup:{Colors.ENDC}")
            print(f"  1. Download Claude Desktop: {Colors.CYAN}https://claude.ai/download{Colors.ENDC}")
            print(f"  2. Install and run Claude Desktop once")
            print(f"  3. Run: {Colors.GREEN}{self.python_cmd} {self.install_dir}/configure_claude.py{Colors.ENDC}")
            print(f"\n{Colors.BLUE}The NMC MCP Server is ready and waiting for Claude Desktop{Colors.ENDC}")
        
        print(f"\n{Colors.HEADER}📚 Useful Commands:{Colors.ENDC}")
        print(f"  • Test connection: {self.python_cmd} {self.install_dir}/main.py")
        print(f"  • Update config: Edit {self.install_dir}/.env")
        if not claude_installed:
            print(f"  • Configure Claude: {self.python_cmd} {self.install_dir}/configure_claude.py")
        
        print(f"\n{Colors.CYAN}Need help? Visit: {GITHUB_REPO}{Colors.ENDC}")
    
    def run(self):
        """Run the complete installation process"""
        try:
            self.print_header()
            
            # Step 1: Check Python
            if not self.check_python():
                print(f"\n{Colors.RED}Please install Python 3.10+ and run this installer again{Colors.ENDC}")
                return False
            
            # Step 2: Download from GitHub
            if not self.download_from_github():
                return False
            
            # Step 3: Setup virtual environment
            if not self.setup_virtual_environment():
                return False
            
            # Step 4: Configure NMC
            if not self.configure_nmc():
                return False
            
            # Step 5: Test connection
            self.test_connection()  # Optional, don't fail if it doesn't work
            
            # Step 6: Configure Claude Desktop
            self.configure_claude_desktop()
            
            # Step 7: Create shortcuts
            self.create_shortcuts()
            
            # Success!
            self.print_success()
            return True
            
        except KeyboardInterrupt:
            print(f"\n\n{Colors.WARNING}Installation cancelled by user{Colors.ENDC}")
            return False
        except Exception as e:
            print(f"\n{Colors.RED}Installation failed: {e}{Colors.ENDC}")
            return False

def main():
    """Main entry point"""
    installer = Installer()
    success = installer.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
