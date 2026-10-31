"""Managed desktop runtime. SDKs live exclusively in ephemeral provider workers."""
class ManagedAssistantRuntime:
    managed = True
    def __init__(self, settings):
        self.settings = settings
    def reset_runner(self):
        if self.settings.busy:
            raise RuntimeError('Cancel active work before reconfiguration')
    def shutdown(self):
        self.settings.cancel()
