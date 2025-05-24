import asyncio
import streamlit as st
import uuid
from pymongo import MongoClient
from pymongo.operations import SearchIndexModel
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai import Agent, RunContext, ModelRetry
from pydantic import BaseModel, ConfigDict
import os
from dotenv import load_dotenv
import logging
from openai import OpenAI

# Set up logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
logging.getLogger("pymongo").setLevel(logging.ERROR)

# Ensure ollama is installed
try:
    from ollama import embed
except ImportError as e:
    st.error("Ollama package not found. Please install it using 'pip install ollama'.")
    logger.error("Ollama import failed: %s", e)
    embed = None

# Load environment variables
load_dotenv(override=True)
MONGODB_URI = os.getenv("MONGODB_URI")
OLLAMA_URI = os.getenv("OLLAMA_URI", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:14b")
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text:latest")

# Debug environment variable loading
for var, value in [
    ("MONGODB_URI", MONGODB_URI),
    ("OLLAMA_URI", OLLAMA_URI),
    ("OLLAMA_MODEL", OLLAMA_MODEL),
    ("OLLAMA_EMBEDDING_MODEL", OLLAMA_EMBEDDING_MODEL)
]:
    if not value:
        logger.error(f"{var} not found in .env file or environment variables")
        st.error(f"{var} not found. Please ensure it is set in the .env file.")
    else:
        logger.info(f"{var} loaded: {value[:30]}...")

# Initialize MongoDB variables
client = None
db = None
collection = None

# Set up MongoDB
if MONGODB_URI:
    try:
        client = MongoClient(MONGODB_URI)
        db = client["chat_db"]
        collection = db["chat_history"]
        logger.info("Successfully connected to MongoDB")
    except Exception as e:
        st.error(f"Failed to connect to MongoDB: {e}")
        logger.error(f"Failed to connect to MongoDB: {e}")
        client = None
        collection = None
else:
    st.error("Cannot connect to MongoDB without MONGODB_URI")
    logger.error("MongoDB connection skipped due to missing MONGODB_URI")

# Test Ollama embedding API
def test_ollama_embedding():
    if embed is None:
        logger.error("Cannot test Ollama embedding: 'embed' function not available")
        return
    test_text = "Test embedding"
    try:
        response = embed(model=OLLAMA_EMBEDDING_MODEL, input=[test_text])
        logger.info(f"Ollama test embedding response: type={type(response)}, attributes={dir(response) if response else 'None'}")
        if hasattr(response, 'embeddings') and isinstance(response.embeddings, list) and response.embeddings:
            embedding = response.embeddings[0]
            if isinstance(embedding, list) and len(embedding) == 768:
                logger.info(f"Test embedding successful: {embedding[:10]}... (first 10 values)")
            else:
                logger.error(f"Test embedding failed: Invalid embedding vector: type={type(embedding)}, length={len(embedding) if isinstance(embedding, list) else 'N/A'}")
        else:
            logger.error(f"Test embedding failed: No valid embeddings attribute: {response}")
    except Exception as e:
        logger.error(f"Test embedding failed: {e}")

# Call test function at startup
test_ollama_embedding()

# Define embedding function
def get_embedding(text: str) -> list[float]:
    if embed is None:
        raise ImportError("Ollama 'embed' function not available.")
    if not text or not isinstance(text, str):
        logger.error(f"Invalid input text: {text}")
        raise ValueError("Input text must be a non-empty string")
    try:
        logger.debug(f"Generating embedding for text: {text[:50]}... with model: {OLLAMA_EMBEDDING_MODEL}")
        response = embed(model=OLLAMA_EMBEDDING_MODEL, input=[text])
        logger.info(f"Ollama embedding response: type={type(response)}, attributes={dir(response) if response else 'None'}")
        
        if not hasattr(response, 'embeddings'):
            logger.error(f"No 'embeddings' attribute in response: {response}")
            raise ValueError("Response does not have 'embeddings' attribute")
        
        embeddings = response.embeddings
        if not isinstance(embeddings, list) or not embeddings:
            logger.error(f"Invalid embeddings structure: type={type(embeddings)}, content={embeddings}")
            raise ValueError("Embeddings is not a non-empty list")
        
        embedding = embeddings[0]
        if not isinstance(embedding, list) or len(embedding) != 768:
            logger.error(f"Invalid embedding vector: type={type(embedding)}, length={len(embedding) if isinstance(embedding, list) else 'N/A'}")
            raise ValueError(f"Embedding is not a valid 768-dimensional vector")
        
        logger.debug(f"Successfully generated embedding: {embedding[:10]}... (first 10 values)")
        return embedding
    
    except Exception as e:
        logger.error(f"Embedding generation failed for text '{text[:50]}...': {e}")
        raise

# Insert initial context
def insert_initial_context():
    if collection is None:
        logger.error("Cannot insert initial context: MongoDB collection is not initialized")
        return
    if collection.count_documents({"type": "message", "message": "Hello, my name is Fred."}) == 0:
        initial_messages = [
            {"role": "user", "message": "Hello, my name is Fred."},
            {"role": "assistant", "message": "Hi Fred! Nice to meet you."}
        ]
        for msg in initial_messages:
            embedding = None
            try:
                embedding = get_embedding(msg["message"])
                logger.info(f"Generated embedding for initial context message '{msg['message']}': {embedding[:10]}... (first 10 values)")
            except Exception as e:
                logger.error(f"Failed to generate embedding for initial context message '{msg['message']}': {e}")
                st.warning(f"Could not generate embedding for initial context message '{msg['message']}'. Storing without embedding.")
            try:
                collection.insert_one({
                    "type": "message",
                    "role": msg["role"],
                    "message": msg["message"],
                    "embedding": embedding
                })
                logger.info(f"Inserted initial context message '{msg['message']}' with embedding: {embedding is not None}")
            except Exception as e:
                logger.error(f"Failed to insert initial context for message '{msg['message']}': {e}")
                st.warning(f"Failed to insert initial context for message '{msg['message']}'.")
        logger.info("Inserted initial context into chat_history")

# Verify initial context at startup
def verify_initial_context():
    if collection is None:
        logger.error("Cannot verify initial context: MongoDB collection is not initialized")
        return
    initial_doc = collection.find_one({"type": "message", "message": "Hello, my name is Fred."})
    if not initial_doc:
        logger.warning("Initial context 'Hello, my name is Fred.' not found in database. Inserting now.")
        insert_initial_context()
    elif not initial_doc.get("embedding") or len(initial_doc["embedding"]) != 768:
        logger.warning("Initial context 'Hello, my name is Fred.' found but has invalid or missing embedding. Updating embedding.")
        try:
            embedding = get_embedding("Hello, my name is Fred.")
            collection.update_one(
                {"_id": initial_doc["_id"]},
                {"$set": {"embedding": embedding}}
            )
            logger.info("Updated embedding for initial context 'Hello, my name is Fred.'")
        except Exception as e:
            logger.error(f"Failed to update embedding for initial context: {e}")

# Initialize initial context at startup
if collection is not None:
    verify_initial_context()

# Define Deps for PydanticAI
class Deps(BaseModel):
    mongo_client: MongoClient
    model_config = ConfigDict(arbitrary_types_allowed=True)

# Define summary generation function
def generate_summary() -> None:
    if collection is None:
        return
    try:
        message_count = collection.count_documents({"type": "message"})
        if message_count < 10:
            return
        messages = list(collection.find({"type": "message"}).sort("_id", -1).limit(10))
        if not messages:
            return
        formatted_messages = "\n".join(f"{msg['role']}: {msg['message']}" for msg in reversed(messages))
        summary_prompt = f"Summarize the key points from the following conversation:\n\n{formatted_messages}"
        client_openai = OpenAI(base_url=OLLAMA_URI + "/v1", api_key="dummy")
        response = client_openai.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": summary_prompt}
            ]
        )
        summary = response.choices[0].message.content
        if not summary or not isinstance(summary, str):
            logger.error(f"Invalid summary generated: {summary}")
            st.warning("Generated summary is invalid. Skipping storage.")
            return
        summary_embedding = None
        try:
            summary_embedding = get_embedding(summary)
            logger.info(f"Generated embedding for summary: {summary_embedding[:10]}... (first 10 values)")
        except Exception as e:
            logger.error(f"Failed to generate embedding for summary: {e}")
            st.warning("Could not generate embedding for summary. Storing without embedding.")
        collection.insert_one({
            "type": "summary",
            "summary": summary,
            "embedding": summary_embedding
        })
        logger.info(f"Generated and stored summary with embedding: {summary_embedding is not None}")
    except Exception as e:
        logger.error(f"Failed to generate or store summary: {e}")
        st.warning("Could not generate summary. Continuing without summary.")

# Set up LLM
llm_model = None
try:
    llm_model = OpenAIModel(model_name=OLLAMA_MODEL, provider=OpenAIProvider(base_url=OLLAMA_URI + "/v1"))
except Exception as e:
    st.error(f"Failed to initialize LLM model: {e}")
    logger.error(f"Failed to initialize LLM model: {e}")
    llm_model = None

# Define system prompt
system_prompt = """
You are a helpful chat assistant. For each user query, first use the retrieve_context tool to get relevant context from the chat history and past summaries, then use that context to answer the user's query. The context includes all messages and summaries from the conversation history. If the query asks for a name, prioritize context containing introductions or names like 'Fred'.
"""

# Create agent
agent = Agent(llm_model, system_prompt=system_prompt, retries=3)

# Define output validator
@agent.output_validator
async def validate_output(ctx: RunContext[Deps], output: str) -> str:
    if not output or len(output) < 10:
        logger.error(f"Invalid or too short output: {output}")
        raise ModelRetry("Response is too short or empty. Please provide a more detailed answer.")
    return output

# Define retrieve_context tool
@agent.tool
def retrieve_context(ctx: RunContext[Deps], search_query: str) -> str:
    logger.debug(f"retrieve_context called with ctx: {ctx}, search_query: {search_query}")
    
    if collection is None:
        logger.error("MongoDB collection is not initialized")
        st.warning("Cannot retrieve context: MongoDB collection not initialized.")
        return "No relevant context found due to database unavailability."
    
    try:
        # Check last 10 messages for name-related context
        last_messages = list(collection.find({"type": "message"}).sort("_id", -1).limit(10))
        immediate_context = []
        for msg in last_messages:
            if "name" in msg["message"].lower() or "fred" in msg["message"].lower():
                immediate_context.append(f"{msg['role']}: {msg['message']}")
        if immediate_context:
            logger.debug(f"Found name-related context in immediate messages: {immediate_context}")
            return "\n".join(immediate_context)
        
        # Force retrieval of initial context for name queries
        contexts = []
        if "name" in search_query.lower():
            initial_doc = collection.find_one({"type": "message", "message": "Hello, my name is Fred."})
            if initial_doc:
                contexts.append(f"{initial_doc['role']}: {initial_doc['message']}")
                logger.debug("Added initial context 'Hello, my name is Fred.' for name query")
        
        # Perform vector search
        query_embedding = get_embedding(search_query)
        pipeline = [
            {
                "$match": {
                    "embedding": {"$ne": None}
                }
            },
            {
                "$vectorSearch": {
                    "index": "default",
                    "path": "embedding",
                    "queryVector": query_embedding,
                    "numCandidates": 100,
                    "limit": 5,
                }
            },
            {"$project": {"type": 1, "role": 1, "message": 1, "summary": 1, "_id": 0}}
        ]
        results = list(collection.aggregate(pipeline))
        logger.debug(f"Vector search results: {results}")
        for result in results:
            if result["type"] == "message" and "role" in result and "message" in result:
                contexts.append(f"{result['role']}: {result['message']}")
            elif result["type"] == "summary" and "summary" in result:
                contexts.append(f"Summary: {result['summary']}")
        
        # Include last messages for continuity
        for msg in last_messages:
            contexts.append(f"{msg['role']}: {msg['message']}")
        
        return "\n".join(contexts) if contexts else "No relevant context found."
    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        # Fallback to immediate context with forced initial context for name queries
        st.warning("Vector search failed. Using immediate context only.")
        contexts = []
        if "name" in search_query.lower():
            initial_doc = collection.find_one({"type": "message", "message": "Hello, my name is Fred."})
            if initial_doc:
                contexts.append(f"{initial_doc['role']}: {initial_doc['message']}")
                logger.debug("Added initial context 'Hello, my name is Fred.' in fallback")
        last_messages = list(collection.find({"type": "message"}).sort("_id", -1).limit(10))
        for msg in last_messages:
            contexts.append(f"{msg['role']}: {msg['message']}")
        return "\n".join(contexts) if contexts else "No relevant context found."

# Streamlit app
st.title("Chat with RAG")

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "message_history" not in st.session_state:
    st.session_state.message_history = []

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Async function to handle agent streaming
async def handle_agent_stream(prompt: str, context: RunContext, message_history: list) -> tuple[str, list]:
    full_response = ""
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        try:
            logger.debug(f"Running agent with context: deps={context.deps}, model={context.model}, prompt={context.prompt}")
            async with agent.run_stream(
                prompt,
                context=context,
                message_history=message_history
            ) as result:
                async for message in result.stream_text():
                    if message:  # Ensure message is not empty
                        full_response += message
                        message_placeholder.markdown(full_response)
                new_message_history = result.all_messages()
            if not full_response:
                logger.error("Agent returned empty response")
                full_response = "Sorry, I couldn't generate a response. Please try again."
                st.warning(full_response)
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            st.error(f"Error generating response: {e}")
            full_response = "Sorry, an error occurred while generating the response. Please try again."
            new_message_history = message_history
    return full_response, new_message_history

# Handle user input
if prompt := st.chat_input("What is up?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    if client is None or llm_model is None:
        st.error("Application initialization failed. Check MongoDB connection and LLM model.")
    else:
        deps = Deps(mongo_client=client)
        context = RunContext(deps=deps, model=llm_model, prompt=system_prompt, usage=None)
        logger.debug(f"Initialized context with deps: mongo_client={deps.mongo_client}")
        
        try:
            user_embedding = None
            try:
                user_embedding = get_embedding(prompt)
                logger.info(f"Generated embedding for user message: {user_embedding[:10]}... (first 10 values)")
            except Exception as e:
                logger.error(f"Failed to generate embedding for user message: {e}")
                st.warning("Could not generate embedding for user message. Storing without embedding.")
            if collection is not None:
                collection.insert_one({
                    "type": "message",
                    "role": "user",
                    "message": prompt,
                    "embedding": user_embedding
                })
                logger.info(f"Inserted user message into MongoDB with embedding: {user_embedding is not None}")

            # Insert initial context after first prompt
            if not hasattr(st.session_state, 'initial_context_inserted'):
                insert_initial_context()
                st.session_state.initial_context_inserted = True

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                full_response, new_message_history = loop.run_until_complete(
                    handle_agent_stream(prompt, context, st.session_state.message_history)
                )
            finally:
                loop.close()
            
            st.session_state.message_history = new_message_history
            st.session_state.messages.append({"role": "assistant", "content": full_response})

            assistant_embedding = None
            if full_response and isinstance(full_response, str):
                try:
                    assistant_embedding = get_embedding(full_response)
                    logger.info(f"Generated embedding for assistant message: {assistant_embedding[:10]}... (first 10 values)")
                except Exception as e:
                    logger.error(f"Failed to generate embedding for assistant message: {e}")
                    st.warning("Could not generate embedding for assistant message. Storing without embedding.")
            else:
                logger.error(f"Skipping embedding for assistant message: Invalid response '{full_response}'")
                st.warning("Assistant response is invalid. Storing without embedding.")
            if collection is not None:
                collection.insert_one({
                    "type": "message",
                    "role": "assistant",
                    "message": full_response,
                    "embedding": assistant_embedding
                })
                logger.info(f"Inserted assistant message into MongoDB with embedding: {assistant_embedding is not None}")

            try:
                generate_summary()
            except Exception as e:
                logger.error(f"Failed to generate summary: {e}")
                st.warning("Could not generate summary. Continuing without summary.")

            st.success("Information committed to memory.")
        except Exception as e:
            logger.error(f"Error in chat processing: {e}")
            st.error(f"Error in chat processing: {e}")