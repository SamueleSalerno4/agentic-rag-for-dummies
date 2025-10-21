# app.py
"""
Main application that launches the Gradio user interface
to chat with the RAG agent.

Run with: python app.py
"""

import gradio as gr
from langchain_core.messages import HumanMessage

# Import the compiled agent graph
from agent import agent_graph
# Import the directory initializer
from components import initialize_directories

def chat_with_agent(message, history):
    """
    Process the user message through the agent graph.
    
    Args:
        message: The user's question
        history: Chat history (currently unused by the stateless
                 agent logic, but required by Gradio)
    
    Returns:
        The agent's response as a string
    """
    print(f"\n--- New User Query --- \nQuery: {message}\n")
    try:
        # Invoke the graph with the current state (just the new message)
        # For a stateful chat, you would pass the entire 'history'
        result = agent_graph.invoke({
            "messages": [HumanMessage(content=message)]
        })
        
        # The last message in the list is the agent's response
        response = result["messages"][-1].content
        print(f"\n--- Final Agent Response --- \nResponse: {response}\n")
        return response
        
    except Exception as e:
        print(f"❌ Error during graph execution: {e}")
        return f"❌ Error: {str(e)}\n\nPlease try rephrasing your question."

def main():
    """Main function to initialize and launch the app."""
    
    # Ensure 'docs' and 'parent_store' directories exist
    initialize_directories()
    
    # Create and launch the interface
    demo = gr.ChatInterface(
        fn=chat_with_agent,
        title="🤖 Agentic RAG Assistant",
        description="Ask questions about your documents. The agent will intelligently retrieve and combine information."
    )

    print("\n🚀 Launching chat interface...")
    print("Access the interface at: http://127.0.0.1:7860 (or the URL provided by Gradio)")
    demo.launch(share=False)

if __name__ == "__main__":
    main()