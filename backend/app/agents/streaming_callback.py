"""
Custom Async Callback Handler for LangChain to stream agentic intermediate steps.
"""
from typing import Any, Dict, List, Optional, Union
from uuid import UUID
import json
from langchain.callbacks.base import AsyncCallbackHandler
from langchain.schema import AgentAction, AgentFinish, LLMResult

class StreamingCallbackHandler(AsyncCallbackHandler):
    """
    Async callback handler that streams intermediate steps of a LangChain agent.
    """

    def __init__(self, queue):
        self.queue = queue

    async def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        """Run when LLM starts."""
        pass

    async def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        """Run on new LLM token. Only available when streaming is enabled."""
        await self.queue.put(json.dumps({"type": "token", "content": token}))

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Run when LLM ends."""
        pass

    async def on_llm_error(
        self, error: Union[Exception, KeyboardInterrupt], **kwargs: Any
    ) -> None:
        """Run when LLM errors."""
        await self.queue.put(json.dumps({"type": "error", "content": str(error)}))

    async def on_chain_start(
        self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs: Any
    ) -> None:
        """Run when chain starts."""
        pass

    async def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> None:
        """Run when chain ends."""
        pass

    async def on_chain_error(
        self, error: Union[Exception, KeyboardInterrupt], **kwargs: Any
    ) -> None:
        """Run when chain errors."""
        await self.queue.put(json.dumps({"type": "error", "content": str(error)}))

    async def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        """Run when tool starts."""
        tool_name = serialized.get("name", "Unknown Tool")
        await self.queue.put(json.dumps({"type": "tool_start", "tool_name": tool_name, "input": input_str}))

    async def on_tool_end(self, output: str, **kwargs: Any) -> None:
        """Run when tool ends."""
        await self.queue.put(json.dumps({"type": "tool_end", "output": output}))

    async def on_tool_error(
        self, error: Union[Exception, KeyboardInterrupt], **kwargs: Any
    ) -> None:
        """Run when tool errors."""
        await self.queue.put(json.dumps({"type": "error", "content": str(error)}))

    async def on_agent_action(self, action: AgentAction, **kwargs: Any) -> None:
        """Run on agent action."""
        await self.queue.put(json.dumps({"type": "agent_action", "action": {"tool": action.tool, "tool_input": action.tool_input, "log": action.log}}))


    async def on_agent_finish(self, finish: AgentFinish, **kwargs: Any) -> None:
        """Run on agent finish."""
        await self.queue.put(json.dumps({"type": "agent_finish", "finish": {"return_values": finish.return_values, "log": finish.log}}))
