from __future__ import annotations

import json
import re
import requests

from ai.routing.routing_result import RoutingResult
from ai.routing.routing_rules import classify_by_rules, get_default_model_for_task

CLASSIFIER_SYSTEM_PROMPT = """You are the central orchestration brain and task router for Jarvis.
Your job is to analyze the user message and recommend the best specialized model.

The models and their specialties are:
- 'deepseek-coder': programming tasks, code debugging, writing Python/scripts, GUI architecture, automations.
- 'gemma': conversational voice assistants, overlays, low-latency creative responses.
- 'mistral': logical reasoning, task planning/decomposition, workflow orchestration, logic puzzles.
- 'qwen2.5-vl': vision processing, screenshot analysis, UI element detection, OCR extraction.
- 'qwen': autonomous agent loop next-step decisions, observation analysis, tool execution reasoning.
- 'phi3': fast, lightweight answers, quick background helper tasks.
- 'llama3': normal chat, general questions, everyday tasks.

Analyze the user's latest request and output a raw JSON object in this exact schema:
{
  "task_type": "coding | voice | planning | vision | agent | fast | general",
  "recommended_model": "deepseek-coder | gemma | mistral | qwen2.5-vl | qwen | phi3 | llama3",
  "confidence": <float between 0.0 and 1.0>,
  "reason": "<short Czech or English explanation>"
}

Rule: Output ONLY the raw JSON object. Do not include markdown codeblocks (do not wrap in ```json), do not output introductory text, explanations, or thinking. Just the raw JSON block starting with { and ending with }."""


def classify_task_llm(prompt: str) -> RoutingResult:
    # 1. Prepare classification request using llama3
    messages = [
        {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
        {"role": "user", "content": f"User query to classify: '{prompt}'"}
    ]
    
    try:
        response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": "llama3",
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": 0.0,  # Deterministic routing
                    "num_predict": 150
                }
            },
            timeout=8
        )
        
        if response.status_code == 200:
            result_text = response.json().get("message", {}).get("content", "").strip()
            
            # Clean markdown code blocks if the LLM wrapped it anyway
            if result_text.startswith("```"):
                result_text = re.sub(r"^```(?:json)?\n", "", result_text)
                result_text = re.sub(r"\n```$", "", result_text)
                result_text = result_text.strip()
            
            # Extract JSON block using regex if there's any surrounding text
            json_match = re.search(r"\{.*\}", result_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                task_type = data.get("task_type", "general")
                recommended_model = data.get("recommended_model", "llama3")
                confidence = float(data.get("confidence", 0.8))
                reason = data.get("reason", "Llama3 LLM classification")
                
                return RoutingResult(task_type, recommended_model, confidence, reason)
                
    except Exception as e:
        print(f"[ROUTER] Llama3 classification request failed: {e}")
        
    # Failsafe: Fallback to rule-based static classification
    print("[ROUTER] Using static keyword rules classification as failsafe.")
    task_type = classify_by_rules(prompt)
    recommended_model = get_default_model_for_task(task_type)
    return RoutingResult(
        task_type=task_type,
        recommended_model=recommended_model,
        confidence=0.50,
        reason="Failsafe static rules"
    )
