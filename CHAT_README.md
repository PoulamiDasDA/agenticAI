# 🌍 Earth at Night AI Chat Interface

A modern web-based chat interface for your Earth at Night AI Assistant built with Streamlit.

## 🚀 Quick Start

### Windows Users
```bash
# Double-click or run in Command Prompt
launch_chat.bat
```

### Linux/Mac Users
```bash
# Make executable and run
chmod +x launch_chat.sh
./launch_chat.sh
```

### Manual Installation
```bash
# Install dependencies
pip install -r requirements_ui.txt

# Run the application
streamlit run chat_ui.py
```

## 🎯 Features

### 💬 Interactive Chat Interface
- **Real-time conversations** with your AI agent
- **Message history** with timestamps
- **Sample questions** for quick testing
- **Clear chat history** functionality

### 🔧 System Management
- **Connection status** indicator
- **Agent initialization** with progress feedback
- **Configuration display** showing current settings
- **Error handling** with detailed feedback

### 🎨 Modern UI Design
- **Responsive layout** that works on desktop and mobile
- **Custom styling** with professional color scheme
- **Status indicators** for connection health
- **Organized sidebar** with controls and info

### 🔍 Smart Search Integration
- **RAG (Retrieval Augmented Generation)** with source citations
- **Document ID citations** in format [id]
- **Multi-source retrieval** from your text index
- **Fallback responses** when information isn't available

## 📋 Prerequisites

Make sure your `.env` file contains:

```env
# Required for chat interface
PROJECT_ENDPOINT=your-ai-project-endpoint
AZURE_SEARCH_ENDPOINT=your-search-endpoint
AZURE_OPENAI_ENDPOINT=your-openai-endpoint
AZURE_OPENAI_KEY=your-openai-key
MANAGED_IDENTITY_CLIENT_ID=your-managed-identity-id

# Agent configuration
TXT_SEARCH_INDEX=txt_files_index
TXT_SEARCH_AGENT_NAME=txt-files-agent
AZURE_OPENAI_GPT_DEPLOYMENT=gpt-4.1-mini

# Storage configuration
TXT_STORAGE_CONTAINER_NAME=earthdata
```

## 🎮 How to Use

1. **Launch the application** using one of the methods above
2. **Initialize the agent** using the sidebar button
3. **Start chatting!** Ask questions about Earth at night topics
4. **Try sample questions** from the sidebar for quick testing

## 🌟 Sample Questions

- "What is bioluminescence and how does it help marine life?"
- "How does night imagery support disaster response?"
- "What causes the urban heat island effect?"
- "How do city lights reveal urban development patterns?"
- "What can satellite imagery tell us about North vs South Korea?"

## 📊 Topics Covered

Your AI assistant can answer questions about:

- 🛰️ **Satellite Imagery**: Nighttime observations from space
- 🏙️ **Urban Lighting**: City development and infrastructure patterns  
- 🦉 **Nocturnal Ecosystems**: Wildlife behavior and bioluminescence
- 🚨 **Disaster Monitoring**: Emergency response using night imagery
- 🌡️ **Climate Science**: Urban heat islands and environmental monitoring

## 🛠️ Troubleshooting

### Connection Issues
- Ensure all environment variables are set correctly
- Check your Azure service endpoints and credentials
- Verify your search index exists and contains data

### Performance Issues
- The first response may take longer as the agent initializes
- Large text retrievals may cause slight delays
- Check your Azure service quotas if experiencing timeouts

### UI Issues
- Refresh the browser if the interface becomes unresponsive
- Clear browser cache if styling appears broken
- Use the "Clear Chat History" button to reset conversation state

## 🔧 Customization

### Modify Sample Questions
Edit the `sample_questions` list in `chat_ui.py`:

```python
sample_questions = [
    "Your custom question here",
    "Another question about your domain",
    # Add more questions...
]
```

### Change Styling
Modify the CSS in the `st.markdown()` section:

```python
st.markdown("""
<style>
    .main-header {
        /* Your custom styles */
    }
</style>
""", unsafe_allow_html=True)
```

### Update Agent Instructions
Modify the `instructions` variable in the `initialize_connections()` method.

## 📱 Accessing the Interface

Once launched, the interface will be available at:
- **Local access**: http://localhost:8501
- **Network access**: http://your-ip:8501 (if configured)

## 🔒 Security Notes

- The interface runs locally and doesn't expose credentials
- All Azure communications use secure HTTPS
- Chat history is stored in browser session only
- No data is persisted between sessions

## 📞 Support

If you encounter issues:
1. Check the terminal/command prompt for error messages
2. Verify your `.env` configuration
3. Ensure your Azure services are running
4. Test your agent directly in the Jupyter notebook first

---

**Happy chatting with your Earth at Night AI Assistant! 🌍✨**
