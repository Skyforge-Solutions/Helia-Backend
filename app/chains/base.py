from langchain_core.runnables import Runnable
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferMemory
from langchain_core.messages import HumanMessage, AIMessage
from app.services.azure_openai import get_azure_llm
from app.chains.prompts import get_system_prompt
from app.db.crud import get_messages
import json
import re

# In-memory store; swap for DB-backed memory later
chat_memory_store = {}

async def get_chat_chain(chat_id: str, model_id: str, user_profile: dict) -> Runnable:
    system = get_system_prompt(model_id)
    
    # Safely serialize user_profile to prevent template variable conflicts
    if user_profile:
        # Filter out SQLAlchemy internal state
        clean_profile = {k: v for k, v in user_profile.items() 
                        if not k.startswith('_') and k != '_sa_instance_state'}
        # Convert to JSON string and escape curly braces to avoid template parsing issues
        profile_json = json.dumps(clean_profile)
        # Escape all curly braces by doubling them to prevent template variable interpretation
        profile_json = profile_json.replace("{", "{{").replace("}", "}}")
        profile_ctx = f"User Info: ```{profile_json}```\n"
    else:
        profile_ctx = ""

    # Create prompt template with properly constructed message list
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system + profile_ctx),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}")
        ]
    )

    llm = get_azure_llm()

    memory = chat_memory_store.get(chat_id)
    if not memory:
        memory = ConversationBufferMemory(return_messages=True, memory_key="history")
        chat_memory_store[chat_id] = memory
        
        # Load conversation history from DB when a new memory is created
        messages = await get_messages(chat_id)
        for msg in messages:
            if msg.role == "user":
                memory.chat_memory.add_message(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                memory.chat_memory.add_message(AIMessage(content=msg.content))

    # Create the chain, integrating the memory as a configurable component
    chain = prompt | llm
    
    # Return the chain with memory properly integrated
    return chain.with_config({"configurable": {"memory": memory}})