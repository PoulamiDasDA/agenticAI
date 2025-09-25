import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime
import time
import json
import re
import os
import logging
import hashlib

logger = logging.getLogger(__name__)

# Import from unified utilities
from unified_scraping_utils import (
    HttpUtils, HtmlUtils, UrlUtils, MetadataExtractor, SkeletonDiscovery, CommonUtils
)

class SimpleScraper:
    def __init__(self, storage_account=None, container_name=None, website="", timestamp=""):
        self.scraped_data = []
        self.http_utils = HttpUtils()
        self.html_utils = HtmlUtils()
        self.url_utils = UrlUtils()
        self.metadata_extractor = MetadataExtractor()
        self.skeleton_discovery = SkeletonDiscovery()
        
        # For immediate upload functionality
        self.storage_account = storage_account
        self.container_name = container_name or os.getenv('AZURE_STORAGE_RAW_CONTAINER_NAME', 'raw')
        self.processed_container_name = os.getenv('AZURE_STORAGE_PROCESSED_CONTAINER_NAME', 'processed')
        self.website = website
        self.timestamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.date_folder = datetime.now().strftime('%Y%m%d')  # Keep YYYYMMDD format for container structure
        self.uploaded_pages = []
        self.upload_enabled = storage_account is not None
        
        # Unique page counter to prevent page number collisions
        self.page_counter = 0

    def get_response(self, url):
        """Get HTTP response using unified utility with browser-like headers"""
        return self.http_utils.get_response(url)

    def get_soup(self, response):
        """Create BeautifulSoup object using unified utility"""
        return self.html_utils.get_soup(response)

    def _select_soup(self, soup, selector, all=False):
        """Select elements using unified utility"""
        return self.html_utils.select_soup(soup, selector, all)

    def _extract_document_number(self, title):
        """Extract document number using unified utility"""
        return self.metadata_extractor.extract_circular_number(title)

    def _extract_effective_date(self, title, url):
        """Extract effective date using unified utility"""
        return self.metadata_extractor.extract_effective_date(title, url)

    def _extract_pdf_link(self, url):
        """Extract PDF link using unified utility"""
        return self.metadata_extractor.extract_pdf_link(url)

    def is_valid_discovery_link(self, url, base_url):
        """Check if link is valid for discovery using unified utility"""
        return self.skeleton_discovery.is_valid_discovery_link(url, base_url)

    def is_same_domain(self, url, base_url):
        """Check if URL is from the same domain using unified utility"""
        return self.url_utils.is_same_domain(url, base_url)

    def _upload_page_immediately(self, page_data, page_number):
        """Upload a single page immediately after scraping and trigger post-processing"""
        if not self.upload_enabled:
            return False
            
        try:
            # Generate UUID from URL hash for consistent naming
            url_hash = hashlib.sha256(page_data.get('url', '').encode('utf-8')).hexdigest()[:8]
            webpage_uuid = url_hash
            
            # Create blob name with new structure: YYYYMMDD/webpage/{website}/webpage_{uuid}.json
            page_blob_name = f"{self.date_folder}/webpage/{self.website}/webpage_{webpage_uuid}.json"
            
            # Add UUID and website metadata to page data
            page_data_with_uuid = page_data.copy()
            page_data_with_uuid['uuid'] = webpage_uuid
            page_data_with_uuid['website'] = self.website
            page_data_with_uuid['blob_path'] = page_blob_name
            
            page_json = json.dumps(page_data_with_uuid, indent=2, ensure_ascii=False)
            upload_result = self.storage_account.upload_text_content(
                container_name=self.container_name,
                blob_name=page_blob_name,
                content=page_json,
                content_type="application/json"
            )
            
            if upload_result.get('status') == 'success':
                self.uploaded_pages.append({
                    'blob_name': page_blob_name,
                    'url': page_data['url'][:100],
                    'content_size': len(str(page_data['content'])),
                    'uuid': webpage_uuid,
                    'page_number': page_number
                })
                logger.info(f"[UPLOAD] Uploaded webpage {webpage_uuid}: {page_data['url'][:50]}...")
                
                # Trigger website-specific post-processing
                self._post_process_page(page_data_with_uuid, page_number)
                
                return True
            else:
                logger.error(f"[UPLOAD] Failed to upload webpage {webpage_uuid}: {upload_result.get('error')}")
                return False
                
        except Exception as e:
            logger.error(f"[UPLOAD] Exception uploading webpage {webpage_uuid if 'webpage_uuid' in locals() else page_number}: {str(e)}")
            return False

    def _post_process_page(self, page_data, page_number):
        """Hook for post-processing after page upload - includes flattening for all websites"""
        try:
            logger.info(f"[POST-PROCESS] Starting post-processing for {self.website} page {page_number}, data type: {type(page_data)}")
            logger.info(f"[POST-PROCESS] Page data keys: {list(page_data.keys()) if isinstance(page_data, dict) else 'Not a dict'}")
            logger.info(f"[POST-PROCESS] URL: {page_data.get('url', 'No URL') if isinstance(page_data, dict) else 'No URL'}")
            
            # Always perform flattening for all websites (using CBUAE processor as generic processor)
            from cbuae_processor import CbuaeProcessor
            processor = CbuaeProcessor()
            
            logger.info(f"[POST-PROCESS] Calling CbuaeProcessor.process_page_immediately for {self.website}")
            processor.process_page_immediately(
                page_data=page_data,
                page_number=page_number,
                date_folder=self.date_folder,
                timestamp=self.timestamp,
                storage_account=self.storage_account,
                container_name=self.processed_container_name
            )
            
            # Website-specific additional processing can be added here
            if self.website == 'cbuae':
                logger.info(f"[POST-PROCESS] CBUAE-specific processing completed for page {page_number}")
            else:
                logger.info(f"[POST-PROCESS] Generic flattening completed for {self.website} page {page_number}")
                
        except Exception as e:
            logger.error(f"[POST-PROCESS] Error in post-processing for {self.website} page {page_number}: {str(e)}")
            import traceback
            traceback.print_exc()

    def _detect_site_type(self, base_url):
        """Auto-detect site type using unified utility"""
        return self.skeleton_discovery.detect_site_type(base_url)

    def discover_site_skeleton_hierarchical(self, base_url, max_depth=2, site_type="auto"):
        """
        Discover site structure and create hierarchical skeleton matching target format.
        
        Args:
            base_url: The base URL to start from
            max_depth: Maximum depth for recursion
            site_type: "specialized", "generic", or "auto" (auto-detects)
        
        Returns:
            Hierarchical structure with consistent fields for both site types.
        """
        logger.info(f"[DISCOVERY] Discovering hierarchical skeleton for: {base_url}")
        logger.info(f"[DISCOVERY] Maximum depth: {max_depth} levels")
        logger.info(f"[DISCOVERY] Site type: {site_type}")
        
        # Auto-detect site type
        if site_type == "auto":
            site_type = self._detect_site_type(base_url)
            logger.info(f"[DISCOVERY] Auto-detected site type: {site_type}")
        
        # Get main skeleton data based on site type
        if site_type == "specialized":
            logger.info("In discover specialized skeleton")
            return self._discover_specialized_skeleton(base_url, max_depth)
        else:
            return self._discover_generic_skeleton(base_url, max_depth)



    def _create_standard_item(self, title, link, base_url, site_type="generic"):
        """Create standardized item structure for both site types"""
        return {
            "main_item_title": title, 
            "main_item_url": link,
            "circular_number": self._extract_document_number(title) if site_type == "specialized" else None,
            "effective_date": self._extract_effective_date(title, link) if site_type == "specialized" else None,
            "reference_link": link
        }

    def _create_standard_sub_item(self, title, link, base_url, site_type="generic"):
        """Create standardized sub-item structure for both site types"""
        return {
            "title": title,
            "reference_link": link,
            "circular_number": self._extract_document_number(title) if site_type == "specialized" else None,
            "effective_date": self._extract_effective_date(title, link) if site_type == "specialized" else None,
            "sub_item_pdf_link": self._extract_pdf_link(link) if site_type == "specialized" else None
        }

    def _discover_specialized_skeleton(self, base_url, max_depth):
        """Discover specialized hierarchical structure for regulatory/legal sites"""
        try:
            logger.info('Inside _discover_specialized_skeleton')
            response = self.get_response(base_url)
            if not response:
                logger.error(f"[ERROR] Failed to get response from {base_url}")
                return {'total_discovered': 0, 'main_sections': [], 'hierarchical_structure': {}}
                
            soup = self.get_soup(response)
            if not soup:
                logger.error(f"[ERROR] Failed to parse HTML from {base_url}")
                return {'total_discovered': 0, 'main_sections': [], 'hierarchical_structure': {}}

            # For CBUAE website, look for the specific navigation structure
            main_sections = []
            
            # Try CBUAE-specific selectors first
            cbuae_nav_container = soup.select_one('.views-element-container.block-views-blockhome-page-book-links-block-1')
            if cbuae_nav_container:
                logger.info("[CBUAE] Found CBUAE navigation container")
                # Extract links from the views structure
                view_rows = cbuae_nav_container.select('.views-row')
                logger.info(f"[CBUAE] Found {len(view_rows)} navigation items")
                
                for row in view_rows:
                    link_elem = row.select_one('a[href]')
                    if link_elem:
                        title = link_elem.get_text(strip=True)
                        href = link_elem.get('href')
                        full_url = urljoin(base_url, href)
                        
                        logger.info(f"[CBUAE] CBUAE Section: {title} -> {full_url}")
                        
                        # Create standardized item
                        item = self._create_standard_item(title, full_url, base_url, "specialized")
                        main_sections.append(item)
            
            # Fallback: Try general navigation selectors
            if not main_sections:
                logger.info("[FALLBACK] CBUAE nav not found, trying general selectors...")
                
                # Try various navigation patterns
                nav_selectors = [
                    '.view-content .views-row a[href]',
                    '.main-menu a[href]',
                    '.primary-nav a[href]',
                    'nav a[href]',
                    '.menu a[href]',
                    '.navigation a[href]'
                ]
                
                for selector in nav_selectors:
                    nav_links = soup.select(selector)
                    if nav_links and len(nav_links) >= 3:  # Must have reasonable number of items
                        logger.info(f"[FALLBACK] Found navigation using selector: {selector} ({len(nav_links)} items)")
                        
                        for link_elem in nav_links[:10]:  # Limit to first 10
                            title = link_elem.get_text(strip=True)
                            if not title or len(title) < 2:
                                continue
                                
                            href = link_elem.get('href')
                            if not href:
                                continue
                                
                            full_url = urljoin(base_url, href)
                            
                            # Skip non-content links
                            if not self.is_valid_discovery_link(full_url, base_url):
                                continue
                            
                            logger.info(f"[FALLBACK] Fallback Section: {title} -> {full_url}")
                            
                            # Create standardized item
                            item = self._create_standard_item(title, full_url, base_url, "specialized")
                            main_sections.append(item)
                        
                        break  # Use first successful selector
            
            # Process each main section to build hierarchical structure
            skeleton_main = []
            for item in main_sections:
                logger.info(f"[PROCESSING] Processing main section: {item['main_item_title']}")
                
                # Get sub-sections for each main item
                sub_item_section = self._get_sub_skeleton_recursive_specialized(
                    item['main_item_url'], max_depth=max_depth-1, base_url=base_url
                )
                item['sub_item_section'] = sub_item_section
                skeleton_main.append(item)
            
            # Build final hierarchical structure
            hierarchical_skeleton = {
                "main_title": self._extract_main_title(soup),
                "main_items": skeleton_main
            }
            
            logger.info(f"[SUCCESS] Found {len(skeleton_main)} main sections")
            return hierarchical_skeleton
            
        except Exception as e:
            logger.error(f"[ERROR] Error in specialized discovery: {e}")
            import traceback
            traceback.print_exc()
            return self._discover_generic_skeleton(base_url, max_depth)

    def _discover_generic_skeleton(self, base_url, max_depth):
        """Discover generic website hierarchical structure with consistent field structure"""
        try:
            response = self.get_response(base_url)
            soup = self.get_soup(response)
            
            # Find navigation elements (common patterns)
            nav_selectors = [
                'nav ul',
                '.navigation ul',
                '.menu ul', 
                '.main-menu ul',
                '#navigation ul',
                '#menu ul',
                '.navbar ul',
                'header ul',
                '.sidebar ul'
            ]
            
            main_sections = None
            for selector in nav_selectors:
                elements = soup.select(f"{selector} > li")
                if elements and len(elements) > 2:  # Must have reasonable number of items
                    main_sections = elements
                    logger.info(f"[GENERIC] Found navigation using selector: {selector}")
                    break
            
            if not main_sections:
                # Fallback to finding all links in common containers
                main_sections = soup.select('a[href]')[:10]  # Limit to first 10 links
                logger.info(f"[GENERIC] Using fallback: first 10 links")
            
            skeleton_main = self._get_main_skeleton_generic(main_sections, base_url, max_depth)
            
            # Build final hierarchical structure
            hierarchical_skeleton = {
                "main_title": self._extract_main_title(soup),
                "main_items": skeleton_main
            }
            
            return hierarchical_skeleton
            
        except Exception as e:
            logger.error(f"[ERROR] Error in generic discovery: {e}")
            return {
                "main_title": "Website Navigation",
                "main_items": []
            }

    def _get_main_skeleton_specialized(self, main_sections, max_depth, base_url):
        """Extract main skeleton items for specialized sites with consistent structure"""
        output = []
        
        # Handle both BeautifulSoup elements and pre-processed list
        if isinstance(main_sections, list):
            # Already processed list of items
            return main_sections
        
        # Original BeautifulSoup processing
        if main_sections:
            for section in main_sections.find_all("li", recursive=False):
                a_tag = section.find("a", href=True)
                if not a_tag:
                    continue
                    
                title = a_tag.get_text(strip=True)
                link = urljoin(base_url, a_tag["href"])
                classes = section.get("class", [])
                
                logger.info(f"[SPECIALIZED] Specialized Parent: {title} {link}")
                
                # Use standardized item creation
                item = self._create_standard_item(title, link, base_url, "specialized")
                
                is_expandable = any(c in classes for c in ["menu-item--expanded", "menu-item--collapsed"])
                is_not_plain_menu = not (len(classes) == 1 and classes[0] == "menu-item")
                
                if (is_expandable or is_not_plain_menu) and max_depth > 0:
                    logger.info(f"[SPECIALIZED] Recursing into: {link}")
                    children = self._get_sub_skeleton_recursive_specialized(
                        link, visited=set(), max_depth=max_depth-1, base_url=base_url
                    )
                    if children:
                        item["sub_item_section"] = children
                else:
                    item["sub_item_section"] = []  # Ensure field exists
                
                output.append(item)
        
        return output

    def _get_main_skeleton_generic(self, main_sections, base_url, max_depth):
        """Extract main skeleton items for generic websites with consistent structure"""
        output = []
        
        for i, section in enumerate(main_sections[:10]):  # Limit to avoid too many items
            try:
                # Handle both <li><a> and direct <a> structures
                if section.name == 'li':
                    a_tag = section.find("a", href=True)
                else:
                    a_tag = section if section.name == 'a' and section.get('href') else None
                
                if not a_tag:
                    continue
                    
                title = a_tag.get_text(strip=True)
                if not title or len(title) < 2:  # Skip empty or very short titles
                    continue
                    
                link = urljoin(base_url, a_tag["href"])
                
                # Skip non-content links
                if not self.is_valid_discovery_link(link, base_url):
                    continue
                
                logger.info(f"[GENERIC] Generic Parent: {title} - {link}")
                
                # Use standardized item creation
                item = self._create_standard_item(title, link, base_url, "generic")
                
                # For generic sites, try to find sub-navigation if depth allows
                if max_depth > 0:
                    children = self._get_sub_skeleton_recursive_generic(
                        link, visited=set(), max_depth=max_depth-1, base_url=base_url
                    )
                    if children:
                        item["sub_item_section"] = children
                    else:
                        item["sub_item_section"] = []  # Ensure field exists
                else:
                    item["sub_item_section"] = []  # Ensure field exists
                
                output.append(item)
                
            except Exception as e:
                logger.warning(f"[WARNING] Error processing section {i}: {e}")
                continue
        
        return output

    def _get_sub_skeleton_recursive_specialized(self, link, visited=None, max_depth=1, base_url=None):
        """Recursively extract sub-skeleton for specialized sites with consistent structure"""
        if visited is None:
            visited = set()
        
        if link in visited or max_depth <= 0:
            return []
        
        visited.add(link)
        
        try:
            logger.info(f"[SUB-SKELETON] Getting sub-skeleton for: {link}")
            response = self.get_response(link)
            soup = self.get_soup(response)
            
            output = []
            
            # For CBUAE website, look for specific content structures
            # Try multiple selectors to find sub-items
            sub_item_selectors = [
                # CBUAE specific selectors
                '.view-content .views-row a[href]',
                '.view-content a[href]',
                '.content-main a[href]',
                '.field-content a[href]',
                # General content selectors
                'main a[href]',
                '.main-content a[href]',
                '#main-content a[href]',
                '.content a[href]',
                'article a[href]',
                # Navigation selectors
                '.menu a[href]',
                '.navigation a[href]',
                'nav a[href]'
            ]
            
            sub_links_found = False
            
            for selector in sub_item_selectors:
                sub_elements = soup.select(selector)
                if sub_elements and len(sub_elements) >= 2:  # Must have reasonable content
                    logger.info(f"[SUB-SKELETON] Found sub-items using selector: {selector} ({len(sub_elements)} items)")
                    
                    # Process the found links
                    for elem in sub_elements[:15]:  # Limit to prevent too many items
                        href = elem.get('href')
                        if not href:
                            continue
                        
                        title = elem.get_text(strip=True)
                        if not title or len(title) < 3:  # Skip very short titles
                            continue
                        
                        full_url = urljoin(base_url or link, href)
                        
                        # Skip non-content links
                        if not self.is_valid_discovery_link(full_url, base_url or link):
                            continue
                        
                        # Skip if it's the same as parent link
                        if full_url == link:
                            continue
                        
                        logger.info(f"[SUB-ITEM] Sub-item: {title} -> {full_url}")
                        
                        # Create standardized sub-item
                        item = self._create_standard_sub_item(title, full_url, base_url, "specialized")
                        
                        # Limited recursion for deeper levels
                        if max_depth > 0 and len(output) < 8:  # Limit depth and breadth
                            children = self._get_sub_skeleton_recursive_specialized(
                                full_url, visited, max_depth-1, base_url
                            )
                            if children:
                                item["body"] = children
                            else:
                                item["body"] = []  # Ensure field exists
                        else:
                            item["body"] = []  # Ensure field exists
                        
                        output.append(item)
                    
                    sub_links_found = True
                    break  # Use first successful selector
            
            if not sub_links_found:
                logger.warning(f"[WARNING] No sub-items found for: {link}")
            
            logger.info(f"[SUCCESS] Found {len(output)} sub-items for: {link}")
            return output
        
        except Exception as e:
            logger.error(f"[ERROR] Error processing specialized sub-skeleton {link}: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _get_sub_skeleton_recursive_generic(self, link, visited=None, max_depth=1, base_url=None):
        """Recursively extract sub-skeleton for generic websites with consistent structure"""
        if visited is None:
            visited = set()
            
        if link in visited or max_depth <= 0:
            return []
            
        visited.add(link)
        
        try:
            response = self.get_response(link)
            soup = self.get_soup(response)
            
            # Find sub-navigation in the page
            sub_nav_selectors = [
                '.submenu a',
                '.sub-navigation a', 
                '.secondary-nav a',
                '.sidebar a',
                'nav.secondary a',
                '.page-nav a'
            ]
            
            sub_links = []
            for selector in sub_nav_selectors:
                elements = soup.select(selector)
                if elements:
                    sub_links = elements[:5]  # Limit sub-items
                    break
            
            if not sub_links:
                # Fallback: find links in main content area
                content_area = soup.find('main') or soup.find('.content') or soup.find('article')
                if content_area:
                    sub_links = content_area.find_all('a', href=True)[:5]
            
            output = []
            
            for sub_link_elem in sub_links:
                if not sub_link_elem.get('href'):
                    continue
                
                title = sub_link_elem.get_text(strip=True)
                if not title or len(title) < 2:
                    continue
                
                sub_link = urljoin(base_url or link, sub_link_elem['href'])
                
                # Skip non-content links
                if not self.is_valid_discovery_link(sub_link, base_url or link):
                    continue
                
                # Use standardized sub-item creation
                item = self._create_standard_sub_item(title, sub_link, base_url, "generic")
                
                # Limited recursion for generic sites
                if max_depth > 0 and len(output) < 3:  # Limit depth and breadth
                    children = self._get_sub_skeleton_recursive_generic(
                        sub_link, visited, max_depth-1, base_url
                    )
                    if children:
                        item["body"] = children
                    else:
                        item["body"] = []  # Ensure field exists
                else:
                    item["body"] = []  # Ensure field exists
                
                output.append(item)
                
        except Exception as e:
            logger.error(f"[ERROR] Error processing generic sub-skeleton {link}: {e}")
            return []
        
        return output

    def _extract_main_title(self, soup):
        """Extract the main title from the page"""
        title_tag = soup.find('title')
        if title_tag:
            return title_tag.get_text(strip=True)
        
        h1_tag = soup.find('h1')
        if h1_tag:
            return h1_tag.get_text(strip=True)
        
        return "Website Navigation"

    def scrape_website(self, urls, max_depth):
        """Simple scraping with requests and BeautifulSoup - filtered URLs are depth 0"""
        visited = set()  # Global visited tracker for ALL URLs
        to_visit = [(url, 0) for url in urls]  # Filtered URLs start at depth 0
        
        logger.info(f"[SCRAPE] Starting simple scrape...")
        logger.info(f"[SCRAPE] Filtered URLs (depth 0): {len(urls)}")
        logger.info(f"[SCRAPE] Maximum depth: {max_depth} levels")
        
        while to_visit:
            url, depth = to_visit.pop(0)
            
            # Skip if already visited
            if url in visited:
                logger.info(f"[SKIP] Skipping already visited: {url}")
                continue
            
            # Skip if depth exceeds maximum
            if depth > max_depth:
                logger.info(f"[SKIP] Skipping depth {depth} (max: {max_depth}): {url}")
                continue
                
            try:
                logger.info(f"[SCRAPING] Scraping [Depth {depth}] ({len(visited)+1}): {url}")
                
                # Use unified HTTP utility for consistency
                response = self.get_response(url)
                if not response:
                    logger.error(f"[ERROR] Failed to get response for {url}, skipping...")
                    visited.add(url)  # Mark as visited to avoid retrying
                    continue
                    
                soup = self.get_soup(response)
                if not soup:
                    logger.error(f"[ERROR] Failed to parse HTML for {url}, skipping...")
                    visited.add(url)  # Mark as visited to avoid retrying
                    continue
                
                # Extract data
                data = {
                    'url': url,
                    'title': soup.title.get_text().strip() if soup.title else '',
                    'content': self.extract_content(soup),
                    'headings': self.extract_headings(soup),
                    'links': self.extract_links(soup, url),
                    'depth': depth,  # Depth where filtered URLs = 0
                    'scraped_at': datetime.now().isoformat()
                }
                
                # Upload immediately if storage is configured
                self.page_counter += 1  # Increment unique page counter
                page_number = self.page_counter
                upload_success = self._upload_page_immediately(data, page_number)
                
                # Only add to scraped_data if upload is disabled OR successful
                # This saves memory when immediate upload is enabled
                if not self.upload_enabled or upload_success:
                    self.scraped_data.append(data)
                elif self.upload_enabled and not upload_success:
                    logger.warning(f"[MEMORY] Page {page_number} upload failed, keeping in memory as fallback")
                    self.scraped_data.append(data)
                
                visited.add(url)  # Mark as visited IMMEDIATELY after scraping
                
                # Find new links to visit - only if not at max depth
                if depth < max_depth:
                    new_links = [link['href'] for link in data['links'] 
                               if self.is_same_domain(link['href'], url)]
                    
                    # Filter out already visited URLs and duplicates in to_visit queue
                    filtered_new_links = []
                    to_visit_urls = [item[0] for item in to_visit]  # Extract URLs from tuples
                    
                    for link in new_links:
                        # Apply filtering logic (like excluding insurance)
                        if 'insurance' in link.lower():
                            continue
                        
                        if link not in visited and link not in to_visit_urls:
                            filtered_new_links.append(link)
                            to_visit.append((link, depth + 1))  # Add with incremented depth
                    
                    if filtered_new_links:
                        logger.info(f"[LINKS] Found {len(new_links)} links, added {len(filtered_new_links)} new ones at depth {depth + 1}")
                        logger.info(f"[LINKS] New links: {filtered_new_links[:3]}{'...' if len(filtered_new_links) > 3 else ''}")
                else:
                    logger.info(f"[DEPTH] At max depth {max_depth}, not discovering new links from this page")
                
                # Count pages by depth for progress tracking
                depth_counts = {}
                for item in self.scraped_data:
                    d = item['depth']
                    depth_counts[d] = depth_counts.get(d, 0) + 1
                
                depth_summary = ", ".join([f"D{d}: {count}" for d, count in sorted(depth_counts.items())])
                logger.info(f"[SUCCESS] Scraped successfully | Total: {len(visited)} | Queue: {len(to_visit)} | By depth: [{depth_summary}]")
                
                # Random delay between 2-5 seconds to be more human-like
                import random
                delay = random.uniform(2, 5)
                time.sleep(delay)
                
            except Exception as e:
                logger.error(f"[ERROR] Error scraping {url}: {e}")
                visited.add(url)  # Mark as visited even if failed to avoid retry
                # Still add a delay even on error to avoid hammering the server
                time.sleep(1)
                continue

        logger.info(f"[COMPLETE] Scraping completed!")
        logger.info(f"[STATS] Total pages scraped: {len(self.scraped_data)}")
        logger.info(f"[STATS] Total URLs visited/attempted: {len(visited)}")
        
        # Final depth summary
        final_depth_counts = {}
        for item in self.scraped_data:
            d = item['depth']
            final_depth_counts[d] = final_depth_counts.get(d, 0) + 1
        
        logger.info(f"[STATS] Pages by depth (filtered URLs as depth 0):")
        for depth in sorted(final_depth_counts.keys()):
            logger.info(f"[STATS]   Depth {depth}: {final_depth_counts[depth]} pages")
        
        return self.scraped_data
    
    def extract_content(self, soup):
        """Extract main content from the page"""
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "header", "footer"]):
            script.decompose()
        
        # Try to find main content
        content_selectors = ['main', '.main-content', '#main-content', '.content', 'article']
        
        for selector in content_selectors:
            content_div = soup.select_one(selector)
            if content_div:
                return content_div.get_text().strip()
        
        # Fallback to body
        body = soup.find('body')
        if body:
            return body.get_text().strip()
        
        return ""
    
    def extract_headings(self, soup):
        """Extract all headings from the page"""
        headings = []
        for i in range(1, 7):
            for heading in soup.find_all(f'h{i}'):
                headings.append({
                    'level': i,
                    'text': heading.get_text().strip()
                })
        return headings
    
    def extract_links(self, soup, base_url):
        """Extract all links from the page"""
        links = []
        for link in soup.find_all('a', href=True):
            href = urljoin(base_url, link.get('href'))
            links.append({
                'text': link.get_text().strip(),
                'href': href
            })
        return links
    
    def is_same_domain(self, url, base_url):
        """Check if URL is from the same domain"""
        try:
            return urlparse(url).netloc == urlparse(base_url).netloc
        except Exception as e:
            return False