"""
Real OpenHands adapter for HarnessLens.

Wraps the OpenHands SDK to run real agents against real SWE-bench tasks.
Success is determined by the SWE-bench harness (test suite execution),
not by this adapter. This adapter's job is to:

1. Set up an OpenHands agent with a real LLM
2. Run it against a real workspace
3. Extract the git patch it produces
4. Extract real token and cost metrics
5. Return the patch and trace events
"""

import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from openhands.sdk import LLM, Agent, Conversation, Tool
from openhands.tools.terminal import TerminalTool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.task_tracker import TaskTrackerTool

from app.schema import TraceEvent, EventType


class OpenHandsAdapter:
    """
    Wraps the OpenHands SDK for real SWE-bench task execution.

    Unlike DummyHarness, this adapter:
    - Calls a real LLM (requires OPENAI_API_KEY or LLM_API_KEY in .env)
    - Executes real code in a real git repository
    - Returns an actual git diff patch
    - Reports real token usage and cost from the LLM metrics
    """

    def __init__(
        self,
        model: str = "gpt-5",
        harness_id: str = "openhands-gpt5",
        workspace_dir: str = "./workspace",
    ):
        self.harness_id = harness_id
        self.workspace_dir = Path(workspace_dir).resolve()

        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
        if not api_key:
            raise ValueError(
                "No API key found. Set OPENAI_API_KEY or LLM_API_KEY in .env"
            )

        self.llm = LLM(
            model=model,
            api_key=api_key,
            usage_id="harnesslens",
        )

        self.agent = Agent(
            llm=self.llm,
            tools=[
                Tool(name=TerminalTool.name),
                Tool(name=FileEditorTool.name),
                Tool(name=TaskTrackerTool.name),
            ],
        )

    def run(self, task: str, instance_id: str) -> tuple[list[TraceEvent], str]:
        """
        Execute a task. Returns (events, git_patch).
        """
        run_id = f"oh-{uuid.uuid4().hex[:8]}"
        events: list[TraceEvent] = []
        cumulative_cost = 0.0
        input_tokens = 0
        output_tokens = 0
        step = 0

        events.append(TraceEvent(
            run_id=run_id,
            harness_id=self.harness_id,
            event_index=0,
            turn_index=0,
            loop_step=0,
            last_tool_called=None,
            event_type=EventType.RUN_STARTED,
            budget_consumed_cents=0.0,
            metadata={"instance_id": instance_id},
        ))

        try:
            conversation = Conversation(
                agent=self.agent,
                workspace=str(self.workspace_dir),
            )
            conversation.send_message(task)
            conversation.run()

            # --- Extract real metrics from the LLM object ---
            metrics = getattr(self.llm, "metrics", None)
            if metrics is not None:
                usage = getattr(metrics, "accumulated_token_usage", None)
                cost = getattr(metrics, "accumulated_cost", None)

                if usage is not None:
                    # usage may be a dict or an object with attributes
                    if isinstance(usage, dict):
                        input_tokens = usage.get("prompt_tokens", 0) or 0
                        output_tokens = usage.get("completion_tokens", 0) or 0
                    else:
                        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
                        output_tokens = getattr(usage, "completion_tokens", 0) or 0

                if cost is not None:
                    cumulative_cost = float(cost) * 100  # USD -> cents

                step = 1
                events.append(TraceEvent(
                    run_id=run_id,
                    harness_id=self.harness_id,
                    event_index=1,
                    turn_index=1,
                    loop_step=1,
                    last_tool_called="llm_call",
                    event_type=EventType.TOOL_CALLED,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_cents=cumulative_cost,
                    budget_consumed_cents=cumulative_cost,
                ))

            # --- Capture the git patch ---
            git_patch = self._capture_git_diff()

            events.append(TraceEvent(
                run_id=run_id,
                harness_id=self.harness_id,
                event_index=step + 1,
                turn_index=step,
                loop_step=step,
                last_tool_called=None,
                event_type=EventType.RUN_COMPLETED,
                budget_consumed_cents=cumulative_cost,
                metadata={"patch_length": len(git_patch)},
            ))

            return events, git_patch

        except Exception as e:
            events.append(TraceEvent(
                run_id=run_id,
                harness_id=self.harness_id,
                event_index=step + 1,
                turn_index=step,
                loop_step=step,
                last_tool_called=None,
                event_type=EventType.RUN_FAILED,
                budget_consumed_cents=cumulative_cost,
                error=str(e),
            ))
            return events, ""

    def _capture_git_diff(self) -> str:
        """Run `git diff HEAD` in the workspace and return the output."""
        try:
            result = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=str(self.workspace_dir),
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.stdout
        except Exception:
            return ""