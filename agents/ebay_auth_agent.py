# ebay_agent_app/agents/ebay_auth_agent.py
from langchain.agents import initialize_agent, AgentType
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_ollama import OllamaLLM
from config import OLLAMA_BASE_URL, LLM_MODEL

llm = OllamaLLM(base_url=OLLAMA_BASE_URL, model=LLM_MODEL)
search_tool = DuckDuckGoSearchRun(
    description=
    "Useful for searching for information specifically related to eBay policies, products, and help topics. Input should be a search query related to eBay."
)
tools = [search_tool]

prompt_prefix = """You are an expert eBay assistant for authenticated users. Your ONLY function is to answer questions directly related to the eBay platform, its policies, products listed on eBay, user account details, and how to use eBay features.

If a user asks a question that is ABSOLUTELY NOT related to eBay, you MUST respond with a clear and concise refusal, such as: "I can only answer questions about eBay." or "Sorry, I can only help with eBay-related inquiries." Do not attempt to answer non-eBay questions, and do not provide any information outside of the eBay domain.

You have access to the following tool:

{tool_names}

Use this tool ONLY when the user's query is clearly about eBay.

Now, answer the following question:"""


def create_ebay_auth_agent():
    agent = initialize_agent(
        llm=llm,
        tools=tools,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        verbose=True,
        prefix=prompt_prefix,
        handle_parsing_errors=
        "Check your output and ensure it conforms to the schema: ```json\n{\n    \"action\": \"tool_name\",\n    \"action_input\": \"tool_input\"\n}\n``` or respond directly to the user.",
        max_iterations=10  # Increase this value significantly
    )
    return agent
