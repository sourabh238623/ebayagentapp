from langchain_community.tools import DuckDuckGoSearchRun

search_tool = DuckDuckGoSearchRun(description=(
    "Useful for searching for information specifically related to eBay policies, products, and help topics. "
    "Input should be a search query related to eBay."))
