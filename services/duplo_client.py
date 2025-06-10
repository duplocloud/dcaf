# services/duplo_client.py
import logging
import requests
from typing import Dict, Any, Optional, List, Union
from urllib.parse import urljoin

try:
    from duplocloud.client import DuploClient as OfficialDuploClient
    DUPLO_CLIENT_AVAILABLE = True
except ImportError:
    DUPLO_CLIENT_AVAILABLE = False
    logging.warning("duplocloud-client package not found. Install with: pip install duplocloud-client")

logger = logging.getLogger(__name__)

class DuploClient:
    """
    HTTP client for interacting with DuploCloud API.
    Extracts host URL, token, tenant name, and tenant ID from platform context.
    """
    
    def __init__(self, platform_context: Optional[Dict[str, Any]] = None):
        """
        Initialize the DuploClient with platform context.
        
        Args:
            platform_context: Dictionary containing duplo_host and duplo_token
        """
        self.host = None
        self.token = None
        self.tenant_name = None
        self.tenant_id = None
        
        # Official client instance
        self.official_client = None

        if platform_context:
            self._configure_from_context(platform_context)
    
    def _configure_from_context(self, platform_context: Dict[str, Any]) -> None:
        """
        Configure client from platform context.
        
        Args:
            platform_context: Dictionary containing duplo_host and duplo_token
        """
        logger.info("Configuring DuploClient from platform context...")
        self.host = platform_context.get('duplo_host')
        self.token = platform_context.get('duplo_token')
        self.tenant_name = platform_context.get('tenant_name')
        self.tenant_id = platform_context.get('tenant_id')
        
        logger.info("Configured DuploClient with host, token, tenant name, and tenant ID")
        if not self.host or not self.token or not self.tenant_name or not self.tenant_id:
            logger.warning("DuploClient missing host, token, tenant name, or tenant ID configuration")
        
        # Initialize official client
        if DUPLO_CLIENT_AVAILABLE:
            try:
                self.official_client = OfficialDuploClient.from_creds(
                    host=self.host,
                    token=self.token,
                    tenant=self.tenant_name,
                )
                logger.info("Official DuploCloud client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize official DuploCloud client: {str(e)}")
    
    def _get_headers(self) -> Dict[str, str]:
        """
        Get headers for API requests including authorization.
        
        Returns:
            Dictionary of HTTP headers
        """
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        
        return headers
    
    def _build_url(self, endpoint: str) -> str:
        """
        Build full URL from endpoint.
        
        Args:
            endpoint: API endpoint path
            
        Returns:
            Full URL
        """
        if not self.host:
            raise ValueError("DuploClient host not configured")
        
        return urljoin(self.host, endpoint)
    
    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Make GET request to DuploCloud API.
        
        Args:
            endpoint: API endpoint path
            params: Optional query parameters
            
        Returns:
            API response as dictionary or empty list/dict if 404 status code
        """
        url = self._build_url(endpoint)
        logger.debug(f"Making GET request to {url}")
        headers = self._get_headers()
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"Resource not found (404) for endpoint: {endpoint}")
                # Return empty list or dict based on expected response type
                # Most DuploCloud API endpoints return lists for collections
                return []
            else:
                # Re-raise other HTTP errors
                raise
    
    def post(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make POST request to DuploCloud API.
        
        Args:
            endpoint: API endpoint path
            data: Request payload
            
        Returns:
            API response as dictionary
        """
        url = self._build_url(endpoint)
        headers = self._get_headers()
        
        logger.debug(f"Making POST request to {url}")
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        
        return response.json()
