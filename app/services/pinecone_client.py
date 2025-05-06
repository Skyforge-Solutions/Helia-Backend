# File: app/services/pinecone_client.py
import os, logging
from enum import Enum
from dotenv import load_dotenv
from pinecone import Pinecone

# Load environment variables
load_dotenv()

logger = logging.getLogger('pinecone')
logger.setLevel(logging.INFO)

# Initialize Pinecone client
pc = Pinecone(
    api_key=os.getenv('PINECONE_API_KEY'),
    environment=os.getenv('PINECONE_ENVIRONMENT')
)

# Define the index name
INDEX_NAME = os.getenv('PINECONE_INDEX_NAME', 'helia-chat-kb')
# Connect to the index
index = pc.Index(INDEX_NAME)

class BotNamespace(Enum):
    SUN_SHIELD = 'sun-shield'
    GROWTH_RAY = 'growth-ray'
    SUNBEAM = 'sunbeam'
    INNER_DAWN = 'inner-dawn'

    @classmethod
    def get_display_name(cls, bot):
        return {
            cls.SUN_SHIELD: 'Helia Sun Shield',
            cls.GROWTH_RAY: 'Helia Growth Ray',
            cls.SUNBEAM: 'Helia Sunbeam',
            cls.INNER_DAWN: 'Helia Inner Dawn'
        }.get(bot, bot)

    @classmethod
    def values(cls):
        return [bot.value for bot in cls]

def embed_texts(texts: list[str], input_type: str) -> list[list[float]]:
    if input_type not in ('passage', 'query'):
        raise ValueError('input_type must be \'passage\' or \'query\'')
    response = pc.inference.embed(
        model='llama-text-embed-v2',
        inputs=texts,
        parameters={'input_type': input_type}
    )
    return [item['values'] for item in response]

def query_text(query: str, bot: str, top_k: int = 5) -> list[dict]:
    if bot not in BotNamespace.values():
        raise ValueError(f'Invalid bot name: {bot}.')
    qv = embed_texts([query], input_type='query')[0]
    res = index.query(
        vector=qv,
        top_k=top_k,
        namespace=bot,
        include_metadata=True
    )
    return [
        {'id': m['id'], 'text': m['metadata'].get('text', ''), 'score': m['score']}
        for m in res.get('matches', [])
    ]
