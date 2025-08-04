# 🌍 AgenticAI - Earth at Night Intelligence Platform

A comprehensive AI-powered platform for exploring and analyzing Earth at Night data using Azure AI services. This project combines multiple data sources, advanced RAG (Retrieval Augmented Generation) capabilities, and interactive interfaces to provide intelligent insights about nighttime satellite imagery, urban lighting patterns, nocturnal ecosystems, and climate science.

## 🌟 Key Features

### 🤖 **Multi-Source AI Agents**
- **Text Document Processing**: Advanced chunking and vectorization of Earth science documents
- **JSON Data Integration**: NASA Earth at Night dataset processing from GitHub and Azure Storage
- **SQL Database Connectivity**: Enterprise data integration with Azure SQL Database
- **Intelligent Retrieval**: Context-aware document search with source attribution

### 🖥️ **Interactive User Interfaces**
- **Chat Interface**: Modern Streamlit-based conversational AI assistant
- **Analytics Dashboard**: Data visualization and insights dashboard
- **Jupyter Notebooks**: Interactive development and testing environments

### 🔧 **Enterprise-Grade Architecture**
- **Azure AI Projects Integration**: Seamless connection to Azure AI Hub
- **Multiple Authentication Methods**: Managed Identity and API Key support
- **Scalable Vector Search**: Azure AI Search with semantic ranking
- **Flexible Data Sources**: Support for GitHub, Azure Storage, and SQL databases

## 📁 Project Structure

```
agenticAI/
├── 📊 Notebooks/
│   ├── ai_search.ipynb              # GitHub JSON data processing
│   ├── ai_search_storage.ipynb      # Azure Storage JSON processing  
│   ├── ai_search_txt_files.ipynb    # Text file processing with chunking
│   ├── agent.ipynb                  # Interactive Q&A agent
│   └── sqldb.ipynb                  # SQL database integration
├── 🖥️ Applications/
│   ├── chat_ui.py                   # Streamlit chat interface
│   ├── analytics_dashboard.py       # Data analytics dashboard
│   ├── launch_chat.bat             # Windows launcher
│   └── launch_chat.sh              # Unix launcher
├── 📄 Data/
│   └── Files/                       # Text documents for processing
│       ├── Earth_At_Night_Overview.txt
│       ├── Earth_Night_Ecosystems.txt
│       ├── Global_Landscape_Earth_At_Night.txt
│       ├── Human_Activity_At_Night.txt
│       └── Night_Imagery_Disaster_Monitoring.txt
├── ⚙️ Configuration/
│   ├── .env                        # Environment variables
│   ├── requirements.txt            # Core dependencies
│   ├── requirements_ui.txt         # UI dependencies
│   └── README.md                   # This file
└── 📚 Documentation/
    └── CHAT_README.md              # Chat interface documentation
```

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Azure subscription with AI services
- Azure AI Hub and Search service configured

### 1. Environment Setup

```bash
# Clone the repository
git clone https://github.com/imanishat/agenticAI.git
cd agenticAI

# Install dependencies
pip install -r requirements.txt
pip install -r requirements_ui.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your Azure credentials
```

### 2. Required Environment Variables

Create a `.env` file with the following configuration:

```env
# Azure AI Project
PROJECT_ENDPOINT=https://your-ai-hub.services.ai.azure.com/api/projects/your-project

# Azure Search
AZURE_SEARCH_ENDPOINT=https://your-search-service.search.windows.net/

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-ai-hub.openai.azure.com/
AZURE_OPENAI_KEY=your-openai-key
AZURE_OPENAI_GPT_DEPLOYMENT=gpt-4.1-mini
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large

# Authentication
MANAGED_IDENTITY_CLIENT_ID=your-managed-identity-id

# Azure Storage (Optional)
AZURE_STORAGE_ACCOUNT_NAME=your-storage-account
AZURE_STORAGE_ACCOUNT_KEY=your-storage-key
AZURE_STORAGE_CONTAINER_NAME=demo
TXT_STORAGE_CONTAINER_NAME=earthdata

# SQL Database (Optional)
SQL_SERVER_NAME=your-sql-server.database.windows.net
SQL_DATABASE_NAME=your-database
SQL_USERNAME=your-username
SQL_PASSWORD=your-password
```

### 3. Launch the Chat Interface

```bash
# Windows
launch_chat.bat

# Unix/Linux/Mac
./launch_chat.sh

# Or manually
streamlit run chat_ui.py
```

## 📊 Core Components

### 1. **Data Processing Notebooks**

#### `ai_search.ipynb` - GitHub Data Processing
- Loads NASA Earth at Night JSON data from GitHub
- Creates Azure AI Search index with vector embeddings
- Sets up knowledge agent for retrieval

#### `ai_search_storage.ipynb` - Azure Storage Integration
- Connects to Azure Storage Account
- Processes JSON data from blob storage
- Includes fallback to GitHub if storage fails

#### `ai_search_txt_files.ipynb` - Text Document Processing
- Intelligent text chunking with sentence boundaries
- Batch processing of multiple text files
- Metadata tracking and document identification

#### `agent.ipynb` - Interactive Q&A Agent
- Conversation threading and context management
- Function tool integration for retrieval
- Source citation and reference tracking

#### `sqldb.ipynb` - Enterprise Database Integration
- Azure SQL Database connectivity
- Skillset creation for data processing
- Indexer configuration for automated updates

### 2. **User Interfaces**

#### Chat Interface (`chat_ui.py`)
- **Modern Streamlit Design**: Responsive UI with custom CSS
- **Real-time Conversations**: Interactive chat with the AI agent
- **Source Citations**: Automatic reference linking to source documents
- **Sample Questions**: Pre-configured queries for quick testing
- **System Status**: Connection monitoring and configuration display

#### Analytics Dashboard (`analytics_dashboard.py`)
- **Data Visualization**: Interactive charts and metrics
- **Performance Monitoring**: System usage and response analytics
- **Insight Generation**: Automated analysis of query patterns

## 🔍 Supported Data Sources

### 1. **Text Documents**
- **Format**: Plain text files (.txt)
- **Processing**: Intelligent chunking with overlap
- **Content**: Earth science research papers, NASA documentation
- **Features**: Metadata extraction, source tracking

### 2. **JSON Datasets**
- **Sources**: GitHub repositories, Azure Storage
- **Format**: Structured NASA Earth at Night data
- **Processing**: Direct indexing with vector embeddings
- **Features**: Page-level chunking, semantic search

### 3. **SQL Databases**
- **Platforms**: Azure SQL Database, SQL Server
- **Processing**: Automated skillset and indexer creation
- **Features**: Real-time synchronization, custom field mapping

## 🧠 AI Capabilities

### **Retrieval Augmented Generation (RAG)**
- **Vector Search**: High-dimensional embedding similarity
- **Semantic Ranking**: Context-aware result prioritization
- **Source Attribution**: Automatic citation generation
- **Multi-Index Support**: Query across different data sources

### **Specialized Knowledge Domains**
- 🛰️ **Satellite Imagery**: Nighttime observations from space
- 🏙️ **Urban Lighting**: City development and infrastructure patterns
- 🦉 **Nocturnal Ecosystems**: Wildlife behavior and bioluminescence
- 🚨 **Disaster Monitoring**: Emergency response using night imagery
- 🌡️ **Climate Science**: Urban heat islands and environmental monitoring

## 🛠️ Technology Stack

### **Azure Services**
- **Azure AI Projects**: Centralized AI service management
- **Azure AI Search**: Enterprise search with AI capabilities
- **Azure OpenAI**: GPT models and embeddings
- **Azure Storage**: Blob storage for documents and data
- **Azure SQL Database**: Relational data storage

### **Development Framework**
- **Python 3.8+**: Core programming language
- **Streamlit**: Web application framework
- **Jupyter Notebooks**: Interactive development environment
- **Azure SDK for Python**: Service integration libraries

### **AI/ML Components**
- **GPT-4.1-mini**: Large language model for conversations
- **text-embedding-3-large**: Vector embeddings for semantic search
- **Knowledge Agents**: Specialized retrieval and reasoning
- **Function Tools**: Custom tool integration for enhanced capabilities

## 📈 Usage Examples

### Example Queries the System Can Handle:

1. **Urban Development Analysis**
   ```
   "How do city lights reveal information about transportation 
   infrastructure and political boundaries?"
   ```

2. **Climate Science**
   ```
   "What role does nighttime imagery play in climate research 
   and monitoring urban heat island effects?"
   ```

3. **Ecological Research**
   ```
   "What animals become active at night and how do they use 
   darkness for survival?"
   ```

4. **Disaster Response**
   ```
   "How does night imagery support disaster response and 
   emergency management?"
   ```

5. **Scientific Discovery**
   ```
   "How do I find lava at night using satellite imagery?"
   ```

## 🔧 Advanced Configuration

### **Custom Index Configuration**
```python
# Text files index for multi-document processing
TXT_SEARCH_INDEX=txt_files_index
TXT_SEARCH_AGENT_NAME=txt-files-agent

# JSON data index for NASA datasets
AZURE_SEARCH_INDEX=earth_at_night_storage
AZURE_SEARCH_AGENT_NAME=earth-search-agent-storage
```

### **Authentication Options**
- **Managed Identity**: Recommended for production deployments
- **API Keys**: Suitable for development and testing
- **DefaultAzureCredential**: Automatic credential resolution

### **Performance Tuning**
- **Vector Dimensions**: 3072 for text-embedding-3-large
- **Chunk Overlap**: 50-100 characters for optimal context
- **Reranker Threshold**: 2.5 for balanced precision/recall

## 🚀 Deployment

### **Local Development**
```bash
# Start the chat interface
streamlit run chat_ui.py --server.port 8501

# Launch analytics dashboard
streamlit run analytics_dashboard.py --server.port 8502
```

### **Production Deployment**
- **Azure Container Instances**: For cloud deployment
- **Azure App Service**: For web application hosting
- **Docker**: Containerized deployment option

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **NASA Earth at Night**: Primary data source for satellite imagery insights
- **Azure AI Services**: Cloud infrastructure and AI capabilities
- **Streamlit Community**: Modern web application framework
- **Open Source Contributors**: Various libraries and tools used in this project

## 📞 Support

For questions, issues, or contributions:
- 📧 **Email**: [Your Contact Email]
- 🐛 **Issues**: [GitHub Issues](https://github.com/imanishat/agenticAI/issues)
- 📖 **Documentation**: See individual notebook files for detailed examples
- 💬 **Discussions**: [GitHub Discussions](https://github.com/imanishat/agenticAI/discussions)

---

**Built with ❤️ using Azure AI Services and Streamlit**