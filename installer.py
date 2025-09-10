#!/usr/bin/env python3
"""
Nasuni Management MCP Server Universal Installer
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
from typing import Optional, Dict, Tuple, List
import tempfile
import time

# GitHub repository URL
GITHUB_REPO = "https://github.com/nasuni-labs/nasuni-management-mcp-desktop-server"
GITHUB_ARCHIVE = "https://github.com/nasuni-labs/nasuni-management-mcp-desktop-server/archive/refs/heads/main.zip"

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

    #boolen to check if claude was successfully configured
    global claude_configured 
    claude_configured = False

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
        print(f"\n{Colors.BLUE}📥 Downloading latest version from GitHub...{Colors.ENDC}")
        
        # Choose installation directory
        default_dir = self.home / "nasuni-management-mcp-server"
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
                zip_path = temp_path / "nasuni-management-mcp-server.zip"
                
                
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
                        zip_path
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
                
                # Normalize AD credentials format (single \ to double \\)
                if '\\' in username:
                    # First convert any double backslashes to single, then double all
                    username = username.replace('\\\\', '\\').replace('\\', '\\\\')
                    #print(f"Normalized AD username format: {username}")
                
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
API_TOKEN="api_token_here"
API_TOKEN_EXPIRES= ''
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
        """Test NMC connection using the login API"""
        print(f"\n{Colors.BLUE}🔍 Testing NMC connection and credentials...{Colors.ENDC}")
        
        # Load the .env file to get credentials
        env_file = self.install_dir / ".env"
        if not env_file.exists():
            print(f"{Colors.WARNING}⚠️  No .env file found, skipping connection test{Colors.ENDC}")
            return True
        
        # Parse the .env file
        nmc_url = username = password = None
        verify_ssl = False
        
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('API_BASE_URL='):
                    nmc_url = line.split('=', 1)[1].strip().strip('"')
                elif line.startswith('NMC_USERNAME='):
                    username = line.split('=', 1)[1].strip().strip('"')
                elif line.startswith('NMC_PASSWORD='):
                    password = line.split('=', 1)[1].strip().strip('"')
                elif line.startswith('VERIFY_SSL='):
                    verify_ssl = line.split('=', 1)[1].strip().lower() == 'true'
        
        if not all([nmc_url, username, password]):
            print(f"{Colors.WARNING}Missing credentials in .env file{Colors.ENDC}")
            return True
        
        # Test login
        login_url = f"{nmc_url}/api/v1.2/auth/login/"
        print(f"Testing login to: {nmc_url}")
        print(f"Username: {username}")
        
        # Create JSON payload
        import json
        payload = json.dumps({"username": username, "password": password})
        
        try:
            # Use curl for macOS/Linux
            curl_cmd = [
                "curl", "-i", "-X", "POST",
                login_url,
                "-H", "Content-Type: application/json",
                "-d", payload
            ]
            
            if not verify_ssl:
                curl_cmd.insert(1, "-k")
            
            result = subprocess.run(
                curl_cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # Check for success indicators
            if "200 OK" in result.stdout or "token" in result.stdout.lower():
                print(f"{Colors.GREEN}✅ Login successful!{Colors.ENDC}")
                return True
            elif "401" in result.stdout:
                print(f"{Colors.RED}❌ Login failed: Invalid credentials{Colors.ENDC}")
                return False
            else:
                print(f"{Colors.WARNING}⚠️  Unexpected response{Colors.ENDC}")
                return False
                    
        except Exception as e:
            print(f"{Colors.WARNING}⚠️  Could not test connection: {e}{Colors.ENDC}")
            return True  # Don't block installation


    
    def check_claude_desktop(self) -> Tuple[bool, List[str], List[Path]]:
        """
        Enhanced Claude Desktop detection
        Returns: (is_installed, app_locations, config_paths)
        """
        claude_installed = False
        claude_locations = []
        possible_config_paths = []
        
        if self.os_type == "Darwin":  # macOS
            # Application locations
            app_locations = [
                Path("/Applications/Claude.app"),
                self.home / "Applications" / "Claude.app",
                Path("/System/Applications/Claude.app"),
                # Additional possible locations
                Path("/Applications/Setapp/Claude.app"),  # Setapp installation
                self.home / "Applications" / "Setapp" / "Claude.app",
            ]
            
            for loc in app_locations:
                if loc.exists():
                    claude_installed = True
                    claude_locations.append(str(loc))
            
            # Config file locations
            possible_config_paths = [
                self.home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
                self.home / ".claude" / "claude_desktop_config.json",
                self.home / "Library" / "Preferences" / "Claude" / "claude_desktop_config.json",
                # Additional fallback locations
                self.home / ".config" / "claude" / "claude_desktop_config.json",
                self.home / ".config" / "Claude" / "claude_desktop_config.json",
            ]
                    
        elif self.os_type == "Windows":
            # Check various Windows installation paths
            program_locations = []
            
            # Standard Program Files locations
            if os.environ.get("PROGRAMFILES"):
                program_locations.append(Path(os.environ["PROGRAMFILES"]) / "Claude")
            if os.environ.get("PROGRAMFILES(X86)"):
                program_locations.append(Path(os.environ["PROGRAMFILES(X86)"]) / "Claude")
            
            # User-specific installations
            if os.environ.get("LOCALAPPDATA"):
                local_appdata = Path(os.environ["LOCALAPPDATA"])
                program_locations.extend([
                    local_appdata / "Claude",
                    local_appdata / "Programs" / "Claude",
                    local_appdata / "Microsoft" / "WindowsApps" / "Claude",
                    local_appdata /"AnthropicClaude",    # MS Store apps
                ])

            # User-specific installations
            if os.environ.get("APPDATA"):
                local_appdata = Path(os.environ["APPDATA"])
                program_locations.extend([
                    local_appdata / "Local"/"AnthropicClaude",
                ])
            
            # Check for Claude executable
            for base in program_locations:
                if base.exists():
                    # Check for various executable names
                    for exe_name in ["Claude.exe", "claude.exe", "Claude Desktop.exe"]:
                        claude_exe = base / exe_name
                        if claude_exe.exists():
                            claude_installed = True
                            claude_locations.append(str(claude_exe))
                            break
            
            # Also check if Claude is in PATH
            claude_in_path = shutil.which("claude") or shutil.which("Claude")
            if claude_in_path:
                claude_installed = True
                claude_locations.append(claude_in_path)
            
            # Check Start Menu for shortcuts (indicates installation)
            if os.environ.get("APPDATA"):
                start_menu_locations = [
                    Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Claude.lnk",
                    Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Claude" / "Claude.lnk",
                ]
                for shortcut in start_menu_locations:
                    if shortcut.exists():
                        claude_installed = True
                        if str(shortcut) not in claude_locations:
                            claude_locations.append(str(shortcut))
            
            # Config file locations for Windows
            possible_config_paths = [
                Path(os.environ.get("APPDATA", self.home / "AppData" / "Roaming")) / "Claude" / "claude_desktop_config.json",
                Path(os.environ.get("LOCALAPPDATA", self.home / "AppData" / "Local")) / "Claude" / "claude_desktop_config.json",
                self.home / ".claude" / "claude_desktop_config.json",
                # Additional possible locations
                Path(os.environ.get("USERPROFILE", self.home)) / ".claude" / "claude_desktop_config.json",
                Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "Claude" / "claude_desktop_config.json",
            ]
            
        else:  # Linux
            # Check various Linux installation methods
            
            # Desktop file locations (indicates proper installation)
            desktop_files = [
                self.home / ".local" / "share" / "applications" / "claude.desktop",
                self.home / ".local" / "share" / "applications" / "claude-desktop.desktop",
                Path("/usr/share/applications/claude.desktop"),
                Path("/usr/share/applications/claude-desktop.desktop"),
                Path("/usr/local/share/applications/claude.desktop"),
                Path("/var/lib/flatpak/exports/share/applications/com.anthropic.claude.desktop"),  # Flatpak
                self.home / ".local/share/flatpak/exports/share/applications/com.anthropic.claude.desktop",  # User Flatpak
                Path("/var/lib/snapd/desktop/applications/claude.desktop"),  # Snap
            ]
            
            for loc in desktop_files:
                if loc.exists():
                    claude_installed = True
                    claude_locations.append(str(loc))
            
            # Check for binary in common locations
            binary_locations = [
                "/usr/bin/claude",
                "/usr/local/bin/claude",
                "/opt/claude/claude",
                "/opt/Claude/Claude",
                str(self.home / ".local" / "bin" / "claude"),
                "/snap/bin/claude",  # Snap installation
                "/var/lib/flatpak/app/com.anthropic.claude/current/active/files/bin/claude",  # Flatpak
            ]
            
            for binary_path in binary_locations:
                if Path(binary_path).exists():
                    claude_installed = True
                    claude_locations.append(binary_path)
            
            # Check if claude is in PATH
            claude_bin = shutil.which("claude") or shutil.which("Claude")
            if claude_bin:
                claude_installed = True
                if claude_bin not in claude_locations:
                    claude_locations.append(claude_bin)
            
            # AppImage check
            downloads_dir = self.home / "Downloads"
            if downloads_dir.exists():
                for appimage in downloads_dir.glob("*laude*.AppImage"):
                    if appimage.is_file() and os.access(appimage, os.X_OK):
                        claude_installed = True
                        claude_locations.append(str(appimage))
            
            # Config file locations for Linux
            possible_config_paths = [
                self.home / ".config" / "Claude" / "claude_desktop_config.json",
                self.home / ".config" / "claude" / "claude_desktop_config.json",
                self.home / ".claude" / "claude_desktop_config.json",
                # Flatpak config location
                self.home / ".var" / "app" / "com.anthropic.claude" / "config" / "Claude" / "claude_desktop_config.json",
                # Snap config location
                self.home / "snap" / "claude" / "current" / ".config" / "Claude" / "claude_desktop_config.json",
                # Additional fallback locations
                self.home / ".local" / "share" / "Claude" / "claude_desktop_config.json",
                self.home / ".local" / "config" / "Claude" / "claude_desktop_config.json",
            ]
        
        # Remove duplicates while preserving order
        claude_locations = list(dict.fromkeys(claude_locations))
        
        return claude_installed, claude_locations, possible_config_paths

    def find_claude_config_file(self, possible_paths: List[Path]) -> Optional[Path]:
        """
        Find the Claude Desktop config file from a list of possible paths
        Returns the first existing config file or the most likely location to create one
        """
        # First, check if any config file already exists
        for path in possible_paths:
            if path.exists():
                print(f"{Colors.GREEN}✅ Found existing config: {path}{Colors.ENDC}")
                return path
        
        # If no config exists, find the first path where the parent directory exists
        # (Claude has been run and created its config directory)
        for path in possible_paths:
            if path.parent.exists():
                print(f"{Colors.BLUE}📝 Will create config at: {path}{Colors.ENDC}")
                return path
        
        # If no parent directories exist, use the most likely default location
        # and create the directory structure
        default_path = possible_paths[0]
        print(f"{Colors.YELLOW}📁 Creating config directory: {default_path.parent}{Colors.ENDC}")
        try:
            default_path.parent.mkdir(parents=True, exist_ok=True)
            return default_path
        except Exception as e:
            print(f"{Colors.RED}❌ Could not create config directory: {e}{Colors.ENDC}")
            return None


    def safe_update_claude_config(self, config_file: Path, new_server_config: Dict) -> bool:
        """
        Safely update Claude Desktop config without removing existing configurations
        """
        try:
            # Load existing config or create new
            if config_file.exists():
                # Create backup first
                backup_file = config_file.with_suffix('.json.backup')
                shutil.copy2(config_file, backup_file)
                print(f"{Colors.BLUE}📋 Created backup: {backup_file}{Colors.ENDC}")
                
                with open(config_file, 'r', encoding='utf-8') as f:
                    try:
                        config = json.load(f)
                        print(f"{Colors.GREEN}✅ Loaded existing config{Colors.ENDC}")
                    except json.JSONDecodeError as e:
                        print(f"{Colors.WARNING}⚠️ Invalid JSON in config file, creating new config{Colors.ENDC}")
                        print(f"   Error: {e}")
                        config = {}
            else:
                print(f"{Colors.BLUE}📝 Creating new config file{Colors.ENDC}")
                config = {}
            
            # Ensure mcpServers section exists
            if "mcpServers" not in config:
                config["mcpServers"] = {}
                print(f"{Colors.BLUE}➕ Added mcpServers section{Colors.ENDC}")
            
            # Check if nasuni-management-mcp-server already exists
            if "nasuni-management-mcp-server" in config["mcpServers"]:
                old_config = config["mcpServers"]["nasuni-management-mcp-server"]
                print(f"{Colors.WARNING}⚠️ Found existing nasuni-management-mcp-server configuration{Colors.ENDC}")
                print(f"   Current command: {old_config.get('command', 'N/A')}")
                print(f"   Current path: {old_config.get('args', ['N/A'])[0] if old_config.get('args') else 'N/A'}")
                print(f"   New command: {new_server_config['command']}")
                print(f"   New path: {new_server_config.get('args', ['N/A'])[0] if new_server_config.get('args') else 'N/A'}")
                
                # Check if configurations are identical
                if old_config == new_server_config:
                    print(f"{Colors.GREEN}✅ Configuration is already up to date{Colors.ENDC}")
                    return True
                
                # Ask user what to do (if not in non-interactive mode)
                if not self.args.non_interactive:
                    print(f"\n{Colors.YELLOW}What would you like to do?{Colors.ENDC}")
                    print("1. Replace with new configuration (recommended for updates)")
                    print("2. Keep existing configuration")
                    print("3. Save as 'nasuni-management-mcp-server-new' (keep both)")
                    
                    try:
                        choice = input("Choice [1]: ").strip() or "1"
                    except (EOFError, KeyboardInterrupt):
                        print(f"\n{Colors.WARNING}Keeping existing configuration{Colors.ENDC}")
                        return True
                    
                    if choice == "2":
                        print(f"{Colors.GREEN}✅ Keeping existing configuration{Colors.ENDC}")
                        return True
                    elif choice == "3":
                        # Save with different name
                        alternative_name = "nasuni-management-mcp-server-new"
                        counter = 1
                        while f"{alternative_name}" in config["mcpServers"]:
                            counter += 1
                            alternative_name = f"nasuni-management-mcp-server-{counter}"
                        
                        config["mcpServers"][alternative_name] = new_server_config
                        print(f"{Colors.GREEN}✅ Added as '{alternative_name}' (keeping both){Colors.ENDC}")
                    else:
                        # Replace (default)
                        print(f"{Colors.BLUE}📝 Replacing existing configuration...{Colors.ENDC}")
                        config["mcpServers"]["nasuni-management-mcp-server"] = new_server_config
                else:
                    # Non-interactive mode: show warning but proceed with update
                    print(f"{Colors.YELLOW}📝 Non-interactive mode: updating configuration{Colors.ENDC}")
                    config["mcpServers"]["nasuni-management-mcp-server"] = new_server_config
            else:
                # No existing config, just add it
                config["mcpServers"]["nasuni-management-mcp-server"] = new_server_config
                print(f"{Colors.GREEN}✅ Added nasuni-management-mcp-server configuration{Colors.ENDC}")
            
            # Show summary of other configured servers
            other_servers = [k for k in config["mcpServers"].keys() if k != "nasuni-management-mcp-server"]
            if other_servers:
                print(f"{Colors.CYAN}ℹ️ Preserving {len(other_servers)} other MCP server(s):{Colors.ENDC}")
                for server in other_servers[:5]:  # Show first 5
                    print(f"   • {server}")
                if len(other_servers) > 5:
                    print(f"   ... and {len(other_servers) - 5} more")
            
            # Write config with nice formatting
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
                f.write('\n')  # Add trailing newline for better git compatibility
            
            print(f"{Colors.GREEN}✅ Config updated successfully{Colors.ENDC}")
            return True
            
        except PermissionError:
            print(f"{Colors.RED}❌ Permission denied writing to config file{Colors.ENDC}")
            print(f"   Try running with administrator/sudo privileges")
            return False
        except Exception as e:
            print(f"{Colors.RED}❌ Failed to update config: {e}{Colors.ENDC}")
            return False

    def configure_claude_desktop(self) -> bool:
        """Enhanced Claude Desktop configuration"""
        print(f"\n{Colors.BLUE}🤖 Configuring Claude Desktop...{Colors.ENDC}")
        
        # Check if Claude Desktop is installed
        claude_installed, claude_locations, possible_config_paths = self.check_claude_desktop()
        
        if not claude_installed:
            print(f"{Colors.WARNING}⚠️ Claude Desktop not found on this system{Colors.ENDC}")
            print(f"\n{Colors.HEADER}To complete setup:{Colors.ENDC}")
            print(f"1. Install Claude Desktop from: {Colors.CYAN}https://claude.ai/download{Colors.ENDC}")
            print(f"2. Run Claude Desktop at least once")
            print(f"3. Run this command to configure it:")
            print(f"   {Colors.GREEN}{self.python_cmd} {self.install_dir}/configure_claude.py{Colors.ENDC}")
            print(f"\nOr manually add this configuration to Claude Desktop:")
            self.print_manual_config()
            self.create_configure_script()
            return False
        
        print(f"{Colors.GREEN}✅ Claude Desktop found at {len(claude_locations)} location(s){Colors.ENDC}")
        for i, loc in enumerate(claude_locations[:3], 1):  # Show first 3 locations
            print(f"   {i}. {loc}")
        if len(claude_locations) > 3:
            print(f"   ... and {len(claude_locations) - 3} more")
        
        # Find the config file
        config_file = self.find_claude_config_file(possible_config_paths)
        
        if not config_file:
            print(f"{Colors.WARNING}⚠️ Could not determine config file location{Colors.ENDC}")
            print(f"\n{Colors.HEADER}This might mean:{Colors.ENDC}")
            print(f"1. Claude Desktop hasn't been run yet")
            print(f"2. Claude is installed in a non-standard location")
            print(f"3. Permission issues accessing config directories")
            print(f"\n{Colors.HEADER}To fix:{Colors.ENDC}")
            print(f"1. Start Claude Desktop at least once")
            print(f"2. Run: {Colors.GREEN}{self.python_cmd} {self.install_dir}/configure_claude.py{Colors.ENDC}")
            print(f"\nOr manually add this configuration to Claude Desktop:")
            self.print_manual_config()
            self.create_configure_script()
            return False
        
        # Prepare the MCP server configuration
        main_py = self.install_dir / "main.py"
        
        # Ensure main.py exists
        if not main_py.exists():
            print(f"{Colors.RED}❌ main.py not found at {main_py}{Colors.ENDC}")
            return False
        
        new_server_config = {
            "command": self.python_cmd,
            "args": [str(main_py)],
            "cwd": str(self.install_dir),
            # Optional: Add environment variables if needed
            # "env": {
            #     "PYTHONPATH": str(self.install_dir)
            # }
        }
        
        # Update the config file
        success = self.safe_update_claude_config(config_file, new_server_config)
        
        if success:
            print(f"\n{Colors.GREEN}✅ Claude Desktop configured successfully!{Colors.ENDC}")
            print(f"   Config file: {config_file}")
            print(f"\n{Colors.HEADER}Next steps:{Colors.ENDC}")
            print(f"1. {Colors.BOLD}Restart Claude Desktop{Colors.ENDC}")
            print(f"2. Look for 'nasuni-management-mcp-server' in the MCP tools menu")
            print(f"3. Test by asking: 'List all my filers'")

            global claude_configured 
            claude_configured = True

            return True
        else:
            print(f"\n{Colors.YELLOW}Please add this configuration manually:{Colors.ENDC}")
            self.print_manual_config()
            return False

    def create_configure_script(self):
        """Create an enhanced standalone script to configure Claude Desktop later"""
        configure_script = self.install_dir / "configure_claude.py"
        
        script_content = f'''#!/usr/bin/env python3
"""
Standalone script to configure Claude Desktop for NMC MCP Server
Run this after installing Claude Desktop
Enhanced version with better detection and safe config updates
"""

import json
import sys
import shutil
import platform
from pathlib import Path
from typing import Optional, List, Dict, Tuple

def find_claude_desktop() -> Tuple[bool, List[str]]:
    """Find Claude Desktop installation"""
    os_type = platform.system()
    home = Path.home()
    claude_installed = False
    claude_locations = []
    
    if os_type == "Darwin":  # macOS
        app_locations = [
            Path("/Applications/Claude.app"),
            home / "Applications" / "Claude.app",
            Path("/System/Applications/Claude.app"),
            Path("/Applications/Setapp/Claude.app"),
        ]
        for loc in app_locations:
            if loc.exists():
                claude_installed = True
                claude_locations.append(str(loc))
                
    elif os_type == "Windows":
        import os
        program_locations = []
        if os.environ.get("PROGRAMFILES"):
            program_locations.append(Path(os.environ["PROGRAMFILES"]) / "Claude")
        if os.environ.get("LOCALAPPDATA"):
            program_locations.append(Path(os.environ["LOCALAPPDATA"]) / "Claude")
            program_locations.append(Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Claude")
        
        for base in program_locations:
            if base.exists():
                for exe_name in ["Claude.exe", "claude.exe"]:
                    if (base / exe_name).exists():
                        claude_installed = True
                        claude_locations.append(str(base / exe_name))
                        
    else:  # Linux
        binary_locations = [
            "/usr/bin/claude",
            "/usr/local/bin/claude",
            "/opt/claude/claude",
            str(home / ".local" / "bin" / "claude"),
        ]
        for path in binary_locations:
            if Path(path).exists():
                claude_installed = True
                claude_locations.append(path)
    
    return claude_installed, claude_locations

def get_config_paths() -> List[Path]:
    """Get possible config file paths"""
    os_type = platform.system()
    home = Path.home()
    
    if os_type == "Darwin":
        return [
            home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
            home / ".claude" / "claude_desktop_config.json",
        ]
    elif os_type == "Windows":
        import os
        return [
            Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / "Claude" / "claude_desktop_config.json",
            Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local")) / "Claude" / "claude_desktop_config.json",
        ]
    else:
        return [
            home / ".config" / "Claude" / "claude_desktop_config.json",
            home / ".config" / "claude" / "claude_desktop_config.json",
            home / ".claude" / "claude_desktop_config.json",
        ]

def configure_claude():
    python_cmd = "{self.python_cmd}"
    main_py = "{self.install_dir / 'main.py'}"
    cwd = "{self.install_dir}"
    
    # Check if Claude is installed
    installed, locations = find_claude_desktop()
    if not installed:
        print("❌ Claude Desktop not found")
        print("Please install from: https://claude.ai/download")
        return False
    
    print(f"✅ Claude Desktop found")
    
    # Find config file
    config_paths = get_config_paths()
    config_file = None
    
    for path in config_paths:
        if path.exists():
            config_file = path
            print(f"✅ Found config: {{path}}")
            break
        elif path.parent.exists():
            config_file = path
            print(f"📝 Will create config at: {{path}}")
            break
    
    if not config_file:
        # Create directory for first option
        config_file = config_paths[0]
        config_file.parent.mkdir(parents=True, exist_ok=True)
        print(f"📁 Created config directory: {{config_file.parent}}")
    
    # Load or create config
    if config_file.exists():
        # Backup existing config
        backup = config_file.with_suffix('.json.backup')
        shutil.copy2(config_file, backup)
        print(f"📋 Backed up to: {{backup}}")
        
        with open(config_file, 'r', encoding='utf-8') as f:
            try:
                config = json.load(f)
            except:
                print("⚠️ Invalid JSON, creating new config")
                config = {{}}
    else:
        config = {{}}
    
    # Add MCP server (preserving existing servers)
    if "mcpServers" not in config:
        config["mcpServers"] = {{}}
    
    # Show existing servers
    existing = [k for k in config["mcpServers"].keys() if k != "nasuni-management-mcp-server"]
    if existing:
        print(f"ℹ️ Preserving {{len(existing)}} existing MCP server(s)")
    
    config["mcpServers"]["nasuni-management-mcp-server"] = {{
        "command": python_cmd,
        "args": [main_py],
        "cwd": cwd
    }}
    
    # Save config
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write('\\n')
    
    print("✅ Claude Desktop configured successfully!")
    print(f"   Config: {{config_file}}")
    print("\\n🚀 Please restart Claude Desktop to use NMC tools")
    return True

if __name__ == "__main__":
    try:
        success = configure_claude()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Error: {{e}}")
        sys.exit(1)
'''
        
        try:
            configure_script.write_text(script_content, encoding="utf-8")
            if self.os_type != "Windows":
                configure_script.chmod(0o755)
            print(f"{Colors.GREEN}✅ Created configuration script: {configure_script}{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.RED}❌ Failed to create configure script: {e}{Colors.ENDC}")

    def print_manual_config(self):
        """Print manual configuration instructions with better formatting"""
        main_py = self.install_dir / "main.py"
        
        config_json = {
            "mcpServers": {
                "nasuni-management-mcp-server": {
                    "command": self.python_cmd,
                    "args": [str(main_py)],
                    "cwd": str(self.install_dir)
                }
            }
        }
        
        print(f"\n{Colors.CYAN}{'='*60}{Colors.ENDC}")
        print(f"{Colors.HEADER}Manual Configuration for claude_desktop_config.json:{Colors.ENDC}")
        print(f"{Colors.CYAN}{'='*60}{Colors.ENDC}")
        print("\nAdd this to your existing mcpServers section:")
        print(f"{Colors.YELLOW}")
        print(json.dumps(config_json["mcpServers"]["nasuni-management-mcp-server"], indent=2))
        print(f"{Colors.ENDC}")
        print(f"\nOr if you have no existing config, use this complete file:")
        print(f"{Colors.YELLOW}")
        print(json.dumps(config_json, indent=2))
        print(f"{Colors.ENDC}")
        print(f"{Colors.CYAN}{'='*60}{Colors.ENDC}")
        
        # Show common config locations
        print(f"\n{Colors.HEADER}Common config file locations:{Colors.ENDC}")
        if self.os_type == "Darwin":
            print(f"  • macOS: ~/Library/Application Support/Claude/claude_desktop_config.json")
        elif self.os_type == "Windows":
            print(f"  • Windows: %APPDATA%\\Claude\\claude_desktop_config.json")
            print(f"            (Usually: C:\\Users\\{{username}}\\AppData\\Roaming\\Claude\\)")
        else:
            print(f"  • Linux: ~/.config/Claude/claude_desktop_config.json")


    def create_shortcuts(self):
        """Create convenient shortcuts/commands"""
        print(f"\n{Colors.BLUE}🔗 Creating shortcuts...{Colors.ENDC}")
        
        if self.os_type == "Windows":
            # Create batch file
            batch_file = self.install_dir / "nasuni-management-mcp.bat"
            batch_content = f'''@echo off
"{self.python_cmd}" "{self.install_dir}\\main.py" %*
'''
            batch_file.write_text(batch_content)
            print(f"  Created: {batch_file}")
            
        else:
            # Create shell script
            shell_file = self.install_dir / "nasuni-management-mcp"
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
        #claude_installed, _ = self.check_claude_desktop()
        claude_installed= claude_configured

        if claude_installed:
            print(f"\n{Colors.HEADER}🚀 Next Steps:{Colors.ENDC}")
            print(f"  1. {Colors.BOLD}Restart Claude Desktop{Colors.ENDC}")
            print(f"  2. Look for 'nasuni-management-mcp-server' in Claude's tools menu")
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
            # Get confirmation before proceeding with setup
            proceed_with_claude_setup = input(f"{Colors.YELLOW}Continue with Claude Setup? (y/n): {Colors.ENDC}").lower()
            
            if proceed_with_claude_setup  != 'y': 
                print(f"\n{Colors.YELLOW}Skipped Claude Setup{Colors.ENDC}")
                return True

            if not self.args.skip_claude and proceed_with_claude_setup == 'y':
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
    input(f"{Colors.YELLOW}Hit enter to exit: {Colors.ENDC}")
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
