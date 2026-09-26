import asyncio
from google.adk.agents import LlmAgent

agent = LlmAgent(name="test", model="gemini-3.5-flash", instruction="hello", tools=[])
print("Instantiated agent with string model")
