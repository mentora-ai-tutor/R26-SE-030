import random
from datetime import datetime


def generate_quiz(topic: str, mastery_score: float = 0.5) -> dict:
    difficulty = 1.0 - mastery_score
    difficulty = max(0.1, min(difficulty, 1.0))

    quiz_bank = {
        "Loops": {
            "easy": [("What does 'for i in range(5)' do?", "Iterates 5 times")],
            "medium": [("What is an infinite loop? Give an example.", "while True: pass")],
            "hard": [("Write a nested loop to print a multiplication table.", "Nested for loops")],
        },
        "Recursion": {
            "easy": [("What is a base case in recursion?", "The stopping condition")],
            "medium": [("Write a recursive factorial function.", "n * factorial(n-1)")],
            "hard": [("Implement recursive merge sort with explanation.", "Divide and conquer")],
        },
        "OOP": {
            "easy": [("What is a class?", "Blueprint for objects")],
            "medium": [("Explain polymorphism with an example.", "Method overriding")],
            "hard": [("Design a class hierarchy for a banking system.", "Inheritance and interfaces")],
        },
    }

    level = "hard" if difficulty > 0.65 else ("medium" if difficulty > 0.35 else "easy")
    bank = quiz_bank.get(topic, quiz_bank.get("Loops"))
    qs = bank.get(level, bank["easy"])
    q = random.choice(qs)

    return {
        "topic": topic,
        "difficulty": round(difficulty, 2),
        "level": level,
        "question": q[0],
        "expected_key": q[1],
        "irt_theta": round(mastery_score * 3 - 1.5, 2),
        "generated_at": datetime.utcnow().isoformat(),
    }
