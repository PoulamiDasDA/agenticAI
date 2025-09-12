import os
import json
import glob
import traceback
from datetime import datetime
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

class StorageAccount:
    """Azure Storage with AAD authentication (works when key-based auth is disabled)"""
    
    def __init__(self, storage_account_name, container_name,credential_type):
        self.storage_account_name = storage_account_name
        self.container_name = container_name
        self.azure_available = False
        self.credential_type = credential_type
        
        # Set up logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        # Try different authentication methods
        self._initialize_client()
    
    def _initialize_client(self):
        """Try different AAD authentication methods"""
        account_url = f"https://{self.storage_account_name}.blob.core.windows.net"
        
        if self.credential_type == 'CLI':
            # Method 1: Try Azure CLI credential (most common for development)
            try:
                from azure.identity import AzureCliCredential
                from azure.storage.blob import BlobServiceClient
                
                credential = AzureCliCredential()
                self.blob_service_client = BlobServiceClient(account_url=account_url, credential=credential)
                
                # Test the connection
                container_client = self.blob_service_client.get_container_client(self.container_name)
                container_client.exists()
                
                self.azure_available = True
                self.logger.info("✅ Azure CLI authentication successful")
                return
                
            except Exception as e:
                self.logger.warning(f"Azure CLI auth failed: {e}")
        
        elif self.credential_type == 'serviceprincipal':
            # Method 2: Try environment variables (service principal)
            try:
                from azure.identity import ClientSecretCredential
                from azure.storage.blob import BlobServiceClient
                
                tenant_id = os.getenv("AZURE_TENANT_ID")
                client_id = os.getenv("AZURE_CLIENT_ID") 
                client_secret = os.getenv("AZURE_CLIENT_SECRET")
                
                if all([tenant_id, client_id, client_secret]):
                    credential = ClientSecretCredential(
                        tenant_id=tenant_id,
                        client_id=client_id,
                        client_secret=client_secret
                    )
                    self.blob_service_client = BlobServiceClient(account_url=account_url, credential=credential)
                    
                    # Test connection
                    container_client = self.blob_service_client.get_container_client(self.container_name)
                    container_client.exists()
                    
                    self.azure_available = True
                    self.logger.info("✅ Service Principal authentication successful")
                    return
                    
            except Exception as e:
                self.logger.warning(f"Service Principal auth failed: {e}")
        
        elif self.credential_type == 'AAD':
            # Method 3: Try DefaultAzureCredential (but with better error handling)
            try:
                from azure.identity import DefaultAzureCredential
                from azure.storage.blob import BlobServiceClient
                
                credential = DefaultAzureCredential()
                self.blob_service_client = BlobServiceClient(account_url=account_url, credential=credential)
                
                # Test connection with timeout
                container_client = self.blob_service_client.get_container_client(self.container_name)
                container_client.exists()
                
                self.azure_available = True
                self.logger.info("✅ Default Azure Credential authentication successful")
                return
                
            except Exception as e:
                self.logger.warning(f"Default credential auth failed: {e}")
        
        # If all methods fail
        self.azure_available = False
        self.logger.warning("⚠️ All Azure authentication methods failed - using local mode")
    
    
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
            self.logger.info(f"✅ Uploaded to Azure: {blob_name}")
            return blob_url
            
        except Exception as e:
            self.logger.error(f"❌ Azure upload failed for {local_file_path}: {e}")
            return f"file://{local_file_path}"
    
    def upload_scraped_data(self, individual_dir, summary_file=None, blob_prefix="central_bank_uae"):
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
            
            # Handle summary file
            summary_results = {'successful_uploads': [], 'failed_uploads': []}
            if summary_file and os.path.exists(summary_file):
                try:
                    summary_blob_name = f"{session_prefix}/summary/{os.path.basename(summary_file)}"
                    summary_url = self.upload_file(summary_file, summary_blob_name)
                    summary_results['successful_uploads'].append({
                        'local_path': summary_file,
                        'blob_name': summary_blob_name,
                        'blob_url': summary_url
                    })
                except Exception as e:
                    summary_results['failed_uploads'].append({
                        'local_path': summary_file,
                        'error': str(e)
                    })
            
            # Return guaranteed structure
            return {
                'session_prefix': session_prefix,
                'individual_files': {
                    'successful_uploads': successful_uploads,
                    'failed_uploads': failed_uploads,
                    'total_files': len(json_files),
                    'total_size_mb': total_size
                },
                'summary_files': summary_results,
                'total_successful': len(successful_uploads) + len(summary_results['successful_uploads']),
                'total_failed': len(failed_uploads) + len(summary_results['failed_uploads']),
                'total_size_mb': total_size,
                'azure_available': self.azure_available,
                'status': 'uploaded' if self.azure_available else 'local_tracking'
            }
            
        except Exception as e:
            self.logger.error(f"❌ Upload operation failed: {e}")
            return {
                'session_prefix': f"failed/{blob_prefix}",
                'individual_files': {'successful_uploads': [], 'failed_uploads': [], 'total_files': 0, 'total_size_mb': 0},
                'summary_files': {'successful_uploads': [], 'failed_uploads': []},
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
    
    # Backward compatibility methods
    def upload_directory(self, *args, **kwargs):
        return {'successful_uploads': [], 'failed_uploads': [], 'total_files': 0, 'total_size_mb': 0}
    
    def upload_blob_content(self, blob_name, content, overwrite=True, metadata=None):
        if not self.azure_available:
            return f"local://{blob_name}"
        
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_name
            )
            blob_client.upload_blob(content.encode('utf-8'), overwrite=overwrite, metadata=metadata)
            return blob_client.url
        except Exception as e:
            self.logger.error(f"Error uploading content: {e}")
            return f"local://{blob_name}"
    
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
    
    def process_with_blob_storage(self, *args, **kwargs):
        return f"local://processed"
    
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
            
            # Create timestamped blob name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            blob_name = f"{blob_prefix}/session_{timestamp}/{filename}"
            
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
