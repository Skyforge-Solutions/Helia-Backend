# import os
# from dotenv import load_dotenv

# load_dotenv()

# def test_azure_openai_endpoint():
#     import requests

#     endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
#     deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
#     api_key = os.getenv("AZURE_OPENAI_KEY")
#     api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")

#     if not all([endpoint, deployment, api_key]):
#         print("ERROR: Missing one of AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT, or AZURE_OPENAI_KEY in environment.")
#         return

#     url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
#     headers = {
#         "Content-Type": "application/json",
#         "api-key": api_key
#     }
#     payload = {
#         "messages": [
#             {"role": "system", "content": "You are a test assistant."},
#             {"role": "user", "content": "Hello"}
#         ],
#         "max_tokens": 1
#     }

#     try:
#         response = requests.post(url, headers=headers, json=payload, timeout=10)
#         if response.status_code == 200:
#             print(response.json())
#         else:
#             print(f"❌ API returned {response.status_code}: {response.text}")
#     except Exception as e:
#         print(f"❌ Request failed: {e}")

# if __name__ == "__main__":
#     test_azure_openai_endpoint()
