import streamlit as st
import os
import sys
from datetime import datetime
import json
import traceback
from dotenv import load_dotenv

# Azure SDK imports
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.core.credentials import AzureKeyCredential
from azure.ai.agents.models import FunctionTool, AgentsNamedToolChoice, AgentsNamedToolChoiceType, FunctionName, ToolSet
from azure.search.documents.agent import KnowledgeAgentRetrievalClient

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="Earth at Night AI Assistant",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        text-align: center;
        margin-bottom: 2rem;
        background: linear-gradient(90deg, #1f4e79, #2e7d9a);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    
    .chat-message {
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .user-message {
        background-color: #e3f2fd;
        border-left: 4px solid #2196f3;
    }
    
    .assistant-message {
        background-color: #f3e5f5;
        border-left: 4px solid #9c27b0;
    }
    
    .error-message {
        background-color: #ffebee;
        border-left: 4px solid #f44336;
    }
    
    .sidebar-info {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 5px;
        margin: 1rem 0;
    }
    
    .status-indicator {
        display: inline-block;
        width: 10px;
        height: 10px;
        border-radius: 50%;
        margin-right: 5px;
    }
    
    .status-connected {
        background-color: #4caf50;
    }
    
    .status-disconnected {
        background-color: #f44336;
    }
</style>
""", unsafe_allow_html=True)

class EarthNightAgent:
    def __init__(self):
        self.project_client = None
        self.agent = None
        self.thread = None
        self.agent_client = None
        self.toolset = None
        self.connection_status = "Disconnected"
        
    def initialize_connections(self):
        """Initialize all Azure connections"""
        try:
            # Load configuration
            project_endpoint = os.environ["PROJECT_ENDPOINT"]
            endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
            azure_openai_endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
            openai_key = os.getenv("AZURE_OPENAI_KEY")
            managed_identity_client_id = os.getenv("MANAGED_IDENTITY_CLIENT_ID")
            
            # Set up credentials
            credential = DefaultAzureCredential(managed_identity_client_id=managed_identity_client_id)
            new_credential = AzureKeyCredential(openai_key)
            
            # Initialize project client
            self.project_client = AIProjectClient(
                endpoint=project_endpoint, 
                credential=credential
            )
            
            # Initialize agent client for retrieval
            agent_name = os.getenv("TXT_SEARCH_AGENT_NAME", "txt-files-agent")
            self.agent_client = KnowledgeAgentRetrievalClient(
                endpoint=endpoint, 
                agent_name=agent_name, 
                credential=new_credential
            )
            
            # Set up the retrieval function
            def agentic_retrieval() -> str:
                """
                Searches text documents about Earth at night topics including satellite imagery, urban lighting, 
                nocturnal ecosystems, disaster monitoring, and climate science.
                The returned data contains text chunks with unique document IDs.
                Be sure to cite sources using the document ID format [id] in your agent's response.
                You must refer to references by their document ID.
                """
                try:
                    if hasattr(st.session_state, 'current_query') and st.session_state.current_query:
                        query = st.session_state.current_query
                        index_name = os.getenv("TXT_SEARCH_INDEX", "txt_files_index")
                        
                        retrieval_result = self.agent_client.retrieve(
                            query=query,
                            index_name=index_name,
                            top=5
                        )
                        
                        retrieval_results = retrieval_result.model_dump()
                        return json.dumps(retrieval_results)
                    else:
                        return json.dumps({"error": "No query provided"})
                except Exception as e:
                    return json.dumps({"error": f"Retrieval failed: {str(e)}"})
            
            # Set up function tool
            function_tool = FunctionTool({ agentic_retrieval })
            self.toolset = ToolSet()
            self.toolset.add(function_tool)
            self.project_client.agents.enable_auto_function_calls(self.toolset)
            
            # Agent instructions
            instructions = """
            A Q&A agent specializing in Earth at night topics including:
            - Nighttime satellite imagery and observations
            - Urban lighting patterns and light pollution
            - Nocturnal ecosystems and wildlife
            - Disaster monitoring using night imagery
            - Human activity patterns visible from space
            - Climate monitoring and urban heat island effects
            - Bioluminescence in marine environments
            
            Sources are text documents that have been processed into chunks. Each source has an 'id' field that must be cited in your answer using the format [id].
            When referencing information, always cite the source using the document ID.
            If you do not have the answer in the provided sources, respond with "I don't know".
            
            Be comprehensive in your answers and cite multiple relevant sources when available.
            """
            
            # Create agent
            self.agent = self.project_client.agents.create_agent(
                model=os.getenv("AZURE_OPENAI_GPT_DEPLOYMENT", "gpt-4o"),
                name="Earth at Night AI Assistant",
                instructions=instructions,
                toolset=self.toolset
            )
            
            # Create conversation thread
            self.thread = self.project_client.agents.threads.create()
            
            self.connection_status = "Connected"
            return True
            
        except Exception as e:
            self.connection_status = f"Error: {str(e)}"
            return False
    
    def ask_question(self, question):
        """Send a question to the agent and get response"""
        try:
            if not self.agent or not self.thread:
                return "Error: Agent not initialized. Please check connection."
            
            # Store current query for retrieval function
            st.session_state.current_query = question
            
            # Send message
            message = self.project_client.agents.messages.create(
                thread_id=self.thread.id,
                role="user",
                content=question
            )
            
            # Run the agent
            run = self.project_client.agents.runs.create_and_process(
                thread_id=self.thread.id,
                agent_id=self.agent.id,
                tool_choice=AgentsNamedToolChoice(
                    type=AgentsNamedToolChoiceType.FUNCTION, 
                    function=FunctionName(name="agentic_retrieval")
                ),
                toolset=self.toolset
            )
            
            if run.status == "failed":
                return f"❌ Failed: {run.last_error}"
            else:
                response = self.project_client.agents.messages.get_last_message_text_by_role(
                    thread_id=self.thread.id, 
                    role="assistant"
                ).text.value
                return response
                
        except Exception as e:
            return f"Error: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"

# Initialize session state
if 'agent' not in st.session_state:
    st.session_state.agent = EarthNightAgent()
    st.session_state.chat_history = []
    st.session_state.initialized = False

# Main UI
def main():
    # Header
    st.markdown('<h1 class="main-header">🌍 Earth at Night AI Assistant</h1>', unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.header("🔧 System Status")
        
        # Connection status
        if st.session_state.agent.connection_status == "Connected":
            status_class = "status-connected"
            status_text = "🟢 Connected"
        else:
            status_class = "status-disconnected"
            status_text = f"🔴 {st.session_state.agent.connection_status}"
        
        st.markdown(f'<div class="sidebar-info"><span class="status-indicator {status_class}"></span>{status_text}</div>', 
                   unsafe_allow_html=True)
        
        # Initialize button
        if st.button("🚀 Initialize Agent", use_container_width=True):
            with st.spinner("Initializing connections..."):
                success = st.session_state.agent.initialize_connections()
                if success:
                    st.session_state.initialized = True
                    st.success("✅ Agent initialized successfully!")
                    st.rerun()
                else:
                    st.error("❌ Failed to initialize agent")
        
        # Configuration info
        if st.session_state.initialized:
            st.header("📊 Configuration")
            config_info = f"""
            **Search Index:** {os.getenv('TXT_SEARCH_INDEX', 'txt_files_index')}
            **Agent Name:** {os.getenv('TXT_SEARCH_AGENT_NAME', 'txt-files-agent')}
            **GPT Model:** {os.getenv('AZURE_OPENAI_GPT_DEPLOYMENT', 'gpt-4o')}
            **Container:** {os.getenv('TXT_STORAGE_CONTAINER_NAME', 'earthdata')}
            """
            st.markdown(f'<div class="sidebar-info">{config_info}</div>', unsafe_allow_html=True)
        
        # Sample questions
        st.header("💡 Sample Questions")
        sample_questions = [
            "What is bioluminescence and how does it help marine life?",
            "How does night imagery support disaster response?",
            "What causes the urban heat island effect?",
            "How do city lights reveal urban development patterns?",
            "What can satellite imagery tell us about North vs South Korea?"
        ]
        
        for i, question in enumerate(sample_questions):
            if st.button(f"Q{i+1}: {question[:30]}...", key=f"sample_{i}", use_container_width=True):
                if st.session_state.initialized:
                    st.session_state.pending_question = question
                else:
                    st.warning("Please initialize the agent first!")
        
        # Clear chat button
        if st.button("🗑️ Clear Chat History", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()
    
    # Main chat interface
    if not st.session_state.initialized:
        st.info("👈 Please initialize the agent using the sidebar to start chatting!")
        st.markdown("""
        ### 🌟 About this Assistant
        
        This AI assistant specializes in answering questions about **Earth at Night** based on processed text documents covering:
        
        - 🛰️ **Satellite Imagery**: Nighttime observations from space
        - 🏙️ **Urban Lighting**: City development and infrastructure patterns  
        - 🦉 **Nocturnal Ecosystems**: Wildlife behavior and bioluminescence
        - 🚨 **Disaster Monitoring**: Emergency response using night imagery
        - 🌡️ **Climate Science**: Urban heat islands and environmental monitoring
        
        **Features:**
        - ✅ Retrieval Augmented Generation (RAG) with source citations
        - ✅ Real-time search across indexed text documents
        - ✅ Conversation history and context awareness
        - ✅ Error handling and fallback responses
        """)
    else:
        # Chat input
        user_input = st.chat_input("Ask me anything about Earth at night...")
        
        # Handle pending question from sample buttons
        if hasattr(st.session_state, 'pending_question'):
            user_input = st.session_state.pending_question
            del st.session_state.pending_question
        
        # Process user input
        if user_input:
            # Add user message to history
            st.session_state.chat_history.append({
                "role": "user",
                "content": user_input,
                "timestamp": datetime.now().strftime("%H:%M:%S")
            })
            
            # Get AI response
            with st.spinner("🤔 Thinking..."):
                response = st.session_state.agent.ask_question(user_input)
            
            # Add assistant response to history
            st.session_state.chat_history.append({
                "role": "assistant", 
                "content": response,
                "timestamp": datetime.now().strftime("%H:%M:%S")
            })
        
        # Display chat history
        for message in st.session_state.chat_history:
            if message["role"] == "user":
                st.markdown(f"""
                <div class="chat-message user-message">
                    <strong>🧑 You ({message['timestamp']}):</strong><br>
                    {message['content']}
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="chat-message assistant-message">
                    <strong>🤖 AI Assistant ({message['timestamp']}):</strong><br>
                    {message['content']}
                </div>
                """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
