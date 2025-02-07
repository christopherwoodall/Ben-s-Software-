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

def compute_ngram_score(data, ngram_type, candidate, current_word):
    """
    Compute a composite score for an n-gram candidate based on:
      - Its usage count.
      - Its recency (more recent uses are favored).
      - A multiplier for the n-gram type.
      - A bonus for extra letters beyond what was typed.
    """
    try:
        last_used = datetime.fromisoformat(data.get("last_used", "1970-01-01T00:00:00"))
    except Exception:
        last_used = datetime(1970, 1, 1)
    now = datetime.now()
    time_diff = (now - last_used).total_seconds()
    recency = 1 / (time_diff + 1)  # The smaller the time_diff, the higher this value.
    # If used within the last hour, add a bonus.
    recency_bonus = 1000 if time_diff < 3600 else 0
    multiplier = 10 if ngram_type == "trigrams" else 5
    base_score = multiplier * (data.get("count", 0) + recency) + recency_bonus
    # Bonus: 20 points for every extra letter beyond what was typed.
    letter_bonus = (len(candidate) - len(current_word)) * 20
    # Extra fixed bonus if the candidate has more than 3 extra letters.
    extra_letter_bonus = 40 if (len(candidate) - len(current_word)) > 3 else 0
    return base_score + letter_bonus + extra_letter_bonus

def compute_freq_score(data):
    """
    Compute a score for a frequent-word candidate based on:
      - Its usage count.
      - Its recency.
      
    If the word was used within the last hour, add a very high bonus.
    """
    try:
        last_used = datetime.fromisoformat(data.get("last_used", "1970-01-01T00:00:00"))
    except Exception:
        last_used = datetime(1970, 1, 1)
    now = datetime.now()
    time_diff = (now - last_used).total_seconds()
    recency = 1 / (time_diff + 1)
    # VERY high bonus if used in the last hour:
    recency_bonus = 5000 if time_diff < 3600 else 0
    return data.get("count", 0) + recency * 20 + recency_bonus

def get_predictive_suggestions(text, num_suggestions=6):
    """
    Returns a list of predictive suggestions based on the current text input.
    
    Strategy:
      1. Tier 1 – N-gram predictions:
         - Split the input into:
             • context: all words except the last (if any)
             • current_word: the last (possibly incomplete) word (unless the text ends with a space).
         - For each n-gram key (from trigrams and bigrams) that starts with "context " (with a trailing space),
           extract the candidate (the word immediately following the context).
         - If the candidate starts with the current_word (or if current_word is empty) and is at least 2 letters long,
           compute its score using compute_ngram_score.
         - Collect these candidates in predictions_ngram.
      
      2. Tier 2 – Frequent words completions:
         - For every word in the frequent_words dictionary that starts with the current_word (and isn’t exactly equal),
           compute its score using compute_freq_score.
      
      3. Tier 3 – Combine candidates:
         - If any n-gram candidates were found, they are used exclusively.
         - Otherwise, use the frequent words completions.
         - If fewer than num_suggestions candidates are available, fill in extra candidates from frequent_words.
    
    All suggestions returned will be at least 2 letters long.
    """
    # Check whether the text (without the "|" cursor marker) ends with a space.
    has_trailing_space = text.rstrip("|").endswith(" ")

    # Clean the input: remove the "|" marker, trim, and convert to uppercase.
    cleaned = text.upper().replace("|", "").strip()
    words = cleaned.split()

    # Tier 0: If no words are entered, return default suggestions from frequent_words.
    if not words:
        default_predictions = []
        for word, data in predictive_data.get("frequent_words", {}).items():
            if len(word) >= 2:
                score = compute_freq_score(data)
                default_predictions.append((word, score))
        sorted_default = sorted(default_predictions, key=lambda x: -x[1])
        return [word for word, _ in sorted_default[:num_suggestions]]

    # Determine context and current (incomplete) word.
    if has_trailing_space:
        # If the text ends with a space, treat the entire cleaned text as context.
        context = cleaned
        current_word = ""
    else:
        current_word = words[-1]
        context = " ".join(words[:-1])  # May be empty if there is only one word.

    # --- Tier 1: N-gram predictions ---
    predictions_ngram = {}
    if context and (has_trailing_space or context != current_word):
        for ngram_type in ["trigrams", "bigrams"]:
            for key, data in predictive_data.get(ngram_type, {}).items():
                # Look for keys that start with "context " (with trailing space).
                if key.startswith(context + " "):
                    key_words = key.split()
                    context_words = context.split()
                    if len(key_words) > len(context_words):
                        candidate = key_words[len(context_words)]
                        # Accept candidate if:
                        #   - Either no current_word is being typed or candidate starts with current_word,
                        #   - Candidate is at least 2 letters long,
                        #   - And its count is at least 1.
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
    if predictions_ngram:
        # If any n-gram candidates are found, use them exclusively.
        combined_predictions = predictions_ngram.copy()
    else:
        combined_predictions = predictions_freq.copy()
    
    # If there are fewer than num_suggestions candidates, fill in extra ones from frequent_words.
    if len(combined_predictions) < num_suggestions:
        extra_candidates = {}
        for word, data in predictive_data.get("frequent_words", {}).items():
            if len(word) >= 2 and word not in combined_predictions and word.startswith(current_word):
                extra_candidates[word] = compute_freq_score(data)
        sorted_extra = sorted(extra_candidates.items(), key=lambda x: -x[1])
        for word, score in sorted_extra:
            if len(combined_predictions) < num_suggestions:
                combined_predictions[word] = score
            else:
                break
        if len(combined_predictions) < num_suggestions:
            extra_candidates = {}
            for word, data in predictive_data.get("frequent_words", {}).items():
                if len(word) >= 2 and word not in combined_predictions:
                    extra_candidates[word] = compute_freq_score(data)
            sorted_extra = sorted(extra_candidates.items(), key=lambda x: -x[1])
            for word, score in sorted_extra:
                if len(combined_predictions) < num_suggestions:
                    combined_predictions[word] = score
                else:
                    break

    sorted_combined = sorted(combined_predictions.items(), key=lambda x: -x[1])
    return [word for word, _ in sorted_combined[:num_suggestions]]

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
