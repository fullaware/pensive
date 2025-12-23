"""Memory extraction functions for topics, keywords, and entities."""
import json
import logging
from openai import OpenAI
from config import LLM_URI, LLM_API_KEY, LLM_MODEL, logger

def extract_topics_and_keywords(text: str) -> dict:
    """Extract topics and keywords from text using LLM."""
    if not text or not isinstance(text, str) or len(text.strip()) < 10:
        return {"topics": [], "keywords": []}
    
    if not LLM_URI or not LLM_MODEL:
        logger.warning("LLM not configured for topic/keyword extraction")
        return {"topics": [], "keywords": []}
    
    try:
        client_openai = OpenAI(base_url=LLM_URI, api_key=LLM_API_KEY or "not-needed")
        prompt = f"""Extract 3-5 main topics and 5-10 key keywords from this text. 
Return ONLY valid JSON in this exact format: {{"topics": ["topic1", "topic2"], "keywords": ["keyword1", "keyword2"]}}

Text: {text[:1000]}"""
        
        response = client_openai.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that extracts topics and keywords. Always return valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        
        result_text = response.choices[0].message.content.strip()
        # Try to extract JSON from response
        if "{" in result_text:
            json_start = result_text.find("{")
            json_end = result_text.rfind("}") + 1
            result_text = result_text[json_start:json_end]
        
        result = json.loads(result_text)
        return {
            "topics": result.get("topics", [])[:5],
            "keywords": result.get("keywords", [])[:10]
        }
    except Exception as e:
        logger.warning(f"Failed to extract topics/keywords: {e}")
        return {"topics": [], "keywords": []}

def extract_entities(text: str) -> list:
    """Extract entities (people, organizations, projects, locations) from text using LLM."""
    if not text or not isinstance(text, str) or len(text.strip()) < 10:
        return []
    
    if not LLM_URI or not LLM_MODEL:
        logger.warning("LLM not configured for entity extraction")
        return []
    
    try:
        client_openai = OpenAI(base_url=LLM_URI, api_key=LLM_API_KEY or "not-needed")
        prompt = f"""Extract entities (people, organizations, projects, locations) from this text.
Return ONLY valid JSON array in this exact format: [{{"type": "person|org|project|location", "name": "Entity Name", "context": "brief context"}}]

Text: {text[:1000]}"""
        
        response = client_openai.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that extracts entities. Always return valid JSON array only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        
        result_text = response.choices[0].message.content.strip()
        # Try to extract JSON from response
        if "[" in result_text:
            json_start = result_text.find("[")
            json_end = result_text.rfind("]") + 1
            result_text = result_text[json_start:json_end]
        
        entities = json.loads(result_text)
        # Validate and filter entities
        valid_entities = []
        for entity in entities:
            if isinstance(entity, dict) and "type" in entity and "name" in entity:
                if entity["type"] in ["person", "org", "project", "location"]:
                    valid_entities.append({
                        "type": entity["type"],
                        "name": entity["name"],
                        "context": entity.get("context", "")
                    })
        return valid_entities[:10]  # Limit to 10 entities
    except Exception as e:
        logger.warning(f"Failed to extract entities: {e}")
        return []


