"""
AgentMem Python SDK.

Three clients, same API surface:

    AgentMemClient        — synchronous HTTP client (scripts, CLIs)
    AsyncAgentMemClient   — async HTTP client (FastAPI, async frameworks)
    LocalAgentMemClient   — zero-setup local SQLite mode (prototyping, CI)

Convenience methods on all clients::

    client.add(agent_id, content, event_time, metadata=...)
    client.add_from_messages(agent_id, messages=[{"role": "assistant", "content": "..."}])
    client.recall(agent_id, query, k=5)
    client.recall_at(agent_id, query, as_of=datetime(...))   # point-in-time / compliance
    client.snapshot(agent_id, as_of=datetime(...))           # full knowledge state at T
    client.backtest_check(agent_id, simulation_as_of=...)    # lookahead-bias detection
    client.erase(subject_id, request_ref)                    # GDPR crypto-shred

Framework integrations (optional extras)::

    # LangChain (chat history + StructuredTools)
    from agentmem_sdk.langchain_integration import AgentMemChatHistory, build_tools

    # LangGraph (node factory functions)
    from agentmem_sdk.langgraph_integration import create_recall_node, create_remember_node

    # CrewAI (BaseTool wrappers)
    from agentmem_sdk.crewai_integration import build_crewai_tools

    # OpenAI Agents SDK (FunctionTool wrappers)
    from agentmem_sdk.openai_agents_integration import build_openai_agent_tools

    # AutoGen v0.4 (FunctionTool) / v0.2 (ConversableAgent)
    from agentmem_sdk.autogen_integration import build_autogen_tools, build_autogen_functions

Install with extras::

    pip install agentmem-sdk[langchain]       # LangChain chat history + tools
    pip install agentmem-sdk[langgraph]       # LangGraph node factories
    pip install agentmem-sdk[crewai]          # CrewAI BaseTool wrappers
    pip install agentmem-sdk[openai-agents]   # OpenAI Agents SDK FunctionTools
    pip install agentmem-sdk[autogen]         # AutoGen v0.4 FunctionTools
    pip install agentmem-sdk[local]           # LocalAgentMemClient (SQLite)
    pip install agentmem-sdk[all]             # Everything
"""
from .sync_client import AgentMemClient
from .client import AsyncAgentMemClient
from .local_client import LocalAgentMemClient

__all__ = [
    "AgentMemClient",
    "AsyncAgentMemClient",
    "LocalAgentMemClient",
]
