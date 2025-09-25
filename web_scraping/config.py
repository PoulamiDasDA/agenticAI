# Web Scraping Configuration File
import os
import logging
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ==============================================================================
# LOGGING CONFIGURATION
# ==============================================================================

def setup_logging():
    """Configure logging for containers and local development"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

# ==============================================================================
# STORAGE CONFIGURATION
# ==============================================================================

STORAGE_CONFIG = {
    'account_name': os.getenv("AZURE_STORAGE_ACCOUNT_NAME", "explorationstorage12"),
    'container_name': os.getenv("AZURE_STORAGE_CONTAINER_NAME", "data"),
    'credential_type': os.getenv("AZURE_CREDENTIAL_TYPE", "AAD")  # Use environment variable
}

# ==============================================================================
# WEBSITE CONFIGURATION
# ==============================================================================

def get_websites_config():
    """
    Get all websites configuration from environment variables
    Multi-website JSON format only
    Returns list of website configurations
    """
    import json
    
    # Multi-website JSON configuration (required)
    websites_json = os.getenv("WEBSITES_CONFIG")
    if not websites_json:
        raise ValueError(
            "WEBSITES_CONFIG environment variable is required. "
            "Please set WEBSITES_CONFIG with JSON array of websites."
        )
    
    try:
        websites_list = json.loads(websites_json)
        # Validate each website config
        validated_websites = []
        for i, website in enumerate(websites_list):
            if not isinstance(website, dict):
                raise ValueError(f"Website {i} must be a dictionary")
            
            # Ensure required fields
            required_fields = ['url', 'name', 'key']
            for field in required_fields:
                if field not in website:
                    raise ValueError(f"Website {i} missing required field: {field}")
            
            # Set defaults for optional fields
            website.setdefault('max_depth', 3)
            website.setdefault('folder_name', website['key'].replace('_', '-'))
            website.setdefault('filters', [])
            
            # Convert filters string to list if needed
            if isinstance(website['filters'], str):
                website['filters'] = [f.strip() for f in website['filters'].split(',') if f.strip()]
            
            validated_websites.append(website)
        
        if not validated_websites:
            raise ValueError("WEBSITES_CONFIG must contain at least one website configuration")
        
        return validated_websites
        
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in WEBSITES_CONFIG: {e}")
    except Exception as e:
        raise ValueError(f"Error parsing WEBSITES_CONFIG: {e}")


def get_website_config(website_key=None):
    """
    Get specific website configuration
    If website_key is None, returns the first/default website
    """
    websites = get_websites_config()
    
    if website_key:
        # Find specific website by key
        for website in websites:
            if website['key'] == website_key:
                return website
        raise ValueError(f"Website '{website_key}' not found. Available: {[w['key'] for w in websites]}")
    
    # Return first website as default
    return websites[0]


def list_available_websites():
    """
    Get list of all available website keys
    """
    websites = get_websites_config()
    return [website['key'] for website in websites]

# ==============================================================================
# PROCESSING CONFIGURATION
# ==============================================================================

PROCESSING_CONFIG = {
    'default_mode': os.getenv('SCRAPING_MODE', 'full'),
    'default_website': os.getenv('DEFAULT_WEBSITE_KEY', None),  # Which website to use by default
    'upload_to_cloud': os.getenv('UPLOAD_TO_CLOUD', 'true').lower() == 'true',
    'flatten_data': os.getenv('FLATTEN_DATA', 'true').lower() == 'true',
    'timer_enabled': os.getenv('TIMER_ENABLED', 'false').lower() == 'true'
}

# ==============================================================================
# HEALTH CHECK CONFIGURATION
# ==============================================================================

HEALTH_CONFIG = {
    'port': int(os.getenv('HEALTH_CHECK_PORT', '8000')),
    'host': os.getenv('HEALTH_CHECK_HOST', '0.0.0.0'),
    'service_name': os.getenv('SERVICE_NAME', 'cbuae-scraper')
}

# ==============================================================================
# REQUEST CONFIGURATION
# ==============================================================================

REQUEST_CONFIG = {
    'timeout': int(os.getenv('REQUEST_TIMEOUT', '10')),
    'max_retries': int(os.getenv('MAX_RETRIES', '3')),
    'backoff_factor': float(os.getenv('BACKOFF_FACTOR', '2')),
    'user_agent': os.getenv('USER_AGENT', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
}

# ==============================================================================
# AZURE FUNCTIONS CONFIGURATION
# ==============================================================================

FUNCTIONS_CONFIG = {
    'auth_level': os.getenv('FUNCTIONS_AUTH_LEVEL', 'FUNCTION'),
    'default_max_files': int(os.getenv('DEFAULT_MAX_FILES', '100')),
    'payload_size_limit_kb': int(os.getenv('PAYLOAD_SIZE_LIMIT_KB', '15'))
}

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def get_storage_config():
    """Get storage configuration as dictionary"""
    return STORAGE_CONFIG.copy()

def get_processing_config():
    """Get processing configuration as dictionary"""
    return PROCESSING_CONFIG.copy()

def get_health_config():
    """Get health check configuration as dictionary"""
    return HEALTH_CONFIG.copy()

def get_request_config():
    """Get request configuration as dictionary"""
    return REQUEST_CONFIG.copy()

def get_functions_config():
    """Get Azure Functions configuration as dictionary"""
    return FUNCTIONS_CONFIG.copy()

def validate_config():
    """Validate required configuration settings"""
    required_env_vars = [
        'AZURE_STORAGE_ACCOUNT_NAME'
    ]
    
    missing_vars = []
    for var in required_env_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {missing_vars}")
    
    return True

# ==============================================================================
# CONFIGURATION SUMMARY
# ==============================================================================

def print_config_summary(logger=None):
    """Print configuration summary for debugging"""
    if not logger:
        logger = setup_logging()
    
    logger.info("=" * 60)
    logger.info("CONFIGURATION SUMMARY")
    logger.info("=" * 60)
    
    # Storage Configuration
    logger.info("Storage Account: %s", STORAGE_CONFIG['account_name'])
    logger.info("Container: %s", STORAGE_CONFIG['container_name'])
    logger.info("Authentication: %s", STORAGE_CONFIG['credential_type'])
    
    # Website Configuration
    try:
        websites = get_websites_config()
        logger.info("Available Websites: %s", len(websites))
        for website in websites:
            logger.info("  [%s] %s (%s)", website['key'], website['name'], website['url'])
            logger.info("      Folder: %s, Max Depth: %s", website.get('folder_name', website['key']), website.get('max_depth', 3))
        
        # Show default website
        default_key = PROCESSING_CONFIG.get('default_website')
        if default_key:
            logger.info("Default Website: %s", default_key)
        else:
            logger.info("Default Website: %s (first website)", websites[0]['key'] if websites else 'none')
            
    except ValueError as e:
        logger.error("Website configuration error: %s", str(e))
    
    # Processing Configuration
    logger.info("Default Mode: %s", PROCESSING_CONFIG['default_mode'])
    logger.info("Upload to Cloud: %s", PROCESSING_CONFIG['upload_to_cloud'])
    logger.info("Flatten Data: %s", PROCESSING_CONFIG['flatten_data'])
    
    # Health Check Configuration
    logger.info("Health Check: %s:%s", HEALTH_CONFIG['host'], HEALTH_CONFIG['port'])
    
    logger.info("=" * 60)

# ==============================================================================
# EXPORT ALL CONFIGURATIONS
# ==============================================================================

__all__ = [
    'setup_logging',
    'STORAGE_CONFIG',
    'PROCESSING_CONFIG',
    'HEALTH_CONFIG',
    'REQUEST_CONFIG',
    'FUNCTIONS_CONFIG',
    'get_website_config',
    'get_storage_config',
    'get_processing_config',
    'get_health_config',
    'get_request_config',
    'get_functions_config',
    'validate_config',
    'print_config_summary'
]