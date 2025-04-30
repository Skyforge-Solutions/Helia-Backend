# app/services/azure_openai.py
import os
from functools import lru_cache
from langchain_openai import AzureChatOpenAI

# ────────────────────────────────────────────────────────────────
# 1) Read & validate once at import time
AZURE_ENDPOINT    = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_DEPLOYMENT  = os.getenv("AZURE_OPENAI_DEPLOYMENT")
AZURE_API_KEY     = os.getenv("AZURE_OPENAI_KEY")
AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")

if not (AZURE_ENDPOINT and AZURE_DEPLOYMENT and AZURE_API_KEY):
    missing = [k for k,v in {
        "AZURE_OPENAI_ENDPOINT": AZURE_ENDPOINT,
        "AZURE_OPENAI_DEPLOYMENT": AZURE_DEPLOYMENT,
        "AZURE_OPENAI_KEY": AZURE_API_KEY
    }.items() if not v]
    raise RuntimeError(f"Missing Azure OpenAI config: {missing}")

# ────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def get_azure_llm() -> AzureChatOpenAI:
    """
    Return a singleton AzureChatOpenAI instance.
    lru_cache ensures we only construct it once per process.
    """
    return AzureChatOpenAI(
        azure_endpoint   = AZURE_ENDPOINT,
        deployment_name  = AZURE_DEPLOYMENT,
        api_key          = AZURE_API_KEY,
        api_version      = AZURE_API_VERSION,
        temperature      = 0.7,
        streaming        = True,
    )