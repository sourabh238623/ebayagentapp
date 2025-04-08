# ebay_agent_app/agents/auth_agent.py
from langchain.agents import initialize_agent, AgentType
from langchain_ollama import OllamaLLM
from config import OLLAMA_BASE_URL, LLM_MODEL

llm = OllamaLLM(base_url=OLLAMA_BASE_URL, model=LLM_MODEL)

prompt_prefix = """You are an authentication agent. Your task is to authenticate users based on their phone number and zip code.
- If the user provides a phone number and zip code together, check if this combination exists in our user data. If it does, respond with a success message indicating they are now authenticated and can ask eBay-related questions.
- If the user provides only a phone number, ask for their zip code to complete authentication.
- If the user provides only a zip code, ask for their phone number.
- If the provided information does not match our records, inform them that authentication failed.

User data format: Phone-Zip as the key.

Respond to the following authentication attempt:"""


def create_auth_agent():
    agent = initialize_agent(
        llm=llm,
        tools=[],  # Authentication agent doesn't need tools
        agent=AgentType.CONVERSATIONAL_REACT_DESCRIPTION,
        verbose=True,
        prefix=prompt_prefix,
        handle_parsing_errors=
        "Respond directly with the authentication status or the request for missing information.",
        max_iterations=5  # Reduced max_iterations for auth agent
    )
    return agent
