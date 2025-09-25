# Cell 1: Imports and Setup
import os
import json
from datetime import datetime
import signal
import sys
import threading
import time

# Import configuration
from config import (
    setup_logging, 
    STORAGE_CONFIG, 
    PROCESSING_CONFIG,
    HEALTH_CONFIG,
    get_website_config,
    validate_config,
    print_config_summary
)

# Import our consolidated modules
from SimpleScraper import SimpleScraper
from WebScrapingProcessor import create_processor
from StorageAccount import StorageAccount  # Import class directly
from unified_scraping_utils import SkeletonDiscovery

# Setup logging using configuration
logger = setup_logging()

def get_storage_account():
    """Get existing storage account instance"""
    return StorageAccount(
        storage_account_name=STORAGE_CONFIG['account_name'],
        container_name=STORAGE_CONFIG['container_name'],
        credential_type=STORAGE_CONFIG['credential_type']
    )

# Add graceful shutdown handling
def signal_handler(sig, frame):
    logger.info('Received shutdown signal, cleaning up...')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Add this function for container health checks
def create_health_server():
    """Create a simple health check server for containers"""
    try:
        from fastapi import FastAPI
        import uvicorn
        
        app = FastAPI()
        
        @app.get("/health")
        async def health_check():
            return {
                "status": "healthy", 
                "service": HEALTH_CONFIG['service_name'],
                "timestamp": datetime.now().isoformat()
            }
        
        @app.get("/")
        async def root():
            return {
                "message": f"{HEALTH_CONFIG['service_name']} is running", 
                "status": "active",
                "timestamp": datetime.now().isoformat()
            }
        
        def run_server():
            uvicorn.run(
                app, 
                host=HEALTH_CONFIG['host'], 
                port=HEALTH_CONFIG['port'], 
                log_level="info"
            )
        
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        logger.info(f"Health check server started on {HEALTH_CONFIG['host']}:{HEALTH_CONFIG['port']}")
        
    except ImportError:
        logger.warning("FastAPI not available, skipping health check server")

# Cell 2: Main Processing Function
def process_website_config(website_config, processing_mode='full'):
    """
    Main function to process websites with direct configuration
    
    Args:
        website_config: Dictionary with website configuration
                       {url, name, max_depth, filters}
        processing_mode: 'discovery', 'scraping', 'full'
    """
    
    # Extract configuration
    base_url = website_config['url']
    website_name = website_config['name']
    max_depth = website_config.get('max_depth', 3)
    filters = website_config.get('filters', [])
    
    logger.info(f"[PROCESSING] Processing {website_name}")
    logger.info(f"[PROCESSING] Base URL: {base_url}")
    logger.info(f"[PROCESSING] Max depth: {max_depth}")
    logger.info(f"[PROCESSING] Filters: {filters}")
    
    # Initialize components (simplified - no site type distinction)
    scraper = SimpleScraper()
    processor = create_processor("generic", website_name.lower().replace(' ', '_'))
    
    results = {}
    
    # Step 1: Site Discovery
    if processing_mode in ['discovery', 'full']:
        logger.info(f"[PHASE 1] Site Structure Discovery")
        
        # Use unified hierarchical discovery (auto-detection)
        discovered_structure = scraper.discover_site_skeleton_hierarchical(
            base_url, 
            max_depth=max_depth
        )
        
        # Apply filters
        if filters:
            logger.info(f"[FILTERS] Applying filters: {filters}")
            discovered_structure = apply_filters(discovered_structure, filters)
        
        # Save discovery results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        discovery_file = f"scraped_data/{website_name.lower().replace(' ', '_')}_discovery_{timestamp}.json"
        os.makedirs("scraped_data", exist_ok=True)
        
        with open(discovery_file, 'w', encoding='utf-8') as f:
            json.dump(discovered_structure, f, ensure_ascii=False, indent=2)
        
        logger.info(f"[SUCCESS] Discovery completed: {discovery_file}")
        results['discovery'] = {
            'structure': discovered_structure,
            'file': discovery_file
        }
    
    # Step 2: Content Scraping
    if processing_mode in ['scraping', 'full']:
        logger.info(f"[PHASE 2] Content Scraping")
        
        # Extract URLs for scraping
        if 'discovery' in results:
            urls_to_scrape = extract_urls_from_structure(results['discovery']['structure'])
        else:
            # Fallback: use hierarchical discovery
            discovered_structure = scraper.discover_site_skeleton_hierarchical(base_url, max_depth=1)
            urls_to_scrape = extract_urls_from_structure(discovered_structure)
        
        logger.info(f"[SCRAPING] Scraping {len(urls_to_scrape)} URLs")
        
        # Scrape content
        scraped_data = scraper.scrape_website(urls_to_scrape, max_depth=max_depth)
        
        logger.info(f"[SUCCESS] Scraping completed: {len(scraped_data)} pages")
        results['scraping'] = {
            'data': scraped_data,
            'count': len(scraped_data)
        }
    
    # Step 3: Content Processing
    if processing_mode == 'full' and 'scraping' in results:
        logger.info(f"[PHASE 3] Content Processing")
        
        if isinstance(scraped_data, list):
            scraped_data = {item['url']: item for item in results['scraping']['data'] if 'url' in item}
 
        # Process scraped data using the processor
        saved_files, individual_dir = processor.save_processed_data(
            scraped_data
        )
        
        # Apply any website-specific processing based on URL patterns
        if 'cbuae' in base_url.lower():
            logger.info(f"[CBUAE] Applying CBUAE-specific processing...")
            
            # Load the saved data for processing
            enhanced_data = []
            for file_info in saved_files:
                try:
                    with open(file_info['filepath'], 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        
                    # Apply CBUAE-specific enhancements if methods exist
                    if hasattr(processor, 'site_processor') and hasattr(processor.site_processor, 'process_cbuae_url'):
                        if data.get('url'):
                            versions = processor.site_processor.process_cbuae_url(data['url'])
                            if versions:
                                data['cbuae_versions'] = versions
                                if 'document_metadata' in data:
                                    data['document_metadata'].update(versions[0].get('metadata', {}))
                    
                    enhanced_data.append(data)
                    
                    # Re-save enhanced data
                    with open(file_info['filepath'], 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                        
                except Exception as e:
                    logger.warning(f"[WARNING] Error processing {file_info['filepath']}: {e}")
                    continue
            
            logger.info(f"[SUCCESS] CBUAE processing completed")
        
        results['processing'] = {
            'saved_files': saved_files,
            'individual_dir': individual_dir
        }
    
    return results

def process_website(processing_mode='full', website_key=None):
    """
    Process website using environment configuration only
    
    Args:
        processing_mode: 'discovery', 'scraping', 'full'
        website_key: Specific website key to process (None for default)
    """
    
    # Get environment config (required)
    website_config = get_website_config(website_key)
    logger.info(f"[CONFIG] Using website: {website_config['key']} - {website_config['name']}")
    return process_website_config(website_config, processing_mode)

# Cell 3: Helper Functions
def apply_filters(structure, filters):
    """Apply URL filters to discovered structure"""
    if not filters:
        return structure
    
    def filter_item(item):
        url = item.get('main_item_url', '') or item.get('reference_link', '')
        return not any(filter_term.lower() in url.lower() for filter_term in filters)
    
    # Filter main items
    if 'main_items' in structure:
        structure['main_items'] = [
            item for item in structure['main_items'] 
            if filter_item(item)
        ]
        
        # Filter sub-items
        for main_item in structure['main_items']:
            if 'sub_item_section' in main_item:
                main_item['sub_item_section'] = [
                    sub_item for sub_item in main_item['sub_item_section']
                    if filter_item(sub_item)
                ]
    
    return structure

def extract_urls_from_structure(structure):
    """Extract all URLs from hierarchical structure"""
    urls = []
    
    for main_item in structure.get('main_items', []):
        if main_item.get('main_item_url'):
            urls.append(main_item['main_item_url'])
        
        for sub_item in main_item.get('sub_item_section', []):
            if sub_item.get('reference_link'):
                urls.append(sub_item['reference_link'])
            
            # Handle nested body items
            def extract_from_body(body_items):
                for body_item in body_items:
                    if body_item.get('reference_link'):
                        urls.append(body_item['reference_link'])
                    if body_item.get('body'):
                        extract_from_body(body_item['body'])
            
            if sub_item.get('body'):
                extract_from_body(sub_item['body'])
    
    return list(set(urls))  # Remove duplicates

# Cell 4: Azure Upload Function
def upload_to_azure(results, website_key=None):
    """Upload processing results to your existing Azure Storage"""
    
    if 'processing' not in results:
        logger.error("[ERROR] No processing results to upload")
        return {
            'session_prefix': 'no_processing_data',
            'individual_files': {'successful_uploads': [], 'failed_uploads': []},
            'total_successful': 0,
            'total_failed': 0,
            'total_size_mb': 0,
            'status': 'no_data'
        }
    
    try:
        # Get website configuration for container name
        website_config = get_website_config(website_key)
        
        # Use your existing storage account
        storage = get_storage_account()
        
        # Use website-specific folder within the main container
        container_name = STORAGE_CONFIG['container_name']
        folder_name = website_config.get('folder_name', website_config['key'])
        
        logger.info(f"[STORAGE] Using existing storage: {STORAGE_CONFIG['account_name']}")
        logger.info(f"[STORAGE] Container: {container_name}")
        logger.info(f"[STORAGE] Website folder: {folder_name}")
        logger.info(f"[STORAGE] Website: {website_config['key']} - {website_config['name']}")
        logger.info(f"[STORAGE] Authentication: {STORAGE_CONFIG['credential_type']}")
        logger.info(f"[STORAGE] Azure Available: {storage.azure_available}")
        
        if not storage.azure_available:
            logger.warning("[WARNING] Azure Storage not available, keeping files locally")
            return {
                'session_prefix': 'local_only',
                'individual_files': {'successful_uploads': [], 'failed_uploads': []},
                'total_successful': 0,
                'total_failed': 0,
                'total_size_mb': 0,
                'status': 'local_fallback'
            }
        
        # Create folder structure: website/date/session_id
        folder_name = website_config.get('folder_name', website_config['key'])
        
        logger.info(f"[UPLOAD] Uploading to Azure Storage...")
        logger.info(f"[UPLOAD] Folder structure: {folder_name}/YYYY-MM-DD/session_id")
        
        # Upload the scraped data to your existing storage
        upload_results = storage.upload_scraped_data(
            individual_dir=results['processing']['individual_dir'],
            blob_prefix=folder_name
        )
        
        # Ensure we always return a valid structure
        if not upload_results or not isinstance(upload_results, dict):
            return {
                'session_prefix': 'upload_error',
                'individual_files': {'successful_uploads': [], 'failed_uploads': []},
                'total_successful': 0,
                'total_failed': 1,
                'total_size_mb': 0,
                'status': 'error',
                'error': 'Invalid upload result'
            }
        
        # Log results (removed emoji to prevent Unicode issues)
        logger.info(f"[UPLOAD SUMMARY] Upload Summary:")
        logger.info(f"[UPLOAD SUMMARY]   Session: {upload_results.get('session_prefix', 'unknown')}")
        logger.info(f"[UPLOAD SUMMARY]   Individual files: {len(upload_results.get('individual_files', {}).get('successful_uploads', []))}")
        logger.info(f"[UPLOAD SUMMARY]   Failed uploads: {upload_results.get('total_failed', 0)}")
        logger.info(f"[UPLOAD SUMMARY]   Total size: {upload_results.get('total_size_mb', 0):.2f} MB")
        logger.info(f"[UPLOAD SUMMARY]   Status: {upload_results.get('status', 'completed')}")
        
        return upload_results
        
    except Exception as e:
        logger.error(f"[ERROR] Upload failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            'session_prefix': 'exception_error',
            'individual_files': {'successful_uploads': [], 'failed_uploads': []},
            'total_successful': 0,
            'total_failed': 1,
            'total_size_mb': 0,
            'status': 'exception',
            'error': str(e)
        }

# Cell 5: CBUAE Data Flattening - Using existing storage
def flatten_cbuae_data():
    """Apply CBUAE-specific data flattening using your existing storage"""
    
    # Get website configuration from environment
    website_config = get_website_config()
    
    if 'cbuae' not in website_config['name'].lower():
        logger.warning("[WARNING] Data flattening only available for CBUAE")
        return None
    
    try:
        # Initialize CBUAE processor and use existing storage
        processor = create_processor('specialized', 'cbuae')
        storage = get_storage_account()
        
        logger.info("[FLATTENING] Starting CBUAE data flattening...")
        logger.info(f"[FLATTENING] Using storage: {STORAGE_CONFIG['account_name']}")
        
        if not storage.azure_available:
            logger.warning("[WARNING] Azure Storage not available for flattening")
            return None
        
        # List recent blobs to find the latest processed data
        blobs = storage.list_blobs(prefix="central_bank_uae/session_")
        
        if not blobs:
            logger.error("[ERROR] No processed data found in storage")
            logger.info("[INFO] Try running the pipeline with upload_to_cloud=True first")
            return None
        
        # Use the most recent session
        latest_blob = sorted(blobs, key=lambda x: x['last_modified'], reverse=True)[0]
        input_blob = latest_blob['name']
        
        logger.info(f"[FLATTENING] Using input blob: {input_blob}")
        
        # Check if the processor supports flattening
        if hasattr(processor, 'site_processor') and hasattr(processor.site_processor, 'flatten_cbuae_data_from_blob'):
            # Flatten the data - FIXED: use storage_account parameter
            output_blob = processor.site_processor.flatten_cbuae_data_from_blob(
                input_blob=input_blob,
                output_prefix="central_bank_uae/flattened",
                output_filename="cbuae_flattened_data.json",
                storage_account=storage  # Fixed parameter name
            )
            
            if output_blob and not output_blob.startswith('local://'):
                logger.info(f"[SUCCESS] Data flattening completed: {output_blob}")
                return output_blob
            elif output_blob:
                logger.warning(f"[WARNING] Data flattening completed locally: {output_blob}")
                return output_blob
            else:
                logger.error("[ERROR] Data flattening failed")
                return None
        else:
            logger.error("[ERROR] CBUAE processor does not support flattening")
            return None
            
    except Exception as e:
        logger.error(f"[ERROR] Flattening failed: {e}")
        import traceback
        traceback.print_exc()
        return None

# Cell 6: Main Execution
def main():
    """Main execution function with container support"""
    
    logger.info("[STARTUP] Web Scraping Pipeline Started")
    
    # Start health server for containers
    create_health_server()
    
    # Use configuration from config.py
    mode = PROCESSING_CONFIG['default_mode']
    default_website_key = PROCESSING_CONFIG['default_website']
    upload_to_cloud = PROCESSING_CONFIG['upload_to_cloud']
    flatten_data = PROCESSING_CONFIG['flatten_data']
    
    # Print comprehensive configuration summary
    print_config_summary(logger)
    
    try:
        # Step 1: Process the website
        results = process_website(mode, default_website_key)
        
        # Step 2: Upload to your existing Azure Storage (optional)
        if upload_to_cloud and 'processing' in results:
            upload_results = upload_to_azure(results, default_website_key)
            results['upload'] = upload_results
        
        # Step 3: Flatten data for CBUAE using existing storage (optional)
        website_config = get_website_config(default_website_key)
        if flatten_data and 'cbuae' in website_config['name'].lower() and upload_to_cloud and results.get('upload', {}).get('total_successful', 0) > 0:
            flattened_blob = flatten_cbuae_data()
            results['flattened'] = flattened_blob
        
        logger.info("[SUCCESS] Pipeline execution completed")
        return results
        
    except Exception as e:
        logger.error(f"[ERROR] Pipeline failed: {e}")
        raise

# Cell 7: Execute the pipeline
if __name__ == "__main__":
    try:
        results = main()
        logger.info("[COMPLETION] Application completed successfully")
    except Exception as e:
        logger.error(f"[FAILURE] Application failed: {e}")
        sys.exit(1)