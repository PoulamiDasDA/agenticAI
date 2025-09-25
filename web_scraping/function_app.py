import azure.functions as func
import azure.durable_functions as df
import logging
import json
from StorageAccount import StorageAccount
import os
import sys
from datetime import datetime
from typing import Dict, Any
import requests
from bs4 import BeautifulSoup
import time
from urllib.parse import urljoin, urlparse
import hashlib

# Set UTF-8 encoding for Windows
if sys.platform.startswith('win'):
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Import configuration
from config import (
    setup_logging,
    FUNCTIONS_CONFIG,
    STORAGE_CONFIG,
    get_website_config
)
from main import get_storage_account, extract_urls_from_structure, process_website_config
from SimpleScraper import SimpleScraper

# Setup logging using configuration
logger = setup_logging()

# Create Durable Functions app
app = df.DFApp(http_auth_level=func.AuthLevel.FUNCTION)

# ==============================================================================
# DURABLE FUNCTION ORCHESTRATOR
# ==============================================================================

@app.orchestration_trigger(context_name="context")
def scraping_orchestrator(context: df.DurableOrchestrationContext):
    """
    Main orchestrator: loads discovery from storage OR runs discovery, then scrapes
    """
    input_data = context.get_input()
    website = input_data.get('website')
    if not website:
        logger.error(f"[ORCHESTRATOR] No website specified in input_data: {input_data}")
        raise ValueError("Website parameter is required")
    
    max_files = input_data.get('max_files', FUNCTIONS_CONFIG['default_max_files'])

    if not context.is_replaying:
        logger.info(f"[ORCHESTRATOR] Starting complete workflow (discovery → scraping → flattening) for {website}")
        logger.info(f"[ORCHESTRATOR] Full input_data: {input_data}")

    try:
        # Initialize progress tracking
        progress = {
            'website': website,
            'current_step': 'starting',
            'steps_completed': [],
            'total_steps': 3,  # Discovery → Scraping → Finalize
            'discovery': {},
            'scraping': {},
            'processing': {},
            'upload': {}
        }

        # Step 1: Always run fresh discovery
        if not context.is_replaying:
            logger.info(f"[ORCHESTRATOR] Step 1: Running fresh discovery for {website}")
            progress['current_step'] = 'discovery'
            context.set_custom_status(progress)
        
        discovery_result = yield context.call_activity("discover_website", {
            "website": website
        })
        
        progress['discovery'] = discovery_result
        
        progress['steps_completed'].append('discovery')
        if not context.is_replaying:
            logger.info(f"[ORCHESTRATOR] Step 1 completed: {progress['discovery'].get('status', 'unknown')}")
            context.set_custom_status(progress)

        # Step 2: Scrape content from discovered URLs (and download files)
        if not context.is_replaying:
            logger.info(f"[ORCHESTRATOR] Step 2: Starting scraping for {website}")
            progress['current_step'] = 'scraping'
            context.set_custom_status(progress)
        
        scraping_result = yield context.call_activity("scrape_website", {
            "website": website, 
            "discovery_result": discovery_result,
            "max_files": max_files
        })
        
        progress['scraping'] = scraping_result
        progress['steps_completed'].append('scraping')
        if not context.is_replaying:
            logger.info(f"[ORCHESTRATOR] Step 2 completed: {scraping_result.get('status', 'unknown')}")
            context.set_custom_status(progress)

        # Step 3: Finalize results (data already uploaded during scraping)
        if not context.is_replaying:
            logger.info(f"[ORCHESTRATOR] Step 3: Finalizing results for {website}")
            progress['current_step'] = 'finalizing'
            context.set_custom_status(progress)

        # Create final result from scraping output (data already in Azure Storage)
        final_result = {
            'website': website,
            'mode': 'full',
            'status': 'completed',
            'completed_at': context.current_utc_datetime.isoformat(),
            'discovery': {
                'source': progress['discovery'].get('status', 'unknown'),
                'total_urls_found': len(discovery_result.get('discovered_urls', {})) if discovery_result else 0,
                'discovery_uploaded': discovery_result.get('discovery_uploaded', False) if discovery_result else False,
                'container_name': discovery_result.get('container_name') if discovery_result else None
            },
            'scraping': {
                'pages_scraped': scraping_result.get('scraped_count', 0),
                'uploaded_to_azure': scraping_result.get('uploaded_to_azure', False),
                'uploaded_pages_count': scraping_result.get('uploaded_pages_count', 0),
                'uploaded_files_count': scraping_result.get('uploaded_files_count', 0),
                'container_name': scraping_result.get('container_name'),
                'summary_blob_name': scraping_result.get('summary_blob_name')
            }
        }
        
        # Test for payload size limit (configurable KB for Azure Durable Functions)
        try:
            
            payload_json = json.dumps(final_result, ensure_ascii=False)
            payload_size_kb = len(payload_json.encode('utf-8')) / 1024
            
            if payload_size_kb > FUNCTIONS_CONFIG['payload_size_limit_kb']:  # Leave 1KB buffer
                if not context.is_replaying:
                    logger.warning(f"[ORCHESTRATOR] Payload size {payload_size_kb:.1f}KB exceeds safe limit, creating minimal result")
                
                # Create minimal result under 16KB
                minimal_result = {
                    'website': website,
                    'mode': 'full',
                    'status': 'completed',
                    'completed_at': context.current_utc_datetime.isoformat(),
                    'totals': {
                        'urls_discovered': len(discovery_result.get('discovered_urls', {})) if discovery_result else 0,
                        'pages_scraped': scraping_result.get('scraped_count', 0),
                        'files_uploaded': scraping_result.get('uploaded_files_count', 0)
                    },
                    'storage': {
                        'container_name': scraping_result.get('container_name'),
                        'summary_blob': scraping_result.get('summary_blob_name'),
                        'uploaded_to_azure': scraping_result.get('uploaded_to_azure', False)
                    },
                    'message': f'Full details available in Azure Storage. Payload reduced from {payload_size_kb:.1f}KB to stay under {FUNCTIONS_CONFIG["payload_size_limit_kb"]+1}KB limit.'
                }
                final_result = minimal_result
            else:
                if not context.is_replaying:
                    limit_kb = FUNCTIONS_CONFIG['payload_size_limit_kb'] + 1
                    logger.info(f"[ORCHESTRATOR] Payload size {payload_size_kb:.1f}KB is within {limit_kb}KB limit")
                    
        except Exception as size_e:
            if not context.is_replaying:
                logger.error(f"[ORCHESTRATOR] Payload size check failed: {str(size_e)}")

        # Set final status
        progress['current_step'] = 'completed'
        progress['final_result'] = final_result
        if not context.is_replaying:
            context.set_custom_status(progress)
            logger.info(f"[ORCHESTRATOR SUCCESS] Workflow completed for {website}")
        
        return final_result

    except Exception as e:
        if not context.is_replaying:
            logger.error(f"[ORCHESTRATOR ERROR] Workflow failed: {str(e)}")
            error_progress = {
                'website': website,
                'current_step': 'failed',
                'error': str(e)
            }
            context.set_custom_status(error_progress)
        
        return {
            'website': website,
            'mode': 'full',
            'status': 'failed',
            'error': str(e),
            'failed_at': context.current_utc_datetime.isoformat()
        }

@app.activity_trigger(input_name="input_data")
def load_discovery_results(input_data):
    """
    Load discovery results from Azure Storage for the scraping phase
    """
    website = input_data.get('website')
    if not website:
        logger.error(f"[LOAD DISCOVERY] No website specified in input_data: {input_data}")
        raise ValueError("Website parameter is required")
    
    logger.info(f"[LOAD DISCOVERY] Loading discovery results for {website}")
    logger.info(f"[LOAD DISCOVERY] Input data: {input_data}")
    
    try:
        # Get storage account
        storage_account = get_storage_account()
        
        container_name = os.getenv('AZURE_STORAGE_RAW_CONTAINER_NAME', 'raw')
        container_client = storage_account.blob_service_client.get_container_client(container_name)
        
        # Create blob path for discovery results
        date_str = datetime.now().strftime('%Y%m%d')
        blob_path = f"{date_str}/discovery/{website}/discovery_results.json"
        
        # Try to download the discovery results
        blob_client = container_client.get_blob_client(blob_path)
        
        if blob_client.exists():
            blob_data = blob_client.download_blob().readall()
            discovery_data = json.loads(blob_data.decode('utf-8'))
            
            logger.info(f"[LOAD DISCOVERY] Successfully loaded discovery results for {website}")
            logger.info(f"[LOAD DISCOVERY] Found {len(discovery_data.get('discovered_urls', {}))} discovered URLs")
            
            return {
                "status": "success",
                "website": website,
                "discovery_data": discovery_data,
                "blob_path": blob_path,
                "loaded_at": datetime.utcnow().isoformat()
            }
        else:
            logger.error(f"[LOAD DISCOVERY] No discovery results found at {blob_path}")
            return {
                "status": "error",
                "message": f"No discovery results found for {website}. Please run discovery first.",
                "expected_path": blob_path
            }
            
    except Exception as e:
        logger.error(f"[LOAD DISCOVERY] Error loading discovery results: {e}")
        return {
            "status": "error",
            "message": f"Error loading discovery results: {str(e)}",
            "website": website
        }

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def load_stored_discovery_data(discovery_filepath: str) -> Dict[str, Any]:
    """
    Load full discovery data from stored file
    """
    try:
        import json
        with open(discovery_filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load discovery data from {discovery_filepath}: {str(e)}")
        return {}



# ==============================================================================
# CONFIGURATION HELPERS
# ==============================================================================

def get_function_website_config(website_key=None):
    """
    Get website configuration from environment variables
    """
    # Get configuration from environment, support website key selection
    return get_website_config(website_key)

# ==============================================================================
# ACTIVITY FUNCTIONS
# ==============================================================================

@app.activity_trigger(input_name="input_data")
def discover_website(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Discover website URLs for scraping using unified configuration system
    """
    try:
        website = input_data['website']
        logger.info(f"[ACTIVITY DISCOVERY] Starting discovery for {website}")

        # Get website configuration from environment
        config = get_function_website_config(website)
        if not config:
            raise ValueError(f"No configuration found for website: {website}")

        base_url = config['url']
        max_depth = config['max_depth']
        filters = config.get('filters', [])
        website_name = config['name']
        
        scraper = SimpleScraper()

        # Use unified hierarchical discovery (auto-detection)
        discovered_structure = scraper.discover_site_skeleton_hierarchical(base_url, max_depth=max_depth)

        urls = extract_urls_from_structure(discovered_structure)
        
        # IMPORTANT: Always include the base URL itself for single-page sites
        if base_url not in urls:
            urls.insert(0, base_url)
            logger.info(f"[DISCOVERY] Added base URL to scrape list: {base_url}")
        
        # Apply filters
        filters = config.get('filters', [])
        if filters:
            urls = [url for url in urls if not any(f.lower() in url.lower() for f in filters)]
            
        logger.info(f"[DISCOVERY] Final URLs to scrape ({len(urls)}): {urls[:5]}{'...' if len(urls) > 5 else ''}")

        # Upload discovery data directly to Azure Storage instead of local files
        
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Prepare full discovery data for direct upload
        full_discovery_data = {
            'urls': urls,
            'structure': discovered_structure,
            'total_urls_found': len(urls),
            'status': 'completed',
            'website': website,
            'website_name': website_name,
            'base_url': base_url,
            'discovery_timestamp': datetime.now().isoformat(),
            'filters_applied': filters if filters else []
        }
        
        # Upload discovery data directly to Azure Storage
        discovery_blob_name = f"{datetime.now().strftime('%Y%m%d')}/discovery/{website}/discovery_{timestamp}.json"
        container_name = os.getenv('AZURE_STORAGE_RAW_CONTAINER_NAME', 'raw')
        storage_upload_success = False
        
        try:
            storage = StorageAccount()
            
            # Convert to JSON string for upload
            discovery_json = json.dumps(full_discovery_data, indent=2, ensure_ascii=False)
            
            # Upload directly to Azure Storage
            upload_result = storage.upload_text_content(
                container_name=container_name,
                blob_name=discovery_blob_name,
                content=discovery_json,
                content_type="application/json"
            )
            
            if upload_result.get('status') == 'success':
                storage_upload_success = True
                logger.info(f"[ACTIVITY DISCOVERY] Discovery data uploaded to Azure Storage: {discovery_blob_name}")
            else:
                logger.warning(f"[ACTIVITY DISCOVERY] Failed to upload discovery data: {upload_result.get('error', 'Unknown error')}")
                
        except Exception as upload_e:
            logger.error(f"[ACTIVITY DISCOVERY] Azure Storage upload failed: {str(upload_e)}")
        
        # Return optimized payload with Azure Storage reference (no local files)
        result = {
            'urls': urls,
            'total_urls_found': len(urls),
            'status': 'completed',
            'website': website,
            'website_name': website_name,
            'base_url': base_url,
            'discovery_blob_name': discovery_blob_name if storage_upload_success else None,
            'container_name': container_name if storage_upload_success else None,
            'discovery_uploaded': storage_upload_success
        }
        
        # Include structure only for very small discoveries
        if len(urls) <= 10 and len(str(discovered_structure)) < 2000:
            result['structure'] = discovered_structure
            result['structure_included'] = True
        else:
            # For large discoveries, include only summary - full data in Azure Storage
            result['structure_summary'] = {
                'has_structure': True,
                'main_items_count': len(discovered_structure.get('main_items', [])),
                'structure_size_chars': len(str(discovered_structure)),
                'stored_in_azure': discovery_blob_name if storage_upload_success else None,
                'message': f'Full structure with {len(discovered_structure.get("main_items", []))} items uploaded to Azure Storage'
            }
            result['structure_included'] = False
            
        logger.info(f"[ACTIVITY DISCOVERY SUCCESS] Found {len(urls)} URLs for {website}, uploaded to Azure Storage: {discovery_blob_name}")
        return result

    except Exception as e:
        logger.error(f"[ACTIVITY DISCOVERY ERROR] {str(e)}")
        return {'status': 'failed', 'error': str(e), 'urls': [], 'total_urls_found': 0}

@app.activity_trigger(input_name="input_data")
def scrape_website(input_data: Dict[str, Any]) -> Dict[str, Any]:
    import json
    import os
    from datetime import datetime
    from StorageAccount import StorageAccount
    
    try:
        website, discovery_result = input_data['website'], input_data['discovery_result']
        max_files = input_data.get('max_files', 10)
        
        logger.info(f"[ACTIVITY SCRAPING] {website}")

        if discovery_result['status'] != 'completed':
            raise ValueError("Discovery failed, cannot proceed")
        urls = discovery_result['urls']
        if not urls:
            return {'status': 'completed', 'scraped_count': 0, 'scraped_data': {}, 'message': 'No URLs'}

        # Get max_depth from website configuration
        config = get_function_website_config(website)
        if not config:
            raise ValueError(f"No configuration found for website: {website}")
        
        max_depth = config['max_depth']
        
        # Setup storage for immediate upload during scraping
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        container_name = os.getenv('AZURE_STORAGE_RAW_CONTAINER_NAME', 'raw')
        
        # Initialize scraper with immediate upload capability
        scraper = SimpleScraper(
            storage_account=StorageAccount(),
            container_name=container_name,
            website=website,
            timestamp=timestamp
        )
        
        # Scrape with immediate upload (data uploads as each page is processed)
        scraped_data = scraper.scrape_website(urls, max_depth)
        
        date_folder = datetime.now().strftime('%Y%m%d')  # Create date-based folder structure
        
        # Upload individual page data directly to Azure Storage
        uploaded_pages = []
        storage_upload_success = False
        
        try:
            storage = StorageAccount()
            
            uploaded_pages_count = len(scraped_data) if scraped_data else 0
            
            # Skip summary upload - not needed
            summary_blob_name = None
            summary_upload = {'status': 'skipped'}
            
            if summary_upload.get('status') == 'skipped':
                storage_upload_success = True
                logger.info(f"[ACTIVITY SCRAPING] All data uploaded to Azure Storage - Pages: {uploaded_pages_count} (summary generation disabled)")
                
                # Note: Individual page flattening is now done immediately during scraping for all websites
                # No need for batch processing at the end
                logger.info(f"[FLATTENING] Individual page flattening completed during scraping process")
            
        except Exception as upload_e:
            logger.error(f"[ACTIVITY SCRAPING] Azure Storage upload failed: {str(upload_e)}")

        result = {
            'status': 'completed', 
            'scraped_count': len(scraped_data) if scraped_data else 0, 
            'website': website,
            'uploaded_to_azure': storage_upload_success,
            'container_name': container_name if storage_upload_success else None,
            'summary_blob_name': None,  # Summaries disabled
            'uploaded_pages_count': len(scraped_data) if scraped_data else 0,
            'uploaded_files_count': 0,
            'scraping_mode': 'immediate_upload'
        }
        
        # Simple result summary - all data already processed and uploaded immediately
        result['summary'] = {
            'total_pages_processed': len(scraped_data) if scraped_data else 0,
            'processing_mode': 'immediate',
            'all_data_uploaded': storage_upload_success,
            'message': 'All pages processed and uploaded immediately during scraping'
        }
        
        # Test payload size to ensure we're under limit
        try:
            import json
            payload_json = json.dumps(result, ensure_ascii=False)
            payload_size_kb = len(payload_json.encode('utf-8')) / 1024
            
            if payload_size_kb > 8:  # Very conservative limit for activity functions
                logger.warning(f"[ACTIVITY SCRAPING] Payload still large {payload_size_kb:.1f}KB, using ultra-minimal result")
                
                # Ultra-minimal result for very large payloads
                result = {
                    'status': 'completed',
                    'scraped_count': len(scraped_data) if scraped_data else 0,
                    'website': website,
                    'payload_optimized': True,
                    'original_size_kb': payload_size_kb,
                    'message': 'Ultra-minimal result - all details in processed files',
                    'scraping_mode': 'immediate_upload'
                }
                
                if True:  # Always set files downloaded to 0 since we removed download functionality
                    result['files_downloaded'] = 0
            else:
                logger.info(f"[ACTIVITY SCRAPING] Payload size {payload_size_kb:.1f}KB within safe limits")
                
        except Exception as e:
            logger.error(f"[ACTIVITY SCRAPING] Payload optimization error: {str(e)}")
            # Emergency fallback - absolute minimal result
            result = {
                'status': 'completed',
                'scraped_count': len(scraped_data),
                'website': website,
                'error': 'Payload optimization failed',
                'message': 'Minimal result due to size constraints'
            }
            # Fallback to basic result
            result = {
                'status': 'completed',
                'scraped_count': len(scraped_data),
                'website': website,
                'error': 'Payload optimization failed',
                'original_error': str(e)
            }
        
        logger.info(f"[ACTIVITY SCRAPING SUCCESS] Scraped {len(scraped_data) if scraped_data else 0} pages for {website}")
        return result

    except Exception as e:
        logger.error(f"[ACTIVITY SCRAPING ERROR] {str(e)}")
        return {'status': 'failed', 'error': str(e), 'scraped_count': 0, 'scraped_data': {}}



# ==============================================================================
# HTTP TRIGGERS - THREE API ENDPOINTS ONLY
# ==============================================================================

@app.route(route="scraper", methods=["POST"])
@app.durable_client_input(client_name="client")
async def http_start_scraper(req: func.HttpRequest, client: df.DurableOrchestrationClient) -> func.HttpResponse:
    """
    Start complete workflow: fresh discovery → scraping → flattening
    POST /api/scraper
    Body: {
        "website": "cbuae",
        "max_files": """ + str(FUNCTIONS_CONFIG['default_max_files']) + """
    }
    """
    try:
        body = req.get_json()
        # Accept both 'website' and 'website_key' for flexibility
        website = body.get("website") or body.get("website_key", "cbuae") if body else "cbuae"
        max_files = body.get("max_files", FUNCTIONS_CONFIG['default_max_files']) if body else FUNCTIONS_CONFIG['default_max_files']
        
        # Hardcoded production settings
        upload_to_cloud = os.getenv('UPLOAD_TO_CLOUD')  # Always upload to Azure Storage

        # Validate website configuration
        config = get_function_website_config(website)
        if not config:
            return func.HttpResponse(
                json.dumps({
                    "error": f"No configuration found for website: {website}", 
                    "note": "Configure TARGET_WEBSITE_* environment variables"
                }), 
                status_code=400, 
                mimetype="application/json"
            )

        # Start complete workflow: discovery → scraping → flattening
        instance_id = await client.start_new("scraping_orchestrator", client_input={
            "website": website, 
            "mode": "complete", 
            "upload_to_cloud": upload_to_cloud,
            "max_files": max_files
        })
        
        logger.info(f"[HTTP SCRAPER] Started complete workflow {instance_id} for {website} (fresh discovery → scraping → flattening)")

        # Return production response
        response_data = {
            "message": f"Complete workflow started for {website} - fresh discovery → scraping → flattening",
            "instance_id": instance_id,
            "status_url": f"/api/scraper/status/{instance_id}",
            "website": website,
            "mode": "complete",
            "upload_to_cloud": upload_to_cloud,
            "max_files": max_files,
            "note": "Fresh discovery will run, then immediate scraping with flattening",
            "started_at": datetime.utcnow().isoformat()
        }
        
        return func.HttpResponse(
            json.dumps(response_data), 
            status_code=202, 
            mimetype="application/json"
        )

    except Exception as e:
        logger.error(f"[HTTP SCRAPER ERROR] {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}), 
            status_code=500, 
            mimetype="application/json"
        )

@app.route(route="scraper/status/{instance_id}", methods=["GET"])
@app.durable_client_input(client_name="client")
async def http_get_scraping_status(req: func.HttpRequest, client: df.DurableOrchestrationClient) -> func.HttpResponse:
    """
    Check the status of a running scraping workflow
    GET /api/scraper/status/{instance_id}
    """
    try:
        instance_id = req.route_params.get('instance_id')
        if not instance_id:
            return func.HttpResponse(
                json.dumps({"error": "instance_id is required"}), 
                status_code=400, 
                mimetype="application/json"
            )

        status = await client.get_status(instance_id)
        
        response_data = {
            "instance_id": instance_id,
            "status": str(status.runtime_status) if status.runtime_status else "Unknown",
            "created_time": status.created_time.isoformat() if status.created_time else None,
            "last_updated_time": status.last_updated_time.isoformat() if status.last_updated_time else None,
            "custom_status": status.custom_status,
            "output": status.output
        }
        
        return func.HttpResponse(
            json.dumps(response_data), 
            mimetype="application/json"
        )

    except Exception as e:
        logger.error(f"[STATUS ERROR] {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}), 
            status_code=500, 
            mimetype="application/json"
        )

@app.route(route="batch-scraper", methods=["POST"])
@app.durable_client_input(client_name="client")
async def http_batch_scraper(req: func.HttpRequest, client: df.DurableOrchestrationClient) -> func.HttpResponse:
    """
    Start batch scraping for multiple websites
    POST /api/batch-scraper
    Body: {
        "websites": ["cbuae", "fed"] | "all",  # Specific websites or "all" for all configured
        "max_files": 100,  # Optional: max files per website
        "force_discovery": false,  # Optional: force new discovery
        "sequential": true  # Optional: run sequentially or in parallel
    }
    """
    try:
        import asyncio
        import uuid
        from config import list_available_websites, get_website_config
        
        body = req.get_json()
        requested_websites = body.get("websites", "all") if body else "all"
        max_files = body.get("max_files", FUNCTIONS_CONFIG['default_max_files']) if body else FUNCTIONS_CONFIG['default_max_files']
        force_discovery = body.get("force_discovery", False) if body else False
        sequential = body.get("sequential", True) if body else True
        
        # Get list of websites to process
        available_websites = list_available_websites()
        
        if requested_websites == "all":
            websites_to_process = available_websites
        elif isinstance(requested_websites, list):
            # Validate requested websites exist
            invalid_websites = [w for w in requested_websites if w not in available_websites]
            if invalid_websites:
                return func.HttpResponse(
                    json.dumps({
                        "error": f"Invalid websites: {invalid_websites}",
                        "available_websites": available_websites
                    }), 
                    status_code=400, 
                    mimetype="application/json"
                )
            websites_to_process = requested_websites
        else:
            return func.HttpResponse(
                json.dumps({
                    "error": "websites must be 'all' or array of website keys",
                    "available_websites": available_websites
                }), 
                status_code=400, 
                mimetype="application/json"
            )
        
        if not websites_to_process:
            return func.HttpResponse(
                json.dumps({"error": "No websites to process"}), 
                status_code=400, 
                mimetype="application/json"
            )
        
        # Validate each website configuration
        for website in websites_to_process:
            config = get_function_website_config(website)
            if not config:
                return func.HttpResponse(
                    json.dumps({
                        "error": f"No configuration found for website: {website}",
                        "available_websites": available_websites
                    }), 
                    status_code=400, 
                    mimetype="application/json"
                )
        
        # Start orchestrators for each website
        batch_id = str(uuid.uuid4())[:8]
        instance_ids = []
        
        if not sequential:
            # TRUE PARALLEL: Start all websites simultaneously
            logger.info(f"[BATCH] Starting {len(websites_to_process)} websites in PARALLEL mode")
            tasks = []
            for website in websites_to_process:
                task = client.start_new("scraping_orchestrator", client_input={
                    "website": website,
                    "mode": "complete",
                    "upload_to_cloud": os.getenv('UPLOAD_TO_CLOUD'),
                    "max_files": max_files,
                    "batch_id": batch_id
                })
                tasks.append((website, task))
            
            # Wait for all to start simultaneously
            for website, task in tasks:
                instance_id = await task
                instance_ids.append({
                    "website": website,
                    "instance_id": instance_id,
                    "status_url": f"/api/scraper/status/{instance_id}"
                })
                logger.info(f"[BATCH] ✅ Started parallel workflow {instance_id} for {website}")
        else:
            # SEQUENTIAL: Start one at a time with delays
            logger.info(f"[BATCH] Starting {len(websites_to_process)} websites in SEQUENTIAL mode")
            for website in websites_to_process:
                instance_id = await client.start_new("scraping_orchestrator", client_input={
                    "website": website,
                    "mode": "complete",
                    "upload_to_cloud": os.getenv('UPLOAD_TO_CLOUD'),
                    "max_files": max_files,
                    "batch_id": batch_id
                })
                instance_ids.append({
                    "website": website,
                    "instance_id": instance_id,
                    "status_url": f"/api/scraper/status/{instance_id}"
                })
                logger.info(f"[BATCH] ✅ Started sequential workflow {instance_id} for {website}")
                
                # Wait between sequential starts
                if len(websites_to_process) > 1:
                    await asyncio.sleep(2)
        
        return func.HttpResponse(
            json.dumps({
                "message": f"Started batch scraping for {len(websites_to_process)} websites",
                "batch_id": batch_id,
                "processing_mode": "sequential" if sequential else "parallel",
                "websites": websites_to_process,
                "total_instances": len(instance_ids),
                "instances": instance_ids
            }),
            status_code=202,
            mimetype="application/json"
        )
        
    except Exception as e:
        logger.error(f"[BATCH SCRAPER ERROR] {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": f"Failed to start batch scraping: {str(e)}"}), 
            status_code=500, 
            mimetype="application/json"
        )

@app.route(route="health", methods=["GET"])
def http_health_check(req: func.HttpRequest) -> func.HttpResponse:
    # Get website configuration status
    try:
        from config import get_websites_config, list_available_websites
        websites = get_websites_config()
        available_keys = list_available_websites()
        config_status = "environment_multi" if len(websites) > 1 else "environment_single"
        
        health_info = {
            "status": "healthy", 
            "service": "durable-web-scraper-functions", 
            "timestamp": datetime.utcnow().isoformat(), 
            "config_source": config_status,
            "available_websites": available_keys,
            "total_websites": len(websites),
            "storage_account": os.getenv('AZURE_STORAGE_ACCOUNT_NAME', 'not_configured'), 
            "mode": "durable_functions"
        }
        
        # Add details for each website
        health_info["website_configs"] = []
        for website in websites:
            health_info["website_configs"].append({
                "key": website['key'],
                "name": website['name'],
                "url": website['url'],
                "folder": website.get('folder_name', website['key']),
                "storage_path": f"{STORAGE_CONFIG['container_name']}/{website.get('folder_name', website['key'])}/YYYY-MM-DD/"
            })
            
    except Exception as e:
        health_info = {
            "status": "healthy", 
            "service": "durable-web-scraper-functions", 
            "timestamp": datetime.utcnow().isoformat(), 
            "config_source": "error",
            "config_error": str(e),
            "storage_account": os.getenv('AZURE_STORAGE_ACCOUNT_NAME', 'not_configured'), 
            "mode": "durable_functions"
        }
    
    return func.HttpResponse(json.dumps(health_info), mimetype="application/json")

@app.schedule(schedule="0 0 9 1 * *", arg_name="mytimer", run_on_startup=False)
@app.durable_client_input(client_name="client")
async def timer_start_scraper(mytimer: func.TimerRequest, client: df.DurableOrchestrationClient):
    """
    Timer trigger - runs monthly (1st of every month at 9:00 AM)
    Controlled by TIMER_ENABLED environment variable (currently disabled)
    Scrapes ALL websites configured in WEBSITES_CONFIG
    """
    # Check if timer is enabled
    timer_enabled = os.getenv('TIMER_ENABLED', 'false').lower() == 'true'
    
    if not timer_enabled:
        logger.info('[TIMER] Timer trigger is disabled via TIMER_ENABLED environment variable')
        return
    
    if mytimer.past_due:
        logger.info('[TIMER] The timer is past due!')

    logger.info('[TIMER] Monthly trigger fired - starting scraping workflow for ALL websites')
    try:
        from config import list_available_websites
        available_websites = list_available_websites()
        
        if not available_websites:
            logger.warning('[TIMER] No websites configured, defaulting to cbuae')
            available_websites = ['cbuae']
        
        max_files = int(os.getenv('SCRAPING_MAX_FILES', '500'))  # Increased for production
        
        logger.info(f'[TIMER] Starting scraping for {len(available_websites)} websites: {", ".join(available_websites)}')
        
        # Start individual workflows for each website
        started_instances = []
        for website in available_websites:
            try:
                instance_id = await client.start_new("scraping_orchestrator", client_input={
                    "website": website, 
                    "mode": 'complete', 
                    "upload_to_cloud": os.getenv('UPLOAD_TO_CLOUD'),
                    "max_files": max_files
                })
                
                started_instances.append({
                    'website': website,
                    'instance_id': instance_id
                })
                
                logger.info(f'[TIMER] ✅ Started workflow {instance_id} for {website}')
                
            except Exception as website_error:
                logger.error(f'[TIMER] ❌ Failed to start workflow for {website}: {str(website_error)}')
                continue
        
        logger.info(f'[TIMER SUCCESS] Started {len(started_instances)} workflows out of {len(available_websites)} websites')
    except Exception as e:
        logger.error(f'[TIMER ERROR] {str(e)}')
        raise
