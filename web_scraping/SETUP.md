# 🚀 Quick Setup Guide

## 📋 Prerequisites
- Python 3.8+
- Azure Functions Core Tools
- Azurite (for local development)

## ⚙️ Configuration Setup

### 1. **Copy Configuration Files**
```bash
# Copy example files
cp local.settings-example.json local.settings.json
cp .env.example .env
```

### 2. **Local Development Setup (Azurite)**
For local development, the example files are already configured for Azurite. Just ensure:

**local.settings.json**:
- `AzureWebJobsStorage`: `"UseDevelopmentStorage=true"`
- `AZURE_STORAGE_ACCOUNT_NAME`: `"devstoreaccount1"`
- `AZURE_CREDENTIAL_TYPE`: `"CONNECTION_STRING"`

### 3. **Production Setup (Azure)**
Update these values in both `local.settings.json` and `.env`:

**Required Azure Services**:
- Azure Storage Account
- Azure OpenAI Service  
- Azure AI Search
- Application Insights

**Update Configuration**:
```json
{
  "AZURE_STORAGE_ACCOUNT_NAME": "your-production-storage-account",
  "AZURE_CREDENTIAL_TYPE": "AAD",
  "MI_CLIENT_ID": "your-managed-identity-id",
  "AZURE_OPENAI_ENDPOINT": "https://your-openai.openai.azure.com/",
  "AZURE_SEARCH_ENDPOINT": "https://your-search.search.windows.net"
}
```

## 🌐 **Website Configuration**

The system supports multiple websites configured in `WEBSITES_CONFIG` JSON array:

```json
"WEBSITES_CONFIG": "[{\"key\":\"httpbin\",\"url\":\"https://httpbin.org/html\",\"name\":\"HTTPBin Test\",\"max_depth\":1,\"folder_name\":\"httpbin-test\",\"filters\":[]},{\"key\":\"sec\",\"url\":\"https://www.ecb.europa.eu/home/html/index.en.html\",\"name\":\"SEC Rules\",\"max_depth\":2,\"folder_name\":\"sec-rules\",\"filters\":[]},{\"key\":\"cbuae\",\"url\":\"https://rulebook.centralbank.ae/en/rulebook/banking\",\"name\":\"Central Bank UAE\",\"max_depth\":3,\"folder_name\":\"cbuae-banking\",\"filters\":[\"insurance\"]}]"
```

**To Add New Websites**: Add objects to the JSON array with these fields:
- `key`: Unique identifier
- `url`: Starting URL
- `name`: Display name
- `max_depth`: Scraping depth limit
- `folder_name`: Storage folder name
- `filters`: Content filters (optional)

## ⏱️ **Timer Configuration**

**Monthly Automation** (Production):
```json
"TIMER_ENABLED": "false"  // Set to "true" to enable monthly scraping
```

**Schedule**: 1st of every month at 9:00 AM UTC (`"0 0 9 1 * *"`)

## 🚀 **Local Development**

### 1. **Start Azurite**
```bash
azurite --silent --location c:\azurite --debug c:\azurite\debug.log
```

### 2. **Start Functions**
```bash
cd web_scraping
func host start
```

### 3. **Test Endpoints**
```powershell
# Test all websites
$body = '{"websites": "all", "sequential": false}'
Invoke-WebRequest -Uri "http://localhost:7071/api/batch-scraper" -Method POST -ContentType "application/json" -Body $body

# Health check
Invoke-WebRequest -Uri "http://localhost:7071/api/health" -Method GET
```

## 📚 **Documentation**

- **API Reference**: See `API_REFERENCE.md` for complete endpoint documentation
- **Configuration**: Both `.env.example` and `local.settings-example.json` have detailed comments
- **Monitoring**: Check Azure Portal for Application Insights logs

## 🔐 **Security Notes**

- **Never commit** `local.settings.json` or `.env` files
- **Use Managed Identity** for production Azure authentication
- **Set appropriate CORS** policies for production
- **Monitor storage costs** with automated scraping

## 📊 **Storage Structure**

```
Container: processed/
├── YYYYMMDD/                 # Date folder
│   └── webpage/              # Content type  
│       ├── httpbin-test/     # Website folders
│       ├── sec-rules/
│       └── cbuae-banking/
│           ├── raw_pages.json
│           └── flattened_pages.json
```

---

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



**Need Help?** Check `API_REFERENCE.md` for complete documentation and examples.
