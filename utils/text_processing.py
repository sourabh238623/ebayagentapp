import re


def clean_response(text):
    """Removes Markdown-style formatting and quotes from the text."""
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
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


def extract_phone_number(text, auth_state):
    """Extracts a phone number from text."""
    if "phone_no_match_count" not in auth_state:
        auth_state["phone_no_match_count"] = 0

    match = re.search(r'\b(?:\d[\s.-]?){9}\d\b', text)
    if not match:
        auth_state["phone_no_match_count"] += 1
        if auth_state["phone_no_match_count"] >= 3:
            return False
    return match.group(0) if match else None


def extract_zip_code(text, auth_state):
    """Extracts a zip code from text."""
    if "zip_no_match_count" not in auth_state:
        auth_state["zip_no_match_count"] = 0
    match = re.search(r'\b\d[\d\s.-]{3}\d\b', text)
    if not match:
        auth_state["zip_no_match_count"] += 1
        if auth_state["zip_no_match_count"] >= 3:
            print("Zip code not valid after multiple attempts:::::")
            return False
    return match.group(0) if match else None
