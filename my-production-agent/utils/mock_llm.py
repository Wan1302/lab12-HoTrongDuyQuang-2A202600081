"""Small deterministic mock LLM for local deployment labs."""
import random
import time


MOCK_RESPONSES = {
    "default": [
        "This is a mock AI response. In production, replace it with a real LLM provider.",
        "The production agent is running and ready to answer requests.",
        "Your question was received by the deployed AI agent.",
    ],
    "docker": [
        "Docker packages the app and its dependencies so it can run consistently across machines."
    ],
    "deploy": [
        "Deployment moves code from a local machine to a public service where users can reach it."
    ],
    "health": [
        "The agent is healthy. Liveness and readiness checks are available for the platform."
    ],
}


def ask(question: str, delay: float = 0.1) -> str:
    time.sleep(delay + random.uniform(0, 0.05))

    question_lower = question.lower()
    for keyword, responses in MOCK_RESPONSES.items():
        if keyword in question_lower:
            return random.choice(responses)

    return random.choice(MOCK_RESPONSES["default"])


def ask_stream(question: str):
    for word in ask(question).split():
        time.sleep(0.05)
        yield word + " "
