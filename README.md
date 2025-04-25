# Updated README.md with detailed documentation about the backend, containerization, and CI/CD setup.

# HeliaChat Backend Documentation

## Project Overview

HeliaChat Backend is a FastAPI-based API that powers an AI-assisted chat application focused on parenting assistance. It offers various AI personas that provide different types of parenting advice through a chat interface.

## Key Features

- **User Authentication System**: JWT-based authentication with secure password hashing
- **Multiple AI Personas**: Different specialized AI personalities for parenting advice
- **Chat Session Management**: Create, update, and manage chat sessions
- **Message History**: Store and retrieve chat message history
- **Azure OpenAI Integration**: Uses Azure's OpenAI service for chat responses
- **User Profiles**: Customizable user profiles with parenting-related preferences
- **Streaming Responses**: Real-time message streaming

## Technology Stack

- **FastAPI**: Modern, high-performance web framework
- **SQLAlchemy**: Asynchronous ORM for database operations
- **LangChain**: Framework for AI model integration
- **Azure OpenAI**: AI provider for chat responses
- **PostgreSQL**: Database backend
- **JWT Authentication**: Token-based security

## Requirements

All dependencies are listed in [`requirements.txt`](requirements.txt), including:
- fastapi
- uvicorn
- sqlalchemy
- python-dotenv
- asyncpg
- langchain
- langchain_openai
- passlib
- python-jose

## Installation & Setup

### Local Development

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Setup environment variables (see below)
5. Run the application:
   ```bash
   uvicorn app.main:app --reload
   ```

### Environment Variables

Create a [`.env`](.env) file in the project root with the following variables:

```
DATABASE_URL=postgresql+asyncpg://user:password@host/dbname
SECRET_KEY=your-secret-key-for-jwt
AZURE_OPENAI_ENDPOINT=your-azure-openai-endpoint
AZURE_OPENAI_DEPLOYMENT=your-deployment-name
AZURE_OPENAI_KEY=your-api-key
AZURE_OPENAI_API_VERSION=2024-02-01
```

## API Endpoints

### Authentication

- `POST /api/auth/register`: Create new user account
- `POST /api/auth/token`: Get JWT token (login)
- `GET /api/auth/me`: Get current user profile

### Chat

- `POST /api/chat/send`: Send a message and get AI response
- `GET /api/sessions`: List all user chat sessions
- `POST /api/sessions`: Create new chat session
- `PUT /api/sessions/{chat_id}`: Update chat session name
- `DELETE /api/sessions/{chat_id}`: Delete a chat session
- `GET /api/history/{chat_id}`: Get chat message history

### User Profile

- `PUT /api/users/me`: Update user profile
- `GET /api/users/me`: Get current user profile

## Database Schema

The application uses three main tables:
- `users`: Stores user accounts and profile data
- `chat_sessions`: Stores metadata about chat conversations
- `chat_messages`: Stores individual chat messages

## Project Structure

```
HeliaChat_BackEnd/
├── app/
│   ├── api/             # API routes
│   │   ├── auth.py      # Authentication endpoints
│   │   └── chat.py      # Chat endpoints
│   ├── chains/          # AI chat chains
│   │   ├── base.py      # Core chat chain logic
│   │   └── prompts.py   # AI persona system prompts
│   ├── db/              # Database
│   │   ├── crud.py      # Database operations
│   │   ├── models.py    # SQLAlchemy models
│   │   └── session.py   # Database connection
│   ├── schemas/         # Pydantic models
│   │   ├── chat.py      # Chat schema models
│   │   └── models.py    # User schema models
│   ├── services/        # External services
│   │   └── azure_openai.py  # Azure OpenAI integration
│   ├── utils/           # Utilities
│   │   ├── auth.py      # Auth utilities
│   │   └── password.py  # Password hashing
│   └── main.py          # Application entry point
├── scripts/             # Utility scripts
│   └── test.py          # Test Azure OpenAI connection
├── requirements.txt     # Project dependencies
└── .env                 # Environment variables (create this)
```

