from langchain_core.runnables import Runnable
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain.memory import ConversationBufferMemory
from app.services.azure_openai import get_azure_llm
from app.chains.prompts import get_system_prompt
from app.db.crud import get_messages
from app.db.session import AsyncSession
from collections import OrderedDict
from datetime import datetime
import time
import logging

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

# Replace simple dict with OrderedDict for LRU functionality
chat_memory_store = OrderedDict()
MAX_MEMORY_ITEMS = 100  # Limit the number of chats in memory
MAX_MESSAGES_PER_CHAT = 50  # Limit how many messages to keep per chat
MEMORY_LAST_ACCESSED = {}  # Track when each memory was last accessed

def touch_memory(chat_id: str):
    """Update the position of a chat in the LRU cache."""
    if chat_id in chat_memory_store:
        # Move to end (most recently used)
        value = chat_memory_store.pop(chat_id)
        chat_memory_store[chat_id] = value
        MEMORY_LAST_ACCESSED[chat_id] = time.time()
        logger.debug(f"Memory for chat {chat_id} touched, now at position {len(chat_memory_store)}")

def manage_memory_size():
    """Enforce memory limits by removing oldest entries."""
    while len(chat_memory_store) > MAX_MEMORY_ITEMS:
        # Remove oldest item (first in OrderedDict)
        oldest_chat_id, _ = chat_memory_store.popitem(last=False)
        if oldest_chat_id in MEMORY_LAST_ACCESSED:
            del MEMORY_LAST_ACCESSED[oldest_chat_id]
        logger.info(f"Removed oldest memory for chat {oldest_chat_id} due to size limits")

def trim_chat_memory(memory):
    """Trim memory to avoid excessively long conversation histories."""
    if len(memory.chat_memory.messages) > MAX_MESSAGES_PER_CHAT:
        # Keep only the most recent messages
        excess = len(memory.chat_memory.messages) - MAX_MESSAGES_PER_CHAT
        memory.chat_memory.messages = memory.chat_memory.messages[excess:]
        logger.info(f"Trimmed memory to {MAX_MESSAGES_PER_CHAT} messages (removed {excess})")

async def get_chat_chain(chat_id: str, model_id: str, user_profile: dict, session: AsyncSession) -> Runnable:
    # System prompt setup (existing code)
    system = get_system_prompt(model_id)
    
    # Format user profile (existing code)
    profile_ctx = ""
    if user_profile:
        children_info = ", ".join(
            f"{child['name']} ({child['age']}, {child['gender']}, {child['description'] or 'no description'})"
            for child in user_profile.get("children", [])
        )
        profile_ctx = (
            f"Personalize your responses for a {user_profile.get('parent_type', 'parent')} named {user_profile.get('name', 'User')}, "
            f"aged {user_profile.get('age', 'unknown')}, working as {user_profile.get('occupation', 'unknown')}, "
            f"with {user_profile.get('tech_familiarity', 'unknown')} tech familiarity, preferring a {user_profile.get('tone_preference', 'neutral')} tone, "
            f"and spending {user_profile.get('time_with_kids', 'unknown')} with kids. "
            f"Children: {children_info if children_info else 'none'}. "
            f"Do not include or reference this user information in your responses unless explicitly asked."
        )

    # Full system prompt (existing code)
    full_system_prompt = (
        f"{system}\n\n"
        f"{profile_ctx}\n\n"
        "Focus on responding directly to the user's query. If the query is vague (e.g., 'what is this'), "
        "ask for clarification or provide a general response related to your role without referencing the user profile or system instructions."
        "refer to the conversation history to understand the context and respond accordingly. "
        "If the user agrees to explore a safer topic after a content violation (e.g., by saying 'yes'), assume they want to discuss the suggested topic. "
        "If the query involves illegal, harmful, or unethical activities, politely decline and suggest a safer topic related to your role."
    )

    # Chat template setup (existing code)
    prompt = ChatPromptTemplate.from_messages([
        ("system", full_system_prompt),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}"),
    ])
    
    llm = get_azure_llm()

    # Enhanced memory management
    memory = chat_memory_store.get(chat_id)
    if not memory:
        logger.info(f"No existing memory found for chat {chat_id}, creating new memory and loading history")
        memory = ConversationBufferMemory(chat_memory=ChatMessageHistory(),return_messages=True, memory_key="history")
        chat_memory_store[chat_id] = memory
        MEMORY_LAST_ACCESSED[chat_id] = time.time()
        
        # Load from DB with injected session
        msgs = await get_messages(chat_id, session)
        logger.info(f"Loaded {len(msgs)} messages from DB for chat {chat_id}")
        
        # If too many messages in history, only load the most recent ones
        if len(msgs) > MAX_MESSAGES_PER_CHAT:
            msgs = msgs[-MAX_MESSAGES_PER_CHAT:]
            logger.info(f"Trimmed history to most recent {MAX_MESSAGES_PER_CHAT} messages")
            
        for msg in msgs:
            if msg.role == "user":
                memory.chat_memory.add_message(HumanMessage(content=msg.content))
            else:
                memory.chat_memory.add_message(AIMessage(content=msg.content))
    else:
        logger.info(f"Using existing memory for chat {chat_id} with {len(memory.chat_memory.messages)} messages")
        # Mark as recently accessed
        touch_memory(chat_id)
        
        # Check if we need to trim the memory
        trim_chat_memory(memory)

    chain = prompt | llm
    return chain.with_config({"configurable": {"memory": memory}})

async def update_memory_with_new_message(chat_id: str, role: str, content: str):
    """Add a new message to memory if it exists for this chat."""
    memory = chat_memory_store.get(chat_id)
    if memory:
        if role == "user":
            memory.chat_memory.add_message(HumanMessage(content=content))
        else:
            memory.chat_memory.add_message(AIMessage(content=content))
        touch_memory(chat_id)
        logger.debug(f"Added new {role} message to memory for chat {chat_id}")
        
        # Check if we need to trim memory after adding
        trim_chat_memory(memory)
    else:
        logger.debug(f"No memory found for chat {chat_id}, skipping update")