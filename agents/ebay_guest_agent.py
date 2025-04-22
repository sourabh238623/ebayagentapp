from langchain.agents import initialize_agent, AgentType
from langchain_groq import ChatGroq
from tools.search_tool import search_tool
from prompts.ebay_prompts import ebay_guest_prompt_prefix
from config import GROQ_API_KEY

model = ChatGroq(model="Gemma2-9b-It", groq_api_key=GROQ_API_KEY)
tools = [search_tool]


def create_ebay_guest_agent():
    agent = initialize_agent(
        llm=model,
        tools=tools,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        verbose=True,
        agent_kwargs={"prefix": ebay_guest_prompt_prefix},
        handle_parsing_errors=(
            "Check your output and ensure it conforms to the schema: ```json\n"
            "{\n"
            '    "action": "tool_name",\n'
            '    "action_input": "tool_input"\n'
            "}\n"
            "``` or respond directly to the user."),
    )
    return agent
