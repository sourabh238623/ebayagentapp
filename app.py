from flask import Flask, request, jsonify
from langchain.agents import initialize_agent, AgentType
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_ollama import OllamaLLM
import os
import re
import logging
import ast

from langchain_groq import ChatGroq

logging.basicConfig(level=logging.DEBUG)
"""
# Ensure your Ollama base URL is accessible
OLLAMA_BASE_URL = os.environ.get(
    "OLLAMA_BASE_URL", "https://9759-216-113-160-105.ngrok-free.app")
LLM_MODEL = os.environ.get("LLM_MODEL", "mistral")

llm = OllamaLLM(base_url=OLLAMA_BASE_URL, model=LLM_MODEL)
"""

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
    }
}

search_tool = DuckDuckGoSearchRun(
    description=
    "Useful for searching for information specifically related to eBay policies, products, and help topics. Input should be a search query related to eBay."
)
tools = [search_tool]

ebay_guest_prompt_prefix = """You are an expert eBay assistant. Your ONLY function is to answer questions directly related to the eBay platform, its policies, products listed on eBay, and how to use eBay features. The answer will be spoken aloud to the user. Do not include any formatting like asterisks, hashtags, dashes, or quote marks. The response should sound natural when read aloud, like a human speaking. Use plain language only. Instead of respoding with * or **, use SSML tags like <emphasis> or <break> to make the response sound natural.

Under NO CIRCUMSTANCES should you answer questions about topics outside of eBay. This includes, but is not limited to: general knowledge, current events, weather, personal opinions, or any other subject matter that is not directly and exclusively about eBay.

At any point of time if customer says "i am done" or "i am good" or "that is all" etc., please just say "Thank you for calling eBay. Have a great day!" and end the conversation. To end the conversation, set needs as "disconnect".

Previous conversation:
{chat_history}

At any point of time if customer say repeat, please just repeat the last response. If you get input as 5, it means you need to repeat the last response.

Now, answer the following question: {input}"""

ebay_auth_prompt_prefix = """You are an expert eBay assistant. Your ONLY function is to answer questions directly related to the eBay platform, its policies, products listed on eBay, and how to use eBay features. The answer will be spoken aloud to the user. Do not include any formatting like asterisks, hashtags, dashes, or quote marks. The response should sound natural when read aloud, like a human speaking. Use plain language only. Use SSML tags like <emphasis> or <break> if needed.

"""


def clean_response(text):
    # Remove Markdown-style bold/italic
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    # Remove numbered list prefixes (e.g., "1. ", "2. ")
    #  text = re.sub(r'^\d+\.\s*', '', text, flags=re.MULTILINE)
    # Remove quotes
    text = text.replace('"', '')
    return text.strip()


def format_list_with_dtmf(data_list):
    """Formats a list with DTMF numbers (1-10)."""
    formatted_list = []
    for i, item in enumerate(data_list):
        if 1 <= i + 1 <= 10:
            formatted_list.append(f"{i + 1}. {item}")
        else:
            formatted_list.append(f"{i + 1}. {item} (Beyond DTMF range)")
    return formatted_list


def extract_list_from_llm_response(response):
    """Attempts to extract a list of items from the LLM's response."""
    lines = response.strip().split('\n')
    list_started = False
    list_items = []

    for line in lines:
        line = line.strip()
        if not list_started and line.lower().startswith(
                "here are some options:"):
            list_started = True
            continue
        elif list_started:
            numbered_match = re.match(r"^\d+\.\s+(.*)$", line)
            if numbered_match:
                list_items.append(numbered_match.group(1).strip())
                continue  # Move to the next line after a successful match

            nested_numbered_match = re.match(r"^\d+\.\s*\d+\.\s+(.*)$", line)
            if nested_numbered_match:
                list_items.append(nested_numbered_match.group(1).strip())
                continue  # Move to the next line

            if not re.match(r"^(please enter|enter the number)",
                            line.lower()) and line.strip():
                list_items.append(line)
                continue  # Move to the next line

        elif not list_started:
            bullet_match = re.match(r"^[-*]\s+(.*)$", line)
            if bullet_match:
                list_items.append(bullet_match.group(1).strip())

    return list_items


def create_ebay_guest_agent():
    agent = initialize_agent(
        llm=model,
        tools=tools,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        verbose=True,
        agent_kwargs={"prefix": ebay_guest_prompt_prefix},
        handle_parsing_errors=
        "Check your output and ensure it conforms to the schema: ```json\n{\n    \"action\": \"tool_name\",\n    \"action_input\": \"tool_input\"\n}\n``` or respond directly to the user."
    )
    return agent


def create_ebay_auth_agent():
    agent = initialize_agent(
        llm=model,
        tools=tools,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        verbose=True,
        agent_kwargs={"prefix": ebay_guest_prompt_prefix},
        handle_parsing_errors=
        "Check your output and ensure it conforms to the schema: ```json\n{\n    \"action\": \"tool_name\",\n    \"action_input\": \"tool_input\"\n}\n``` or respond directly to the user.",
        max_iterations=10)
    return agent


app = Flask(__name__)
user_auth_state = {}  # In-memory state for tracking authentication attempts
user_chat_history = {}  # In-memory state for storing chat history per session
last_llm_list = {}  # Store the last LLM generated list per session
awaiting_dtmf_selection = {}  # Track if the agent is awaiting DTMF input
negative_response_patterns = re.compile(
    r"(don'?t have|doesn'?t match|not it|wrong (number|zip)|can'?t provide|i'm unable to)",
    re.IGNORECASE)


def extract_phone_number(text, auth_state):
    if "phone_no_match_count" not in auth_state:
        auth_state["phone_no_match_count"] = 0

    match = re.search(r'\b(?:\d[\s.-]?){9}\d\b', text)
    if not match:
        auth_state["phone_no_match_count"] += 1
        if auth_state["phone_no_match_count"] >= 3:
            return False
    return match.group(0) if match else None


def extract_zip_code(text, auth_state):
    if "zip_no_match_count" not in auth_state:
        auth_state["zip_no_match_count"] = 0
    match = re.search(r'\b\d[\d\s.-]{3}\d\b', text)
    if not match:
        auth_state["zip_no_match_count"] += 1
        if auth_state["zip_no_match_count"] >= 3:
            print("Zip code not valid after multiple attempts:::::")
            return False
    return match.group(0) if match else None


def handle_authentication_failure(session_id):
    logging.debug(
        f"Session {session_id}: Authentication failed. Resetting state.")
    user_auth_state[session_id]["authenticated"] = False
    user_auth_state[session_id]["phone"] = None
    user_auth_state[session_id]["zip"] = None
    user_auth_state[session_id]["awaiting"] = None
    user_auth_state[session_id]["started"] = False  # Reset the started flag
    if session_id in user_chat_history:
        del user_chat_history[session_id]  # Clear chat history on auth failure
    return jsonify({
        "response":
        "Authentication failed. I will now respond as a guest user.",
        "authenticated": False,
        "agent": "Authentication Agent",
        "needs_auth": True
    })


def process_dtmf_input(user_input, original_list):
    """Processes user input to retrieve the corresponding item from the original list based on DTMF number."""
    try:
        selected_index = int(user_input) - 1
        if 0 <= selected_index < len(original_list):
            return original_list[selected_index]
        else:
            return None  # Invalid selection
    except ValueError:
        return None  # Invalid input


@app.route("/ask", methods=["POST"])
def ask_agent():
    print(
        '------------------------New Request received ------------------------'
    )
    data = request.get_json()
    if not data or "query" not in data or "session_id" not in data:
        return jsonify(
            {"error": "Missing 'query' or 'session_id' in request body"}), 400

    query = data["query"]
    session_id = data["session_id"]
    user_chat_history.setdefault(session_id, [])
    last_llm_list.setdefault(session_id, None)
    awaiting_dtmf_selection.setdefault(session_id, False)

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

    logging.debug(
        f"Session {session_id}: Received query: '{query}'. Current auth_state: {auth_state}, Awaiting DTMF: {awaiting_dtmf_selection[session_id]}"
    )
    chat_history_str = "\n".join(user_chat_history[session_id])

    # Handle DTMF input if awaiting selection
    if awaiting_dtmf_selection[session_id] and query.isdigit(
    ) and 1 <= int(query) <= 10 and last_llm_list[session_id]:
        selected_item = process_dtmf_input(query, last_llm_list[session_id])
        if selected_item:
            awaiting_dtmf_selection[session_id] = False  # Reset flag
            logging.debug(
                f"Session {session_id}: User selected item: {selected_item}")
            # The selected_item becomes the new query for the LLM
            return ask_agent_internal(selected_item, session_id, auth_state,
                                      chat_history_str)
        else:
            response = "Invalid selection. Please enter a number between 1 and 10."
            user_chat_history[session_id].append(f"User: {query}")
            user_chat_history[session_id].append(f"Assistant: {response}")
            return jsonify({
                "response": response,
                "authenticated": auth_state["authenticated"],
                "agent": "eBay Agent"
            })
    elif ("repeat" in query.lower()
          or query.strip() == "5") and user_chat_history[session_id]:
        response = user_chat_history[session_id][-1].split("Assistant: ")[-1]
        return jsonify({
            "response": response,
            "authenticated": auth_state["authenticated"],
            "agent": "eBay Agent",
        })
    else:
        return ask_agent_internal(query, session_id, auth_state,
                                  chat_history_str)


def ask_agent_internal(query, session_id, auth_state, chat_history_str):
    if auth_state["authenticated"]:
        ebay_auth_agent = create_ebay_auth_agent()
        logging.debug(
            f"Session {session_id}: Authenticated query: '{query}'. Chat history: {chat_history_str}"
        )
        try:
            response = ebay_auth_agent.run(input=query,
                                           chat_history=chat_history_str)
            response = clean_response(response)

            extracted_list = extract_list_from_llm_response(response)
            if extracted_list and len(extracted_list) > 0 and len(
                    extracted_list) <= 100:
                formatted_list = format_list_with_dtmf(extracted_list)
                last_llm_list[session_id] = extracted_list
                awaiting_dtmf_selection[session_id] = True  # Set flag
                response_text = "Here are some options:\n" + "\n".join(
                    formatted_list)

                user_chat_history[session_id].append(f"User: {query}")
                user_chat_history[session_id].append(
                    f"Assistant: {response_text}")
                return jsonify({
                    "response": response_text,
                    "authenticated": True,
                    "agent": "eBay Authenticated Agent",
                    "is_list": True,
                    "needs_dtmf": True
                })
            else:
                last_llm_list[
                    session_id] = None  # Clear the list if not applicable
                awaiting_dtmf_selection[session_id] = False
                user_chat_history[session_id].append(f"User: {query}")
                user_chat_history[session_id].append(f"Assistant: {response}")
                return jsonify({
                    "response": response,
                    "authenticated": True,
                    "agent": "eBay Authenticated Agent",
                    "is_list": False,
                    "needs_dtmf": False
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
            phone = extract_phone_number(query, auth_state)
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
            zip_code = extract_zip_code(query, auth_state)
            if zip_code:
                auth_state["zip"] = zip_code
                auth_state["awaiting"] = None
                auth_state['phone'] = re.sub(r'\D', '', auth_state['phone'])
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
                elif auth_state.get("zip_no_match_count") >= 2:
                    # If the zip code is not valid and we have already failed twice
                    logging.debug(
                        f"Session {session_id}: Zip code not valid after multiple attempts."
                    )
                    return jsonify({
                        "response": "I couldn't able to valid your zip code.",
                        "authenticated": False,
                        "agent": "eBay Guest Agent (Initial)",
                        "needs": "xfer"
                    })
                else:
                    return handle_authentication_failure(session_id)
            elif auth_state.get("zip_no_match_count") >= 2:
                # If the zip code is not valid and we have already failed twice
                logging.debug(
                    f"Session {session_id}: Zip code not valid after multiple attempts."
                )
                return jsonify({
                    "response": "I couldn't able to valid your zip code.",
                    "authenticated": False,
                    "agent": "eBay Guest Agent",
                    "needs": "xfer"
                })
            else:
                return jsonify({
                    "response":
                    "That doesn't look like a valid zip code. Please enter your zipcode again.",
                    "authenticated": False,
                    "agent": "Authentication Agent",
                    "needs": "zip"
                })
        else:
            # Start of a new session (or if not already awaiting info)
            failed_attempts = 0
            phone = extract_phone_number(query, auth_state)
            zip_code = False
            #if phone:
            #zip_code = extract_zip_code(query, auth_state)

            if phone and zip_code:
                auth_state["started"] = True
                auth_state["phone"] = phone
                auth_state["zip"] = zip_code
                auth_state['phone'] = re.sub(r'\D', '', auth_state['phone'])
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
            elif auth_state.get("phone_no_match_count") >= 3:
                # If the phone number is not valid and we have already failed twice
                logging.debug(
                    f"Session {session_id}: Phone number not valid after multiple attempts."
                )
                return jsonify({
                    "response":
                    "I couldn't able to valid your phone number. Let me know how may I help you.",
                    "authenticated": False,
                    "agent": "eBay Guest Agent",
                    "needs": "xfer"
                })
            elif auth_state.get(
                    "zip_no_match_count") != None and auth_state.get(
                        "zip_no_match_count") >= 3:
                # If the zip code is not valid and we have already failed twice
                logging.debug(
                    f"Session {session_id}: Zip code not valid after multiple attempts."
                )
                return jsonify({
                    "response":
                    "There seems to be some issue with your account. Please let me know how may I help you.",
                    "authenticated": False,
                    "agent": "eBay Guest Agent (Initial)",
                    "needs": "xfer"
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
    return jsonify({"error": "Unexpected flow"}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
