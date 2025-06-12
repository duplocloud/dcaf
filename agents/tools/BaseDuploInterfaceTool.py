import logging
from typing import Optional
from schemas.UnableToConnetToDuploError import UnableToConnectToDuploException
from schemas.messages import PlatformContext
from services.duplo_client import DuploClient

logger = logging.getLogger(__name__)

class BaseDuploInterfaceTool:
    def __init__(self, platform_context: Optional[PlatformContext]):
        self.duplo_client = self._initialize_duplo_client(platform_context)

    def _initialize_duplo_client(self, platform_context: Optional[PlatformContext]):
        """
        Initialize DuploClient with platform context.
        
        Args:
            platform_context: Dictionary containing duplo_host, duplo_token, etc.
        
        Returns:
            Initialized DuploClient or None if validation fails
        """ 
        try:
            if not self._is_platform_context_valid(platform_context):
                raise UnableToConnectToDuploException("platform_context does not have enough for to access duplo")
                
            logger.info("Initializing DuploClient...")
            return DuploClient(platform_context)
        except Exception as e:
            logger.error(f"Error initializing DuploClient: {str(e)}")
            return None
        
    def _is_platform_context_valid(self, platform_context: Optional[PlatformContext]):
        """
        Validate that the platform context contains all required fields.
        
        Args:
            platform_context: Dictionary containing duplo_host, duplo_token, etc.
        
        Returns:
            True if all required fields are present, False otherwise
        """
        if not platform_context:
            logger.error("Platform context is missing")
            return False
            
        required_fields = ['duplo_host', 'duplo_token', 'tenant_name', 'tenant_id']
        logger.info("Validating platform context")
        
        # Check if all required fields exist and are not empty
        missing_fields = []
        for field in required_fields:
            if not platform_context.get(field):
                missing_fields.append(field)
        
        if missing_fields:
            logger.error(f"Missing required fields in platform context: {', '.join(missing_fields)}")
            return False
        
        logger.info("Platform context validation successful")
        return True