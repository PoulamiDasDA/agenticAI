import os
import json
import re
import pandas as pd
import logging
from datetime import datetime
from urllib.parse import urlparse
from unified_scraping_utils import HttpUtils, HtmlUtils, CommonUtils
from StorageAccount import StorageAccount  # Import the class directly
from cbuae_processor import CbuaeProcessor

# Configure logger for this module
logger = logging.getLogger(__name__)

class WebScrapingProcessor:
    """Generic web scraping processor with modular design"""
    
    def __init__(self, filename_prefix="web_scraper", site_processor=None, storage_account=None):
        self.filename_prefix = filename_prefix
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.saved_files = []
        self.filtered_out_files = []
        self.processed_tables = {}
        self.site_processor = site_processor or CbuaeProcessor()
        self.storage_account = storage_account
        
        # Initialize utilities
        self.http_utils = HttpUtils()
        self.html_utils = HtmlUtils()
        self.common_utils = CommonUtils()

    def _get_storage_account(self):
        """Get storage account instance - create if needed"""
        if not self.storage_account:
            # Use default configuration for existing storage account
            self.storage_account = StorageAccount(
                storage_account_name=os.getenv("AZURE_STORAGE_ACCOUNT_NAME", "explorationstorage12"),
                container_name=os.getenv("AZURE_STORAGE_CONTAINER_NAME", "data"),
                credential_type="default"
            )
        return self.storage_account

    def extract_versioned_body_text(self, soup, effective_date):
        """Extract versioned body text using unified utilities"""
        versions = []
        
        # Extract main content
        body_content = soup.get_text(strip=True)
        if body_content:
            version = {
                'content': body_content,
                'effective_from': effective_date,
                'is_latest': True,
                'version_number': '1.0',
                'body_text': body_content
            }
            versions.append(version)
        
        return versions

    def process_body_list_recursive(self, body_list):
        """Process body list recursively and return count of processed items"""
        processed = 0
        for body_item in body_list:
            if body_item.get('reference_link'):
                processed += 1
            if body_item.get('body'):
                processed += self.process_body_list_recursive(body_item['body'])
        return processed

    def clean_text(self, text):
        """Clean text using unified utilities"""
        if not text:
            return ""
        return self.common_utils.clean_text(text)

    def extract_metadata(self, soup, url):
        """Extract metadata from HTML using unified utilities"""
        # Extract title - handle missing extract_title method
        title = "Unknown Title"
        if soup.title:
            title = soup.title.get_text().strip()
        elif hasattr(self.html_utils, 'extract_title'):
            title = self.html_utils.extract_title(soup)
        else:
            # Fallback: try to find h1 or first heading
            h1 = soup.find('h1')
            if h1:
                title = h1.get_text().strip()
            else:
                # Last resort: use part of URL
                title = url.split('/')[-1].replace('-', ' ').title()
        
        metadata = {
            'title': title,
            'url': url,
            'extraction_date': datetime.now().isoformat(),
            'domain': urlparse(url).netloc
        }
        
        # Extract additional metadata
        description = soup.find('meta', attrs={'name': 'description'})
        if description:
            metadata['description'] = description.get('content', '')
        
        keywords = soup.find('meta', attrs={'name': 'keywords'})
        if keywords:
            metadata['keywords'] = keywords.get('content', '')
        
        return metadata

    def extract_tables(self, soup):
        """Extract tables from HTML using unified utilities"""
        return self.html_utils.extract_tables(soup)

    def process_single_page(self, url, content):
        """Process a single page and return structured data"""
        try:
            # Parse HTML content - use get_soup instead of create_soup
            from bs4 import BeautifulSoup
            if isinstance(content, str):
                soup = BeautifulSoup(content, 'html.parser')
            else:
                soup = self.html_utils.get_soup(content) if hasattr(self.html_utils, 'get_soup') else BeautifulSoup(str(content), 'html.parser')
            
            if not soup:
                return None
            
            # Extract basic metadata
            metadata = self.extract_metadata(soup, url)
            
            # Extract main content
            main_content = self.html_utils.extract_main_content(soup) if hasattr(self.html_utils, 'extract_main_content') else soup.get_text()
            body_text = self.clean_text(main_content)
            
            # Extract tables
            tables = self.extract_tables(soup)
            
            # Create base document structure
            document = {
                'url': url,
                'title': metadata['title'],
                'body_text': body_text,
                'extraction_date': metadata['extraction_date'],
                'document_metadata': metadata,
                'tables': tables,
                'processing_notes': []
            }
            
            # Apply site-specific processing if available
            if self.site_processor and hasattr(self.site_processor, 'process_single_page'):
                document = self.site_processor.process_single_page(document, soup)
            
            return document
            
        except Exception as e:
            logger.error(f"[ERROR] Error processing {url}: {e}")
            return None

    def save_processed_data(self, scraped_data):
        """Save processed data as individual JSON files with summary"""
        # Create output directory
        individual_dir = f"scraped_data/{self.filename_prefix}_individual_{self.timestamp}"
        os.makedirs(individual_dir, exist_ok=True)
        
        # Initialize tracking
        saved_files = []
        filtered_out_files = []
        
        # Handle both dict and list formats
        if isinstance(scraped_data, list):
            # Convert list to dict using URL as key
            scraped_data_dict = {}
            for item in scraped_data:
                if isinstance(item, dict) and 'url' in item:
                    scraped_data_dict[item['url']] = item
                else:
                    logger.warning(f"[WARNING] Skipping invalid item: {item}")
            scraped_data = scraped_data_dict
        elif not isinstance(scraped_data, dict):
            logger.error(f"[ERROR] Invalid scraped_data type: {type(scraped_data)}")
            return [], None, individual_dir
        
        # Process each page
        for url, page_data in scraped_data.items():
            try:
                # Process the page content
                processed_doc = self.process_single_page(url, page_data.get('content', ''))
                
                if not processed_doc:
                    filtered_out_files.append({
                        'url': url,
                        'reason': 'Failed to process content'
                    })
                    continue
                
                # Apply content filters
                if self._should_filter_content(processed_doc):
                    filtered_out_files.append({
                        'url': url,
                        'reason': 'Content filtered out',
                        'title': processed_doc.get('title', 'Unknown')
                    })
                    continue
                
                # Save individual file
                safe_filename = self.common_utils.create_safe_filename(processed_doc['title'])
                filename = f"{safe_filename}.json"
                filepath = os.path.join(individual_dir, filename)
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(processed_doc, f, ensure_ascii=False, indent=2)
                
                # Track saved file
                file_info = {
                    'filename': filename,
                    'filepath': filepath,
                    'url': url,
                    'title': processed_doc['title'],
                    'file_size_kb': os.path.getsize(filepath) / 1024,
                    'word_count': len(processed_doc.get('body_text', '').split())
                }
                saved_files.append(file_info)
                
            except Exception as e:
                logger.error(f"[ERROR] Error saving {url}: {e}")
                filtered_out_files.append({
                    'url': url,
                    'reason': f'Save error: {str(e)}'
                })
                continue
        
        # Create summary data
        summary_data = {
            'metadata': {
                'site': self.filename_prefix,
                'processing_date': datetime.now().isoformat(),
                'session_id': self.timestamp,
                'individual_files_directory': individual_dir
            },
            'statistics': {
                'total_pages_processed': len(scraped_data),
                'successful_saves': len(saved_files),
                'filtered_out': len(filtered_out_files),
                'total_file_size_kb': sum(f['file_size_kb'] for f in saved_files),
                'total_word_count': sum(f['word_count'] for f in saved_files)
            },
            'saved_files': saved_files,
            'filtered_files': filtered_out_files
        }
        
        # Save summary file
        summary_filename = f"{self.filename_prefix}_summary_{self.timestamp}.json"
        summary_file = os.path.join("scraped_data", summary_filename)
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)
        
        # Store for instance access
        self.saved_files = saved_files
        self.filtered_out_files = filtered_out_files
        
        # Log summary (removed emoji to prevent Unicode issues)
        logger.info(f"[PROCESSING SUMMARY] Processing Summary:")
        logger.info(f"[PROCESSING SUMMARY]   Files saved: {len(saved_files)}/{len(scraped_data)}")
        logger.info(f"[PROCESSING SUMMARY]   Files filtered out: {len(filtered_out_files)}")
        logger.info(f"[PROCESSING SUMMARY]   Summary index: {summary_file}")
        logger.info(f"[PROCESSING SUMMARY]   Total size: {summary_data['statistics']['total_file_size_kb']:.1f} KB")
        
        return saved_files, summary_file, individual_dir

    def _should_filter_content(self, document):
        """Determine if content should be filtered out"""
        # Basic content filtering logic
        body_text = document.get('body_text', '')
        title = document.get('title', '')
        
        # Filter out very short content
        if len(body_text.strip()) < 100:
            return True
        
        # Filter out navigation or error pages
        if any(keyword in title.lower() for keyword in ['404', 'error', 'not found', 'navigation']):
            return True
        
        # Apply site-specific filtering if available
        if self.site_processor and hasattr(self.site_processor, 'should_filter_content'):
            return self.site_processor.should_filter_content(document)
        
        return False

    # Blob-based processing functions using Storage_Account
    def process_skeleton_to_full(self, input_blob: str, output_prefix: str, 
                                output_filename: str, section_name: str) -> str:
        """Process skeleton data to full data using blob storage"""
        storage = self._get_storage_account()
        
        return storage.process_with_blob_storage(
            self.process_skeleton_to_full_data, 
            input_blob, output_prefix, output_filename, 
            section_name
        )

    def fix_empty_body_versions(self, input_blob: str, output_prefix: str, 
                               output_filename: str) -> str:
        """Fix empty body versions using blob storage"""
        storage = self._get_storage_account()
        
        return storage.process_with_blob_storage(
            self.fix_empty_body_versions_data, 
            input_blob, output_prefix, output_filename
        )

    def add_circular_metadata(self, input_blob: str, output_prefix: str, 
                             output_filename: str, section_name: str) -> str:
        """Add circular metadata using blob storage"""
        storage = self._get_storage_account()
        
        return storage.process_with_blob_storage(
            self.site_processor.add_circular_metadata_to_data, 
            input_blob, output_prefix, output_filename, 
            section_name
        )

    def update_latest_flags(self, input_blob: str, output_prefix: str, 
                           output_filename: str) -> str:
        """Update latest flags using blob storage"""
        storage = self._get_storage_account()
        
        return storage.process_with_blob_storage(
            self.update_latest_flags_data, 
            input_blob, output_prefix, output_filename
        )

    def process_skeleton_to_full_data(self, skeleton_data, section_name):
        """Process skeleton data to full data in memory"""
        # Generic skeleton to full data processing
        return skeleton_data

    def fix_empty_body_versions_data(self, data):
        """Fix empty body versions in memory"""
        # Generic fix for empty body versions
        return data

    def update_latest_flags_data(self, data):
        """Update latest flags in memory"""
        # Generic update of latest flags
        return data


# Factory function to create processor with site-specific functionality
def create_processor(site_type="cbuae", filename_prefix=None):
    """Factory function to create processor with site-specific functionality"""
    if site_type.lower() == "cbuae" or site_type.lower() == "specialized":
        site_processor = CbuaeProcessor()
        filename_prefix = filename_prefix or "central_bank_uae"
    else:
        site_processor = None
        filename_prefix = filename_prefix or "web_scraper"
    
    return WebScrapingProcessor(filename_prefix, site_processor)


# Wrapper function for backward compatibility
def save_individual_json_files(data, filename_prefix="central_bank_uae"):
    """Backward compatibility wrapper"""
    processor = create_processor("cbuae", filename_prefix)
    return processor.save_processed_data(data)