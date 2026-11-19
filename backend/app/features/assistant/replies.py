"""Rule-based reading of short replies — yes / no / "which one" — with no AI.

Built for speech-to-text as much as typing: recognisers add punctuation and
filler ("Yes.", "yeah do it", "no thanks", "the second one", "number two"),
and users mix in Hindi ("haan", "nahi", "theek hai", "dusra").

Safety rule: a reply counts as YES only if EVERY word in it is a yes/filler
word. "yes please" confirms; "yes but make it 8am" does not — that's a
changed request, and a changed request must never reuse a pending
confirmation. Same for NO and for choices.
"""
import re

_YES = {
    "yes", "y", "yeah", "yea", "yep", "yup", "sure", "ok", "okay", "confirm", "confirmed",
    "correct", "right", "absolutely", "definitely", "affirmative", "proceed",
    # Hindi / Hinglish
    "haan", "han", "haa", "ha", "ji", "theek", "thik", "hai", "bilkul", "kar",
}
_NO = {
    "no", "n", "nope", "nah", "cancel", "stop", "never", "mind", "dont", "don't", "not",
    "abort",
    # Hindi / Hinglish
    "nahi", "nahin", "mat", "rehne", "rahne",
}
# Words that may surround a yes/no/choice without changing its meaning.
_FILLER = {
    "please", "do", "it", "that", "that's", "thats", "is", "go", "ahead", "thanks", "thank",
    "you", "the", "one", "a", "an", "option", "number", "choice", "i", "want", "pick",
    "select", "choose", "mean", "meant", "dijiye", "karo", "kijiye", "wala", "wali",
    "de", "dena", "bhai", "dear", "just", "this",
}
_NUMBER_WORDS = {
    "one": 1, "first": 1, "1st": 1, "pehla": 1, "pehli": 1, "ek": 1,
    # (Hindi "do" = two is deliberately absent: "do it" must not pick option 2.)
    "two": 2, "second": 2, "2nd": 2, "dusra": 2, "doosra": 2, "dusri": 2,
    "three": 3, "third": 3, "3rd": 3, "teesra": 3, "teen": 3,
    "four": 4, "fourth": 4, "4th": 4, "chautha": 4, "char": 4,
    "five": 5, "fifth": 5, "5th": 5, "paanch": 5,
    "six": 6, "sixth": 6, "6th": 6,
    "seven": 7, "seventh": 7, "7th": 7,
    "eight": 8, "eighth": 8, "8th": 8,
    "nine": 9, "ninth": 9, "9th": 9,
    "ten": 10, "tenth": 10, "10th": 10,
}


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _only(words: list[str], vocabulary: set[str]) -> bool:
    return bool(words) and all(w in vocabulary or w in _FILLER for w in words) and any(
        w in vocabulary for w in words
    )


def is_yes(text: str) -> bool:
    words = _words(text)
    return _only(words, _YES) and not any(w in _NO for w in words)


# Words in _YES that also appear in polite refusals ("ji nahi", "nahi hai").
_NEUTRAL = {"kar", "hai", "ji"}


def is_no(text: str) -> bool:
    words = _words(text)
    no_vocabulary = _NO | _NEUTRAL
    return _only(words, no_vocabulary) and not any(w in _YES - _NEUTRAL for w in words)


def parse_choice(text: str, count: int) -> int | None:
    """1-based choice from "2", "the second one", "number two", "dusra" —
    only when the reply is nothing but that choice (plus filler). Returns
    None if it isn't a pure choice or is out of 1..count."""
    words = _words(text)
    numbers = []
    for w in words:
        if w.isdigit():
            numbers.append(int(w))
        elif w in _NUMBER_WORDS and w != "one":  # "one" is filler in "the second one"
            numbers.append(_NUMBER_WORDS[w])
        elif w not in _FILLER:
            return None
    if not numbers and words == ["one"]:
        numbers = [1]
    if len(numbers) != 1:
        return None
    return numbers[0] if 1 <= numbers[0] <= count else None


def is_number_reply(text: str) -> bool:
    """A bare number/ordinal (even out of range) — used to re-ask rather
    than treat "7" as a brand-new request."""
    words = _words(text)
    return bool(words) and all(w.isdigit() or w in _NUMBER_WORDS or w in _FILLER for w in words) and any(
        w.isdigit() or (w in _NUMBER_WORDS and w != "one") for w in words
    )
