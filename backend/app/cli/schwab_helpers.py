"""
Helper functions for Schwab OAuth automation
"""
import subprocess
import time
import httpx
from pathlib import Path
from app.logger import logger


class OAuthServerManager:
    """Manages the FastAPI server for OAuth callbacks"""
    
    def __init__(self):
        self.process = None
        self.server_url = "http://127.0.0.1:8000"
    
    def is_server_running(self, require_https: bool = False) -> bool:
        """Check if server is already running"""
        # Try HTTPS first, then HTTP
        urls = ["https://127.0.0.1:8000", "http://127.0.0.1:8000"]
        if require_https:
            urls = ["https://127.0.0.1:8000"]  # Only check HTTPS
        
        for url in urls:
            try:
                response = httpx.get(f"{url}/health", timeout=2.0, verify=False)
                if response.status_code == 200:
                    self.server_url = url
                    return True
            except:
                continue
        return False
    
    def start_server(self) -> bool:
        """Start the FastAPI server in the background with HTTPS"""
        backend_path = Path(__file__).parent.parent.parent
        key_file = backend_path / "key.pem"
        cert_file = backend_path / "cert.pem"
        
        # Determine if we're using HTTPS
        use_https = key_file.exists() and cert_file.exists()
        
        # Check if correct type of server is already running
        if use_https and self.is_server_running(require_https=True):
            logger.info("OAuth HTTPS server already running")
            return True
        elif not use_https and self.is_server_running():
            logger.info("OAuth HTTP server already running")
            return True
        
        # Kill any old HTTP server if we're starting HTTPS
        if use_https:
            try:
                import psutil
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        cmdline = proc.info.get('cmdline', [])
                        if cmdline and 'uvicorn' in ' '.join(cmdline) and 'app.main:app' in ' '.join(cmdline):
                            # Check if it's NOT running with SSL
                            if '--ssl-keyfile' not in ' '.join(cmdline):
                                logger.info(f"Killing old HTTP server (PID {proc.info['pid']})")
                                proc.terminate()
                                proc.wait(timeout=3)
                    except:
                        continue
            except ImportError:
                # psutil not available, try pkill
                subprocess.run(['pkill', '-f', 'uvicorn app.main:app'], stderr=subprocess.DEVNULL)
                time.sleep(1)
        
        try:
            venv_python = backend_path / ".venv" / "bin" / "python"
            
            # Build uvicorn command
            cmd = [
                str(venv_python), "-m", "uvicorn",
                "app.main:app",
                "--host", "127.0.0.1",
                "--port", "8000",
            ]
            
            # Add SSL if certificates exist
            if use_https:
                cmd.extend([
                    "--ssl-keyfile", str(key_file),
                    "--ssl-certfile", str(cert_file),
                ])
                logger.info("Starting OAuth server with HTTPS")
            else:
                logger.warning("SSL certificates not found, starting with HTTP")
            
            # Start uvicorn in background
            self.process = subprocess.Popen(
                cmd,
                cwd=str(backend_path),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            
            # Wait for server to start
            for _ in range(15):
                time.sleep(0.5)
                if use_https and self.is_server_running(require_https=True):
                    logger.success("OAuth HTTPS server started")
                    return True
                elif not use_https and self.is_server_running():
                    logger.success("OAuth HTTP server started")
                    return True
            
            logger.error("OAuth server failed to start")
            return False
            
        except Exception as e:
            logger.error(f"Failed to start OAuth server: {e}")
            return False
    
    def stop_server(self):
        """Stop the OAuth server"""
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
            logger.info("OAuth server stopped")


# Global instance
oauth_server = OAuthServerManager()
