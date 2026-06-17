from __future__ import annotations

from .agent import Agent
from .storage import TranscriptStore


def run_session_command(agent: Agent, store: TranscriptStore, prompt: str) -> None:
    parts = prompt.split()
    if len(parts) == 1 or parts[1] == "current":
        print(f"session: {agent.state.session_id}")
        print(f"messages: {len(agent.state.messages)}")
        print(f"planning_status: {agent.state.planning_status}")
        return
    if parts[1] == "save":
        store.save_state(agent.state)
        print(f"session state saved: {agent.state.session_id}")
        return
    if parts[1] == "load":
        if len(parts) < 3:
            print("Usage: /session load ID")
            return
        previous_session_id = agent.state.session_id
        session_id = parts[2]
        agent.load_session(session_id)
        print(f"session switched: {previous_session_id} -> {agent.state.session_id}")
        print(f"messages: {len(agent.state.messages)}")
        print(f"planning_status: {agent.state.planning_status}")
        return
    print("Usage: /session current | /session save | /session load ID")
