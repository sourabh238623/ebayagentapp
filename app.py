from flask import Flask, request, jsonify
from langchain.agents import initialize_agent, AgentType
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_groq import ChatGroq
import os
import re
import logging

logging.basicConfig(level=logging.DEBUG)

os.environ[
    "GROQ_API_KEY"] = "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"
model = ChatGroq(model="Gemma2-9b-It")

USER_DATA = {
    "1234567890-98109": {
        "authenticated": True
    },
    "9876543210-12345": {
        "authenticated": True
    },
    "8473236970-98012": {
        "authenticated": True
    },
}

search_tool = DuckDuckGoSearchRun(
    description=
    "Useful for searching for information specifically related to eBay policies, products, and help topics. Input should be a search query related to eBay."
)
tools = [search_tool]

EBAY_GUEST_PROMPT_PREFIX = """You are an expert eBay assistant. Your ONLY function is to answer questions directly related to the eBay platform, its policies, products listed on eBay, and how to use eBay features.

Under NO CIRCUMSTANCES should you answer questions about topics outside of eBay. This includes, but is not limited to: general knowledge, current events, weather, personal opinions, or any other subject matter that is not directly and exclusively about eBay.

If a user asks a non-eBay question, you MUST respond with a clear and concise refusal, such as: "I can only answer questions about eBay." or "Sorry, I can only help with eBay-related inquiries." Do not attempt to answer non-eBay questions, and do not provide any information outside of the eBay domain.

Here are some examples:

User: What is eBay's return policy?
You: I should use the search tool to find eBay's return policy.

User: How do I sell an item on eBay?
You: I should use the search tool to find instructions on selling items on eBay.

User: What is the weather in Vancouver, WA?
You: I can only answer questions about eBay.

User: What are the current stock prices?
You: I can only answer questions about eBay.


Previous conversation:
{chat_history}

At any point of time if customer say repeat, please just repeat the last response. If you get input as 5, it means you need to repeat the last response.

Now, answer the following question: {input}"""

EBAY_AUTH_PROMPT_PREFIX = EBAY_GUEST_PROMPT_PREFIX


def create_ebay_guest_agent():
    return initialize_agent(
        llm=model,
        tools=tools,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        verbose=True,
        prefix=EBAY_GUEST_PROMPT_PREFIX,
        handle_parsing_errors=
        "Check your output and ensure it conforms to the schema: ```json\n{\n    \"action\": \"tool_name\",\n    \"action_input\": \"tool_input\"\n}\n``` or respond directly to the user.",
    )


def create_ebay_auth_agent():
    return initialize_agent(
        llm=model,
        tools=tools,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        verbose=True,
        prefix=EBAY_AUTH_PROMPT_PREFIX,
        handle_parsing_errors=
        "Check your output and ensure it conforms to the schema: ```json\n{\n    \"action\": \"tool_name\",\n    \"action_input\": \"tool_input\"\n}\n``` or respond directly to the user.",
        max_iterations=10,
    )


app = Flask(__name__)
user_auth_state = {}
user_chat_history = {}

@app.route('/')
def health_check():
    return jsonify({"status": "healthy"})


def extract_phone_number(text, auth_state):
    auth_state.setdefault("phone_no_match_count", 0)
    match = re.search(r'\b(?:\d[\s.-]?){9}\d\b', text)
    if not match:
        auth_state["phone_no_match_count"] += 1
        if auth_state["phone_no_match_count"] >= 3:
            return False
    return re.sub(r'\D', '', match.group(0)) if match else None


def extract_zip_code(text, auth_state):
    auth_state.setdefault("zip_no_match_count", 0)
    match = re.search(r'\b\d[\d\s.-]{3}\d\b', text)
    if not match:
        auth_state["zip_no_match_count"] += 1
        if auth_state["zip_no_match_count"] >= 3:
            return False
    return match.group(0) if match else None


def handle_authentication_failure(session_id):
    logging.debug(
        f"Session {session_id}: Authentication failed. Resetting state.")
    user_auth_state[session_id] = {
        "authenticated": False,
        "phone": None,
        "zip": None,
        "awaiting": None,
        "started": False,
    }
    user_chat_history.pop(session_id, None)
    return jsonify({
        "response":
        "Authentication failed. I will now respond as a guest user.",
        "authenticated": False,
        "agent": "eBay Guest Agent",
        "needs": "xfer",
    })


@app.route("/ask", methods=["POST"])
def ask_agent():
    data = request.get_json()
    if not data or "query" not in data or "session_id" not in data:
        return jsonify(
            {"error": "Missing 'query' or 'session_id' in request body"}), 400

    query = data["query"]
    session_id = data["session_id"]

    user_chat_history.setdefault(session_id, [])
    auth_state = user_auth_state.setdefault(
        session_id, {
            "authenticated": False,
            "phone": None,
            "zip": None,
            "awaiting": None,
            "started": False,
            "initial_query_context": None,
        })

    if auth_state["authenticated"]:
        ebay_agent = create_ebay_auth_agent()
    else:
        ebay_agent = create_ebay_guest_agent()

    chat_history_str = "\n".join(user_chat_history[session_id])

    if query.lower() in ("repeat", "5") and user_chat_history[session_id]:
        response = user_chat_history[session_id][-1].split("Assistant: ")[-1]
        return jsonify({
            "response": response,
            "authenticated": auth_state["authenticated"],
            "agent": "eBay Agent",
        })

    try:
        if not auth_state["authenticated"] and auth_state["started"]:
            # authentication flow
            if auth_state["awaiting"] == "phone":
                phone = extract_phone_number(query, auth_state)
                if phone:
                    auth_state["phone"] = phone
                    auth_state["awaiting"] = "zip"
                    return jsonify({
                        "response": "Please provide your zip code.",
                        "authenticated": False,
                        "agent": "Authentication Agent",
                        "needs": "zip"
                    })
                else:
                    return jsonify({
                        "response": "Invalid phone number, please try again",
                        "authenticated": False,
                        "agent": "Authentication Agent",
                        "needs": "phone"
                    })
            elif auth_state["awaiting"] == "zip":
                zip_code = extract_zip_code(query, auth_state)
                if zip_code:
                    auth_state["zip"] = zip_code
                    if f"{auth_state['phone']}-{auth_state['zip']}" in USER_DATA:
                        auth_state["authenticated"] = True
                        return jsonify({
                            "response": "Authentication successful.",
                            "authenticated": True,
                            "agent": "eBay Agent"
                        })
                    else:
                        return handle_authentication_failure(session_id)
                else:
                    return jsonify({
                        "response": "Invalid zip code, please try again",
                        "authenticated": False,
                        "agent": "Authentication Agent",
                        "needs": "zip"
                    })
        else:
            if not auth_state["started"]:
                auth_state["started"] = True
                auth_state["initial_query_context"] = ' '.join(
                    query.split()[:4]) + ('...'
                                          if len(query.split()) > 4 else '')
                return jsonify({
                    "response":
                    f"To assist you further, please provide your phone number.",
                    "authenticated": False,
                    "agent": "Authentication Agent",
                    "needs": "phone"
                })

        response = ebay_agent.run(input=query, chat_history=chat_history_str)
        user_chat_history[session_id].append(f"User: {query}")
        user_chat_history[session_id].append(f"Assistant: {response}")
        return jsonify({
            "response": response,
            "authenticated": auth_state["authenticated"],
            "agent": "eBay Agent"
        })
    except Exception as e:
        logging.error(f"Session {session_id}: Agent Error: {e}")
        return jsonify({"error": f"Agent Error: {str(e)}"}), 500

if __name__ == '__main__':
    import atexit
    
    @atexit.register
    def shutdown():
        logging.info("Shutting down the application")
    
    app.run(host='0.0.0.0', port=5000, debug=False)
