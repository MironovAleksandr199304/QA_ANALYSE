import json
import re

MUST_HAVE = ["python", "sql", "api", "testing"]
NICE_TO_HAVE = ["playwright", "selenium", "postman", "pytest", "cicd"]


AGGRESSIVE_WORDS = ["stupid", "idiot", "hate"]


def _hard_score(text: str) -> tuple[float, dict]:
    lower = text.lower()
    must = []
    nice = []

    for skill in MUST_HAVE:
        if skill in lower:
            must.append({"skill": skill, "level": "used", "evidence": [skill]})

    for skill in NICE_TO_HAVE:
        if skill in lower:
            nice.append({"skill": skill, "level": "mention", "evidence": [skill]})

    must_score = 100 * len(must) / max(len(MUST_HAVE), 1)
    nice_bonus = 20 * len(nice) / max(len(NICE_TO_HAVE), 1)
    score = min(100, must_score + nice_bonus)
    return score, {"must_have": must, "nice_to_have": nice, "score": round(score, 2)}


def _soft_score(text: str) -> tuple[float, dict]:
    grammar_issues = len(re.findall(r"\s{2,}", text))
    capslock_flags = sum(1 for token in text.split() if len(token) > 4 and token.isupper())
    aggressive_flags = sum(1 for w in AGGRESSIVE_WORDS if w in text.lower())

    penalty = grammar_issues * 1.5 + capslock_flags * 2 + aggressive_flags * 10
    score = max(0, 100 - penalty)
    return score, {
        "grammar_issues": grammar_issues,
        "capslock_flags": capslock_flags,
        "aggressive_lexicon_flags": aggressive_flags,
        "score": round(score, 2),
    }


def _sanity_score(text: str) -> tuple[float, dict, list]:
    penalties = []
    date_overlap = []
    stuffing = len(re.findall(r"\b(test|qa|automation)\b", text.lower())) > 50

    if stuffing:
        penalties.append({"code": "KEYWORD_STUFFING", "value": 10, "reason": "Suspicious keyword repetition"})

    if "10+ years" in text.lower() and "intern" in text.lower():
        penalties.append({"code": "ROLE_MISMATCH", "value": 8, "reason": "Senior experience with intern role language"})

    total_penalty = sum(p["value"] for p in penalties)
    score = max(0, 100 - total_penalty)

    details = {
        "experience_vs_stack": [],
        "role_vs_responsibility": [p["reason"] for p in penalties if p["code"] == "ROLE_MISMATCH"],
        "date_overlaps": date_overlap,
        "keyword_stuffing": stuffing,
        "score": round(score, 2),
    }
    return score, details, penalties


def analyze_resume(text: str, weights: dict | None = None) -> dict:
    weights = weights or {"hard": 0.6, "soft": 0.2, "sanity": 0.2}

    hard_score, hard_details = _hard_score(text)
    soft_score, soft_details = _soft_score(text)
    sanity_score, sanity_details, penalties = _sanity_score(text)

    penalty_sum = sum(p["value"] for p in penalties)
    total = (
        weights["hard"] * hard_score
        + weights["soft"] * soft_score
        + weights["sanity"] * sanity_score
        - penalty_sum
    )
    total = max(0, min(100, total))

    if total >= 75:
        label = "green"
    elif total >= 50:
        label = "yellow"
    else:
        label = "red"

    details = {
        "hard": hard_details,
        "soft": soft_details,
        "sanity": sanity_details,
        "penalties": penalties,
    }

    return {
        "score_total": round(total, 2),
        "score_hard": round(hard_score, 2),
        "score_soft": round(soft_score, 2),
        "score_sanity": round(sanity_score, 2),
        "label": label,
        "details_json": json.dumps(details, ensure_ascii=False),
    }
