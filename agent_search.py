from pydantic_ai import Agent
from pydantic_ai.common_tools.duckduckgo import duckduckgo_search_tool
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

model = OpenAIModel(
    # model_name=os.getenv('OLLAMA_MODEL'), # granite is not good for this
    # model_name='llama3.1:8b-instruct-q8_0', # Recommended LLM for tools
    model_name='qwen3:14b', # Recommended LLM for tools
    # model_name='llama3.1:8b', # Default LLM  
    provider=OpenAIProvider(base_url='http://localhost:11434/v1'), # Default LLM URI
)

agent = Agent(
    model,
    tools=[duckduckgo_search_tool()],
    system_prompt='Search DuckDuckGo for the given query and return the results.',
)

result = agent.run_sync(
    'Can you list the top five highest-grossing animated films of 2025?'
)
print(result.output)