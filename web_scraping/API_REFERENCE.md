# Web Scraping Azure Functions - API Reference

## 📋 Overview

This Azure Functions application provides a comprehensive web scraping service with multi-website support, automated scheduling, and intelligent content processing.

**Base URL**: `http://localhost:7071/api` (local) | `https://your-function-app.azurewebsites.net/api` (production)

---

## 🔄 **Timer Trigger** (Automated Execution)

### **Monthly Automated Scraping**
- **Schedule**: `0 0 9 1 * *` (1st of every month at 9:00 AM UTC)
- **Status**: Controlled by `TIMER_ENABLED` environment variable
- **Function**: `timer_start_scraper`
- **Execution**: Automatically processes ALL configured websites

**What it does:**
1. Processes all websites in `WEBSITES_CONFIG` 
2. Runs complete workflow: Discovery → Scraping → Flattening
3. Uses parallel processing for efficiency
4. Uploads to Azure Storage with timestamped folders

**Next Execution**: October 1, 2025 at 9:00 AM UTC

---

## 🌐 **HTTP Endpoints**

### **1. Batch Scraper** (Recommended)
```http
POST /api/batch-scraper
```

**Description**: Process multiple websites simultaneously with parallel or sequential execution.

**Request Body**:
```json
{
  "websites": "all" | ["httpbin", "sec", "cbuae"] | ["cbuae"],
  "sequential": false,  // true for sequential, false for parallel
  "complete_workflow": true  // Optional: force complete workflow
}
```

**Response**:
```json
{
  "message": "Batch processing started",
  "mode": "parallel",
  "websites": ["httpbin", "sec", "cbuae"],
  "orchestrator_instances": [
    {
      "website": "httpbin",
      "instance_id": "abc123...",
      "status_url": "/api/scraper/status/abc123..."
    },
    {
      "website": "sec", 
      "instance_id": "def456...",
      "status_url": "/api/scraper/status/def456..."
    },
    {
      "website": "cbuae",
      "instance_id": "ghi789...",
      "status_url": "/api/scraper/status/ghi789..."
    }
  ],
  "total_websites": 3
}
```

**Examples**:
```bash
# Process all websites in parallel (recommended)
curl -X POST "http://localhost:7071/api/batch-scraper" \
  -H "Content-Type: application/json" \
  -d '{"websites": "all", "sequential": false}'

# Process specific websites sequentially  
curl -X POST "http://localhost:7071/api/batch-scraper" \
  -H "Content-Type: application/json" \
  -d '{"websites": ["cbuae", "sec"], "sequential": true}'

# PowerShell example
$body = '{"websites": "all", "sequential": false}'
Invoke-WebRequest -Uri "http://localhost:7071/api/batch-scraper" -Method POST -ContentType "application/json" -Body $body
```

---

### **2. Single Website Scraper** (Legacy)
```http
POST /api/scraper
```

**Description**: Process a single website with complete workflow.

**Request Body**:
```json
{
  "website": "cbuae" | "sec" | "httpbin",
  "max_files": 500  // Optional
}
```

**Response**:
```json
{
  "message": "Complete workflow started for cbuae - fresh discovery → scraping → flattening",
  "instance_id": "abc123...",
  "status_url": "/api/scraper/status/abc123...",
  "website": "cbuae",
  "mode": "complete",
  "upload_to_cloud": null,
  "max_files": 500
}
```

---

### **3. Status Check**
```http
GET /api/scraper/status/{instance_id}
```

**Description**: Check the status of a running scraping operation.

**Parameters**:
- `instance_id`: The instance ID returned from scraper endpoints

**Response**:
```json
{
  "instanceId": "abc123...",
  "runtimeStatus": "Running" | "Completed" | "Failed" | "Pending",
  "input": {
    "website": "cbuae",
    "mode": "complete"
  },
  "output": null | { /* completion data */ },
  "createdTime": "2025-09-25T16:45:00.000Z",
  "lastUpdatedTime": "2025-09-25T16:46:30.000Z"
}
```

**Example**:
```bash
curl "http://localhost:7071/api/scraper/status/abc123..."
```

---

### **4. Health Check**
```http
GET /api/health
```

**Description**: Simple health check endpoint.

**Response**:
```json
{
  "status": "healthy",
  "timestamp": "2025-09-25T16:45:00.000Z"
}
```

---

## ⚙️ **Configuration**

### **Supported Websites**
The system supports these pre-configured websites:

1. **HTTPBin Test** (`httpbin`)
   - URL: `https://httpbin.org/html`
   - Max Depth: 1
   - Folder: `httpbin-test`

2. **SEC Rules** (`sec`)
   - URL: `https://www.ecb.europa.eu/home/html/index.en.html`
   - Max Depth: 2  
   - Folder: `sec-rules`

3. **Central Bank UAE** (`cbuae`)
   - URL: `https://rulebook.centralbank.ae/en/rulebook/banking`
   - Max Depth: 3
   - Folder: `cbuae-banking`
   - Filters: `["insurance"]`

### **Environment Variables**
```bash
# Timer Configuration
TIMER_ENABLED=false                    # Enable/disable automated timer
  
# Website Configuration (JSON Array)
WEBSITES_CONFIG=[{...}]                # Multi-website configuration

# Azure Storage
AZURE_STORAGE_CONNECTION_STRING="..."  # Storage connection
AZURE_STORAGE_RAW_CONTAINER_NAME="raw"
AZURE_STORAGE_PROCESSED_CONTAINER_NAME="processed"

# Processing Limits  
SCRAPING_MAX_DEPTH=5                   # Default max depth
SCRAPING_MAX_FILES=500                 # Default max files
SCRAPING_FILTERS="insurance"           # Default filters
```

---

## 📁 **Output Structure**

### **Azure Storage Layout**
```
Container: processed/
├── 20250925/              # Date folder (YYYYMMDD)
│   └── webpage/           # Content type
│       ├── httpbin-test/  # Website-specific folder
│       │   ├── raw_pages.json
│       │   └── flattened_pages.json
│       ├── sec-rules/     
│       │   ├── raw_pages.json  
│       │   └── flattened_pages.json
│       └── cbuae-banking/
│           ├── raw_pages.json
│           └── flattened_pages.json
```

### **Content Format**
**Raw Pages** (`raw_pages.json`):
```json
[
  {
    "url": "https://example.com/page1",
    "title": "Page Title",
    "content": "Full HTML content...",
    "timestamp": "2025-09-25T16:45:00Z",
    "metadata": {
      "website": "cbuae",
      "depth": 1
    }
  }
]
```

**Flattened Pages** (`flattened_pages.json`):
```json
[
  {
    "url": "https://example.com/page1", 
    "title": "Page Title",
    "flattened_content": "Clean text content...",
    "timestamp": "2025-09-25T16:45:00Z",
    "metadata": {
      "website": "cbuae",
      "circular_number": "REG-001",
      "effective_date": "2025-01-01"
    }
  }
]
```

---

## 🚀 **Usage Examples**

### **PowerShell Examples**
```powershell
# Process all websites in parallel (fastest)
$body = '{"websites": "all", "sequential": false}'
$response = Invoke-WebRequest -Uri "http://localhost:7071/api/batch-scraper" -Method POST -ContentType "application/json" -Body $body
$response.Content | ConvertFrom-Json | ConvertTo-Json -Depth 10

# Process only CBUAE 
$body = '{"websites": ["cbuae"], "sequential": false}'
Invoke-WebRequest -Uri "http://localhost:7071/api/batch-scraper" -Method POST -ContentType "application/json" -Body $body

# Check status
Invoke-WebRequest -Uri "http://localhost:7071/api/scraper/status/YOUR_INSTANCE_ID" -Method GET
```

### **cURL Examples**  
```bash
# Process all websites
curl -X POST "http://localhost:7071/api/batch-scraper" \
  -H "Content-Type: application/json" \
  -d '{"websites": "all", "sequential": false}'

# Health check
curl "http://localhost:7071/api/health"
```

---

## ⏱️ **Performance**

### **Parallel vs Sequential Processing**
- **Parallel** (`sequential: false`): All websites process simultaneously
  - ✅ **Fastest**: ~2-3x faster than sequential  
  - ✅ **Recommended**: For regular usage
  - ⚠️ **Resource intensive**: Higher CPU/memory usage

- **Sequential** (`sequential: true`): Websites process one after another
  - ✅ **Resource friendly**: Lower memory footprint
  - ⚠️ **Slower**: Takes longer for multiple websites

### **Typical Execution Times**
- **HTTPBin**: ~30 seconds (single page)
- **SEC**: ~2-3 minutes (depth 2) 
- **CBUAE**: ~5-8 minutes (depth 3, filtered)

---

## 🔧 **Development & Testing**

### **Local Testing**
1. Start Azurite: `azurite --silent --location c:\azurite --debug c:\azurite\debug.log`
2. Start Functions: `func host start`
3. Test endpoints using PowerShell or cURL examples above

### **Timer Testing**
To test timer locally, temporarily modify:
```python
# In function_app.py, change schedule to every minute
@app.schedule(schedule="0 * * * * *", arg_name="mytimer", run_on_startup=False)
```
```json
// In local.settings.json, enable timer
"TIMER_ENABLED": "true"
```

### **Production Deployment**
1. Deploy to Azure Functions
2. Configure environment variables
3. Set `TIMER_ENABLED=true` for automated monthly execution
4. Monitor via Azure Portal or Application Insights

---

## 📊 **Monitoring & Logs**

### **Application Insights Integration**
- All operations logged with correlation IDs
- Performance metrics tracked
- Error monitoring and alerting available

### **Log Levels**
- `INFO`: Normal operation flow
- `WARNING`: Non-critical issues 
- `ERROR`: Operation failures
- `DEBUG`: Detailed debugging (set `LOG_LEVEL=DEBUG`)

---

## 🎯 **Best Practices**

1. **Use Batch Scraper**: More efficient than single website calls
2. **Enable Parallel Processing**: Faster execution for multiple websites  
3. **Monitor Storage Usage**: Check Azure Storage consumption regularly
4. **Set Appropriate Limits**: Configure `max_files` based on needs
5. **Use Timer for Regular Updates**: Monthly automated execution recommended
6. **Check Status Regularly**: Monitor long-running operations
7. **Handle Rate Limits**: Some websites may have rate limiting

---

## 🔒 **Security & Compliance**

- **Authentication**: Function-level authentication required
- **Storage**: Secure Azure Storage with connection strings
- **Rate Limiting**: Respectful scraping with delays
- **Content Filtering**: Configurable content filters per website
- **Audit Trail**: Complete logging of all operations

---

**Last Updated**: September 25, 2025  
**Version**: 2.0 (Multi-website with Timer Support)