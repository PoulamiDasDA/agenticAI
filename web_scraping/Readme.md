# Azure Durable Functions Web Scraping API Documentation

## Overview
This Azure Function App provides a comprehensive web scraping service using Durable Functions architecture with orchestrator, activity, HTTP trigger, and timer functions.

## 🔐 Managed Identity Access Requirements

When deploying the Function App, the following access levels were assigned to the managed identity:

### Azure Storage Account
- **Storage Blob Data Contributor**: Read, write, and delete blob data
- **Storage Queue Data Contributor**: Manage queue messages for durable functions
- **Storage Table Data Contributor**: Access table storage for workflow state
- **Storage Account Contributor**: Manage storage account properties

### Application Insights
- **Monitoring Metrics Publisher**: Publish custom metrics and telemetry
- **Application Insights Component Contributor**: Access to insights data

### Key Vault (if used)
- **Key Vault Secrets User**: Read secrets for configuration

---

## 🌐 HTTP Trigger Functions (Public APIs)

### 1. Health Check Endpoint
- **Route**: `/api/health`
- **Method**: `GET`
- **Authentication**: None required
- **Purpose**: Service health monitoring and configuration verification

#### Functionality
- ✅ Confirms service is operational
- ✅ Shows available websites (`cbuae`, `generic`)
- ✅ Displays storage account configuration
- ✅ Returns service metadata and timestamp
- ✅ Used for monitoring and diagnostics

#### Response Example
```json
{
  "status": "healthy",
  "service": "durable-web-scraper-functions", 
  "timestamp": "2025-09-11T10:30:00.000Z",
  "available_websites": ["cbuae", "generic"],
  "storage_account": "explorationstorage12",
  "mode": "durable_functions"
}
```

#### curl example

curl -X GET "https://your-function-app.azurewebsites.net/api/health"

### 2. Web Scraping Endpoint
Route: /api/scraper
Method: POST
Authentication: Function key required
Purpose: Start comprehensive web scraping workflows
Functionality
✅ Initiates durable function orchestration
✅ Validates website availability
✅ Starts full scraping workflow (discovery → scraping → processing → upload)
✅ Optional file download integration (PDFs, Word docs)
✅ Returns instance ID for tracking progress

##### Request Parameters
```json
{
  "website": "cbuae",           // Target website
  "upload_to_cloud": true,      // Store results in Azure Storage
  "download_files": true,       // Download attachments (optional)
  "max_files": 10              // Limit file downloads (optional)
}
```

#### Response Example
```json
{
  "message": "Full scraping started for cbuae",
  "instance_id": "abc123def456",
  "status_url": "/api/scraper/status/abc123def456",
  "website": "cbuae",
  "upload_to_cloud": true,
  "started_at": "2025-09-11T10:30:00.000Z"
}
```

#### curl example

```
curl -X POST "https://your-function-app.azurewebsites.net/api/scraper?code=YOUR_FUNCTION_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "website": "cbuae",
       "upload_to_cloud": true,
       "download_files": true,
       "max_files": 10
     }'
```

### 3. Status Monitoring Endpoint
Route: /api/scraper/status/{instance_id}
Method: GET
Authentication: Function key required
Purpose: Real-time workflow progress monitoring
Functionality
✅ Tracks orchestration execution status
✅ Shows current workflow step
✅ Displays completed phases
✅ Provides detailed progress data
✅ Shows intermediate results from each phase

#### Response during execution
```json
{
  "instance_id": "abc123def456",
  "status": "Running",
  "custom_status": {
    "website": "cbuae",
    "current_step": "scraping",
    "steps_completed": ["discovery"],
    "total_steps": 4,
    "discovery": {
      "status": "completed",
      "total_urls_found": 32,
      "urls": ["url1", "url2", "..."]
    },
    "scraping": {
      "status": "in_progress",
      "scraped_count": 15,
      "file_downloads": {
        "total_downloaded": 5,
        "downloaded_files": ["file1.pdf", "file2.docx"]
      }
    }
  }
}
```

#### Response when completed
```json
{
  "instance_id": "abc123def456",
  "status": "Completed",
  "custom_status": {
    "website": "cbuae",
    "current_step": "completed",
    "steps_completed": ["discovery", "scraping", "processing", "upload"],
    "total_steps": 4,
    "final_result": {
      "website": "cbuae",
      "total_urls_discovered": 32,
      "total_pages_scraped": 25,
      "total_files_processed": 20,
      "total_files_uploaded": 15
    }
  },
  "output": {
    "website": "cbuae",
    "status": "completed",
    "discovery": {"total_urls_found": 32},
    "scraping": {"scraped_count": 25},
    "processing": {"processed_count": 20},
    "upload": {"total_successful": 15}
  }
}
```

#### curl example

curl -X GET "https://your-function-app.azurewebsites.net/api/scraper/status/abc123def456?code=YOUR_FUNCTION_KEY"

⏰ Timer Trigger Function (Automated)
### 4. Scheduled Scraper
Schedule: 0 0 9 * * * (Daily at 9:00 AM UTC)
Authentication: None (internal trigger)
Purpose: Automated daily scraping execution
Functionality
✅ Runs automatically without manual intervention
✅ Uses environment variables for configuration
✅ Starts full scraping workflow for configured website
✅ Handles past-due execution detection
✅ Comprehensive error logging for monitoring
Environment Variables
SCRAPING_WEBSITE: Target website (default: "cbuae")
SCRAPING_UPLOAD_TO_CLOUD: Upload behavior (default: "true")

#### Schedule format

0 0 9 * * *
│ │ │ │ │ │
│ │ │ │ │ └─── Day of week (0-6, Sunday=0)
│ │ │ │ └───── Month (1-12)
│ │ │ └─────── Day of month (1-31)
│ │ └───────── Hour (0-23)
│ └─────────── Minute (0-59)
└───────────── Second (0-59)

🎯 Orchestrator Function (Internal)
### 5. Scraping Orchestrator
Type: Durable Function Orchestrator
Purpose: Workflow coordination and state management
Functionality
✅ Manages entire scraping workflow lifecycle
✅ Coordinates activity function execution
✅ Handles error recovery and retry logic
✅ Maintains workflow state across executions
✅ Provides real-time status updates
✅ Ensures data consistency and transaction integrity
Workflow Steps
Discovery: Website structure analysis and URL extraction
Scraping: Content extraction and file downloads
Processing: Data transformation and file creation
Upload: Azure Storage persistence

Error Handling
Individual activity failures don't stop the entire workflow
Comprehensive error logging and status reporting
Graceful degradation for partial failures
Structured error responses with detailed failure information

⚡ Activity Functions (Internal Workers)
### 6. Website Discovery Activity
Purpose: Website structure analysis and URL discovery

Functionality
✅ Hierarchical site structure discovery
✅ URL extraction with depth-based crawling
✅ Site-type detection (specialized vs generic)
✅ URL filtering (excludes unwanted content)
✅ Metadata extraction (titles, structure)
Discovery Methods
Specialized Sites: Hierarchical skeleton discovery for structured websites
Generic Sites: Basic skeleton discovery for general websites
Depth Control: Configurable maximum crawling depth
Filter Rules: Automatic exclusion of unwanted content (e.g., insurance pages)

### 7. Content Scraping Activity
Purpose: Content extraction and file downloads

Functionality
✅ Text content extraction from discovered URLs
✅ Integrated file download (PDFs, Word documents)
✅ Rate limiting for respectful crawling
✅ Error handling for failed pages
✅ Progress tracking and statistics
File Download Features
Supported Formats: PDF (.pdf) and Word documents (.docx, .doc)
De-duplication: SHA256 hash-based duplicate detection
Rate Limiting: 0.5-1 second delays between requests
Size Limits: Configurable maximum file sizes
Timeout Handling: 15-second timeout per request

### 8. Data Processing Activity
Purpose: Content processing and file organization

Functionality
✅ Website-specific content processing
✅ JSON file creation for each scraped page
✅ Summary file generation
✅ Temporary directory management
✅ Data validation and quality checks
Processing Features
Individual Files: One JSON file per scraped page
Summary Generation: Consolidated summary of all scraped data
Data Validation: Content quality checks and validation
Metadata Extraction: Title, URL, timestamp, and content structure

### 9. Storage Upload Activity
Purpose: Azure Storage persistence

Functionality
✅ Bulk file upload to Azure Blob Storage
✅ Organized folder structure creation
✅ Upload progress tracking
✅ Error handling and retry logic

## Storage organization

Container: data/
├── durable_functions/
│   └── cbuae/
│       ├── individual_files/
│       │   ├── page_001.json
│       │   ├── page_002.json
│       │   └── ...
│       ├── pdfs/
│       │   ├── document_001.pdf
│       │   └── ...
│       ├── words/
│       │   ├── document_001.docx
│       │   └── ...
│       └── summary_YYYYMMDD_HHMMSS.json

Application Settings (Azure Portal)
Runtime Version: Python 3.11
Always On: Recommended for consistent performance
HTTPS Only: Enabled for security
Managed Identity: System-assigned identity enabled
✅ Managed identity authentication


## MI Permission summary

Storage Account:
├── Storage Blob Data Contributor
├── Storage Queue Data Contributor
├── Storage Table Data Contributor
└── Storage Account Contributor

Application Insights:
├── Monitoring Metrics Publisher
└── Application Insights Component Contributor

Key Vault (optional):
└── Key Vault Secrets User
