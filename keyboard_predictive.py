import json
import os
from datetime import datetime

# Define paths for predictive text data
PREDICTIVE_FILE = "predictive_ngrams.json"

# Global variable to store JSON data (prevents reloading every keystroke)
predictive_data = {}

# Load JSON data once and ensure all words are uppercase
def load_json():
    global predictive_data
    if not os.path.exists(PREDICTIVE_FILE) or os.stat(PREDICTIVE_FILE).st_size == 0:
        predictive_data = {"frequent_words": {}, "bigrams": {}, "trigrams": {}}
        return

    try:
        with open(PREDICTIVE_FILE, "r", encoding="utf-8") as file:
            predictive_data = json.load(file)

        # Convert all words to uppercase for consistency
        predictive_data["frequent_words"] = {k.upper(): v for k, v in predictive_data["frequent_words"].items()}
        predictive_data["bigrams"] = {k.upper(): v for k, v in predictive_data["bigrams"].items()}
        predictive_data["trigrams"] = {k.upper(): v for k, v in predictive_data["trigrams"].items()}

        print("✅ Predictive JSON Loaded. Sample words:", list(predictive_data["frequent_words"].keys())[:10])
    except json.JSONDecodeError:
        predictive_data = {"frequent_words": {}, "bigrams": {}, "trigrams": {}}

# Save JSON data
def save_json():
    with open(PREDICTIVE_FILE, "w", encoding="utf-8") as file:
        json.dump(predictive_data, file, indent=4)

from datetime import datetime

def compute_ngram_score(data, ngram_type):
    """
    Compute a composite score for an n-gram candidate based on:
      - Its usage count.
      - Its recency (more recent uses are favored).
      - A multiplier for the n-gram type (trigrams get a higher multiplier).
    """
    try:
        last_used = datetime.fromisoformat(data.get("last_used", "1970-01-01T00:00:00"))
    except Exception:
        last_used = datetime(1970, 1, 1)
    now = datetime.now()
    time_diff = (now - last_used).total_seconds()  # seconds elapsed
    recency = 1 / (time_diff + 1)  # smaller time_diff gives a larger recency score
    multiplier = 2 if ngram_type == "trigrams" else 1
    return multiplier * (data.get("count", 0) + recency)

def get_predictive_suggestions(text, num_suggestions=6):
    """
    Returns predictive suggestions based on the current text input.

    Priority is given to:
      1. N-gram predictions (trigrams over bigrams) that factor in recency and usage.
      2. Fallback to frequent_words completions.
    
    Default placeholder suggestions (from frequent_words) are returned when no input is present,
    but any suggestion returned will be at least 2 letters long.

    Importantly, if the input ends with a space (e.g. "I LOVE "),
    then the entire cleaned text is treated as context (with no incomplete word).
    """
    # Determine if the original text (without the cursor marker) ends with a space.
    has_trailing_space = text.rstrip("|").endswith(" ")

    # Clean the input: remove the cursor marker, trim, and convert to uppercase.
    cleaned = text.upper().replace("|", "").strip()
    words = cleaned.split()
    
    # --- Default: No input → default suggestions from frequent_words ---
    if not words:
        default_predictions = []
        for word, data in predictive_data.get("frequent_words", {}).items():
            if len(word) >= 2:
                default_predictions.append((word, data.get("count", 0)))
        sorted_default = sorted(default_predictions, key=lambda x: -x[1])
        return [word for word, _ in sorted_default[:num_suggestions]]
    
    # Determine context and current (incomplete) word.
    if has_trailing_space:
        # If the text ends with a space, treat the entire cleaned text as context.
        context = cleaned
        current_word = ""
    else:
        current_word = words[-1]
        context = " ".join(words[:-1])
    
    # --- Case 1: Use n-gram predictions if context exists (or if there's a trailing space) ---
    if context and (has_trailing_space or context != current_word):
        predictions_ngram = {}
        for ngram_type in ["trigrams", "bigrams"]:
            for key, data in predictive_data.get(ngram_type, {}).items():
                # Only consider keys that start with "context " (including a trailing space).
                if key.startswith(context + " "):
                    key_words = key.split()
                    context_words = context.split()
                    if len(key_words) > len(context_words):
                        next_word = key_words[len(context_words)]
                        # Accept the candidate if it starts with the current word (or if current_word is empty),
                        # is at least 2 letters long, and its count is at least 1.
                        if (current_word == "" or next_word.startswith(current_word)) and len(next_word) >= 2 and data.get("count", 0) >= 1:
                            score = compute_ngram_score(data, ngram_type)
                            predictions_ngram[next_word] = predictions_ngram.get(next_word, 0) + score
        if predictions_ngram:
            sorted_ngram = sorted(predictions_ngram.items(), key=lambda x: -x[1])
            return [word for word, _ in sorted_ngram[:num_suggestions]]
    
    # --- Case 2: Fallback to frequent_words completions ---
    predictions_freq = {}
    for word, data in predictive_data.get("frequent_words", {}).items():
        if word.startswith(current_word) and word != current_word and len(word) >= 2:
            predictions_freq[word] = data.get("count", 0)
    sorted_freq = sorted(predictions_freq.items(), key=lambda x: -x[1])
    return [word for word, _ in sorted_freq[:num_suggestions]]

def update_word_usage(text):
    # Remove the cursor indicator from the text.
    text = text.replace("|", "")
    words = text.strip().upper().split()
    timestamp = datetime.now().isoformat()

    # Update frequent words
    for word in words:
        if len(word) <= 9:
            if word in predictive_data["frequent_words"]:
                predictive_data["frequent_words"][word]["count"] += 1
                predictive_data["frequent_words"][word]["last_used"] = timestamp
            else:
                predictive_data["frequent_words"][word] = {"count": 1, "last_used": timestamp}

    # Update bigrams
    for i in range(len(words) - 1):
        bigram = f"{words[i]} {words[i+1]}"
        if bigram in predictive_data["bigrams"]:
            predictive_data["bigrams"][bigram]["count"] += 1
            predictive_data["bigrams"][bigram]["last_used"] = timestamp
        else:
            predictive_data["bigrams"][bigram] = {"count": 1, "last_used": timestamp}

    # Update trigrams
    for i in range(len(words) - 2):
        trigram = f"{words[i]} {words[i+1]} {words[i+2]}"
        if trigram in predictive_data["trigrams"]:
            predictive_data["trigrams"][trigram]["count"] += 1
            predictive_data["trigrams"][trigram]["last_used"] = timestamp
        else:
            predictive_data["trigrams"][trigram] = {"count": 1, "last_used": timestamp}

    save_json()  # Save updates

# Load data once when script starts
load_json()
