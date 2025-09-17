import re
import json
import logging
import traceback
from urllib.parse import urljoin
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path
from StorageAccount import StorageAccount

# Import from unified utilities
from unified_scraping_utils import HttpUtils, HtmlUtils, MetadataExtractor, CommonUtils

# Configure logger for this module
logger = logging.getLogger(__name__)

class CbuaeProcessor:
    """CBUAE-specific processing functions including data flattening"""
    
    def __init__(self, base_url="https://rulebook.centralbank.ae/"):
        self.base_url = base_url
        self.http_utils = HttpUtils()
        self.html_utils = HtmlUtils()
        self.metadata_extractor = MetadataExtractor()
        self.common_utils = CommonUtils()

    def build_title_hierarchy(self, titles: List[str], main_item_title: str) -> str:
        """
        Build hierarchical title by concatenating all titles starting from main_item_title.
        
        Args:
            titles: List of titles in the hierarchy
            main_item_title: The main item title to start the hierarchy
        
        Returns:
            String with titles separated by ' | '
        """
        # Filter out empty titles and create hierarchy
        filtered_titles = [title.strip() for title in [main_item_title] + titles if title and title.strip()]
        return " | ".join(filtered_titles)

    def extract_body_texts_recursive(
        self,
        item: Dict[str, Any], 
        main_title: str,
        main_item_title: str,
        main_item_url: str,
        parent_metadata: Dict[str, Any],
        title_hierarchy: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Recursively extract body_text entries and their metadata from nested structure.
        
        Args:
            item: Current item in the JSON structure
            main_title: The main title from root level
            main_item_title: The main item title
            main_item_url: The main item URL
            parent_metadata: Metadata from parent levels
            title_hierarchy: Current title hierarchy path
        
        Returns:
            List of flattened records containing body_text and metadata
        """
        if title_hierarchy is None:
            title_hierarchy = []
        
        flattened_records = []
        
        # Get current item's metadata
        current_metadata = parent_metadata.copy()
        
        # Update metadata with current item's fields
        if "title" in item:
            title_hierarchy.append(item["title"])
            current_metadata["current_title"] = item["title"]
        
        if "reference_link" in item:
            current_metadata["reference_link"] = item["reference_link"]
        
        if "circular_number" in item:
            current_metadata["circular_number"] = item["circular_number"]
        
        if "effective_date" in item:
            current_metadata["effective_date"] = item["effective_date"]
        
        if "sub_item_pdf_link" in item:
            current_metadata["sub_item_pdf_link"] = item["sub_item_pdf_link"]
        
        # Check for body_versions (contains body_text entries)
        if "body_versions" in item:
            for version in item["body_versions"]:
                if "body_text" in version:
                    # Create flattened record in standardized format
                    flattened_record = {
                        "text": version["body_text"],
                        "metadata": {
                            "authority": "CBUAE",
                            "heading": self.build_title_hierarchy(title_hierarchy, main_item_title),
                            "link": current_metadata.get("reference_link"),
                            "type": "web",
                            "date": current_metadata.get("effective_date"),
                            "is_latest": version.get("is_latest", False),
                            "additional": {
                                "main_title": main_title,
                                "main_item_title": main_item_title,
                                "current_title": current_metadata.get("current_title"),
                                "reference_link": main_item_url,
                                "circular_number": current_metadata.get("circular_number"),
                                "effective_date": current_metadata.get("effective_date"),
                                "sub_item_pdf_link": current_metadata.get("sub_item_pdf_link"),
                                "effective_from": version.get("effective_from"),
                                "effective_to": version.get("effective_to"),
                                "version": version.get("version")
                            }
                        }
                    }
                    
                    flattened_records.append(flattened_record)
        
        # Recursively process nested body items
        if "body" in item:
            for nested_item in item["body"]:
                nested_records = self.extract_body_texts_recursive(
                    nested_item,
                    main_title,
                    main_item_title,
                    main_item_url,
                    current_metadata,
                    title_hierarchy.copy()
                )
                flattened_records.extend(nested_records)
        
        return flattened_records

    def flatten_cbuae_data_from_blob(self, input_blob: str, output_prefix: str, output_filename: str, storage_account: StorageAccount) -> str:
        """
        Main function to flatten the CBUAE JSON data from blob storage.
        
        Args:
            input_blob: Blob path to input JSON file
            output_prefix: Output blob prefix
            output_filename: Output filename
            storage_account: StorageAccount instance to use
        
        Returns:
            Blob path to output file if successful, None otherwise
        """
        try:
            logger.info(f"[FLATTENING] Loading data from blob: {input_blob}")
            content = storage_account.download_blob_content(input_blob)
            data = json.loads(content)
            
            # Flatten the data
            logger.info("[FLATTENING] Flattening data...")
            flattened_records = self.flatten_cbuae_data_memory(data)
            
            logger.info(f"[FLATTENING] Generated {len(flattened_records)} flattened records")
            
            # Upload to blob
            output_content = json.dumps(flattened_records, ensure_ascii=False, indent=2)
            output_blob = storage_account.upload_to_latest(
                output_prefix,
                output_filename,
                output_content
            )
            
            logger.info(f"[FLATTENING] Uploaded flattened data to: {output_blob}")
            
            # Log summary statistics
            total_latest = sum(1 for record in flattened_records if record.get('metadata', {}).get('is_latest'))
            total_versions = len(flattened_records) - total_latest
            
            logger.info(f"[FLATTENING SUMMARY] Summary:")
            logger.info(f"[FLATTENING SUMMARY]   Total records: {len(flattened_records)}")
            logger.info(f"[FLATTENING SUMMARY]   Latest versions: {total_latest}")
            logger.info(f"[FLATTENING SUMMARY]   Historical versions: {total_versions}")
            
            return output_blob
            
        except Exception as e:
            logger.error(f"[ERROR] Error flattening data: {e}")
            import traceback
            traceback.print_exc()
            return None

    def flatten_individual_pages_from_session(self, date_folder: str, timestamp: str, website: str, storage_account: StorageAccount) -> List[str]:
        """
        Flatten individual page files from a scraping session.
        
        Args:
            date_folder: Date folder (e.g., "20241217")
            timestamp: Session timestamp (e.g., "20241217_143052") - for unique filenames
            website: Website name (e.g., "cbuae")
            storage_account: StorageAccount instance
            
        Returns:
            List of blob paths for flattened individual page files
        """
        try:
            flattened_blobs = []
            
            # List all page files in the session
            page_prefix = f"{date_folder}/pages/{website}/"
            logger.info(f"[INDIVIDUAL FLATTENING] Looking for pages with prefix: {page_prefix}")
            
            # Get list of page blobs (this would need to be implemented in StorageAccount)
            page_blobs = storage_account.list_blobs_with_prefix("scrapeddata", page_prefix)
            
            for page_blob in page_blobs:
                if page_blob.endswith('.json'):
                    try:
                        logger.info(f"[INDIVIDUAL FLATTENING] Processing: {page_blob}")
                        
                        # Download and parse the page content
                        content = storage_account.download_blob_content("scrapeddata", page_blob)
                        page_data = json.loads(content)
                        
                        # Extract page number from blob name (e.g., page_1.json -> 1)
                        page_filename = page_blob.split('/')[-1]  # Get just the filename
                        page_number = page_filename.replace('page_', '').replace('.json', '')
                        
                        # Flatten this individual page
                        flattened_records = self.flatten_single_page_data(page_data, page_number)
                        
                        if flattened_records:
                            # Upload flattened individual page
                            output_content = json.dumps(flattened_records, ensure_ascii=False, indent=2)
                            flattened_blob_name = f"{date_folder}/flattened/{website}/page_{page_number}_flattened_{timestamp}.json"
                            
                            upload_result = storage_account.upload_blob_content(
                                container_name="scrapeddata",
                                blob_name=flattened_blob_name,
                                content=output_content,
                                content_type="application/json"
                            )
                            
                            if upload_result.get('status') == 'success':
                                flattened_blobs.append(flattened_blob_name)
                                logger.info(f"[INDIVIDUAL FLATTENING] ✅ Created: {flattened_blob_name} ({len(flattened_records)} records)")
                            else:
                                logger.error(f"[INDIVIDUAL FLATTENING] ❌ Failed to upload: {flattened_blob_name}")
                                
                    except Exception as page_e:
                        logger.error(f"[INDIVIDUAL FLATTENING] Error processing {page_blob}: {str(page_e)}")
                        continue
            
            logger.info(f"[INDIVIDUAL FLATTENING] Completed. Created {len(flattened_blobs)} flattened page files")
            return flattened_blobs
            
        except Exception as e:
            logger.error(f"[INDIVIDUAL FLATTENING] Error: {str(e)}")
            import traceback
            traceback.print_exc()
            return []

    def flatten_single_page_data(self, page_data: Dict[str, Any], page_number: str) -> List[Dict[str, Any]]:
        """
        Flatten data from a single page.
        
        Args:
            page_data: Single page data from scraping
            page_number: Page number for tracking
            
        Returns:
            List of flattened records from this page
        """
        try:
            # Extract the actual content that needs flattening
            # The page_data structure is: {'url': ..., 'title': ..., 'content': {...}}
            content = page_data.get('content', {})
            
            if not content:
                logger.warning(f"[SINGLE PAGE FLATTENING] No content found in page {page_number}")
                return []
            
            # Use the existing flattening logic but for single page content
            flattened_records = self.flatten_cbuae_data_memory(content)
            
            # Add page tracking metadata to each record
            for record in flattened_records:
                if 'metadata' not in record:
                    record['metadata'] = {}
                record['metadata']['source_page_number'] = page_number
                record['metadata']['source_url'] = page_data.get('url', '')
                record['metadata']['page_title'] = page_data.get('title', '')
                record['metadata']['scraped_at'] = page_data.get('scraped_at', '')
            
            return flattened_records
            
        except Exception as e:
            logger.error(f"[SINGLE PAGE FLATTENING] Error processing page {page_number}: {str(e)}")
            return []

    def flatten_cbuae_data_memory(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Main function to flatten the CBUAE JSON data structure.
        
        Args:
            data: The loaded JSON data
            
        Returns:
            List of flattened records
        """
        flattened_records = []
        
        main_title = data.get("main_title", "")
        
        # Process each main item
        for main_item in data.get("main_items", []):
            main_item_title = main_item.get("main_item_title", "")
            main_item_url = main_item.get("main_item_url", "")
            
            # Process sub_item_section
            if "sub_item_section" in main_item:
                for sub_item in main_item["sub_item_section"]:
                    # Extract metadata from sub_item level
                    sub_item_metadata = {}
                    
                    if "title" in sub_item:
                        sub_item_metadata["title"] = sub_item["title"]
                    if "reference_link" in sub_item:
                        sub_item_metadata["reference_link"] = sub_item["reference_link"]
                    if "circular_number" in sub_item:
                        sub_item_metadata["circular_number"] = sub_item["circular_number"]
                    if "effective_date" in sub_item:
                        sub_item_metadata["effective_date"] = sub_item["effective_date"]
                    if "sub_item_pdf_link" in sub_item:
                        sub_item_metadata["sub_item_pdf_link"] = sub_item["sub_item_pdf_link"]
                    
                    # Process body items recursively
                    if "body" in sub_item:
                        for body_item in sub_item["body"]:
                            records = self.extract_body_texts_recursive(
                                body_item,
                                main_title,
                                main_item_title,
                                main_item_url,
                                sub_item_metadata,
                                [sub_item.get("title", "")]
                            )
                            flattened_records.extend(records)
        
        return flattened_records

    def extract_circular_number_and_date(self, soup):
        """Extract CBUAE-specific circular number, effective date, and issued date from soup"""
        circular_number = None
        effective_date = None
        issued_date = None
        
        # CBUAE-specific patterns for circular number
        patterns = [
            r'circular\s+no\.?\s*[:\-]?\s*([A-Z0-9\/\-]+)',
            r'regulation\s+no\.?\s*[:\-]?\s*([A-Z0-9\/\-]+)',
            r'notice\s+no\.?\s*[:\-]?\s*([A-Z0-9\/\-]+)',
        ]
        
        text_content = soup.get_text().lower()
        for pattern in patterns:
            match = re.search(pattern, text_content, re.IGNORECASE)
            if match:
                circular_number = match.group(1).strip()
                break
        
        # CBUAE-specific date patterns
        date_patterns = [
            r'effective\s+(?:from\s+)?date\s*[:\-]?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})',
            r'effective\s+(?:from\s+)?(\d{1,2}\s+\w+\s+\d{2,4})',
            r'issued\s+(?:on\s+)?date\s*[:\-]?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})',
            r'issued\s+(?:on\s+)?(\d{1,2}\s+\w+\s+\d{2,4})',
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text_content, re.IGNORECASE)
            if match and not effective_date:
                if 'effective' in pattern:
                    effective_date = match.group(1).strip()
                elif 'issued' in pattern:
                    issued_date = match.group(1).strip()
        
        return circular_number, effective_date, issued_date

    def extract_department_info(self, url, title):
        """Extract CBUAE-specific department and institution information"""
        institution = "Banking"
        department = "Capital Adequacy"  # Default
        department_link = url
        
        # CBUAE-specific department extraction
        if 'capital-adequacy' in url.lower():
            department = "Capital Adequacy"
        elif 'consumer-protection' in url.lower():
            department = "Consumer Protection"
        elif 'anti-money-laundering' in url.lower():
            department = "Anti-Money Laundering"
        elif 'fitness-propriety' in url.lower():
            department = "Fitness and Propriety"
        else:
            # Try to extract from title
            if 'capital' in title.lower():
                department = "Capital Adequacy"
            elif 'consumer' in title.lower():
                department = "Consumer Protection"
            elif 'aml' in title.lower() or 'money laundering' in title.lower():
                department = "Anti-Money Laundering"
        
        return institution, department, department_link

    def extract_version_and_dates(self, content, title):
        """Extract CBUAE-specific version and date information from content"""
        metadata = {
            'version': None,
            'effective_date': None,
            'effective_from': None,
            'effective_to': None,
            'last_updated': None,
            'revision_date': None,
            'document_number': None,
            'document_date': None,
            'circular_number': None
        }
        
        # Combine title and content for analysis
        text = f"{title} {content}".lower()
        
        # Version patterns
        version_patterns = [
            r'version\s*[:.]?\s*(\d+(?:\.\d+)*)',
            r'v\s*(\d+(?:\.\d+)*)',
            r'revision\s*[:.]?\s*(\d+(?:\.\d+)*)',
            r'amendment\s*[:.]?\s*(\d+)',
            r'update\s*[:.]?\s*(\d+(?:\.\d+)*)'
        ]
        
        for pattern in version_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                metadata['version'] = match.group(1)
                break
        
        # CBUAE-specific date patterns
        date_patterns = [
            (r'effective\s+from\s*[:.]?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})', 'effective_from'),
            (r'effective\s+from\s*[:.]?\s*(\d{1,2}\s+\w+\s+\d{2,4})', 'effective_from'),
            (r'effective\s+from\s*[:.]?\s*(\w+\s+\d{1,2},?\s+\d{2,4})', 'effective_from'),
            
            (r'effective\s+to\s*[:.]?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})', 'effective_to'),
            (r'effective\s+to\s*[:.]?\s*(\d{1,2}\s+\w+\s+\d{2,4})', 'effective_to'),
            (r'effective\s+to\s*[:.]?\s*(\w+\s+\d{1,2},?\s+\d{2,4})', 'effective_to'),
            
            (r'effective\s+date\s*[:.]?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})', 'effective_date'),
            (r'effective\s+date\s*[:.]?\s*(\d{1,2}\s+\w+\s+\d{2,4})', 'effective_date'),
            (r'effective\s+date\s*[:.]?\s*(\w+\s+\d{1,2},?\s+\d{2,4})', 'effective_date'),
            
            (r'last\s+updated\s*[:.]?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})', 'last_updated'),
            (r'last\s+updated\s*[:.]?\s*(\d{1,2}\s+\w+\s+\d{2,4})', 'last_updated'),
            (r'last\s+updated\s*[:.]?\s*(\w+\s+\d{1,2},?\s+\d{2,4})', 'last_updated'),
            
            (r'revision\s+date\s*[:.]?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})', 'revision_date'),
            (r'revised\s+on\s*[:.]?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})', 'revision_date'),
            
            (r'dated\s*[:.]?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})', 'document_date'),
        ]
        
        # Extract dates
        for pattern, field in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match and not metadata[field]:
                metadata[field] = match.group(1)
        
        # CBUAE-specific patterns
        uae_patterns = [
            (r'circular\s+no\.\s*(\w+\s*\d+[\/\-]\d+)', 'circular_number'),
            (r'regulation\s+no\.\s*(\d+[\/\-]\d+)', 'document_number'),
            (r'notice\s+no\.\s*(\d+[\/\-]\d+)', 'document_number'),
        ]
        
        for pattern, field in uae_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match and not metadata[field]:
                metadata[field] = match.group(1)
        
        return metadata

    def create_azure_ai_search_format(self, item, content_type, text_words, link_words, version_metadata):
        """Create CBUAE-specific Azure AI Search format"""
        # Extract department and institution info
        institution, department, department_link = self.extract_department_info(
            item.get('url', ''), 
            item.get('title', '')
        )
        
        # Build metadata display
        metadata_display = self.common_utils.format_metadata_display(version_metadata)
        
        # Create search document
        search_doc = {
            "id": f"cbuae_{hash(item.get('url', ''))%1000000}",
            "title": f"{item.get('title', 'Untitled')}{metadata_display}",
            "content": item.get('content', ''),
            "url": item.get('url', ''),
            "authority": "Central Bank of UAE",
            "institution": institution,
            "department": department,
            "department_link": department_link,
            "content_type": content_type,
            "text_words": text_words,
            "link_words": link_words,
            "total_words": text_words + link_words,
            "scraped_at": item.get('scraped_at', datetime.now().isoformat()),
            "metadata": version_metadata
        }
        
        return search_doc

    def process_cbuae_url(self, url):
        """Process a CBUAE URL to extract versioned content"""
        try:
            response = self.http_utils.get_response(url)
            if not response:
                return []
            
            soup = self.html_utils.get_soup(response)
            if not soup:
                return []
            
            # Extract content and metadata
            content = soup.get_text(strip=True)
            title = soup.title.get_text().strip() if soup.title else "Unknown"
            
            # Extract version and date metadata
            version_metadata = self.extract_version_and_dates(content, title)
            
            # Extract circular number and dates
            circular_number, effective_date, issued_date = self.extract_circular_number_and_date(soup)
            
            if circular_number:
                version_metadata['circular_number'] = circular_number
            if effective_date:
                version_metadata['effective_date'] = effective_date
            if issued_date:
                version_metadata['issued_date'] = issued_date
            
            # Create version record
            version = {
                'content': content,
                'effective_from': effective_date or issued_date,
                'is_latest': True,
                'version_number': version_metadata.get('version', '1.0'),
                'body_text': content,
                'metadata': version_metadata
            }
            
            return [version]
            
        except Exception as e:
            logger.error(f"[ERROR] Error processing CBUAE URL {url}: {e}")
            return []

    def add_circular_metadata_to_data(self, data, section_name):
        """Add CBUAE-specific circular metadata to data structure"""
        try:
            # Process main items
            for main_item in data.get("main_items", []):
                # Add metadata to main item
                if main_item.get("main_item_url"):
                    versions = self.process_cbuae_url(main_item["main_item_url"])
                    if versions and versions[0].get('metadata'):
                        main_item.update(versions[0]['metadata'])
                
                # Process sub-sections
                for sub_section in main_item.get("sub_item_section", []):
                    # Process body items
                    for body_item in sub_section.get("body", []):
                        if body_item.get("reference_link"):
                            versions = self.process_cbuae_url(body_item["reference_link"])
                            if versions:
                                body_item["body_versions"] = versions
            
            return data
            
        except Exception as e:
            logger.error(f"[ERROR] Error adding circular metadata: {e}")
            traceback.print_exc()
            return data

    def should_filter_content(self, document):
        """CBUAE-specific content filtering logic"""
        # CBUAE-specific filtering logic can be added here
        body_text = document.get('body_text', '')
        title = document.get('title', '')
        
        # Filter out very short CBUAE content
        if len(body_text.strip()) < 50:
            return True
        
        # Filter out CBUAE navigation pages
        navigation_keywords = ['home', 'index', 'menu', 'navigation', 'sitemap']
        if any(keyword in title.lower() for keyword in navigation_keywords):
            return True
        
        # CBUAE-specific content filters
        cbuae_filter_keywords = ['under construction', 'coming soon', 'maintenance']
        if any(keyword in body_text.lower() for keyword in cbuae_filter_keywords):
            return True
        
        return False

    def process_single_page(self, document, soup):
        """CBUAE-specific single page processing"""
        try:
            # Extract CBUAE-specific metadata
            circular_number, effective_date, issued_date = self.extract_circular_number_and_date(soup)
            
            # Add CBUAE-specific fields to document
            if circular_number:
                document['circular_number'] = circular_number
                document['document_metadata']['circular_number'] = circular_number
            
            if effective_date:
                document['effective_date'] = effective_date
                document['document_metadata']['effective_date'] = effective_date
            
            if issued_date:
                document['issued_date'] = issued_date
                document['document_metadata']['issued_date'] = issued_date
            
            # Extract department information
            institution, department, department_link = self.extract_department_info(
                document['url'], 
                document['title']
            )
            
            document['document_metadata']['institution'] = institution
            document['document_metadata']['department'] = department
            document['document_metadata']['department_link'] = department_link
            document['document_metadata']['authority'] = "Central Bank of UAE"
            
            # Add CBUAE processing note
            document['processing_notes'].append("CBUAE-specific processing applied")
            
            return document
            
        except Exception as e:
            logger.error(f"[ERROR] Error in CBUAE single page processing: {e}")
            return document