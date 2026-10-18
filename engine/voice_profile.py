"""Summarize observable writing habits without storing message text."""

import re
from collections import Counter
from collections.abc import Iterable
from statistics import median


def voice_profile(sent_bodies: Iterable[str]) -> dict:
    """Return a compact, JSON-compatible profile of supplied new email text."""

    def unknown(reason: str) -> dict:
        return {"status": "unknown", "reason": reason}

    if isinstance(sent_bodies, (str, bytes)):
        return unknown("Supply a collection of message bodies, not a single text value.")
    try:
        bodies = tuple(sent_bodies)
    except TypeError:
        return unknown("The supplied bodies are not iterable.")
    if any(not isinstance(body, str) for body in bodies):
        return unknown("Every body must be text; invalid entries were not silently discarded.")
    usable = tuple(body for body in bodies if body.strip())
    count = len(usable)
    if not count:
        return unknown("No nonempty sent message text was supplied.")
    greetings = Counter()
    signoffs = Counter()
    word_counts = []
    character_counts = []
    contraction_occurrences = 0
    contraction_messages = 0
    exclamation_messages = 0
    question_messages = 0
    exclamation_marks = 0
    question_marks = 0
    markers = Counter()
    greeting_pattern = re.compile(
        r"^(good morning|good afternoon|good evening|hello|hi|hey|dear)(?=[\s,!:]|$)", re.IGNORECASE
    )
    closing_pattern = re.compile(
        r"^(kind regards|best regards|warm regards|yours sincerely|yours faithfully|with thanks|"
        r"thank you|take care|talk soon|regards|sincerely|warmly|cheers|thanks|best)[,!]?$",
        re.IGNORECASE,
    )
    contraction_pattern = re.compile(
        r"\b(?:[a-z]+n['’]t|(?:i|you|he|she|it|we|they|that|there|what|who|how|where|when|here|let)"
        r"['’](?:m|re|ve|ll|d|s))\b",
        re.IGNORECASE,
    )
    for body in usable:
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        greeting = greeting_pattern.match(lines[0])
        greeting_name = greeting.group(1).casefold() if greeting else None
        if greeting_name:
            greetings[greeting_name] += 1
            if greeting_name == "dear":
                markers["Dear greeting"] += 1
            elif greeting_name == "hey":
                markers["Hey greeting"] += 1
        for line in reversed(lines[-3:]):
            closing = closing_pattern.fullmatch(line)
            if closing:
                label = closing.group(1).casefold()
                signoffs[label] += 1
                if label in {"kind regards", "yours sincerely", "yours faithfully", "sincerely"}:
                    markers["Formal closing"] += 1
                elif label in {"cheers", "talk soon"}:
                    markers["Casual closing"] += 1
                break
        word_counts.append(len(re.findall(r"\b[^\W_]+(?:['’][^\W_]+)*\b", body)))
        character_counts.append(len(body))
        contractions = len(contraction_pattern.findall(body))
        contraction_occurrences += contractions
        contraction_messages += bool(contractions)
        exclamations = body.count("!") + body.count("！")
        questions = body.count("?") + body.count("？")
        exclamation_marks += exclamations
        question_marks += questions
        exclamation_messages += bool(exclamations)
        question_messages += bool(questions)
        for label, pattern in (
            ("Would you", r"\bwould you\b"),
            ("Could you", r"\bcould you\b"),
            ("I would appreciate", r"\bi would appreciate\b"),
            ("Gonna or wanna", r"\b(?:gonna|wanna)\b"),
        ):
            if re.search(pattern, body, re.IGNORECASE):
                markers[label] += 1
    if contraction_messages:
        markers["Messages with contractions"] = contraction_messages
    if exclamation_messages:
        markers["Messages with exclamation marks"] = exclamation_messages

    weights = {
        "Dear greeting": 20,
        "Hey greeting": -20,
        "Formal closing": 20,
        "Casual closing": -20,
        "Would you": 10,
        "Could you": 10,
        "I would appreciate": 10,
        "Gonna or wanna": -20,
        "Messages with contractions": -10,
        "Messages with exclamation marks": -5,
    }
    contributions = [
        {"marker": marker, "messages": occurrences, "points": round(weights[marker] * occurrences / count, 3)}
        for marker, occurrences in markers.items()
    ]
    contributions.sort(key=lambda item: (-abs(item["points"]), item["marker"]))
    raw_score = 50 + sum(weights[marker] * occurrences / count for marker, occurrences in markers.items())
    formality = (
        {
            "score": round(max(0, min(100, raw_score)), 1),
            "scale": "0 casual, 100 formal",
            "method": "English lexical heuristic; baseline 50, then listed points, clamped to 0–100",
            "markers": contributions,
        }
        if contributions
        else {"score": None, "status": "unknown", "reason": "No supported formality markers were found.", "markers": []}
    )

    def frequencies(values: Counter) -> dict:
        ordered = sorted(values.items(), key=lambda item: (-item[1], item[0]))
        return {
            "usual": [
                {"text": text, "count": frequency, "share": round(frequency / count, 3)}
                for text, frequency in ordered[:5]
            ],
            "without_detected": count - sum(values.values()),
            "other_detected": sum(frequency for _, frequency in ordered[5:]),
        }

    def usage(messages: int, occurrences: int) -> dict:
        return {"messages": messages, "share": round(messages / count, 3), "occurrences": occurrences}

    return {
        "status": "limited_sample" if count < 5 else "observed",
        "sample": {"messages": count, "ignored_empty": len(bodies) - count},
        "greetings": frequencies(greetings),
        "signoffs": frequencies(signoffs),
        "length": {"median_words": median(word_counts), "median_characters": median(character_counts)},
        "contractions": usage(contraction_messages, contraction_occurrences),
        "exclamations": usage(exclamation_messages, exclamation_marks),
        "questions": usage(question_messages, question_marks),
        "formality": formality,
    }
