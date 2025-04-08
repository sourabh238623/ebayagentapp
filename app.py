from flask import Flask, request, jsonify
from langchain.agents import initialize_agent, AgentType
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_ollama import OllamaLLM
import os
import re
import logging

logging.basicConfig(level=logging.DEBUG)

# Ensure your Ollama base URL is accessible
OLLAMA_BASE_URL = os.environ.get(
    "OLLAMA_BASE_URL", "https://9759-216-113-160-105.ngrok-free.app")
LLM_MODEL = os.environ.get("LLM_MODEL", "mistral")

llm = OllamaLLM(base_url=OLLAMA_BASE_URL, model=LLM_MODEL)
USER_DATA = {
    "1234567890-98109": {
        "authenticated": True
    },
    "9876543210-12345": {
        "authenticated": True
    }
}

search_tool = DuckDuckGoSearchRun(
    description=
    "Useful for searching for information specifically related to eBay policies, products, and help topics. Input should be a search query related to eBay."
)
tools = [search_tool]

ebay_guest_prompt_prefix = """Your primary function is to answer questions ONLY about eBay. Your answer should be based on the information provided by the search tool. your answer should be short upto 5 lines
If a user asks a question that is NOT related to eBay, you MUST reply sorry i didn't get, please ask me anything about ebay.
You have access to the following tool:
{tool_names}
Use this tool ONLY when the user's query is clearly about eBay.
Now, answer the following question:"""

ebay_auth_prompt_prefix = """You are a helpful eBay assistant for authenticated users. You can answer detailed questions about eBay, including account-specific information and actions.
You have access to the following tool to search for eBay-related information:
{tool_names}
Use this tool to answer the user's query.
Now, answer the following question:"""


def create_ebay_guest_agent():
    agent = initialize_agent(
        llm=llm,
        tools=tools,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        verbose=True,
        prefix=ebay_guest_prompt_prefix,
        handle_parsing_errors=
        "Check your output and ensure it conforms to the schema: ```json\n{\n    \"action\": \"tool_name\",\n    \"action_input\": \"tool_input\"\n}\n``` or respond directly to the user."
    )
    return agent


def create_ebay_auth_agent():
    agent = initialize_agent(
        llm=llm,
        tools=tools,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        verbose=True,
        prefix=ebay_auth_prompt_prefix,
        handle_parsing_errors=
        "Check your output and ensure it conforms to the schema: ```json\n{\n    \"action\": \"tool_name\",\n    \"action_input\": \"tool_input\"\n}\n``` or respond directly to the user.",
        max_iterations=10)
    return agent


app = Flask(__name__)
user_auth_state = {}  # In-memory state for tracking authentication attempts


def extract_phone_number(text):
    match = re.search(r'\b\d{10}\b', text)
    return match.group(0) if match else None


def extract_zip_code(text):
    match = re.search(r'\b\d{5}\b', text)
    return match.group(0) if match else None


def handle_authentication_failure(session_id):
    logging.debug(
        f"Session {session_id}: Authentication failed. Resetting state.")
    user_auth_state[session_id]["authenticated"] = False
    user_auth_state[session_id]["phone"] = None
    user_auth_state[session_id]["zip"] = None
    user_auth_state[session_id]["awaiting"] = None
    user_auth_state[session_id]["started"] = False  # Reset the started flag
    return jsonify({
        "response":
        "Authentication failed. I will now respond as a guest user.",
        "authenticated": False,
        "agent": "Authentication Agent",
        "needs_auth": True
    })


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
            "started": False,
            "initial_query_context": None
        })
    user_auth_state[session_id] = auth_state  # Ensure state is initialized
    negative_response_patterns = re.compile(
        r"(don'?t have|doesn'?t match|not it|wrong (number|zip)|can'?t provide|i'm unable to)",
        re.IGNORECASE)

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
        # Authentication flow for non-authenticated sessions
        if auth_state["awaiting"] == "phone":
            if negative_response_patterns.search(query):
                return handle_authentication_failure(session_id)
            phone = extract_phone_number(query)
            if phone:
                auth_state["phone"] = phone
                auth_state["awaiting"] = "zip"
                logging.debug(
                    f"Session {session_id}: Phone received. New auth_state: {auth_state}"
                )
                return jsonify({
                    "response":
                    "Thank you for your phone number. Please provide your zip code.",
                    "authenticated": False,
                    "agent": "Authentication Agent",
                    "needs": "zip"
                })
            else:
                return jsonify({
                    "response":
                    "That doesn't look like a valid phone number. Please provide it.",
                    "authenticated": False,
                    "agent": "Authentication Agent",
                    "needs": "phone"
                })
        elif auth_state["awaiting"] == "zip":
            if negative_response_patterns.search(query):
                return handle_authentication_failure(session_id)
            zip_code = extract_zip_code(query)
            if zip_code:
                auth_state["zip"] = zip_code
                auth_state["awaiting"] = None
                if auth_state[
                        "phone"] and f"{auth_state['phone']}-{auth_state['zip']}" in USER_DATA:
                    auth_state["authenticated"] = True
                    logging.debug(
                        f"Session {session_id}: Authentication successful. New auth_state: {auth_state}"
                    )
                    return jsonify({
                        "response":
                        "Authentication successful. You can now ask eBay-related questions.",
                        "authenticated": True,
                        "agent": "Authentication Agent"
                    })
                else:
                    return handle_authentication_failure(session_id)
            else:
                return jsonify({
                    "response":
                    "That doesn't look like a valid zip code. Please provide it.",
                    "authenticated": False,
                    "agent": "Authentication Agent",
                    "needs": "zip"
                })
        else:
            # Start of a new session (or if not already awaiting info)
            phone = extract_phone_number(query)
            zip_code = extract_zip_code(query)

            if phone and zip_code:
                auth_state["started"] = True
                auth_state["phone"] = phone
                auth_state["zip"] = zip_code
                if f"{auth_state['phone']}-{auth_state['zip']}" in USER_DATA:
                    auth_state["authenticated"] = True
                    logging.debug(
                        f"Session {session_id}: Authentication successful (initial). New auth_state: {auth_state}"
                    )
                    return jsonify({
                        "response":
                        "Authentication successful. You can now ask eBay-related questions.",
                        "authenticated": True,
                        "agent": "Authentication Agent"
                    })
                else:
                    return handle_authentication_failure(session_id)
            elif phone:
                auth_state["started"] = True
                auth_state["phone"] = phone
                auth_state["awaiting"] = "zip"
                logging.debug(
                    f"Session {session_id}: Phone received (initial). New auth_state: {auth_state}"
                )
                return jsonify({
                    "response":
                    "Thank you for your phone number. Please provide your zip code.",
                    "authenticated": False,
                    "agent": "Authentication Agent",
                    "needs": "zip"
                })
            elif zip_code:
                auth_state["started"] = True
                auth_state["zip"] = zip_code
                auth_state["awaiting"] = "phone"
                logging.debug(
                    f"Session {session_id}: Zip received (initial). New auth_state: {auth_state}"
                )
                return jsonify({
                    "response":
                    "Thank you for your zip code. Please provide your phone number.",
                    "authenticated": False,
                    "agent": "Authentication Agent",
                    "needs": "phone"
                })
            elif not auth_state["started"]:
                # First interaction in a new session, not phone or zip
                auth_state["started"] = True
                match = re.search(
                    r"(ebay selling policy|ebay buying policy|ebay return policy)",
                    query, re.IGNORECASE)
                if match:
                    auth_state["initial_query_context"] = match.group(1)
                else:
                    auth_state["initial_query_context"] = ' '.join(
                        query.split()[:4]) + ('...' if len(query.split()) > 4
                                              else '')

                logging.debug(
                    f"Session {session_id}: Initial non-auth query. New auth_state: {auth_state}"
                )
                return jsonify({
                    "response":
                    f"I understand you have a query about '{auth_state['initial_query_context']}'. To assist you further with eBay-related questions, please provide your phone number for authentication.",
                    "authenticated": False,
                    "agent": "eBay Guest Agent (Initial)",
                    "needs": "phone"
                })
            else:
                # If 'started' is True but still not authenticated and not awaiting,
                # and the input is not phone/zip, we should probably re-prompt for auth.
                logging.debug(
                    f"Session {session_id}: Started but not authenticated/awaiting. Reprompting for phone."
                )
                return jsonify({
                    "response":
                    "Please provide your phone number to begin authentication.",
                    "authenticated": False,
                    "agent": "Authentication Agent",
                    "needs": "phone"
                })


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
