"""Fact Extractor using Gemini 2.5 Flash with structured JSON output."""

import json
from typing import List, Dict, Any
from ..config import settings
from ..models.memory import Fact, ExtractionResult, MemoryCategory


EXTRACTION_SYSTEM_PROMPT = """You are an expert cognitive memory extraction engine for AI agents.
Your job is to read conversational turns between a User and an AI Agent, and extract ATOMIC, PERMANENT FACTS about the user, their environment, their preferences, their constraints, or their project decisions.

CRITICAL RULES:
1. IGNORE SMALL TALK: Greetings ("hello", "how are you"), pleasantries ("thanks", "bye"), or temporary conversational filler have NO meaningful memory value.
2. EXTRACT ATOMIC FACTS: Each fact must be a standalone, self-contained statement (e.g., "User uses Windows 11 with Python 3.12" or "User is vegetarian and allergic to peanuts").
3. CLASSIFY CAREFULLY:
   - PREFERENCE: coding style, habits, likes/dislikes
   - FACT: identity, role, location, tech stack
   - DECISION: project architecture decisions, approved frameworks
   - CONSTRAINT: allergies, hard limitations, strict budgets
   - EPISODIC: major events or milestones
4. IDENTIFY ENTITY & ATTRIBUTE:
   - entity: the subject (e.g. "user", "project", "database")
   - attribute: specific property (e.g. "location", "primary_language", "diet")
   - value: current value (e.g. "Tokyo", "TypeScript", "Vegetarian")
5. IMPORTANCE: Rate importance from 0.0 (trivial trivia) to 1.0 (vital constraint or hard requirement).
"""


class FactExtractor:
    """Extracts structured facts from raw conversational messages."""

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or settings.gemini_api_key
        self.model = model or settings.extraction_model
        self._client = None

        if self.api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except Exception:
                self._client = None

    def extract(self, messages: List[Dict[str, str]]) -> ExtractionResult:
        """Extracts atomic facts from a list of conversation turns."""
        if not messages:
            return ExtractionResult(facts=[], has_meaningful_content=False, summary_of_interaction="Empty message history")

        # Format conversation for the prompt
        convo_text = ""
        for m in messages:
            role = m.get("role", "user").capitalize()
            content = m.get("content", "")
            convo_text += f"{role}: {content}\n"

        # If live Gemini Client is available, call Gemini 2.5 Flash with structured output
        if self._client:
            try:
                from google.genai import types
                
                response = self._client.models.generate_content(
                    model=self.model,
                    contents=[convo_text],
                    config=types.GenerateContentConfig(
                        system_instruction=EXTRACTION_SYSTEM_PROMPT,
                        response_mime_type="application/json",
                        response_schema=ExtractionResult,
                        temperature=0.1,
                    ),
                )
                if response.text:
                    data = json.loads(response.text)
                    return ExtractionResult.model_validate(data)
            except Exception as e:
                # Fall back to heuristic rule-based extraction if API fails or offline
                pass

        return self._rule_based_fallback_extract(messages)

    def _rule_based_fallback_extract(self, messages: List[Dict[str, str]]) -> ExtractionResult:
        """Heuristic rule-based extractor used for offline testing when no API key is provided."""
        facts: List[Fact] = []
        user_texts = [m.get("content", "") for m in messages if m.get("role") == "user"]
        combined = " ".join(user_texts).lower()

        # Basic small-talk check
        small_talk_words = ["hi", "hello", "hey", "thanks", "thank you", "ok", "okay", "bye", "how are you"]
        is_only_small_talk = all(w in small_talk_words for w in combined.split() if len(w) > 1)
        if is_only_small_talk and len(combined.split()) < 5:
            return ExtractionResult(facts=[], has_meaningful_content=False, summary_of_interaction="Greeting only")

        # Common statement patterns for demo/offline test
        import re

        # Location patterns (e.g. "I live in Tokyo", "moved to London")
        loc_match = re.search(r"(?:live in|moved to|relocated to|located in)\s+([A-Za-z\s]+?)(?:\.|\,|$|\sand)", combined)
        if loc_match:
            loc = loc_match.group(1).strip().title()
            facts.append(Fact(
                statement=f"User lives in {loc}",
                category=MemoryCategory.FACT,
                entity="user",
                attribute="location",
                value=loc,
                importance=0.85
            ))

        # Preference patterns (e.g. "I prefer TypeScript", "I love Python")
        pref_match = re.search(r"(?:prefer|prefer using|love|frequently use)\s+([A-Za-z0-9#\+\s]+?)(?:\.|\,|$|\sover|\sbecause)", combined)
        if pref_match:
            pref = pref_match.group(1).strip().title()
            facts.append(Fact(
                statement=f"User prefers using {pref}",
                category=MemoryCategory.PREFERENCE,
                entity="user",
                attribute="preference",
                value=pref,
                importance=0.75
            ))

        # Cloud provider / migration patterns (e.g. "migrate from AWS to Google Cloud", "hosted on AWS")
        cloud_match = re.search(r"(?:hosted on|deployed on|migrate(?:d)? (?:our cloud )?from \w+ to|switch(?:ed)? to)\s+([A-Za-z0-9\s]+?)(?:\.|\,|$|\sand)", combined)
        if cloud_match:
            cloud = cloud_match.group(1).strip().title()
            facts.append(Fact(
                statement=f"User hosts infrastructure on {cloud}",
                category=MemoryCategory.DECISION,
                entity="project",
                attribute="cloud_provider",
                value=cloud,
                importance=0.85
            ))

        # Tech stack / database patterns (e.g. "build with FastAPI and PostgreSQL")
        if "fastapi" in combined:
            facts.append(Fact(
                statement="User builds core backend with FastAPI",
                category=MemoryCategory.DECISION,
                entity="project",
                attribute="backend_framework",
                value="FastAPI",
                importance=0.85
            ))
        if "postgresql" in combined or "postgres" in combined:
            facts.append(Fact(
                statement="User uses PostgreSQL database",
                category=MemoryCategory.DECISION,
                entity="project",
                attribute="database",
                value="PostgreSQL",
                importance=0.90
            ))

        # Generic fallback if meaningful text without matched regex
        if not facts and len(combined.strip()) > 10 and not is_only_small_talk:
            facts.append(Fact(
                statement=user_texts[0].strip(),
                category=MemoryCategory.FACT,
                entity="user",
                attribute="statement",
                value=user_texts[0].strip(),
                importance=0.60
            ))

        return ExtractionResult(
            facts=facts,
            has_meaningful_content=len(facts) > 0,
            summary_of_interaction=f"Extracted {len(facts)} facts from message"
        )
