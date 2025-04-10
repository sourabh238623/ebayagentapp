from flask import Flask, request, jsonify
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_ollama import OllamaLLM
from langchain.agents import initialize_agent, AgentType
import os
import re
import logging
import json

logging.basicConfig(level=logging.DEBUG)

OLLAMA_BASE_URL = os.environ.get(
    "OLLAMA_BASE_URL", "https://0ba6-216-113-160-105.ngrok-free.app")
LLM_MODEL = os.environ.get("LLM_MODEL", "mistral")
llm = OllamaLLM(base_url=OLLAMA_BASE_URL, model=LLM_MODEL)

USER_DATA = {
    "1234567890-98109": {
        "authenticated": True
    },
    "9876543210-12345": {
        "authenticated": True
    },
    "8473236970-98012": {
        "authenticated": True
    }
}

search_tool = DuckDuckGoSearchRun(
    description=
    "Useful for searching for information specifically related to eBay policies, products, and help topics. Input should be a search query related to eBay."
)
tools = [search_tool]

ebay_guest_prompt_prefix = """Your primary function is to answer questions ONLY about eBay. Your answer should be based on the information provided by the search tool. Your answer should be short, up to 5 lines.
If a user asks a question that is NOT related to eBay, you MUST reply "Sorry, I didn't get that, please ask me anything about eBay."
You have access to the following tool:
{tool_names}
Use this tool ONLY when the user's query is clearly about eBay.
Now, answer the following question:"""

ebay_auth_prompt_prefix = """You are a helpful eBay assistant for authenticated users. You can answer detailed questions about eBay, including account-specific information and actions.
You have access to the following tool to search for eBay-related information:
{tool_names}
Use this tool to answer the user's query. Be detailed and helpful.
Now, answer the following question:"""


def create_ebay_guest_agent():
    agent = initialize_agent(
        llm=llm,
        tools=tools,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        verbose=True,
        prefix=ebay_guest_prompt_prefix,
        handle_parsing_errors=
        "Check your output and ensure it conforms to the schema.")
    return agent


def create_ebay_auth_agent():
    agent = initialize_agent(
        llm=llm,
        tools=tools,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        verbose=True,
        prefix=ebay_auth_prompt_prefix,
        handle_parsing_errors=
        "Check your output and ensure it conforms to the schema.",
        max_iterations=10)
    return agent


app = Flask(__name__)
user_auth_state = {}


def extract_phone_number(text):
    # Remove all non-digit characters
    digits = re.sub(r'\D', '', text)

    # Ensure we have exactly 10 digits (standard phone number length)
    match = re.fullmatch(r'\d{10}', digits)

    return match.group(0) if match else None


def extract_zip_code(text):
    match = re.search(r'\b\d{5}\b', text)
    return match.group(0) if match else None


negative_response_patterns = re.compile(
    r"(don'?t have|doesn'?t match|not it|wrong (number|zip)|can'?t provide|i'm unable to)",
    re.IGNORECASE)


@app.route("/ask", methods=["POST"])
def ask_agent():
    data = request.get_json()
    if not data or "query" not in data or "session_id" not in data:
        return jsonify(
            {"error": "Missing 'query' or 'session_id' in request body"}), 400

    query = data["query"]
    session_id = data["session_id"]
    auth_state = user_auth_state.get(
        session_id, {
            "authenticated": False,
            "phone": None,
            "zip": None,
            "awaiting": None,
            "started": False
        })
    user_auth_state[session_id] = auth_state

    logging.debug(
        f"Session {session_id}: Received query: '{query}'. Current auth_state: {auth_state}"
    )

    if auth_state["authenticated"]:
        ebay_auth_agent = create_ebay_auth_agent()
        try:
            response = ebay_auth_agent.run(query)
            logging.debug(
                f"Session {session_id}: Authenticated response: {response}")
            return jsonify({
                "response": response,
                "authenticated": True,
                "agent": "eBay Authenticated Agent"
            })
        except Exception as e:
            logging.error(
                f"Session {session_id}: eBay Authenticated Agent Error: {e}")
            return jsonify(
                {"error": f"eBay Authenticated Agent Error: {str(e)}"}), 500
    else:
        if auth_state["awaiting"] == "phone":
            if negative_response_patterns.search(query):
                auth_state["awaiting"] = None
                return jsonify({
                    "response":
                    "No, Problem, Please tell me how can i help you. you can ask me any ebay related queries",
                    "authenticated": False,
                    "agent": "Authentication Agent"
                })
            phone = extract_phone_number(query)
            if phone:
                auth_state["phone"] = phone
                auth_state["awaiting"] = "zip"
                return jsonify({
                    "response": "Thank you. Please provide your zip code.",
                    "authenticated": False,
                    "agent": "Authentication Agent",
                    "needs": "zip"
                })
            else:
                return jsonify({
                    "response":
                    "That doesn't look like a phone number. Could you please provide me your phone number?",
                    "authenticated": False,
                    "agent": "Authentication Agent",
                    "needs": "phone"
                })
        elif auth_state["awaiting"] == "zip":
            if negative_response_patterns.search(query):
                auth_state["awaiting"] = None
                return jsonify({
                    "response":
                    "No, Problem, Please tell me how can i help you. you can ask me any ebay related queries.",
                    "authenticated": False,
                    "agent": "Authentication Agent"
                })
            zip_code = extract_zip_code(query)
            if zip_code:
                auth_state["zip"] = zip_code
                auth_state["awaiting"] = None
                if auth_state.get(
                        "phone"
                ) and f"{auth_state['phone']}-{zip_code}" in USER_DATA:
                    auth_state["authenticated"] = True
                    return jsonify({
                        "response":
                        "Thanks for being an ebay customer, Please let me know how can i help you.",
                        "authenticated": True,
                        "agent": "Authentication Agent"
                    })
                else:
                    auth_state["phone"] = None
                    auth_state["zip"] = None
                    auth_state["started"] = True
                    return jsonify({
                        "response": "Authentication failed.",
                        "authenticated": False,
                        "agent": "Authentication Agent",
                        "needs": "phone"
                    })
            else:
                return jsonify({
                    "response":
                    "That doesn't look like a zip code. Please provide it.",
                    "authenticated": False,
                    "agent": "Authentication Agent",
                    "needs": "zip"
                })
        else:
            # Initial check for phone or zip
            phone = extract_phone_number(query)
            zip_code = extract_zip_code(query)

            if phone and zip_code:
                auth_state["phone"] = phone
                auth_state["zip"] = zip_code
                if f"{phone}-{zip_code}" in USER_DATA:
                    auth_state["authenticated"] = True
                    return jsonify({
                        "response":
                        "Authentication successful. Ask your eBay question.",
                        "authenticated": True,
                        "agent": "Authentication Agent"
                    })
                else:
                    auth_state["started"] = True
                    return jsonify({
                        "response": "Authentication failed.",
                        "authenticated": False,
                        "agent": "Authentication Agent",
                        "needs": "phone"
                    })
            elif phone:
                auth_state["started"] = True
                auth_state["awaiting"] = "zip"
                auth_state["phone"] = phone
                return jsonify({
                    "response": "Thank you. Please provide your zip code.",
                    "authenticated": False,
                    "agent": "Authentication Agent",
                    "needs": "zip"
                })
            elif zip_code:
                auth_state["started"] = True
                auth_state["awaiting"] = "phone"
                auth_state["zip"] = zip_code
                return jsonify({
                    "response": "Thank you. Please provide your phone number.",
                    "authenticated": False,
                    "agent": "Authentication Agent",
                    "needs": "phone"
                })
            else:
                # If no auth info, treat as a guest query initially
                ebay_guest_agent = create_ebay_guest_agent()
                try:
                    response = ebay_guest_agent.run(query)
                    return jsonify({
                        "response": response,
                        "authenticated": False,
                        "agent": "eBay Guest Agent"
                    })
                except Exception as e:
                    logging.error(
                        f"Session {session_id}: eBay Guest Agent Error: {e}")
                    return jsonify(
                        {"error": f"eBay Guest Agent Error: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
