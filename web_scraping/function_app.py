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
import hashlib

# Set UTF-8 encoding for Windows
if sys.platform.startswith('win'):
    os.environ['PYTHONIOENCODING'] = 'utf-8'

from main import WEBSITES, get_storage_account, extract_urls_from_structure
from SimpleScraper import SimpleScraper

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
    Main orchestrator: loads discovery from storage OR runs discovery, then scrapes
    """
    input_data = context.get_input()
    website = input_data.get('website', 'cbuae')
    max_files = input_data.get('max_files', 100)
    force_discovery = input_data.get('force_discovery', False)
    
    upload_to_cloud = True  # Always upload to Azure Storage
    download_files = True   # Always download attachments

    if not context.is_replaying:
        logger.info(f"[ORCHESTRATOR] Starting workflow for {website} (discovery from storage, force_discovery: {force_discovery})")

    try:
        # Initialize progress tracking
        progress = {
            'website': website,
            'current_step': 'starting',
            'steps_completed': [],
            'total_steps': 3,  # Load/Discover → Scraping → Finalize
            'discovery': {},
            'scraping': {},
            'processing': {},
            'upload': {}
        }

        # Step 1: Try to load discovery from storage OR run new discovery
        discovery_result = None
        
        if not force_discovery:
            if not context.is_replaying:
                logger.info(f"[ORCHESTRATOR] Step 1a: Loading discovery from storage for {website}")
                progress['current_step'] = 'loading_discovery'
                context.set_custom_status(progress)
            
            # Try to load existing discovery results
            load_result = yield context.call_activity("load_discovery_results", {
                "website": website
            })
            
            if load_result.get('status') == 'success':
                discovery_result = load_result['discovery_data']
                progress['discovery'] = {
                    'status': 'loaded_from_storage',
                    'total_urls_found': len(discovery_result.get('discovered_urls', {})),
                    'loaded_from': load_result.get('blob_path'),
                    'loaded_at': load_result.get('loaded_at')
                }
                if not context.is_replaying:
                    logger.info(f"[ORCHESTRATOR] Discovery loaded from storage: {len(discovery_result.get('discovered_urls', {}))} URLs")
        
        # If no discovery found or forced, run new discovery
        if discovery_result is None or force_discovery:
            if not context.is_replaying:
                logger.info(f"[ORCHESTRATOR] Step 1b: Running new discovery for {website}")
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
            "download_files": download_files,
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
        
        # Add file download summary if enabled
        if download_files:
            final_result['file_downloads'] = scraping_result.get('file_downloads_summary', {})
        
        # Test for payload size limit (16KB for Azure Durable Functions)
        try:
            import json
            payload_json = json.dumps(final_result, ensure_ascii=False)
            payload_size_kb = len(payload_json.encode('utf-8')) / 1024
            
            if payload_size_kb > 15:  # Leave 1KB buffer
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
                        'files_uploaded': scraping_result.get('uploaded_files_count', 0),
                        'documents_downloaded': scraping_result.get('file_downloads_summary', {}).get('total_downloaded', 0) if download_files else 0
                    },
                    'storage': {
                        'container_name': scraping_result.get('container_name'),
                        'summary_blob': scraping_result.get('summary_blob_name'),
                        'uploaded_to_azure': scraping_result.get('uploaded_to_azure', False)
                    },
                    'message': f'Full details available in Azure Storage. Payload reduced from {payload_size_kb:.1f}KB to stay under 16KB limit.'
                }
                final_result = minimal_result
            else:
                if not context.is_replaying:
                    logger.info(f"[ORCHESTRATOR] Payload size {payload_size_kb:.1f}KB is within 16KB limit")
                    
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
    website = input_data.get('website', 'cbuae')
    
    logger.info(f"[LOAD DISCOVERY] Loading discovery results for {website}")
    
    try:
        # Get storage account
        storage_account = get_storage_account()
        
        container_name = "scrapeddata"
        container_client = storage_account.get_container_client(container_name)
        
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

        # Upload discovery data directly to Azure Storage instead of local files
        import json
        from datetime import datetime
        from StorageAccount import StorageAccount
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Prepare full discovery data for direct upload
        full_discovery_data = {
            'urls': urls,
            'structure': discovered_structure,
            'total_urls_found': len(urls),
            'site_type': site_type,
            'status': 'completed',
            'website': website,
            'discovery_timestamp': datetime.now().isoformat(),
            'filters_applied': filters if filters else []
        }
        
        # Upload discovery data directly to Azure Storage
        discovery_blob_name = f"{datetime.now().strftime('%Y%m%d')}/discovery/{website}/discovery_{timestamp}.json"
        container_name = "scrapeddata"  # Use the configured container name
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
            'site_type': site_type,
            'status': 'completed',
            'website': website,
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
        
        # Setup storage for immediate upload during scraping
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        container_name = "scrapeddata"
        
        # Initialize scraper with immediate upload capability
        scraper = SimpleScraper(
            storage_account=StorageAccount(),
            container_name=container_name,
            website=website,
            timestamp=timestamp,
            download_files=download_files
        )
        
        # Scrape with immediate upload (data uploads as each page is processed)
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
                                                    current_timestamp = int(time.time())
                                                    safe_text = ''.join(c for c in text[:30] if c.isalnum() or c in ' -_').strip().replace(' ', '_')
                                                    filename = f"{safe_text}_{current_timestamp}_{files_found_count+1}{ext}" if safe_text else f"document_{current_timestamp}_{files_found_count+1}{ext}"

                                                    # Store file info for later upload to Azure Storage
                                                    downloaded_files.append({
                                                        'filename': filename,
                                                        'content': file_response.content,
                                                        'size': len(file_response.content),
                                                        'url': full_url,
                                                        'text': text[:50],
                                                        'type': doc_type,
                                                        'source_page': url,
                                                        'content_type': 'application/pdf' if doc_type == 'PDF' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
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
        
        date_folder = datetime.now().strftime('%Y%m%d')  # Create date-based folder structure
        
        # Upload individual page data and files directly to Azure Storage
        uploaded_pages = []
        uploaded_files = []
        storage_upload_success = False
        
        try:
            storage = StorageAccount()
            
            uploaded_pages_count = len(scraped_data) if scraped_data else 0
            
            # Upload downloaded files directly to Azure Storage (if any)
            if download_files and downloaded_files:
                for file_info in downloaded_files:
                    file_blob_name = f"attachments/{date_folder}/{website}/{timestamp}/{file_info['filename']}"
                    
                    try:
                        file_upload_result = storage.upload_blob_content(
                            container_name=container_name,
                            blob_name=file_blob_name,
                            content=file_info['content'],  # Use content directly from memory
                            content_type=file_info.get('content_type', 'application/octet-stream')
                        )
                        
                        if file_upload_result.get('status') == 'success':
                            uploaded_files.append({
                                'blob_name': file_blob_name,
                                'filename': file_info['filename'],
                                'size': file_info['size'],
                                'blob_url': file_upload_result.get('blob_url'),
                                'source_url': file_info['url'][:100],
                                'type': file_info['type']
                            })
                            logger.info(f"[ACTIVITY SCRAPING] Uploaded file: {file_info['filename']} ({file_info['size']} bytes)")
                        else:
                            logger.error(f"[ACTIVITY SCRAPING] Failed to upload {file_info['filename']}: {file_upload_result.get('error')}")
                            
                    except Exception as file_e:
                        logger.error(f"[ACTIVITY SCRAPING] Failed to upload file {file_info['filename']}: {str(file_e)}")
            
            # Upload summary data
            summary_blob_name = f"{date_folder}/summaries/{website}/summary_{timestamp}.json"
            summary_data = {
                'website': website,
                'scraped_count': len(scraped_data) if scraped_data else 0,
                'scraping_timestamp': datetime.now().isoformat(),
                'scraping_mode': 'immediate_upload',  # Indicate that pages were uploaded immediately
                'download_files_enabled': download_files,
                'file_downloads': {
                    'total_downloaded': len(downloaded_files),
                    'total_failed': file_download_result.get('total_failed', 0),
                    'total_size_bytes': sum(f['size'] for f in downloaded_files),
                    'files_by_type': {
                        'PDF': len([f for f in downloaded_files if f['type'] == 'PDF']),
                        'Word': len([f for f in downloaded_files if f['type'] == 'Word'])
                    }
                } if download_files else None,
                'uploaded_pages': uploaded_pages_count,
                'uploaded_files': len(uploaded_files),
                'pages_note': 'Pages uploaded immediately during scraping - see pages/ folder',
                'files_blob_references': uploaded_files[:10],   # Sample references
                'container_name': container_name,
                'storage_structure': {
                    'pages_path': f'{date_folder}/pages/{website}/',
                    'attachments_path': f'{date_folder}/attachments/{website}/',
                    'discovery_path': f'{date_folder}/discovery/{website}/',
                    'summary_path': f'{date_folder}/summaries/{website}/',
                    'flattened_path': f'{date_folder}/flattened/{website}/'
                }
            }
            
            summary_json = json.dumps(summary_data, indent=2, ensure_ascii=False)
            summary_upload = storage.upload_text_content(
                container_name=container_name,
                blob_name=summary_blob_name,
                content=summary_json,
                content_type="application/json"
            )
            
            if summary_upload.get('status') == 'success':
                storage_upload_success = True
                logger.info(f"[ACTIVITY SCRAPING] All data uploaded to Azure Storage - Pages: {len(uploaded_pages)}, Files: {len(uploaded_files)}")
                
                # Note: Individual page flattening is now done immediately during scraping for CBUAE
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
            'summary_blob_name': summary_blob_name if storage_upload_success else None,
            'uploaded_pages_count': len(scraped_data) if scraped_data else 0,
            'uploaded_files_count': len(uploaded_files),
            'scraping_mode': 'immediate_upload'
        }
        
        # Add file download summary if enabled
        if download_files:
            result['file_downloads_summary'] = {
                'total_downloaded': file_download_result.get('total_downloaded', 0),
                'total_failed': file_download_result.get('total_failed', 0),
                'total_size_bytes': file_download_result.get('total_size_bytes', 0),
                'uploaded_to_azure': len(uploaded_files)
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
                
                if download_files:
                    result['files_downloaded'] = file_download_result.get('total_downloaded', 0)
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
        
        logger.info(f"[ACTIVITY SCRAPING SUCCESS] Scraped {len(scraped_data) if scraped_data else 0} pages, downloaded {file_download_result['total_downloaded']} files for {website}")
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
    Start full scraping workflow - automatically loads discovery results from storage and then scrapes
    POST /api/scraper
    Body: {
        "website": "cbuae",
        "max_files": 100,
        "force_discovery": false  # Optional: force new discovery if true
    }
    """
    try:
        body = req.get_json()
        website = body.get("website", "cbuae") if body else "cbuae"
        max_files = body.get("max_files", 100) if body else 100
        force_discovery = body.get("force_discovery", False) if body else False
        
        # Hardcoded production settings
        upload_to_cloud = True  # Always upload to Azure Storage
        download_files = True   # Always download attachments

        if website not in WEBSITES:
            return func.HttpResponse(
                json.dumps({
                    "error": f"Unknown website: {website}", 
                    "available_websites": list(WEBSITES.keys())
                }), 
                status_code=400, 
                mimetype="application/json"
            )

        # Start orchestrator with production parameters - it will load discovery from storage
        instance_id = await client.start_new("scraping_orchestrator", client_input={
            "website": website, 
            "mode": "full", 
            "upload_to_cloud": upload_to_cloud,
            "download_files": download_files,
            "max_files": max_files,
            "force_discovery": force_discovery
        })
        
        logger.info(f"[HTTP SCRAPER] Started workflow {instance_id} for {website} (loads discovery from storage)")

        # Return production response
        response_data = {
            "message": f"Scraping started for {website} - will load discovery from storage",
            "instance_id": instance_id,
            "status_url": f"/api/scraper/status/{instance_id}",
            "website": website,
            "mode": "production",
            "upload_to_cloud": True,
            "download_files": True,
            "max_files": max_files,
            "force_discovery": force_discovery,
            "note": "Discovery results automatically loaded from Azure Storage",
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

@app.route(route="health", methods=["GET"])
def http_health_check(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(json.dumps({"status": "healthy", "service": "durable-web-scraper-functions", "timestamp": datetime.utcnow().isoformat(), "available_websites": list(WEBSITES.keys()), "storage_account": os.getenv('AZURE_STORAGE_ACCOUNT_NAME', 'not_configured'), "mode": "durable_functions"}), mimetype="application/json")

@app.schedule(schedule="0 0 9 1 * *", arg_name="mytimer", run_on_startup=False)
@app.durable_client_input(client_name="client")
async def timer_start_scraper(mytimer: func.TimerRequest, client: df.DurableOrchestrationClient):
    """
    Monthly timer trigger - runs on the 1st day of each month at 9:00 AM UTC
    Controlled by TIMER_ENABLED environment variable
    Production mode: always uploads to cloud and downloads files
    """
    # Check if timer is enabled
    timer_enabled = os.getenv('TIMER_ENABLED', 'false').lower() == 'true'
    
    if not timer_enabled:
        logger.info('[TIMER] Timer trigger is disabled via TIMER_ENABLED environment variable')
        return
    
    if mytimer.past_due:
        logger.info('[TIMER] The timer is past due!')

    logger.info('[TIMER] Monthly trigger fired - starting production scraping workflow')
    try:
        website = os.getenv('SCRAPING_WEBSITE', 'cbuae')
        max_files = int(os.getenv('SCRAPING_MAX_FILES', '500'))  # Increased for production
        
        # Hardcoded production settings
        upload_to_cloud = True  # Always upload to Azure Storage
        download_files = True   # Always download attachments
        
        instance_id = await client.start_new("scraping_orchestrator", client_input={
            "website": website, 
            "mode": 'production', 
            "upload_to_cloud": upload_to_cloud,
            "download_files": download_files,
            "max_files": max_files
        })
        
        logger.info(f'[TIMER SUCCESS] Started monthly production workflow {instance_id} for {website}')
    except Exception as e:
        logger.error(f'[TIMER ERROR] {str(e)}')
        raise
