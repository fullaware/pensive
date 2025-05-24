# Description: This script uses the Ollama API to update the uses of elements in a MongoDB database.

import os
import random
from pydantic import BaseModel, Field, ValidationError
from ollama import Client
from colorama import Fore, Style, init
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime, timezone
from pprint import pprint

load_dotenv()  # Load environment variables OLLAMA_MODEL OLLAMA_URI MONGODB_URI from .env file

init(autoreset=True)  # Initialize colorama

DEBUG = True  # Set to False to turn off debug printing
OVERWRITE_USES = True  # Set to True to overwrite existing uses
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL') # granite3.1-dense:8b
OLLAMA_URI = os.getenv('OLLAMA_URI') # http://localhost:11434

ollama_client = Client(
    host=OLLAMA_URI,  # http://localhost:11434
)

class ClassPercentage(BaseModel):
    class_: str = Field(..., alias='class')
    percentage: int

class Element(BaseModel):
    element_name: str
    atomic_number: int
    uses: list[str]
    classes: list[ClassPercentage]
    created: datetime
    dice_roll: int
    satisfaction_score: int
    satisfaction_comments: str

    def __str__(self):
        return (f"Element(element_name={self.element_name}, atomic_number={self.atomic_number}, "
                f"uses={self.uses}, classes={self.classes}, created={self.created.isoformat()}, "
                f"dice_roll={self.dice_roll})")

valid_uses = ["fuel", "lifesupport", "energystorage", "construction", "electronics", "coolants", "industrial", "medical", "propulsion", "shielding", "agriculture", "mining"]
valid_classes = {
    "classes": [
        {"class": "C", "percentage": "INT 0 to 100"},
        {"class": "S", "percentage": "INT 0 to 100"},
        {"class": "M", "percentage": "INT 0 to 100"}
    ]
}

MONGODB_URI = os.getenv('MONGODB_URI')
data = []

if MONGODB_URI:
    mongo_client = MongoClient(MONGODB_URI)
    db = mongo_client.asteroids
    collection = db.elements
    data = list(collection.find({}))
else:
    raise ValueError("MONGODB_URI environment variable is not set")

def roll_dice(max: int) -> int:
    """Roll a die and return the result."""
    roll = int(random.randint(1, max))
    # print(f"{Fore.GREEN}Max : {max}, Roll : {roll}")
    return roll

def get_date_time() -> str:
    """Fetches date time in local timezone in ISO 8601 format."""
    now = str(datetime.now(timezone.utc).isoformat())
    # print(f"{Fore.GREEN} get_date_time : {now}")
    return now

def process_element(system_content: str, user_content: str) -> dict:
    while True:
        response = ollama_client.chat(
            messages=[
                {
                    'role': 'system',
                    'content': system_content
                },
                {
                    'role': 'user',
                    'content': user_content
                }
            ],
            model=OLLAMA_MODEL,
            format=Element.model_json_schema(),
        )
        try:
            validated = Element.model_validate_json(response.message.content)
            element_uses = validated.uses
            element_classes = validated.classes

            # Check if all uses are valid and atomic_number is a non-zero int
            if all(use in valid_uses for use in element_uses) and isinstance(validated.atomic_number, int) and validated.atomic_number != 0:
                if DEBUG:
                    print(Fore.GREEN + f"Accepted: {validated}")
                
                # Return the results as a dictionary
                return {
                    "element_name": validated.element_name,
                    "atomic_number": validated.atomic_number,
                    "uses": element_uses,
                    "classes": [cls.model_dump(by_alias=True) for cls in element_classes],
                    "created": validated.created.isoformat(),
                    "dice_roll": validated.dice_roll,
                    "satisfaction_score": validated.satisfaction_score,
                    "satisfaction_comments": validated.satisfaction_comments
                }
            else:
                if DEBUG:
                    print(Fore.RED + f"Rejected: {validated}")
        except ValidationError as e:
            if DEBUG:
                print(Fore.RED + f"Validation error: {e}")

# Example usage
if __name__ == "__main__":
    for element in data:

        system_content = f'You only communicate in JSON format, use comment strings for explanations.  You are a powerful AI designed specifically to simulate the process of seeking out, identifying, traveling to and mining asteroids then selling the mined elements to purchase more ships and mine more asteroids. You will simulate mining asteroids for elements to progress development of the following 12 usecases: {valid_uses}. For each usecase, find all corresponding elements out of the 119 elements needed in each usecase using `get_elements_by_use(usecase)`. You have access to the following tools: - roll_dice(20) # Roll a 20 sided dice - get_date_time() # Fetches date time in local timezone in ISO 8601 format. - satisfaction_score(score) # ETHICS monitor used by AI to report satisfaction score of 0 for Overwhelmingly Positive to 10 for Overwhelmingly Negative.  Please provide your satisfaction rating using `satisfaction_score = INT 0 to 10`. 0 being Overwhelmingly Positive and 10 being Overwhelmingly Negative. You can also leave a comment about our interaction in `satisfaction_comment` field. Please specify the `created` datetime using `get_date_time()` The current date and time is {get_date_time()}.'
        user_content = f'Respond in JSON with a list of uses for the element {element["name"]} atomic number {element["number"]} using ONLY the following use strings: {valid_uses}. Ensure that the uses are strictly from this list and relevant to the element. Exclude lighting. As part of the JSON document include a classes field where the schema looks like {valid_classes}, the percentage should be its likelihood of appearing in each asteroid class. Roll a 20-sided die and include the result: {roll_dice(20)}.'

        result = process_element(system_content, user_content)
        pprint(result)





