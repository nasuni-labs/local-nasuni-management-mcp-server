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
import argparse
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
    YELLOW = '\033[93m'

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
        Colors.YELLOW = ''

# Handle Windows terminal compatibility
if platform.system() == 'Windows':
    try:
        # Try to enable ANSI escape sequences on Windows 10+
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except:
        # If that fails, try colorama
        try:
            import colorama
            colorama.init(autoreset=True)
        except ImportError:
            # If colorama not available, disable colors
            Colors.disable()
else:
    # For non-Windows, colors should work
    pass

class Installer:
    def __init__(self, args=None):
        self.os_type = platform.system()
        self.arch = platform.machine()
        self.home = Path.home()
        self.install_dir = None
        self.python_cmd = None
        self.pip_cmd = None
        self.venv_path = None
        self.config = {}
        
        # Handle arguments
        if args is None:
            # Create default args if none provided
            self.args = argparse.Namespace(
                directory=None,
                non_interactive=False,
                skip_claude=False,
                nmc_url=None,
                username=None,
                password=None,
                use_git=False,
                quiet=False
            )
        else:
            self.args = args
        
    def print_header(self):
        """Print welcome header"""
        try:
            print(f"\n{Colors.CYAN}{'='*60}{Colors.ENDC}")
            print(f"{Colors.BOLD}{Colors.HEADER}🚀 NMC MCP Server Universal Installer{Colors.ENDC}")
            print(f"{Colors.CYAN}{'='*60}{Colors.ENDC}")
            print(f"OS: {Colors.GREEN}{self.os_type}{Colors.ENDC}")
            print(f"Architecture: {Colors.GREEN}{self.arch}{Colors.ENDC}")
            print(f"Python: {Colors.GREEN}{sys.version.split()[0]}{Colors.ENDC}")
            print(f"Repository: {Colors.GREEN}{GITHUB_REPO}{Colors.ENDC}")
            print(f"{Colors.CYAN}{'='*60}{Colors.ENDC}\n")
        except Exception as e:
            # Fallback without colors if there's any issue
            print("\n" + "="*60)
            print("NMC MCP Server Universal Installer")
            print("="*60)
            print(f"OS: {self.os_type}")
            print(f"Architecture: {self.arch}")
            print(f"Python: {sys.version.split()[0]}")
            print(f"Repository: {GITHUB_REPO}")
            print("="*60 + "\n")
    
    def check_python(self) -> bool:
        """Check if Python 3.10+ is installed"""
        print(f"{Colors.BLUE}📋 Checking Python version...{Colors.ENDC}")
        
        if sys.version_info < (3, 10):
            print(f"{Colors.RED}❌ Python 3.10+ required (you have {sys.version}){Colors.ENDC}")
            self.offer_python_install()
            return False
        
        print(f"{Colors.GREEN}✅ Python {sys.version.split()[0]} is compatible{Colors.ENDC}")
        
        # Use the current Python executable
        self.python_cmd = sys.executable
        
        # Find pip command - prefer using python -m pip
        self.pip_cmd = f'"{self.python_cmd}" -m pip'
        
        # Test if pip is available
        try:
            result = subprocess.run(
                [self.python_cmd, "-m", "pip", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                print(f"{Colors.WARNING}⚠️  pip not found, attempting to install...{Colors.ENDC}")
                # Try to bootstrap pip
                try:
                    subprocess.run(
                        [self.python_cmd, "-m", "ensurepip", "--default-pip"],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                except:
                    print(f"{Colors.RED}Could not install pip automatically{Colors.ENDC}")
                    print("Please install pip manually and retry")
                    return False
        except Exception as e:
            print(f"{Colors.WARNING}⚠️  Could not verify pip: {e}{Colors.ENDC}")
        
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
    
    def try_git_clone(self) -> bool:
        """Try to clone using git if available"""
        print(f"{Colors.BLUE}Checking for git...{Colors.ENDC}")
        
        # Check if git is available
        git_cmd = shutil.which("git")
        if not git_cmd:
            print(f"{Colors.WARNING}Git not found, using direct download{Colors.ENDC}")
            return False
        
        print(f"{Colors.GREEN}Git found, cloning repository...{Colors.ENDC}")
        
        try:
            # Git clone with progress
            result = subprocess.run(
                ["git", "clone", "--progress", f"{GITHUB_REPO}.git", str(self.install_dir)],
                capture_output=False,  # Show git's progress output
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                print(f"{Colors.GREEN}✅ Repository cloned successfully{Colors.ENDC}")
                return True
            else:
                print(f"{Colors.WARNING}Git clone failed, trying direct download{Colors.ENDC}")
                return False
                
        except subprocess.TimeoutExpired:
            print(f"{Colors.WARNING}Git clone timed out, trying direct download{Colors.ENDC}")
            return False
        except Exception as e:
            print(f"{Colors.WARNING}Git clone error: {e}{Colors.ENDC}")
            return False
    
    def download_from_github(self) -> bool:
        """Download latest code from GitHub"""
        print(f"\n{Colors.BLUE}📥 Getting latest version from GitHub...{Colors.ENDC}")
        
        # Choose installation directory
        if self.args.directory:
            self.install_dir = Path(self.args.directory).expanduser().resolve()
            print(f"Using specified directory: {self.install_dir}")
        else:
            default_dir = self.home / "nmc-mcp-server"
            
            if self.args.non_interactive:
                self.install_dir = default_dir
                print(f"Using default directory: {self.install_dir}")
            else:
                try:
                    # Try to get user input with timeout and error handling
                    print(f"Installation directory [{default_dir}]: ", end='', flush=True)
                    
                    # Check if we're in an interactive terminal
                    try:
                        # Windows-specific check
                        if self.os_type == "Windows":
                            install_path = input().strip()
                        else:
                            if hasattr(sys.stdin, 'isatty') and sys.stdin.isatty():
                                install_path = input().strip()
                            else:
                                install_path = ""
                                print("(using default)")
                    except:
                        install_path = ""
                        print("(using default)")
                        
                except (EOFError, KeyboardInterrupt):
                    # User pressed Ctrl+D or Ctrl+C
                    install_path = ""
                    print("(using default)")
                except Exception as e:
                    # Any other error, use default
                    print(f"(using default)")
                    install_path = ""
                
                if not install_path:
                    self.install_dir = default_dir
                else:
                    self.install_dir = Path(install_path).expanduser().resolve()
        
        # Check if directory exists
        if self.install_dir.exists():
            if self.args.non_interactive:
                print(f"{Colors.WARNING}Directory exists, removing old installation...{Colors.ENDC}")
                shutil.rmtree(self.install_dir, ignore_errors=True)
            else:
                try:
                    print(f"{Colors.WARNING}Directory exists. Overwrite? (y/n): {Colors.ENDC}", end='', flush=True)
                    try:
                        response = input().lower().strip()
                    except:
                        response = 'n'
                        print("n")
                        
                    if response != 'y':
                        print(f"{Colors.RED}Installation cancelled{Colors.ENDC}")
                        return False
                except:
                    print(f"{Colors.RED}Installation cancelled (directory exists){Colors.ENDC}")
                    return False
                    
                shutil.rmtree(self.install_dir, ignore_errors=True)
        
        # Try git clone first if available and not disabled
        if not self.args.use_git or self.try_git_clone():
            return True
        
        # Fall back to ZIP download
        print(f"{Colors.BLUE}📥 Downloading as ZIP archive...{Colors.ENDC}")
        
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
                    
                    # Only update every 5% to reduce console output
                    if int(percent) % 5 == 0:
                        bar_length = 40
                        filled = int(bar_length * percent / 100)
                        bar = '█' * filled + '-' * (bar_length - filled)
                        # Use carriage return to overwrite the same line
                        print(f'\rDownloading: |{bar}| {percent:.0f}%', end='', flush=True)
                
                print(f"Downloading from: {GITHUB_ARCHIVE}")
                print("This may take a moment...")
                
                # For Windows or quiet mode, minimize output
                if self.os_type == "Windows" or self.args.quiet:
                    # Simple download without progress on Windows
                    try:
                        print("Downloading... ", end='', flush=True)
                        urllib.request.urlretrieve(GITHUB_ARCHIVE, zip_path)
                        print("Done!")
                    except Exception as e:
                        print(f"Failed: {e}")
                        raise
                else:
                    # Progress bar for Unix-like systems
                    urllib.request.urlretrieve(
                        GITHUB_ARCHIVE, 
                        zip_path,
                        reporthook=download_progress
                    )
                    print()  # New line after progress bar
                
                # Extract zip file
                print(f"{Colors.BLUE}📦 Extracting files...{Colors.ENDC}")
                
                # For Windows or quiet mode, extract quietly to avoid console overflow
                if self.os_type == "Windows" or self.args.quiet:
                    print("Extracting archive... ", end='', flush=True)
                    try:
                        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                            # Get total number of files
                            total_files = len(zip_ref.namelist())
                            
                            # Extract without verbose output
                            zip_ref.extractall(temp_path)
                        
                        print(f"Done! ({total_files} files)")
                    except Exception as e:
                        print(f"Failed: {e}")
                        raise
                else:
                    # More verbose extraction for Unix-like systems
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        total_files = len(zip_ref.namelist())
                        print(f"Extracting {total_files} files...")
                        
                        # Extract with simple progress
                        for i, file in enumerate(zip_ref.namelist()):
                            if i % 10 == 0:  # Update every 10 files
                                print(f'\rExtracting: {i}/{total_files} files', end='', flush=True)
                            zip_ref.extract(file, temp_path)
                        
                        print(f'\rExtracted: {total_files}/{total_files} files - Done!')
                
                # Find the extracted directory (GitHub adds -main suffix)
                extracted_dirs = [d for d in temp_path.iterdir() if d.is_dir()]
                if not extracted_dirs:
                    raise Exception("No directory found in archive")
                
                source_dir = extracted_dirs[0]
                
                # Move files to installation directory
                print("Installing files... ", end='', flush=True)
                files_copied = 0
                for item in source_dir.iterdir():
                    dest = self.install_dir / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest, dirs_exist_ok=True)
                        # Count files in directory
                        files_copied += sum(1 for _ in item.rglob('*') if _.is_file())
                    else:
                        shutil.copy2(item, dest)
                        files_copied += 1
                
                print(f"Done! ({files_copied} files installed)")
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
        
        # First, ensure the venv module is available
        try:
            # Check if venv module exists
            result = subprocess.run(
                [self.python_cmd, "-c", "import venv"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                print(f"{Colors.WARNING}⚠️ venv module not found. Attempting to install...{Colors.ENDC}")
                
                # Try to install venv (on some systems it's separate)
                if self.os_type == "Windows":
                    print("On Windows, venv should be included with Python.")
                    print("Try reinstalling Python from python.org with standard library included.")
                else:
                    print("Try: sudo apt-get install python3-venv (Ubuntu/Debian)")
                    print("Or: sudo dnf install python3-venv (Fedora)")
                
                # Try using virtualenv as fallback
                print(f"\n{Colors.BLUE}Trying virtualenv as fallback...{Colors.ENDC}")
                try:
                    subprocess.run(
                        [self.python_cmd, "-m", "pip", "install", "virtualenv"],
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    
                    result = subprocess.run(
                        [self.python_cmd, "-m", "virtualenv", str(self.venv_path)],
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    
                    if result.returncode == 0:
                        print(f"{Colors.GREEN}✅ Created virtual environment using virtualenv{Colors.ENDC}")
                    else:
                        raise Exception("virtualenv also failed")
                        
                except Exception as e:
                    print(f"{Colors.RED}Could not create virtual environment: {e}{Colors.ENDC}")
                    print(f"\n{Colors.YELLOW}Proceeding without virtual environment...{Colors.ENDC}")
                    print("Dependencies will be installed globally.")
                    
                    # Use global Python
                    return self.setup_without_venv()
        except Exception as e:
            print(f"{Colors.WARNING}Could not verify venv module: {e}{Colors.ENDC}")
        
        # Try to create virtual environment
        try:
            print("Creating virtual environment...")
            
            # Clear any existing broken venv
            if self.venv_path.exists():
                print("Removing existing venv directory...")
                shutil.rmtree(self.venv_path, ignore_errors=True)
            
            # Create venv with explicit options for better compatibility
            result = subprocess.run(
                [self.python_cmd, "-m", "venv", str(self.venv_path), "--clear"],
                capture_output=True,
                text=True,
                timeout=120  # Increased timeout
            )
            
            if result.returncode != 0:
                print(f"{Colors.RED}venv creation failed with error:{Colors.ENDC}")
                print(f"STDOUT: {result.stdout}")
                print(f"STDERR: {result.stderr}")
                
                # Try without extra options
                print(f"{Colors.BLUE}Trying simplified venv creation...{Colors.ENDC}")
                result = subprocess.run(
                    [self.python_cmd, "-m", "venv", str(self.venv_path)],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if result.returncode != 0:
                    print(f"{Colors.RED}Still failed: {result.stderr}{Colors.ENDC}")
                    return self.setup_without_venv()
            
            # Get venv Python and pip paths
            if self.os_type == "Windows":
                venv_python = self.venv_path / "Scripts" / "python.exe"
                venv_pip = self.venv_path / "Scripts" / "pip.exe"
            else:
                venv_python = self.venv_path / "bin" / "python"
                venv_pip = self.venv_path / "bin" / "pip"
            
            # Verify venv was created
            if not venv_python.exists():
                print(f"{Colors.RED}Virtual environment not created properly{Colors.ENDC}")
                return self.setup_without_venv()
            
            # Upgrade pip
            print(f"{Colors.BLUE}📦 Upgrading pip...{Colors.ENDC}")
            result = subprocess.run(
                [str(venv_python), "-m", "pip", "install", "--upgrade", "pip"],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                print(f"{Colors.WARNING}Could not upgrade pip: {result.stderr}{Colors.ENDC}")
            
            # Install requirements
            requirements_file = self.install_dir / "requirements.txt"
            if requirements_file.exists():
                print(f"{Colors.BLUE}📦 Installing dependencies...{Colors.ENDC}")
                print("This may take a few minutes...")
                
                result = subprocess.run(
                    [str(venv_python), "-m", "pip", "install", "-r", str(requirements_file)],
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minutes timeout
                )
                
                if result.returncode != 0:
                    print(f"{Colors.RED}Failed to install dependencies:{Colors.ENDC}")
                    print(result.stderr)
                    return False
                    
                print(f"{Colors.GREEN}✅ Dependencies installed{Colors.ENDC}")
            else:
                print(f"{Colors.WARNING}⚠️  No requirements.txt found{Colors.ENDC}")
            
            self.python_cmd = str(venv_python)
            return True
            
        except subprocess.TimeoutExpired:
            print(f"{Colors.RED}❌ Installation timed out{Colors.ENDC}")
            return False
        except Exception as e:
            print(f"{Colors.RED}❌ Failed to setup virtual environment: {e}{Colors.ENDC}")
            return self.setup_without_venv()
    
    def setup_without_venv(self) -> bool:
        """Setup without virtual environment - install globally"""
        print(f"\n{Colors.YELLOW}Installing without virtual environment...{Colors.ENDC}")
        
        response = ""
        if not self.args.non_interactive:
            print(f"{Colors.WARNING}This will install packages globally.{Colors.ENDC}")
            print("Continue? (y/n): ", end='', flush=True)
            try:
                response = input().lower().strip()
            except:
                response = "n"
        else:
            response = "y"  # Auto-yes in non-interactive mode
        
        if response != 'y':
            print(f"{Colors.RED}Installation cancelled{Colors.ENDC}")
            return False
        
        # Install requirements globally
        requirements_file = self.install_dir / "requirements.txt"
        if requirements_file.exists():
            print(f"{Colors.BLUE}📦 Installing dependencies globally...{Colors.ENDC}")
            
            result = subprocess.run(
                [self.python_cmd, "-m", "pip", "install", "-r", str(requirements_file)],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                print(f"{Colors.RED}Failed to install dependencies:{Colors.ENDC}")
                print(result.stderr)
                return False
                
            print(f"{Colors.GREEN}✅ Dependencies installed globally{Colors.ENDC}")
        
        # Keep using the same Python command
        # Don't change self.python_cmd since we're using the system Python
        return True
    
    def configure_nmc(self) -> bool:
        """Configure NMC connection settings"""
        print(f"\n{Colors.HEADER}🔐 NMC Configuration{Colors.ENDC}")
        
        # Check if credentials provided via command line
        if self.args.nmc_url and self.args.username and self.args.password:
            nmc_url = self.args.nmc_url
            username = self.args.username
            password = self.args.password
            verify_ssl = False
            print(f"Using provided credentials for {nmc_url}")
        elif self.args.non_interactive:
            print(f"{Colors.WARNING}Non-interactive mode: Creating sample .env file{Colors.ENDC}")
            self.create_sample_env()
            return True
        else:
            print("Enter your NMC connection details:\n")
            
            try:
                # Check if we're in interactive mode
                if not (hasattr(sys.stdin, 'isatty') and sys.stdin.isatty()):
                    print(f"{Colors.WARNING}Non-interactive mode detected.{Colors.ENDC}")
                    print("Please create .env file manually with your NMC credentials.")
                    self.create_sample_env()
                    return True
                
                # Get NMC URL
                print("NMC Server URL (e.g., https://nmc.company.com): ", end='', flush=True)
                nmc_url = input().strip()
                if not nmc_url:
                    print(f"\n{Colors.RED}❌ NMC URL is required{Colors.ENDC}")
                    return False
                
                # Ensure URL has protocol
                if not nmc_url.startswith(('http://', 'https://')):
                    nmc_url = f"https://{nmc_url}"
                
                # Get credentials
                print("NMC Username: ", end='', flush=True)
                username = input().strip()
                if not username:
                    print(f"\n{Colors.RED}❌ Username is required{Colors.ENDC}")
                    return False
                
                # Use getpass for password
                password = getpass.getpass("NMC Password: ")
                if not password:
                    print(f"{Colors.RED}❌ Password is required{Colors.ENDC}")
                    return False
                
                # SSL verification
                print("Verify SSL certificate? (y/n) [n]: ", end='', flush=True)
                verify_ssl = input().lower()
                
            except (EOFError, KeyboardInterrupt):
                print(f"\n{Colors.WARNING}Configuration interrupted. Creating sample .env file...{Colors.ENDC}")
                self.create_sample_env()
                return True
            except Exception as e:
                print(f"\n{Colors.RED}Error during configuration: {e}{Colors.ENDC}")
                self.create_sample_env()
                return True
        
        # Ensure URL has protocol
        if not nmc_url.startswith(('http://', 'https://')):
            nmc_url = f"https://{nmc_url}"
        
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
    
    def create_sample_env(self):
        """Create a sample .env file for manual configuration"""
        sample_env = self.install_dir / ".env.example"
        env_content = """# NMC API Configuration
# Edit this file and rename to .env

API_BASE_URL="https://your-nmc-server.com"
NMC_USERNAME="your-username"
NMC_PASSWORD="your-password"
VERIFY_SSL=false
API_TIMEOUT=30.0
"""
        try:
            sample_env.write_text(env_content)
            print(f"{Colors.YELLOW}📝 Created sample configuration: {sample_env}{Colors.ENDC}")
            print(f"   Edit this file with your credentials and rename to .env")
        except Exception as e:
            print(f"{Colors.RED}Failed to create sample config: {e}{Colors.ENDC}")
    
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
    
    def check_claude_desktop(self) -> tuple:
        """Check if Claude Desktop is installed"""
        claude_installed = False
        claude_locations = []
        
        if self.os_type == "Darwin":  # macOS
            # Check for Claude.app
            app_locations = [
                "/Applications/Claude.app",
                self.home / "Applications" / "Claude.app",
                "/System/Applications/Claude.app"
            ]
            for loc in app_locations:
                if Path(loc).exists():
                    claude_installed = True
                    claude_locations.append(str(loc))
                    
        elif self.os_type == "Windows":
            # Check Windows registry and common paths
            program_files = [
                Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")),
                Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")),
                Path(os.environ.get("LOCALAPPDATA", "")) / "Programs"
            ]
            for base in program_files:
                if base.exists():
                    claude_path = base / "Claude" / "Claude.exe"
                    if claude_path.exists():
                        claude_installed = True
                        claude_locations.append(str(claude_path))
            
            # Also check AppData for Claude installation
            appdata_claude = Path(os.environ.get("LOCALAPPDATA", "")) / "Claude"
            if appdata_claude.exists():
                claude_installed = True
                claude_locations.append(str(appdata_claude))
            
            # Check Start Menu for Claude shortcut
            start_menu = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            if start_menu.exists() and (start_menu / "Claude.lnk").exists():
                claude_installed = True
                
        else:  # Linux
            # Check common Linux locations
            desktop_files = [
                self.home / ".local" / "share" / "applications" / "claude.desktop",
                Path("/usr/share/applications/claude.desktop"),
                Path("/usr/local/share/applications/claude.desktop")
            ]
            for loc in desktop_files:
                if loc.exists():
                    claude_installed = True
                    claude_locations.append(str(loc))
            
            # Check if claude binary exists in PATH
            claude_bin = shutil.which("claude")
            if claude_bin:
                claude_installed = True
                claude_locations.append(claude_bin)
        
        return claude_installed, claude_locations
    
    def configure_claude_desktop(self) -> bool:
        """Configure Claude Desktop to use the MCP server"""
        print(f"\n{Colors.BLUE}🤖 Configuring Claude Desktop...{Colors.ENDC}")
        
        # Check if Claude Desktop is installed
        claude_installed, claude_locations = self.check_claude_desktop()
        
        if not claude_installed:
            print(f"{Colors.WARNING}⚠️  Claude Desktop not found on this system{Colors.ENDC}")
            print(f"\n{Colors.HEADER}To complete setup:{Colors.ENDC}")
            print(f"1. Install Claude Desktop from: {Colors.CYAN}https://claude.ai/download{Colors.ENDC}")
            print(f"2. After installing Claude, run this command to configure it:")
            print(f"   {Colors.GREEN}{self.python_cmd} {self.install_dir}/configure_claude.py{Colors.ENDC}")
            print(f"\nOr manually add this configuration to Claude Desktop:")
            self.print_manual_config()
            self.create_configure_script()
            return False
        
        print(f"{Colors.GREEN}✅ Claude Desktop found{Colors.ENDC}")
        if claude_locations:
            print(f"   Location: {claude_locations[0]}")
        
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
            # Claude is installed but config directory doesn't exist yet
            print(f"{Colors.WARNING}⚠️  Claude Desktop config directory not found{Colors.ENDC}")
            print(f"\n{Colors.HEADER}This usually means Claude Desktop hasn't been run yet.{Colors.ENDC}")
            print(f"1. Start Claude Desktop at least once")
            print(f"2. Then run: {Colors.GREEN}{self.python_cmd} {self.install_dir}/configure_claude.py{Colors.ENDC}")
            print(f"\nOr manually add this configuration to Claude Desktop:")
            self.print_manual_config()
            self.create_configure_script()
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
            "args": [str(main_py)],
            "cwd": str(self.install_dir)
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
    
    def create_configure_script(self):
        """Create a standalone script to configure Claude Desktop later"""
        configure_script = self.install_dir / "configure_claude.py"
        
        script_content = f'''#!/usr/bin/env python3
"""
Standalone script to configure Claude Desktop for NMC MCP Server
Run this after installing Claude Desktop
"""

import json
import sys
from pathlib import Path

def configure_claude():
    python_cmd = "{self.python_cmd}"
    main_py = "{self.install_dir / 'main.py'}"
    cwd = "{self.install_dir}"
    
    # Find config file (same logic as main installer)
    import platform
    os_type = platform.system()
    home = Path.home()
    
    if os_type == "Darwin":
        config_paths = [
            home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
            home / ".claude" / "claude_desktop_config.json"
        ]
    elif os_type == "Windows":
        import os
        config_paths = [
            home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json",
            Path(os.getenv("APPDATA", "")) / "Claude" / "claude_desktop_config.json"
        ]
    else:
        config_paths = [
            home / ".config" / "Claude" / "claude_desktop_config.json",
            home / ".claude" / "claude_desktop_config.json"
        ]
    
    config_file = None
    for path in config_paths:
        if path.parent.exists():
            config_file = path
            break
    
    if not config_file:
        print("❌ Claude Desktop config directory not found")
        print("Please run Claude Desktop at least once, then try again")
        return False
    
    # Create config directory if needed
    config_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Load or create config
    if config_file.exists():
        with open(config_file, 'r') as f:
            config = json.load(f)
    else:
        config = {{}}
    
    # Add MCP server
    if "mcpServers" not in config:
        config["mcpServers"] = {{}}
    
    config["mcpServers"]["nmc-mcp-server"] = {{
        "command": python_cmd,
        "args": [main_py],
        "cwd": cwd
    }}
    
    # Save config
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)
    
    print("✅ Claude Desktop configured successfully!")
    print(f"   Config file: {{config_file}}")
    print("\\n🚀 Please restart Claude Desktop to use NMC tools")
    return True

if __name__ == "__main__":
    success = configure_claude()
    sys.exit(0 if success else 1)
'''
        
        configure_script.write_text(script_content)
        if self.os_type != "Windows":
            configure_script.chmod(0o755)
        
        print(f"{Colors.GREEN}✅ Created configuration script: {configure_script}{Colors.ENDC}")
    
    def print_manual_config(self):
        """Print manual configuration instructions"""
        main_py = self.install_dir / "main.py"
        
        config_json = {
            "mcpServers": {
                "nmc-mcp-server": {
                    "command": self.python_cmd,
                    "args": [str(main_py)],
                    "cwd": str(self.install_dir)
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
            
            # Step 5: Test connection (skip in non-interactive mode)
            if not self.args.non_interactive:
                self.test_connection()  # Optional, don't fail if it doesn't work
            
            # Step 6: Configure Claude Desktop (skip if requested)
            if not self.args.skip_claude:
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
            import traceback
            traceback.print_exc()
            return False

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='NMC MCP Server Universal Installer')
    parser.add_argument('-d', '--directory', help='Installation directory')
    parser.add_argument('-n', '--non-interactive', action='store_true', 
                       help='Run in non-interactive mode (use defaults)')
    parser.add_argument('--skip-claude', action='store_true',
                       help='Skip Claude Desktop configuration')
    parser.add_argument('--use-git', action='store_true',
                       help='Prefer git clone over ZIP download')
    parser.add_argument('-q', '--quiet', action='store_true',
                       help='Minimal output (recommended for Windows console)')
    parser.add_argument('--nmc-url', help='NMC server URL')
    parser.add_argument('--username', help='NMC username')
    parser.add_argument('--password', help='NMC password')
    
    args = parser.parse_args()
    
    # On Windows, default to quiet mode to prevent crashes
    if platform.system() == "Windows" and not args.quiet:
        print("Note: Running in reduced output mode on Windows to prevent console issues.")
        print("Use --verbose flag if you want detailed output.\n")
        args.quiet = True
    
    # Validate that if credentials are provided, all are provided
    if any([args.nmc_url, args.username, args.password]):
        if not all([args.nmc_url, args.username, args.password]):
            print(f"Error: If providing credentials, you must provide --nmc-url, --username, and --password")
            sys.exit(1)
    
    installer = Installer(args)
    success = installer.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()