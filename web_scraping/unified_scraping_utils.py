import os
import json
import requests
import logging
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import re
from datetime import datetime, timedelta

# Configure logger for this module
logger = logging.getLogger(__name__)

class HttpUtils:
    """HTTP request utilities"""
    
    DEFAULT_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    @staticmethod
    def get_response(url, timeout=30, headers=None):
        """Get HTTP response with error handling and retry logic"""
        try:
            session_headers = HttpUtils.DEFAULT_HEADERS.copy()
            if headers:
                session_headers.update(headers)
            
            response = requests.get(url, timeout=timeout, headers=session_headers)
            response.raise_for_status()
            return response
        except Exception as e:
            logger.error(f"[HTTP ERROR] Error fetching {url}: {e}")
            return None

class HtmlUtils:
    """HTML parsing utilities"""
    
    CONTENT_SELECTORS = {
        'content': ['.main-content', '#main-content', '.content', 'main', 'article', '.post-content'],
        'navigation': ['nav', '.navigation', '.nav', '.menu'],
        'sidebar': ['.sidebar', '.aside', 'aside']
    }
    
    @staticmethod
    def get_soup(response):
        """Create BeautifulSoup object from response"""
        if not response:
            return None
        try:
            return BeautifulSoup(response.content, 'html.parser')
        except Exception as e:
            logger.error(f"[HTML ERROR] Error parsing HTML: {e}")
            return None
    
    @staticmethod
    def select_soup(soup, selector, all=False):
        """Enhanced CSS selector with fallbacks"""
        if not soup:
            return [] if all else None
        
        # Handle predefined selector groups
        if selector in HtmlUtils.CONTENT_SELECTORS:
            selectors = HtmlUtils.CONTENT_SELECTORS[selector]
            for sel in selectors:
                result = soup.select(sel) if all else soup.select_one(sel)
                if result:
                    return result
            return [] if all else None
        
        # Standard CSS selector
        return soup.select(selector) if all else soup.select_one(selector)

    @staticmethod
    def extract_title(soup):
        """Extract title from HTML"""
        if not soup:
            return "Unknown Title"
        
        # Try title tag first
        if soup.title:
            title = soup.title.get_text().strip()
            if title:
                return title
        
        # Try h1 tags
        h1 = soup.find('h1')
        if h1:
            title = h1.get_text().strip()
            if title:
                return title
        
        # Try meta title
        meta_title = soup.find('meta', attrs={'property': 'og:title'}) or soup.find('meta', attrs={'name': 'title'})
        if meta_title:
            title = meta_title.get('content', '').strip()
            if title:
                return title
        
        return "Unknown Title"
    
    @staticmethod
    def extract_main_content(soup):
        """Extract main content from HTML"""
        if not soup:
            return ""
        
        # Try predefined content selectors
        content_selectors = HtmlUtils.CONTENT_SELECTORS['content']
        for selector in content_selectors:
            element = soup.select_one(selector)
            if element:
                return element.get_text(strip=True)
        
        # Fallback: remove navigation and sidebar, get body text
        # Remove navigation elements
        for nav in soup.find_all(['nav', 'header', 'footer']):
            nav.decompose()
        
        # Remove sidebar elements
        for sidebar in soup.find_all(class_=['sidebar', 'aside']):
            sidebar.decompose()
        
        # Get body content
        body = soup.find('body')
        if body:
            return body.get_text(strip=True)
        
        # Last resort: get all text
        return soup.get_text(strip=True)
    
    @staticmethod
    def extract_tables(soup):
        """Extract tables from HTML"""
        if not soup:
            return []
        
        tables = []
        for table in soup.find_all('table'):
            table_data = {
                'headers': [],
                'rows': [],
                'summary': table.get('summary', ''),
                'caption': ''
            }
            
            # Extract caption
            caption = table.find('caption')
            if caption:
                table_data['caption'] = caption.get_text(strip=True)
            
            # Extract headers
            header_row = table.find('tr')
            if header_row:
                headers = header_row.find_all(['th', 'td'])
                table_data['headers'] = [header.get_text(strip=True) for header in headers]
            
            # Extract rows
            rows = table.find_all('tr')[1:]  # Skip header row
            for row in rows:
                cells = row.find_all(['td', 'th'])
                row_data = [cell.get_text(strip=True) for cell in cells]
                if row_data:  # Only add non-empty rows
                    table_data['rows'].append(row_data)
            
            if table_data['headers'] or table_data['rows']:
                tables.append(table_data)
        
        return tables

class UrlUtils:
    """URL manipulation utilities"""
    
    @staticmethod
    def is_valid_url(url):
        """Check if URL is valid"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False
    
    @staticmethod
    def is_same_domain(url1, url2):
        """Check if two URLs are from the same domain"""
        try:
            return urlparse(url1).netloc == urlparse(url2).netloc
        except:
            return False
    
    @staticmethod
    def extract_path_hierarchy(url):
        """Extract path hierarchy from URL for navigation structure"""
        try:
            parsed_url = urlparse(url)
            path_parts = [part for part in parsed_url.path.split('/') if part]
            
            # Build hierarchy path
            path = []
            for part in path_parts:
                # Clean and format part
                clean_part = part.replace('-', ' ').replace('_', ' ').title()
                path.append(clean_part)
            
            return path
        except:
            return []

class MetadataExtractor:
    """Metadata extraction utilities"""
    
    @staticmethod
    def extract_circular_number(text):
        """Extract circular number from text"""
        if not text:
            return None
        
        patterns = [
            r'Circular\s+No\.?\s*(\d+(?:/\d+)*)',
            r'Circular\s*(\d+(?:/\d+)*)',
            r'No\.?\s*(\d+(?:/\d+)*(?:/\d+)*)',
            r'(\d+/\d+/\d+)',
            r'(\d+/\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None
    
    @staticmethod
    def extract_effective_date(text, url=None):
        """Extract effective date from text or URL"""
        if not text:
            return None
        
        # Date patterns
        date_patterns = [
            r'effective\s+(?:from\s+)?(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
            r'dated?\s+(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})'
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                # Normalize date format
                date_str = date_str.replace('-', '/')
                return date_str
        
        return None
    
    @staticmethod
    def extract_pdf_link(url_or_links):
        """Extract PDF download link"""
        if isinstance(url_or_links, str):
            return url_or_links if url_or_links.endswith('.pdf') else None
        
        # Handle list of links
        for link in url_or_links:
            if isinstance(link, dict):
                href = link.get('href', '')
            else:
                href = str(link)
            
            if href.endswith('.pdf'):
                return href
        return None

class CommonUtils:
    """Common utility functions"""
    
    @staticmethod
    def create_clean_filename(url, page_number):
        """Create a clean filename from URL"""
        try:
            parsed_url = urlparse(url)
            clean_path = re.sub(r'[^\w\-_\.]', '_', parsed_url.path)
            clean_path = clean_path.strip('_').replace('__', '_')
            
            if not clean_path or clean_path == '_' or clean_path == '':
                clean_path = f"page_{page_number:03d}"
            else:
                clean_path = clean_path[:50].strip('_')
                if not clean_path:
                    clean_path = f"page_{page_number:03d}"
        except:
            clean_path = f"page_{page_number:03d}"
        
        return clean_path
    
    @staticmethod
    def analyze_content_type(content, links):
        """Analyze if content is primarily text, links, or mixed"""
        if not content or len(content.strip()) == 0:
            return "empty", 0, 0
        
        # Clean content - remove extra whitespace and newlines
        clean_content = ' '.join(content.split())
        content_words = len(clean_content.split())
        
        # Count link text
        link_text = ' '.join([link.get('text', '').strip() for link in links if link.get('text')])
        link_words = len(link_text.split()) if link_text else 0
        
        # Calculate ratios
        total_words = content_words
        if total_words == 0:
            return "empty", 0, 0
        
        text_words = total_words - link_words
        
        # Determine content type based on ratios and absolute counts
        if text_words < 10:  # Very little text content
            if link_words > text_words * 3:  # Links dominate significantly
                return "mostly_links", text_words, link_words
        
        if text_words >= 20:  # Substantial text content
            return "text_rich", text_words, link_words
        elif text_words >= 10:  # Moderate text content
            return "mixed", text_words, link_words
        else:
            return "mostly_links", text_words, link_words
    
    @staticmethod
    def save_json_file(data, filepath):
        """Save JSON file with error handling"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # Calculate file size
            file_size = os.path.getsize(filepath) / 1024  # KB
            return file_size
        except Exception as e:
            logger.error(f"[FILE ERROR] Error saving file {filepath}: {e}")
            return 0
    
    @staticmethod
    def clean_text(text):
        """Clean and normalize text content"""
        if not text:
            return ""
        
        # Remove extra whitespace and normalize
        cleaned = re.sub(r'\s+', ' ', text.strip())
        
        # Remove common HTML entities that might have been missed
        cleaned = cleaned.replace('&nbsp;', ' ')
        cleaned = cleaned.replace('&amp;', '&')
        cleaned = cleaned.replace('&lt;', '<')
        cleaned = cleaned.replace('&gt;', '>')
        cleaned = cleaned.replace('&quot;', '"')
        cleaned = cleaned.replace('&#39;', "'")
        
        # Remove excessive punctuation
        cleaned = re.sub(r'[.]{3,}', '...', cleaned)
        cleaned = re.sub(r'[-]{3,}', '---', cleaned)
        
        # Clean up spacing around punctuation
        cleaned = re.sub(r'\s+([,.!?;:])', r'\1', cleaned)
        cleaned = re.sub(r'([,.!?;:])\s+', r'\1 ', cleaned)
        
        return cleaned.strip()
    
    @staticmethod
    def create_safe_filename(title, max_length=100):
        """Create a safe filename from title"""
        if not title:
            return "untitled"
        
        # Clean the title
        safe_name = re.sub(r'[^\w\s\-_.]', '', title)
        safe_name = re.sub(r'\s+', '_', safe_name.strip())
        safe_name = safe_name.lower()
        
        # Limit length
        if len(safe_name) > max_length:
            safe_name = safe_name[:max_length].rstrip('_')
        
        # Ensure it's not empty
        if not safe_name:
            safe_name = "untitled"
        
        return safe_name

    @staticmethod
    def format_metadata_display(metadata):
        """Format metadata for display"""
        if not metadata:
            return ""
        
        display_parts = []
        
        # Add version if available
        if metadata.get('version'):
            display_parts.append(f"v{metadata['version']}")
        
        # Add effective date if available
        if metadata.get('effective_date'):
            display_parts.append(f"({metadata['effective_date']})")
        
        if display_parts:
            return f" [{' '.join(display_parts)}]"
        
        return ""

class SkeletonDiscovery:
    """Site skeleton discovery utilities"""
    
    @staticmethod
    def is_valid_discovery_link(url, base_url):
        """Check if link is valid for discovery"""
        try:
            if not UrlUtils.is_same_domain(url, base_url):
                return False
            
            # Skip file downloads and non-content
            skip_patterns = [
                '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip', '.rar',
                'javascript:', 'mailto:', 'tel:', '#', '?print=', '/print/'
            ]
            
            return not any(pattern in url.lower() for pattern in skip_patterns)
        except:
            return False
    
    @staticmethod
    def detect_site_type(base_url):
        """Auto-detect the type of website"""
        specialized_patterns = [
            "centralbank.ae",
            "rulebook.",
            "regulations.",
            "legal.",
            "compliance.",
            "policy.",
            "directive"
        ]
        
        for pattern in specialized_patterns:
            if pattern in base_url.lower():
                return "specialized"
        return "generic"

# Backward compatibility - keep existing function names
def get_response(url, timeout=30):
    """Backward compatibility wrapper"""
    return HttpUtils.get_response(url, timeout)

def get_soup(response):
    """Backward compatibility wrapper"""
    return HtmlUtils.get_soup(response)

def select_soup(soup, selector, all=False):
    """Backward compatibility wrapper"""
    return HtmlUtils.select_soup(soup, selector, all)

def extract_circular_number(text):
    """Backward compatibility wrapper"""
    return MetadataExtractor.extract_circular_number(text)

def extract_effective_date(text, url=None):
    """Backward compatibility wrapper"""
    return MetadataExtractor.extract_effective_date(text, url)

def extract_pdf_link(url_or_links):
    """Backward compatibility wrapper"""
    return MetadataExtractor.extract_pdf_link(url_or_links)

# Export constants for backward compatibility
DEFAULT_HEADERS = HttpUtils.DEFAULT_HEADERS
CONTENT_SELECTORS = HtmlUtils.CONTENT_SELECTORS