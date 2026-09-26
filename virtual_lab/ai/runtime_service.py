import asyncio
import threading
from google.adk.sessions import InMemorySessionService
from virtual_lab.ai.vertex_agents import create_virtual_lab_runner

class AgentRuntimeService:
    def __init__(self):
        self.session_svc = InMemorySessionService()
        # Biology and other workspaces must open before Vertex is configured.
        # Build and cache the runner only when the first research request starts.
        self._runner = None
        
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="AgentRuntimeLoop")
        self.thread.start()

    @property
    def runner(self):
        if self._runner is None:
            self._runner = create_virtual_lab_runner(self.session_svc)
        return self._runner

    def reset_runner(self):
        """Called by settings only while no research request is running."""
        self._runner = None
        
    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run_coroutine(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)
        
    def shutdown(self):
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5.0)

    async def get_or_create_session(self, experiment_id: str, user_id: str = "local_operator"):
        # Create experiment-scoped sessions
        # First, try to list sessions for this user.
        sessions = await self.session_svc.list_sessions(app_name="virtual_lab", user_id=user_id)
        for s in sessions.sessions:
            if s.state.get("experiment_id") == experiment_id:
                return s
                
        # If not found, create a new one.
        session = await self.session_svc.create_session(
            app_name="virtual_lab", user_id=user_id, state={"experiment_id": experiment_id}
        )
        return session
