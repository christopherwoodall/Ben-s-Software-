import json
import os
from datetime import datetime

# Define paths for predictive text data
PREDICTIVE_FILE = os.path.join(os.path.dirname(__file__), "predictive_ngrams.json")

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

def compute_ngram_score(data, ngram_type, candidate, current_word):
    """
    Compute a composite score for an n-gram candidate based on:
      - Its usage count.
      - Its recency (more recent uses are favored).
      - A multiplier for the n-gram type.
      - A bonus for extra letters beyond what was typed.
      
    Revised: If the candidate was used within the past week, it gets a huge bonus.
    """
    try:
        last_used = datetime.fromisoformat(data.get("last_used", "1970-01-01T00:00:00"))
    except Exception:
        last_used = datetime(1970, 1, 1)
    now = datetime.now()
    time_diff = (now - last_used).total_seconds()  # time difference in seconds
    recency = 1 / (time_diff + 1)  # higher value for more recent usage

    # NEW: Revised recency bonus for the past week.
    if time_diff < 3600:  # within 1 hour
        recency_bonus = 10000
    elif time_diff < 604800:  # within 1 week (604800 seconds)
        recency_bonus = 5000
    else:
        recency_bonus = 0

    multiplier = 10 if ngram_type == "trigrams" else 5
    base_score = multiplier * (data.get("count", 0) + recency) + recency_bonus
    letter_bonus = (len(candidate) - len(current_word)) * 20
    extra_letter_bonus = 40 if (len(candidate) - len(current_word)) > 3 else 0
    return base_score + letter_bonus + extra_letter_bonus

def compute_freq_score(data):
    """
    Compute a score for a frequent-word candidate based on:
      - Its usage count.
      - Its recency (with a huge bonus if used very recently).
      
    Revised: If the word was used within the past week, it gets a very high bonus.
    """
    try:
        last_used = datetime.fromisoformat(data.get("last_used", "1970-01-01T00:00:00"))
    except Exception:
        last_used = datetime(1970, 1, 1)
    now = datetime.now()
    time_diff = (now - last_used).total_seconds()
    recency = 1 / (time_diff + 1)
    if time_diff < 3600:
        recency_bonus = 10000
    elif time_diff < 604800:
        recency_bonus = 5000
    else:
        recency_bonus = 0
    return data.get("count", 0) + recency * 20 + recency_bonus

def get_predictive_suggestions(text, num_suggestions=6):
    """
    Returns a list of predictive suggestions based on the current text input.
    """
    # Check if the text (without the "|" cursor marker) ends with a space.
    has_trailing_space = text.rstrip("|").endswith(" ")

    # Clean the input: remove the "|" marker, trim spaces, and convert to uppercase.
    cleaned = text.upper().replace("|", "").strip()
    words = cleaned.split()

    # Default suggestions if nothing is typed
    DEFAULT_WORDS = ["YES", "NO", "HELP"]

    # --- Tier 0: If no words are entered, return frequent words first ---
    if not words:
        default_predictions = []
        for word, data in predictive_data.get("frequent_words", {}).items():
            if len(word) >= 2:
                score = compute_freq_score(data)
                default_predictions.append((word, score))

        # Sort by frequency
        sorted_default = sorted(default_predictions, key=lambda x: -x[1])

        # Take the top results
        final_predictions = [word for word, _ in sorted_default[:num_suggestions]]

        # Ensure "YES, NO, HELP" appear **at the end**
        for default_word in DEFAULT_WORDS:
            if default_word not in final_predictions:
                final_predictions.append(default_word)

        # Truncate to the max number of suggestions
        return final_predictions[:num_suggestions]

    # --- Otherwise, proceed with normal prediction logic ---

    # Determine context and current (incomplete) word.
    if has_trailing_space:
        context = cleaned
        current_word = ""
    else:
        current_word = words[-1]
        context = " ".join(words[:-1])  # May be empty if only one word exists.

    # --- Tier 1: N-gram predictions ---
    predictions_ngram = {}
    if context and (has_trailing_space or context != current_word):
        for ngram_type in ["trigrams", "bigrams"]:
            for key, data in predictive_data.get(ngram_type, {}).items():
                if key.startswith(context + " "):
                    key_words = key.split()
                    context_words = context.split()
                    if len(key_words) > len(context_words):
                        candidate = key_words[len(context_words)]
                        if (current_word == "" or candidate.startswith(current_word)) and len(candidate) >= 2 and data.get("count", 0) >= 1:
                            score = compute_ngram_score(data, ngram_type, candidate, current_word)
                            predictions_ngram[candidate] = predictions_ngram.get(candidate, 0) + score

    # --- Tier 2: Frequent words completions ---
    predictions_freq = {}
    for word, data in predictive_data.get("frequent_words", {}).items():
        if word.startswith(current_word) and word != current_word and len(word) >= 2:
            score = compute_freq_score(data)
            predictions_freq[word] = score

    # --- Tier 3: Combine candidates ---
    combined_predictions = predictions_ngram if predictions_ngram else predictions_freq

    # Sort and limit results
    sorted_combined = sorted(combined_predictions.items(), key=lambda x: -x[1])
    final_predictions = [word for word, _ in sorted_combined[:num_suggestions]]

    # Ensure "YES, NO, HELP" appear **at the end**
    for default_word in DEFAULT_WORDS:
        if default_word not in final_predictions:
            final_predictions.append(default_word)

    # Truncate to the max number of suggestions
    return final_predictions[:num_suggestions]


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
