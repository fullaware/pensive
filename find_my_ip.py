import os
import subprocess
from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext, Tool
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from dotenv import load_dotenv


load_dotenv()

model = OpenAIModel(
    # model_name=os.getenv('OLLAMA_MODEL'), # granite is not good for this
    # model_name='llama3.1:8b-instruct-q8_0', # Recommended LLM for tools
    model_name='qwen3:14b', # Recommended LLM for tools
    # model_name='llama3.1:8b', # Default LLM  
    provider=OpenAIProvider(base_url='http://localhost:11434/v1'), # Default LLM URI
)


class ResponseModel(BaseModel):
    """Automatic Structured response with metadata."""
    continent_location: str 
    country_location: str
    city_location: str
    internet_provider: str = Field(description="what is the name of internet service provider")
    ip_address_v4: str = Field(description="what is IP address (version 4) - IPv4")
    ip_address_v6: str = Field(description="what is IP address (version 6) - IPv6")


agent = Agent(
    model=model,
    result_type=ResponseModel,
    system_prompt=(
        "You are an intelligent research agent. "
        "Analyze user request carefully and provide structured responses and use suitble tools to fullfil user request"
    ),
    result_retries = 3
)

@agent.tool_plain
def get_current_ip_address() -> str:
    """Get public IP address using ifconfig.me website"""
    command = ['curl','ifconfig.me']
    result = subprocess.run(command, capture_output=True, text=True)
    print(result.stdout)
    return result.stdout
    
@agent.tool_plain
def get_ip_info_with_whois(ip_to_track) -> str:
    """Get information about the IP address using Whois"""
    command = ['whois', ip_to_track]
    result = subprocess.run(command, capture_output=True, text=True)
    print(result.stdout)
    return result.stdout


data_list = []

response = agent.run_sync("can you guess where I am now?")
print(response.output.model_dump_json(indent=2))

# Uncomment to debug :)
print("--------------Debug----------------\n\n\n")
print(str(response.usage()))
print(response.all_messages())