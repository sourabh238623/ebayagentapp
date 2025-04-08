# ebay_agent_app/app.py
from flask import Flask, request, jsonify
from agents.ebay_guest_agent import create_ebay_guest_agent
from agents.ebay_auth_agent import create_ebay_auth_agent
from agents.auth_agent import create_auth_agent
from config import USER_DATA
import re

app = Flask(__name__)
user_auth_state = {}  # In-memory state for tracking authentication attempts


def extract_phone_number(text):
    """Extracts a 10-digit phone number from text."""
    match = re.search(r'\b\d{10}\b', text)
    if match:
        return match.group(0)
    return None


def extract_zip_code(text):
    """Extracts a 5-digit zip code from text."""
    match = re.search(r'\b\d{5}\b', text)
    if match:
        return match.group(0)
    return None


@app.route("/ask", methods=["POST"])
def ask_agent():
    data = request.get_json()
    if not data or "query" not in data or "session_id" not in data:
        return jsonify(
            {"error": "Missing 'query' or 'session_id' in request body"}), 400

    query = data["query"]
    session_id = data["session_id"]

    auth_state = user_auth_state.get(session_id, {
        "authenticated": False,
        "phone": None,
        "zip": None
    })
    user_auth_state[session_id] = auth_state  # Ensure state is initialized

    if auth_state["authenticated"]:
        # User is authenticated, route to eBay agent
        ebay_auth_agent = create_ebay_auth_agent()
        try:
            response = ebay_auth_agent.run(query)
            return jsonify({
                "response": response,
                "authenticated": True,
                "agent": "eBay Authenticated Agent"
            })
        except Exception as e:
            return jsonify(
                {"error": f"eBay Authenticated Agent Error: {str(e)}"}), 500
    else:
        # User not authenticated, use authentication agent
        auth_agent = create_auth_agent()
        auth_input = query
        try:
            auth_response = auth_agent.run(input=auth_input, chat_history=[])
            print(f"Authentication Agent Response: {auth_response}")
            print(f"Current Auth State for {session_id}: {auth_state}")

            processed_auth = False

            # Try to extract phone number from the query
            if auth_state["phone"] is None:
                phone = extract_phone_number(query)
                if phone:
                    auth_state["phone"] = phone
                    processed_auth = True
                    if auth_state["zip"]:
                        if f"{auth_state['phone']}-{auth_state['zip']}" in USER_DATA:
                            auth_state["authenticated"] = True
                            return jsonify({
                                "response":
                                "Authentication successful. You can now ask eBay-related questions.",
                                "authenticated": True,
                                "agent": "Authentication Agent"
                            })
                        else:
                            auth_state["phone"] = None
                            auth_state["zip"] = None
                            return jsonify({
                                "response":
                                "Authentication failed. Please provide your phone number and zip code.",
                                "authenticated": False,
                                "agent": "Authentication Agent"
                            })
                    else:
                        return jsonify({
                            "response":
                            "Please provide your zip code for authentication.",
                            "authenticated": False,
                            "agent": "Authentication Agent",
                            "needs": "zip"
                        })

            # Try to extract zip code from the query
            if not processed_auth and auth_state["zip"] is None:
                zip_code = extract_zip_code(query)
                if zip_code:
                    auth_state["zip"] = zip_code
                    processed_auth = True
                    if auth_state["phone"]:
                        if f"{auth_state['phone']}-{auth_state['zip']}" in USER_DATA:
                            auth_state["authenticated"] = True
                            return jsonify({
                                "response":
                                "Authentication successful. You can now ask eBay-related questions.",
                                "authenticated": True,
                                "agent": "Authentication Agent"
                            })
                        else:
                            auth_state["phone"] = None
                            auth_state["zip"] = None
                            return jsonify({
                                "response":
                                "Authentication failed. Please provide your phone number and zip code.",
                                "authenticated": False,
                                "agent": "Authentication Agent"
                            })
                    else:
                        return jsonify({
                            "response":
                            "Please provide your phone number for authentication.",
                            "authenticated": False,
                            "agent": "Authentication Agent",
                            "needs": "phone"
                        })

            if not processed_auth:
                # If the query wasn't recognized as auth info, pass it to the guest agent
                ebay_guest_agent = create_ebay_guest_agent()
                guest_response = ebay_guest_agent.run(query)
                return jsonify({
                    "response": guest_response,
                    "authenticated": False,
                    "agent": "eBay Guest Agent",
                    "needs_auth": True
                })

        except Exception as e:
            return jsonify({"error":
                            f"Authentication Agent Error: {str(e)}"}), 500

    return jsonify({"error": "Should not reach here"}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
