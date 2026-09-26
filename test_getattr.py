def __getattr__(name):
    if name == "my_agent":
        print("Instantiating my_agent")
        return "AgentInstance"
    raise AttributeError(f"module {__name__} has no attribute {name}")
