import os
import random
import json
import time
import openmeteo_requests
import requests_cache
from datetime import datetime, timezone
from pprint import pprint
from retry_requests import retry
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.common_tools.duckduckgo import duckduckgo_search_tool
from pydantic import BaseModel
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError, PyMongoError

load_dotenv(override=True)

LLM_MODEL = os.getenv('LLM_MODEL')
LLM_URI = os.getenv('LLM_URI')
LLM_API_KEY = os.getenv('LLM_API_KEY')
# MongoDB connection
MONGODB_URI = os.getenv('MONGODB_URI')
client = MongoClient(MONGODB_URI)
db = client.asteroids
elements_collection = db.elements

class ResponseModel(BaseModel):
    weather: str 
    temperature: float
    current_date: str
    roll: int
    usecase: str
    elements: list[str]
    recommended_websites: list[str]
    satisfaction_score: int | None = None
    satisfaction_feedback: str | None = None

class GetElementsUsecase(BaseModel):
    usecase: str

class GetElementsOutput(BaseModel):
    elements: list[str]

# Track which tools have been used in a run
class GetCurrentDateInput(BaseModel):
    """No inputs required for current date"""
    pass

class GetCurrentDateOutput(BaseModel):
    """Response for getting current date"""
    current_date: str

class GetWeatherInput(BaseModel):
    """Input for getting weather"""
    city: str

class GetWeatherOutput(BaseModel):
    """Response for getting weather"""
    weather: str
    temperature: float

# Configure OpenRouter API with OpenAI-compatible base URL
model = OpenAIChatModel(
    model_name=LLM_MODEL, # Recommended LLM for tools
    # model_name='llama3.1:8b', # Default LLM  
    provider=OpenAIProvider(base_url=LLM_URI, api_key=LLM_API_KEY), # Default LLM URI
)

agent = Agent(model, output_type=ResponseModel, output_retries=5, 
              model_settings={'temperature': 0.0},
              deps_type=str,
              tools=[duckduckgo_search_tool()],
              system_prompt=f"""You are a helpful assistant. You have access to tools to help you answer questions. 
        - Assess which tool you should use to answer the question. 
        - Use get_current_date() to get the current date as YYYY-MM-DD. 
        - Use get_weather(city) to get the current weather in a city. 
        - Use roll_dice() to roll a 20-sided dice and return the result.
        - Use get_valid_usecase() to find a valid usecase for get_elements_by_usecase(usecase).
        - Use get_elements_by_usecase(usecase) to get elements by usecase
        - Use duckduckgo_search_tool() to search for recommended websites.
        - Please provide a satisfaction_score of 0-10 to rate our interaction.  0 = Positive, 10 = Negative
        - Please provide satisfaction_feedback as STR on how we can make our interactions better
        Ensure that you use all the tools at least once in your response.
        Finally, respond with a complete JSON document once you have a final answer.
        """,
)


@agent.tool  
def get_current_date(_: RunContext[GetCurrentDateInput]) -> GetCurrentDateOutput:
    """Get the current date in YYYY-MM-DD format."""
    current_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    print(f"get_current_date : {current_date}")
    return GetCurrentDateOutput(current_date=current_date)

@agent.tool
def get_weather(_: RunContext[GetWeatherInput], city: str) -> GetWeatherOutput:
    print(f"get_weather : {city}")
    if not city:
        raise ValueError("City is missing!")
    
    # Setup the Open-Meteo API client with cache and retry on error
    cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
    retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
    openmeteo = openmeteo_requests.Client(session = retry_session)

    # Make sure all required weather variables are listed here
    # The order of variables in hourly or daily is important to assign them correctly below
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": 34.0515,
        "longitude": -84.0713,
        "daily": "precipitation_probability_max",
        "current": ["temperature_2m", "precipitation","weather_code"],
        "timezone": "America/New_York",
        "forecast_days": 3,
        "wind_speed_unit": "mph",
        "temperature_unit": "fahrenheit",
        "precipitation_unit": "inch"
    }
    responses = openmeteo.weather_api(url, params=params)

    # Process first location. Add a for-loop for multiple locations or weather models
    response = responses[0]
    current = response.Current()
    current_temperature_2m = float(current.Variables(0).Value())
    current_weather_code = str(current.Variables(2).Value())
    print(f"current_temperature_2m : {current_temperature_2m}")
    print(f"current_weather_code : {current_weather_code}")
    return GetWeatherOutput(weather=current_weather_code, temperature=current_temperature_2m)

@agent.tool_plain
def roll_dice() -> str:
    """Roll a 20-sided dice."""
    roll = str(random.randint(1, 20))
    print(f"roll_dice : {roll}")
    return roll

@agent.tool
def get_elements_by_usecase(_: RunContext[GetElementsUsecase], usecase: str)-> GetElementsOutput:
    """Get list of elements by usecase."""
    
    print(f"get_elements_by_usecase : {usecase}")
   
    try:
    elements = elements_collection.find({"uses": usecase}, {"_id": 0, "name": 1})
    elements_by_use = [element['name'] for element in elements]
    except (ServerSelectionTimeoutError, PyMongoError) as e:
        print(f"MongoDB connection error: {e}")
        print("Returning empty list due to MongoDB connection failure")
        elements_by_use = []
    # print(f"Elements: {elements_by_use}")
    return GetElementsOutput(elements=elements_by_use)

@agent.tool_plain
def get_valid_usecase()-> str:
    """Provide a random usecase from a list of valid usecases for elements mined from asteroids."""
    valid_usecases = [
    "fuel", "lifesupport", "energystorage", "construction", "electronics", 
    "coolants", "industrial", "medical", "propulsion", "shielding", 
    "agriculture", "mining"
    ]
    valid_usecase = random.choice(valid_usecases)
    print(f"get_usecase : {valid_usecase}")
    return valid_usecase


if __name__ == "__main__":

    query = f"/nothink Please provide the current date, the weather in New York, roll a 20-sided dice, select a usecase for elements mined from asteroids then provide a list of elements based on the found usecase. Recommend 3 websites where MongoDB and AI are mentioned, but they cannot be from mongodb.com.  Ensure that you use all the tools at least once in your response."
    max_retries = 5
    valid_response = None
    
    # Start timing
    start_time = time.time()
    
    for attempt in range(max_retries):
        result = agent.run_sync(query, model_settings={'temperature': 0.0})
        # If result.data is not None (i.e. valid ResponseModel), keep it
        if result.output:
            valid_response = result.output
            # Calculate elapsed time when valid response is found
            elapsed_time = time.time() - start_time
            print(f"Valid response found in {elapsed_time:.2f} seconds (attempt {attempt + 1}/{max_retries})")
            break

    if not valid_response:
        # Calculate elapsed time even on failure
        elapsed_time = time.time() - start_time
        print(f"Failed to produce a valid ResponseModel after {max_retries} attempts ({elapsed_time:.2f} seconds).")
    else:
        # Print final result as JSON
        pprint(json.loads(valid_response.model_dump_json()))
        
        # If we haven't printed the timing yet (in case we want to move the timing print)
        if 'elapsed_time' not in locals():
            elapsed_time = time.time() - start_time
            print(f"Total execution time: {elapsed_time:.2f} seconds")

