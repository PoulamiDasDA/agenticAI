import azure.functions as func
import azure.durable_functions as df
import logging
import json
import os
import sys
from datetime import datetime
from typing import Dict, Any
import requests
from bs4 import BeautifulSoup
import time
from urllib.parse import urljoin, urlparse
from collections import deque
import hashlib
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential

# Set UTF-8 encoding for Windows
if sys.platform.startswith('win'):
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Import your existing modules
from main import WEBSITES, get_storage_account, extract_urls_from_structure
from SimpleScraper import SimpleScraper
from WebScrapingProcessor import create_processor

# Configure logging with UTF-8 encoding
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Durable Functions app
app = df.DFApp(http_auth_level=func.AuthLevel.FUNCTION)

# ==============================================================================
# DURABLE FUNCTION ORCHESTRATOR
# ==============================================================================

@app.orchestration_trigger(context_name="context")
def scraping_orchestrator(context: df.DurableOrchestrationContext):
    """
    Enhanced orchestrator that performs full scraping workflow including file downloads
    """
    input_data = context.get_input()
    website = input_data.get('website', 'cbuae')
    upload_to_cloud = input_data.get('upload_to_cloud', True)
    download_files = input_data.get('download_files', False)
    max_files = input_data.get('max_files', 10)  # Reduced default

    if not context.is_replaying:
        logger.info(f"[ORCHESTRATOR] Starting full workflow for {website} (download_files: {download_files})")

    try:
        # Initialize progress tracking
        progress = {
            'website': website,
            'current_step': 'starting',
            'steps_completed': [],
            'total_steps': 4 if upload_to_cloud else 3,  # Removed separate file download step
            'discovery': {},
            'scraping': {},
            'processing': {},
            'upload': {}
        }

        # Step 1: Discover website URLs
        if not context.is_replaying:
            logger.info(f"[ORCHESTRATOR] Step 1: Starting discovery for {website}")
            progress['current_step'] = 'discovery'
            context.set_custom_status(progress)
        
        discovery_result = yield context.call_activity("discover_website", {
            "website": website
        })
        
        progress['discovery'] = discovery_result
        progress['steps_completed'].append('discovery')
        if not context.is_replaying:
            logger.info(f"[ORCHESTRATOR] Step 1 completed: {discovery_result.get('status', 'unknown')}")
            context.set_custom_status(progress)

        # Step 2: Scrape content from discovered URLs (and download files if enabled)
        if not context.is_replaying:
            logger.info(f"[ORCHESTRATOR] Step 2: Starting scraping for {website}")
            progress['current_step'] = 'scraping'
            context.set_custom_status(progress)
        
        scraping_result = yield context.call_activity("scrape_website", {
            "website": website, 
            "discovery_result": discovery_result,
            "download_files": download_files,
            "max_files": max_files
        })
        
        progress['scraping'] = scraping_result
        progress['steps_completed'].append('scraping')
        if not context.is_replaying:
            logger.info(f"[ORCHESTRATOR] Step 2 completed: {scraping_result.get('status', 'unknown')}")
            context.set_custom_status(progress)
        
        # Step 3: Process scraped data
        if not context.is_replaying:
            logger.info(f"[ORCHESTRATOR] Step 3: Starting processing for {website}")
            progress['current_step'] = 'processing'
            context.set_custom_status(progress)
        
        processing_result = yield context.call_activity("process_scraped_data", {
            "website": website, 
            "scraping_result": scraping_result
        })
        
        progress['processing'] = processing_result
        progress['steps_completed'].append('processing')
        if not context.is_replaying:
            logger.info(f"[ORCHESTRATOR] Step 3 completed: {processing_result.get('status', 'unknown')}")
            context.set_custom_status(progress)
        
        # Step 4: Upload scraped data to storage (if enabled)
        upload_result = {}
        if upload_to_cloud:
            if not context.is_replaying:
                logger.info(f"[ORCHESTRATOR] Step 4: Starting upload for {website}")
                progress['current_step'] = 'upload'
                context.set_custom_status(progress)
            
            upload_result = yield context.call_activity("upload_to_storage", {
                "website": website, 
                "processing_result": processing_result
            })
            
            progress['upload'] = upload_result
            progress['steps_completed'].append('upload')
            if not context.is_replaying:
                logger.info(f"[ORCHESTRATOR] Step 4 completed: {upload_result.get('status', 'unknown')}")
                context.set_custom_status(progress)

        # Step 5: Download and upload files (if enabled) - REMOVED, now integrated in scraping step

        # Prepare final result
        final_result = {
            'website': website,
            'mode': 'full',
            'upload_to_cloud': upload_to_cloud,
            'download_files': download_files,
            'discovery': discovery_result,
            'scraping': scraping_result,
            'processing': processing_result,
            'upload': upload_result,
            'status': 'completed',
            'completed_at': context.current_utc_datetime.isoformat(),
            'total_urls_discovered': discovery_result.get('total_urls_found', 0),
            'total_pages_scraped': scraping_result.get('scraped_count', 0),
            'total_files_processed': processing_result.get('processed_count', 0),
            'total_files_uploaded': upload_result.get('total_successful', 0) if upload_to_cloud else 0,
            'total_documents_downloaded': scraping_result.get('file_downloads', {}).get('total_downloaded', 0) if download_files else 0
        }

        # Set final status
        progress['current_step'] = 'completed'
        progress['final_result'] = final_result
        if not context.is_replaying:
            context.set_custom_status(progress)
            logger.info(f"[ORCHESTRATOR SUCCESS] Full workflow completed for {website}")
        
        return final_result

    except Exception as e:
        if not context.is_replaying:
            logger.error(f"[ORCHESTRATOR ERROR] Full workflow failed: {str(e)}")
            progress['current_step'] = 'failed'
            progress['error'] = str(e)
            context.set_custom_status(progress)
        
        return {
            'website': website,
            'mode': 'full',
            'status': 'failed',
            'error': str(e),
            'failed_at': context.current_utc_datetime.isoformat()
        }

# ==============================================================================
# ACTIVITY FUNCTIONS
# ==============================================================================

@app.activity_trigger(input_name="input_data")
def discover_website(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Discover website URLs for scraping
    """
    try:
        website = input_data['website']
        logger.info(f"[ACTIVITY DISCOVERY] Starting discovery for {website}")

        if website not in WEBSITES:
            raise ValueError(f"Unknown website: {website}")

        config = WEBSITES[website]
        base_url, site_type, max_depth = config['url'], config['type'], config['max_depth']
        scraper = SimpleScraper()

        if site_type == 'specialized':
            discovered_structure = scraper.discover_site_skeleton_hierarchical(base_url, max_depth=max_depth, site_type=site_type)
        else:
            discovered_urls = scraper.discover_site_skeleton(base_url, max_depth)
            discovered_structure = {
                'main_title': f"{config['name']} Navigation",
                'main_items': [
                    {
                        'main_item_title': info.get('title', 'Unknown'),
                        'main_item_url': url,
                        'sub_item_section': []
                    } for url, info in discovered_urls.items()
                ]
            }

        urls = extract_urls_from_structure(discovered_structure)
        filters = config.get('filters', [])
        if filters:
            urls = [url for url in urls if not any(f.lower() in url.lower() for f in filters)]

        result = {
            'urls': urls,
            'structure': discovered_structure,
            'total_urls_found': len(urls),
            'site_type': site_type,
            'status': 'completed',
            'website': website
        }
        logger.info(f"[ACTIVITY DISCOVERY SUCCESS] Found {len(urls)} URLs for {website}")
        return result

    except Exception as e:
        logger.error(f"[ACTIVITY DISCOVERY ERROR] {str(e)}")
        return {'status': 'failed', 'error': str(e), 'urls': [], 'total_urls_found': 0}

@app.activity_trigger(input_name="input_data")
def scrape_website(input_data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        website, discovery_result = input_data['website'], input_data['discovery_result']
        download_files = input_data.get('download_files', False)
        max_files = input_data.get('max_files', 10)
        
        logger.info(f"[ACTIVITY SCRAPING] {website} (download_files: {download_files})")

        if discovery_result['status'] != 'completed':
            raise ValueError("Discovery failed, cannot proceed")
        urls = discovery_result['urls']
        if not urls:
            return {'status': 'completed', 'scraped_count': 0, 'scraped_data': {}, 'message': 'No URLs'}

        # Get max_depth from website configuration
        if website not in WEBSITES:
            raise ValueError(f"Unknown website: {website}")
        
        max_depth = WEBSITES[website]['max_depth']
        scraper = SimpleScraper()
        
        # First, do the regular scraping
        scraped_data = scraper.scrape_website(urls, max_depth)
        
        # Initialize file download results
        file_download_result = {
            'total_downloaded': 0,
            'total_failed': 0,
            'downloaded_files': [],
            'failed_downloads': [],
            'total_size_bytes': 0
        }
        
        # If file downloads enabled, scan the scraped pages for attachments
        if download_files:
            logger.info(f"[ACTIVITY SCRAPING] Starting file downloads for {website}")
            
            try:
                # Setup Azure Storage for file downloads
                account_name = os.getenv('AZURE_STORAGE_ACCOUNT_NAME', 'explorationstorage12')
                container_name = os.getenv('AZURE_STORAGE_CONTAINER_NAME', 'data')
                
                if account_name and container_name:
                    credential = DefaultAzureCredential()
                    blob_service_client = BlobServiceClient(
                        account_url=f"https://{account_name}.blob.core.windows.net",
                        credential=credential
                    )
                    blob_container_client = blob_service_client.get_container_client(container_name)
                    
                    # Setup HTTP session for file downloads
                    file_session = requests.Session()
                    file_session.headers.update({
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    })
                    
                    downloaded_files = []
                    failed_downloads = []
                    uploaded_hashes = set()
                    files_found_count = 0
                    
                    # Scan URLs for attachments (limit to prevent timeouts)
                    urls_to_scan = urls[:max_files]
                    
                    for url in urls_to_scan:
                        if files_found_count >= max_files:
                            break
                            
                        try:
                            response = file_session.get(url, timeout=15)
                            if response.status_code == 200:
                                soup = BeautifulSoup(response.content, 'html.parser')
                                
                                # Find PDF and Word document links
                                for a in soup.find_all('a', href=True):
                                    if files_found_count >= max_files:
                                        break
                                        
                                    href = a['href']
                                    text = a.text.strip()
                                    full_url = urljoin(url, href) if not href.startswith('http') else href

                                    is_document = False
                                    doc_type = None

                                    if (href.endswith('.pdf') or 'pdf' in href.lower()):
                                        is_document = True
                                        doc_type = 'PDF'
                                    elif (href.endswith(('.doc', '.docx')) or 'doc' in href.lower()):
                                        is_document = True
                                        doc_type = 'Word'

                                    if is_document:
                                        try:
                                            # Download the file immediately
                                            file_response = file_session.get(full_url, timeout=15)
                                            
                                            if file_response.status_code == 200 and len(file_response.content) > 1000:
                                                # De-duplication by hash
                                                content_hash = hashlib.sha256(file_response.content).hexdigest()
                                                if content_hash not in uploaded_hashes:
                                                    uploaded_hashes.add(content_hash)
                                                    
                                                    # Generate filename
                                                    ext = ".pdf" if doc_type == 'PDF' else (".docx" if 'docx' in full_url else ".doc")
                                                    timestamp = int(time.time())
                                                    safe_text = ''.join(c for c in text[:30] if c.isalnum() or c in ' -_').strip().replace(' ', '_')
                                                    filename = f"{safe_text}_{timestamp}_{files_found_count+1}{ext}" if safe_text else f"document_{timestamp}_{files_found_count+1}{ext}"
                                                    blob_path = f"{website}/{doc_type.lower()}s/{filename}"

                                                    # Upload to blob storage
                                                    blob_container_client.upload_blob(
                                                        name=blob_path,
                                                        data=file_response.content,
                                                        overwrite=False
                                                    )

                                                    downloaded_files.append({
                                                        'filename': filename,
                                                        'blob_path': blob_path,
                                                        'size': len(file_response.content),
                                                        'url': full_url,
                                                        'text': text[:50],
                                                        'type': doc_type,
                                                        'source_page': url
                                                    })
                                                    
                                                    files_found_count += 1
                                                    time.sleep(0.5)  # Rate limiting
                                            else:
                                                failed_downloads.append({
                                                    'url': full_url,
                                                    'text': text[:50],
                                                    'type': doc_type,
                                                    'source_page': url,
                                                    'status': file_response.status_code
                                                })
                                        except Exception as file_e:
                                            failed_downloads.append({
                                                'url': full_url,
                                                'text': text[:50],
                                                'type': doc_type,
                                                'source_page': url,
                                                'error': str(file_e)
                                            })
                                            
                            time.sleep(0.3)  # Rate limiting between pages
                            
                        except Exception as page_e:
                            logger.warning(f"[SCRAPING] Error checking files on {url}: {str(page_e)}")
                            continue
                    
                    # Update file download results
                    file_download_result = {
                        'total_downloaded': len(downloaded_files),
                        'total_failed': len(failed_downloads),
                        'downloaded_files': downloaded_files,
                        'failed_downloads': failed_downloads[:5],  # Limit for response size
                        'total_size_bytes': sum(f['size'] for f in downloaded_files)
                    }
                    
                    logger.info(f"[ACTIVITY SCRAPING] Downloaded {len(downloaded_files)} files during scraping")
                    
            except Exception as download_e:
                logger.error(f"[ACTIVITY SCRAPING] File download error: {str(download_e)}")
                file_download_result['error'] = str(download_e)

        # Prepare result with both scraped content and file download info
        result = {
            'status': 'completed', 
            'scraped_count': len(scraped_data), 
            'scraped_data': scraped_data, 
            'website': website
        }
        
        # Add file download results if enabled
        if download_files:
            result['file_downloads'] = file_download_result
        
        logger.info(f"[ACTIVITY SCRAPING SUCCESS] Scraped {len(scraped_data)} pages, downloaded {file_download_result['total_downloaded']} files for {website}")
        return result

    except Exception as e:
        logger.error(f"[ACTIVITY SCRAPING ERROR] {str(e)}")
        return {'status': 'failed', 'error': str(e), 'scraped_count': 0, 'scraped_data': {}}

@app.activity_trigger(input_name="input_data")
def process_scraped_data(input_data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        website, scraping_result = input_data['website'], input_data['scraping_result']
        logger.info(f"[ACTIVITY PROCESSING] {website}")

        if scraping_result['status'] != 'completed':
            raise ValueError("Scraping failed")
        scraped_data = scraping_result['scraped_data']
        if not scraped_data:
            return {'status': 'completed', 'processed_count': 0, 'saved_files': [], 'message': 'No data'}

        processor = create_processor(website)
        saved_files = []
        individual_dir = f"/tmp/{website}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_individual"
        os.makedirs(individual_dir, exist_ok=True)

        for url, data in scraped_data.items():
            processed_data = processor.process_single_page(url, data)
            if processed_data:
                filename = f"{len(saved_files)+1:04d}_{url.split('/')[-1][:50]}.json"
                filepath = os.path.join(individual_dir, filename)
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(processed_data, f, ensure_ascii=False, indent=2)
                saved_files.append(filepath)

        summary_file = f"/tmp/{website}_summary.json"
        processor.save_processed_data(scraped_data, summary_file)

        return {'status': 'completed', 'processed_count': len(saved_files), 'saved_files': saved_files, 'individual_dir': individual_dir, 'summary_file': summary_file, 'website': website}

    except Exception as e:
        logger.error(f"[ACTIVITY PROCESSING ERROR] {str(e)}")
        return {'status': 'failed', 'error': str(e), 'processed_count': 0, 'saved_files': []}

@app.activity_trigger(input_name="input_data")
def upload_to_storage(input_data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        website, processing_result = input_data['website'], input_data['processing_result']
        logger.info(f"[ACTIVITY UPLOAD] {website}")

        if processing_result['status'] != 'completed':
            raise ValueError("Processing failed")

        storage = get_storage_account()
        upload_results = storage.upload_scraped_data(
            individual_dir=processing_result['individual_dir'],
            summary_file=processing_result.get('summary_file'),
            blob_prefix=f"durable_functions/{website}"
        )

        return {**upload_results, 'website': website}

    except Exception as e:
        logger.error(f"[ACTIVITY UPLOAD ERROR] {str(e)}")
        return {'status': 'failed', 'error': str(e), 'total_successful': 0, 'total_failed': 1}

# ==============================================================================
# HTTP TRIGGERS
# ==============================================================================

@app.route(route="scraper", methods=["POST"])
@app.durable_client_input(client_name="client")
async def http_start_full_scraper(req: func.HttpRequest, client: df.DurableOrchestrationClient) -> func.HttpResponse:
    """
    Start full scraping workflow with optional file downloads
    POST /api/scraper
    Body: {
        "website": "cbuae", 
        "upload_to_cloud": true,
        "download_files": false,
        "max_files": 10
    }
    """
    try:
        body = req.get_json()
        website = body.get("website", "cbuae") if body else "cbuae"
        upload_to_cloud = body.get("upload_to_cloud", True) if body else True
        download_files = body.get("download_files", False) if body else False
        max_files = body.get("max_files", 10) if body else 10  # Reduced default

        if website not in WEBSITES:
            return func.HttpResponse(
                json.dumps({
                    "error": f"Unknown website: {website}", 
                    "available_websites": list(WEBSITES.keys())
                }), 
                status_code=400, 
                mimetype="application/json"
            )

        # Start orchestrator with enhanced parameters
        instance_id = await client.start_new("scraping_orchestrator", client_input={
            "website": website, 
            "mode": "full", 
            "upload_to_cloud": upload_to_cloud,
            "download_files": download_files,
            "max_files": max_files
        })
        
        logger.info(f"[HTTP FULL SCRAPER] Started workflow {instance_id} for {website} (files: {download_files})")

        # Return enhanced response
        response_data = {
            "message": f"Full scraping started for {website}",
            "instance_id": instance_id,
            "status_url": f"/api/scraper/status/{instance_id}",
            "website": website,
            "mode": "full",
            "upload_to_cloud": upload_to_cloud,
            "download_files": download_files,
            "max_files": max_files,
            "started_at": datetime.utcnow().isoformat()
        }
        
        return func.HttpResponse(
            json.dumps(response_data), 
            status_code=202, 
            mimetype="application/json"
        )

    except Exception as e:
        logger.error(f"[HTTP FULL SCRAPER ERROR] {str(e)}")
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

@app.route(route="health", methods=["GET"])
def http_health_check(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(json.dumps({"status": "healthy", "service": "durable-web-scraper-functions", "timestamp": datetime.utcnow().isoformat(), "available_websites": list(WEBSITES.keys()), "storage_account": os.getenv('AZURE_STORAGE_ACCOUNT_NAME', 'not_configured'), "mode": "durable_functions"}), mimetype="application/json")

@app.schedule(schedule="0 0 9 * * *", arg_name="mytimer", run_on_startup=False)
@app.durable_client_input(client_name="client")
async def timer_start_scraper(mytimer: func.TimerRequest, client: df.DurableOrchestrationClient):
    if mytimer.past_due:
        logger.info('[TIMER] The timer is past due!')

    logger.info('[TIMER] Trigger fired - starting daily workflow')
    try:
        website = os.getenv('SCRAPING_WEBSITE', 'cbuae')
        upload_to_cloud = os.getenv('SCRAPING_UPLOAD_TO_CLOUD', 'true').lower() == 'true'
        instance_id = await client.start_new("scraping_orchestrator", client_input={"website": website, "mode": 'full', "upload_to_cloud": upload_to_cloud})
        logger.info(f'[TIMER SUCCESS] Started workflow {instance_id} for {website}')
    except Exception as e:
        logger.error(f'[TIMER ERROR] {str(e)}')
        raise
