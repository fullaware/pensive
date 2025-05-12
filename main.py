import streamlit as st
import uuid
from pymongo import MongoClient
from ollama import embed
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai import Agent, RunContext
from pydantic import BaseModel, ConfigDict
import os
from dotenv import load_dotenv
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logging.getLogger("pymongo").setLevel(logging.INFO)

# Load environment variables from .env file
load_dotenv()
MONGODB_URI = os.getenv("MONGODB_URI")
OLLAMA_URI = os.getenv("OLLAMA_URI")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")

# Set up MongoDB
try:
    client = MongoClient(MONGODB_URI)
    db = client["chat_db"]
    collection = db["chat_history"]
except Exception as e:
    st.error(f"Failed to connect to MongoDB: {e}")
    client = None
    collection = None

# Create vector search index if not exists
if collection is not None:
    index_name = "default"
    index_def = {
        "mappings": {
            "dynamic": True,
            "fields": {
                "embedding": {
                    "dimensions": 768,
                    "similarity": "cosine",
                    "type": "knnVector"
                }
            }
        }
    }
    try:
        if not collection.list_search_indexes():
            collection.create_search_index(index_def, name=index_name)
            logger.info("Created MongoDB vector search index")
    except Exception as e:
        st.error(f"Failed to create MongoDB vector search index: {e}")
        logger.error(f"Failed to create MongoDB vector search index: {e}")

# Insert initial context if not present
if collection is not None:
    if collection.count_documents({"session_id": "initial"}) == 0:
        initial_messages = [
            {"role": "user", "message": "Hello, my name is Fred."},
            {"role": "assistant", "message": "Hi Fred! Nice to meet you."}
        ]
        for msg in initial_messages:
            try:
                embedding = get_embedding(msg["message"])
                collection.insert_one({
                    "session_id": "initial",
                    "role": msg["role"],
                    "message": msg["message"],
                    "embedding": embedding
                })
            except Exception as e:
                logger.error(f"Failed to insert initial context for message '{msg['message']}': {e}")
        else:
            logger.info("Inserted initial context into chat_history")

# Define Deps for PydanticAI
class Deps(BaseModel):
    mongo_client: MongoClient
    session_id: str
    model_config = ConfigDict(arbitrary_types_allowed=True)

# Define embedding function
def get_embedding(text):
    try:
        response = embed(model='nomic-embed-text', input=[text])
        logger.debug(f"Ollama API response: {response}")
        if not response or not isinstance(response, dict) or not response.get('embeddings'):
            raise ValueError("Invalid or empty embedding response from Ollama")
        embeddings = response['embeddings']
        if not isinstance(embeddings, list) or not embeddings or not isinstance(embeddings[0], list):
            raise ValueError("Embeddings field is not a valid list of vectors")
        embedding = embeddings[0]
        if not isinstance(embedding, list) or len(embedding) != 768:
            raise ValueError(f"Embedding is not a valid 768-dimensional vector: {embedding}")
        return embedding
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        raise

# Set up LLM
try:
    llm_model = OpenAIModel(model_name=OLLAMA_MODEL, provider=OpenAIProvider(base_url=OLLAMA_URI + "/v1"))
except Exception as e:
    st.error(f"Failed to initialize LLM model: {e}")
    llm_model = None

# Define system prompt
system_prompt = """
You are a helpful chat assistant. For each user query, first use the retrieve_context tool to get relevant context from the chat history, then use that context to answer the user's query.
"""

# Create agent
agent = Agent(llm_model, system_prompt=system_prompt)

# Define retrieve_context tool
@agent.tool
def retrieve_context(ctx: RunContext[Deps], search_query: str) -> str:
    if ctx.deps is None:
        logger.error("Dependencies not provided to RunContext")
        raise ValueError("Dependencies not provided to RunContext")
    logger.debug(f"RunContext deps: {ctx.deps}")
    collection = ctx.deps.mongo_client["chat_db"]["chat_history"]
    try:
        query_embedding = get_embedding(search_query)
        pipeline = [
            {"$match": {"session_id": ctx.deps.session_id}},
            {
                "$vectorSearch": {
                    "index": "default",
                    "path": "embedding",
                    "query": query_embedding,
                    "numCandidates": 50,
                    "limit": 5,
                }
            },
            {"$project": {"message": 1, "_id": 0}}
        ]
        results = list(collection.aggregate(pipeline))
        contexts = [result['message'] for result in results]
        return "\n".join(contexts)
    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        raise

# Streamlit app
st.title("Chat with RAG")

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Handle user input
if prompt := st.chat_input("What is up?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Set up dependencies
    if client is None or llm_model is None:
        st.error("Application initialization failed. Check MongoDB connection and LLM model.")
    else:
        deps = Deps(mongo_client=client, session_id=st.session_state.session_id)
        context = RunContext(deps=deps, model=llm_model, prompt=system_prompt, usage=None)
        
        # Generate response
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            try:
                result = agent.run_sync(prompt, context=context)
                full_response = result.output
                message_placeholder.markdown(full_response)
            except Exception as e:
                logger.error(f"Error generating response: {e}")
                st.error(f"Error generating response: {e}")
                full_response = "Sorry, an error occurred while generating the response."
        
        # Append assistant's response
        st.session_state.messages.append({"role": "assistant", "content": full_response})
        
        # Store in MongoDB
        if collection is not None:
            try:
                user_embedding = get_embedding(prompt)
                logger.debug(f"User embedding: {user_embedding}")
                collection.insert_one({
                    "session_id": st.session_state.session_id,
                    "role": "user",
                    "message": prompt,
                    "embedding": user_embedding
                })
                
                assistant_embedding = get_embedding(full_response)
                logger.debug(f"Assistant embedding: {assistant_embedding}")
                collection.insert_one({
                    "session_id": st.session_state.session_id,
                    "role": "assistant",
                    "message": full_response,
                    "embedding": assistant_embedding
                })
            except Exception as e:
                logger.error(f"Error storing messages in MongoDB: {e}")
                st.error(f"Error storing messages in MongoDB: {e}")