import os
import json
import glob
import traceback
from datetime import datetime
from dotenv import load_dotenv
from typing import List
import logging

# Azure Storage imports
try:
    from azure.storage.blob import BlobServiceClient, ContentSettings
    from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
    AZURE_IMPORTS_AVAILABLE = True
except ImportError:
    AZURE_IMPORTS_AVAILABLE = False

# Load environment variables
load_dotenv()

class StorageAccount:
    """Azure Storage with AAD authentication (works when key-based auth is disabled)"""
    
    def __init__(self, storage_account_name=None, container_name=None, credential_type=None):
        self.storage_account_name = storage_account_name or os.getenv('AZURE_STORAGE_ACCOUNT_NAME', 'defaultstorageaccount')
        self.container_name = container_name or os.getenv('AZURE_STORAGE_CONTAINER_NAME', 'default-container')
        self.azure_available = False
        
        # Auto-detect environment: Use AZURE_CREDENTIAL_TYPE to control authentication
        if credential_type:
            self.credential_type = credential_type
        elif os.getenv('AZURE_CREDENTIAL_TYPE'):
            self.credential_type = os.getenv('AZURE_CREDENTIAL_TYPE')
        else:
            self.credential_type = 'AAD'  # Default for local development
        
        # Set up logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        # Try different authentication methods
        self._initialize_client()
    
    def _initialize_client(self):
        """Try different AAD authentication methods"""
        account_url = f"https://{self.storage_account_name}.blob.core.windows.net"
        
        # Check if using Azurite for local development
        if self.storage_account_name == 'devstoreaccount1':
            try:
                # Azurite connection string
                azurite_connection_string = "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
                
                self.blob_service_client = BlobServiceClient.from_connection_string(azurite_connection_string)
                
                # Test the connection
                container_client = self.blob_service_client.get_container_client(self.container_name)
                try:
                    container_client.exists()
                except:
                    # Create container if it doesn't exist
                    container_client.create_container()
                
                self.azure_available = True
                self.logger.info("Azurite local storage connection successful")
                return
                
            except Exception as e:
                self.logger.warning(f"Azurite connection failed: {e}")
        
        if self.credential_type == 'AAD':
            # Method 1: Try DefaultAzureCredential (works for development and CI/CD)
            try:
                credential = DefaultAzureCredential()
                self.blob_service_client = BlobServiceClient(account_url=account_url, credential=credential)
                
                # Test the connection
                container_client = self.blob_service_client.get_container_client(self.container_name)
                container_client.exists()
                
                self.azure_available = True
                self.logger.info("DefaultAzureCredential authentication successful")
                return
                
            except Exception as e:
                self.logger.warning(f"DefaultAzureCredential auth failed: {e}")
        
        elif self.credential_type == 'managedidentity':
            # Method 4: Try ManagedIdentityCredential for Azure Functions
            try:
                # For system-assigned managed identity, don't pass client_id
                # For user-assigned managed identity, pass client_id
                client_id = os.getenv('AZURE_CLIENT_ID') or os.getenv('AzureWebJobsStorage__clientId')
                if client_id:
                    # User-assigned managed identity
                    credential = ManagedIdentityCredential(client_id=client_id)
                    self.logger.info(f"Using user-assigned managed identity: {client_id}")
                else:
                    # System-assigned managed identity (default)
                    credential = ManagedIdentityCredential()
                    self.logger.info("Using system-assigned managed identity")
                
                self.blob_service_client = BlobServiceClient(account_url=account_url, credential=credential)
                
                # Test connection
                container_client = self.blob_service_client.get_container_client(self.container_name)
                container_client.exists()
                
                self.azure_available = True
                self.logger.info("Managed Identity authentication successful")
                return
                
            except Exception as e:
                self.logger.warning(f"Managed Identity auth failed: {e}")
                # Fallback to DefaultAzureCredential
                try:
                    credential = DefaultAzureCredential()
                    self.blob_service_client = BlobServiceClient(account_url=account_url, credential=credential)
                    
                    # Test connection
                    container_client = self.blob_service_client.get_container_client(self.container_name)
                    container_client.exists()
                    
                    self.azure_available = True
                    self.logger.info("Fallback to Default Azure Credential successful")
                    return
                    
                except Exception as fallback_e:
                    self.logger.warning(f"Fallback credential auth also failed: {fallback_e}")
        
        # If all methods fail
        self.azure_available = False
        self.logger.warning("All Azure authentication methods failed - using local mode")
    
    def _ensure_container_exists(self, container_name):
        """Helper method to ensure container exists"""
        if not self.azure_available:
            return False
        
        try:
            container_client = self.blob_service_client.get_container_client(container_name)
            if not container_client.exists():
                container_client.create_container()
                self.logger.info(f"Created container: {container_name}")
            return True
        except Exception as e:
            self.logger.warning(f"Container creation/check failed for {container_name}: {e}")
            return True  # Container might already exist, which is fine
    
    
    def upload_file(self, local_file_path, blob_name=None, overwrite=True, metadata=None):
        """Upload file with AAD authentication"""
        if not os.path.exists(local_file_path):
            raise FileNotFoundError(f"Local file not found: {local_file_path}")
        
        if not self.azure_available:
            self.logger.info(f"📁 Azure unavailable, file kept locally: {local_file_path}")
            return f"file://{local_file_path}"
        
        try:
            if blob_name is None:
                blob_name = os.path.basename(local_file_path)
            
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name, 
                blob=blob_name
            )
            
            upload_metadata = {
                "uploaded_at": datetime.utcnow().isoformat(),
                "source": "central_bank_uae_scraper",
                "file_size": str(os.path.getsize(local_file_path))
            }
            if metadata:
                upload_metadata.update(metadata)
            
            with open(local_file_path, 'rb') as data:
                blob_client.upload_blob(data, overwrite=overwrite, metadata=upload_metadata)
            
            blob_url = blob_client.url
            self.logger.info(f"Uploaded to Azure: {blob_name}")
            return blob_url
            
        except Exception as e:
            self.logger.error(f"Azure upload failed for {local_file_path}: {e}")
            return f"file://{local_file_path}"
    
    def upload_scraped_data(self, individual_dir, blob_prefix="central_bank_uae"):
        """Upload scraped data with guaranteed return structure"""
        try:
            # Count files first
            json_files = glob.glob(os.path.join(individual_dir, "*.json"))
            total_size = sum(os.path.getsize(f) for f in json_files if os.path.exists(f)) / (1024 * 1024)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_prefix = f"{blob_prefix}/session_{timestamp}"
            
            successful_uploads = []
            failed_uploads = []
            
            self.logger.info(f"📤 Processing {len(json_files)} files")
            
            # Upload individual files
            for i, file_path in enumerate(json_files, 1):
                try:
                    blob_name = f"{session_prefix}/individual_pages/{os.path.basename(file_path)}"
                    blob_url = self.upload_file(file_path, blob_name)
                    
                    successful_uploads.append({
                        'local_path': file_path,
                        'blob_name': blob_name,
                        'blob_url': blob_url,
                        'file_size_bytes': os.path.getsize(file_path)
                    })
                    
                    status = "uploaded" if self.azure_available else "tracked locally"
                    self.logger.info(f"[UPLOAD PROGRESS] {i:3d}/{len(json_files)} - {os.path.basename(file_path)} ({status})")
                    
                except Exception as e:
                    failed_uploads.append({
                        'local_path': file_path,
                        'error': str(e)
                    })
                    self.logger.error(f"Failed to process {file_path}: {e}")
            
            # Return guaranteed structure
            return {
                'session_prefix': session_prefix,
                'individual_files': {
                    'successful_uploads': successful_uploads,
                    'failed_uploads': failed_uploads,
                    'total_files': len(json_files),
                    'total_size_mb': total_size
                },
                'total_successful': len(successful_uploads),
                'total_failed': len(failed_uploads),
                'total_size_mb': total_size,
                'azure_available': self.azure_available,
                'status': 'uploaded' if self.azure_available else 'local_tracking'
            }
            
        except Exception as e:
            self.logger.error(f"Upload operation failed: {e}")
            return {
                'session_prefix': f"failed/{blob_prefix}",
                'individual_files': {'successful_uploads': [], 'failed_uploads': [], 'total_files': 0, 'total_size_mb': 0},
                'total_successful': 0,
                'total_failed': 1,
                'total_size_mb': 0,
                'azure_available': False,
                'error': str(e),
                'status': 'failed'
            }
    
    def list_blobs(self, prefix="", max_results=None):
        """List blobs with AAD authentication"""
        if not self.azure_available:
            return []
        
        try:
            container_client = self.blob_service_client.get_container_client(self.container_name)
            blobs = container_client.list_blobs(name_starts_with=prefix)
            
            blob_list = []
            count = 0
            for blob in blobs:
                if max_results and count >= max_results:
                    break
                blob_list.append({
                    'name': blob.name,
                    'size': blob.size,
                    'last_modified': blob.last_modified,
                    'url': f"https://{self.storage_account_name}.blob.core.windows.net/{self.container_name}/{blob.name}"
                })
                count += 1
            
            return blob_list
        except Exception as e:
            self.logger.error(f"Error listing blobs: {e}")
            return []
    
    def list_blobs_with_prefix(self, container_name: str, prefix: str) -> List[str]:
        """
        List blob names with a specific prefix in a container.
        
        Args:
            container_name: Name of the container
            prefix: Blob name prefix to filter by
            
        Returns:
            List of blob names (strings)
        """
        if not self.azure_available:
            self.logger.warning("[LIST BLOBS] Azure not available, returning empty list")
            return []
        
        try:
            container_client = self.blob_service_client.get_container_client(container_name)
            blobs = container_client.list_blobs(name_starts_with=prefix)
            
            blob_names = [blob.name for blob in blobs]
            self.logger.info(f"[LIST BLOBS] Found {len(blob_names)} blobs with prefix: {prefix}")
            return blob_names
            
        except Exception as e:
            self.logger.error(f"[LIST BLOBS] Error listing blobs with prefix {prefix}: {e}")
            return []
    
    # Backward compatibility methods
    
    def upload_text_content(self, container_name, blob_name, content, content_type="text/plain", overwrite=True):
        """Upload text content to Azure Storage"""
        if not self.azure_available:
            return {'status': 'failed', 'error': 'Azure Storage not available', 'blob_url': f"local://{blob_name}"}
        
        try:
            # Ensure the configured container exists
            self._ensure_container_exists(container_name)
            
            blob_client = self.blob_service_client.get_blob_client(
                container=container_name,
                blob=blob_name
            )
            
            # Create proper ContentSettings object
            content_settings = ContentSettings(content_type=content_type)
            
            blob_client.upload_blob(
                content.encode('utf-8'), 
                overwrite=overwrite, 
                content_settings=content_settings
            )
            return {'status': 'success', 'blob_url': blob_client.url}
        except Exception as e:
            self.logger.error(f"Error uploading text content: {e}")
            return {'status': 'failed', 'error': str(e), 'blob_url': f"local://{blob_name}"}
    
    def upload_blob_content(self, container_name, blob_name, content, content_type="application/octet-stream", overwrite=True):
        """Upload binary content to Azure Storage"""
        if not self.azure_available:
            return {'status': 'failed', 'error': 'Azure Storage not available', 'blob_url': f"local://{blob_name}"}
        
        try:
            # Ensure the configured container exists
            self._ensure_container_exists(container_name)
            
            blob_client = self.blob_service_client.get_blob_client(
                container=container_name,
                blob=blob_name
            )
            
            # Create proper ContentSettings object
            content_settings = ContentSettings(content_type=content_type)
            
            blob_client.upload_blob(
                content, 
                overwrite=overwrite, 
                content_settings=content_settings
            )
            return {'status': 'success', 'blob_url': blob_client.url}
        except Exception as e:
            self.logger.error(f"Error uploading blob content: {e}")
            return {'status': 'failed', 'error': str(e), 'blob_url': f"local://{blob_name}"}


    
    def download_blob_content(self, blob_name):
        if not self.azure_available:
            return "{}"
        
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_name
            )
            content = blob_client.download_blob().readall()
            return content.decode('utf-8')
        except Exception as e:
            self.logger.error(f"Error downloading blob: {e}")
            return "{}"
    

    
    def upload_to_latest(self, blob_prefix, filename, content, overwrite=True):
        """
        Upload content to latest blob path with timestamp
        
        Args:
            blob_prefix: Prefix for the blob path
            filename: Name of the file
            content: Content to upload (string)
            overwrite: Whether to overwrite existing blob
            
        Returns:
            Blob name if successful, None if failed
        """
        try:
            if not self.azure_available:
                self.logger.warning("[UPLOAD TO LATEST] Azure not available, saving locally")
                # Save locally as fallback
                local_dir = f"scraped_data/flattened_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                os.makedirs(local_dir, exist_ok=True)
                local_path = os.path.join(local_dir, filename)
                with open(local_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                return f"local://{local_path}"
            
            # Create timestamped blob name with new folder structure
            date_folder = datetime.now().strftime("%Y%m%d")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            blob_name = f"{date_folder}/flattened/{blob_prefix}/{filename}"
            
            # Upload using existing method
            success = self.upload_blob_content(blob_name, content, overwrite=overwrite)
            
            if success:
                self.logger.info(f"[UPLOAD TO LATEST] Uploaded to Azure: {blob_name}")
                return blob_name
            else:
                self.logger.error(f"[UPLOAD TO LATEST] Failed to upload: {blob_name}")
                return None
                
        except Exception as e:
            self.logger.error(f"[UPLOAD TO LATEST] Error in upload_to_latest: {e}")
            return None
