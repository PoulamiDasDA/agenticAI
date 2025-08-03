import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="Earth at Night Analytics Dashboard",
    page_icon="📊",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin: 0.5rem 0;
    }
    
    .metric-value {
        font-size: 2rem;
        font-weight: bold;
    }
    
    .metric-label {
        font-size: 0.9rem;
        opacity: 0.8;
    }
    
    .dashboard-header {
        text-align: center;
        padding: 2rem 0;
        background: linear-gradient(90deg, #1e3c72, #2a5298);
        color: white;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
</style>
""", unsafe_allow_html=True)

def load_sample_data():
    """Generate sample data for demonstration"""
    # Sample query data
    queries = [
        {"query": "What is bioluminescence?", "timestamp": datetime.now() - timedelta(hours=2), "response_time": 1.2},
        {"query": "Urban heat island effect", "timestamp": datetime.now() - timedelta(hours=1), "response_time": 0.8},
        {"query": "Disaster monitoring satellite", "timestamp": datetime.now() - timedelta(minutes=30), "response_time": 1.5},
        {"query": "City lights from space", "timestamp": datetime.now() - timedelta(minutes=15), "response_time": 0.9},
        {"query": "Nocturnal ecosystems", "timestamp": datetime.now() - timedelta(minutes=5), "response_time": 1.1},
    ]
    
    # Sample topic distribution
    topics = {
        "Urban Lighting": 35,
        "Nocturnal Ecosystems": 25,
        "Disaster Monitoring": 20,
        "Climate Science": 15,
        "Space Observations": 5
    }
    
    # Sample performance metrics
    metrics = {
        "total_queries": 127,
        "avg_response_time": 1.1,
        "success_rate": 95.2,
        "active_sessions": 8
    }
    
    return queries, topics, metrics

def main():
    # Header
    st.markdown("""
    <div class="dashboard-header">
        <h1>📊 Earth at Night Analytics Dashboard</h1>
        <p>Monitor your AI assistant's performance and usage patterns</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Load sample data
    queries, topics, metrics = load_sample_data()
    
    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{metrics['total_queries']}</div>
            <div class="metric-label">Total Queries</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{metrics['avg_response_time']:.1f}s</div>
            <div class="metric-label">Avg Response Time</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{metrics['success_rate']:.1f}%</div>
            <div class="metric-label">Success Rate</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{metrics['active_sessions']}</div>
            <div class="metric-label">Active Sessions</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Charts row
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 Query Activity Over Time")
        
        # Convert queries to DataFrame
        df_queries = pd.DataFrame(queries)
        df_queries['hour'] = df_queries['timestamp'].dt.hour
        
        # Group by hour and count
        hourly_counts = df_queries.groupby('hour').size().reset_index(name='count')
        
        fig_line = px.line(
            hourly_counts, 
            x='hour', 
            y='count',
            title="Queries per Hour",
            markers=True
        )
        fig_line.update_layout(
            xaxis_title="Hour of Day",
            yaxis_title="Number of Queries",
            showlegend=False
        )
        st.plotly_chart(fig_line, use_container_width=True)
    
    with col2:
        st.subheader("🎯 Topic Distribution")
        
        # Create pie chart for topics
        fig_pie = px.pie(
            values=list(topics.values()),
            names=list(topics.keys()),
            title="Most Asked Topics"
        )
        fig_pie.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_pie, use_container_width=True)
    
    # Response time analysis
    st.subheader("⚡ Response Time Analysis")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Response time histogram
        fig_hist = px.histogram(
            df_queries,
            x='response_time',
            nbins=10,
            title="Response Time Distribution"
        )
        fig_hist.update_layout(
            xaxis_title="Response Time (seconds)",
            yaxis_title="Frequency"
        )
        st.plotly_chart(fig_hist, use_container_width=True)
    
    with col2:
        # Response time vs query length (simulated)
        df_queries['query_length'] = df_queries['query'].str.len()
        
        fig_scatter = px.scatter(
            df_queries,
            x='query_length',
            y='response_time',
            title="Response Time vs Query Length",
            hover_data=['query']
        )
        fig_scatter.update_layout(
            xaxis_title="Query Length (characters)",
            yaxis_title="Response Time (seconds)"
        )
        st.plotly_chart(fig_scatter, use_container_width=True)
    
    # Recent queries table
    st.subheader("📋 Recent Queries")
    
    # Format recent queries for display
    recent_df = df_queries.copy()
    recent_df['timestamp'] = recent_df['timestamp'].dt.strftime('%H:%M:%S')
    recent_df = recent_df[['timestamp', 'query', 'response_time']].sort_values('timestamp', ascending=False)
    recent_df.columns = ['Time', 'Query', 'Response Time (s)']
    
    st.dataframe(recent_df, use_container_width=True)
    
    # System status
    st.subheader("🔧 System Status")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.info("🟢 **Azure Search**: Connected")
        st.write(f"Endpoint: {os.getenv('AZURE_SEARCH_ENDPOINT', 'Not configured')}")
    
    with col2:
        st.info("🟢 **Azure OpenAI**: Connected") 
        st.write(f"Model: {os.getenv('AZURE_OPENAI_GPT_DEPLOYMENT', 'Not configured')}")
    
    with col3:
        st.info("🟢 **Storage Account**: Connected")
        st.write(f"Container: {os.getenv('TXT_STORAGE_CONTAINER_NAME', 'Not configured')}")
    
    # Configuration details
    with st.expander("🔍 View Configuration Details"):
        config_data = {
            "Search Index": os.getenv('TXT_SEARCH_INDEX', 'Not set'),
            "Agent Name": os.getenv('TXT_SEARCH_AGENT_NAME', 'Not set'),
            "Storage Container": os.getenv('TXT_STORAGE_CONTAINER_NAME', 'Not set'),
            "GPT Deployment": os.getenv('AZURE_OPENAI_GPT_DEPLOYMENT', 'Not set'),
            "Embedding Model": os.getenv('AZURE_OPENAI_EMBEDDING_DEPLOYMENT', 'Not set'),
        }
        
        for key, value in config_data.items():
            st.write(f"**{key}**: `{value}`")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #666; padding: 1rem;">
        🌍 Earth at Night AI Assistant Analytics Dashboard<br>
        <small>Monitor performance, track usage, and optimize your AI system</small>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
