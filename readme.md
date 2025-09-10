
````markdown
# Ben's Accessibility Software

> ⚠️ **Disclaimer**  
> This project was created by a caregiver with no formal programming background.  
> Most of the code was generated with **AI assistance (ChatGPT)** and refined through testing.  
> It is **not professional-grade software**, but an **open-source example** of what families and caregivers can achieve using AI to build bespoke accessibility tools.  

---

## Overview

This project was developed for **Ben**, who lives with **TUBB4A-related Leukodystrophy (H-ABC)** and uses only two switches (head left/right) to interact with his computer.  

It gives Ben the ability to:

- Communicate using a **robust predictive text keyboard**  
- Speak **quick communication phrases** from a customizable list  
- Watch and navigate his favorite shows and movies  
- Play simple games  
- Access trivia and word challenges  
- Control his computer with system and emergency functions
- Search Images and Videos on YouTube via his new Search Web app as of Sept 2025  

The project is shared openly to inspire others to build similar accessibility tools.  

---

## Features

### Predictive Text Keyboard (`keyboard/keyboard.py`)

- Custom-built predictive text engine (developed by hand, not AI-generated)  
- Optimized for **scan-and-select navigation** with two switches  
- Supports **quick phrases** (`data/communication.xlsx`)  
- Text-to-Speech (TTS) for all typed content  
- Includes Spanish keyboard variant (`keyboard/spanish/`)  

### Main Communication Hub (`comm-v10.py`)

- Central interface with scanning menus  
- Integrated **emergency, settings, communication, and entertainment** menus  
- Auto-hides when Chrome is active, restores after closing  

### Entertainment

- **Show Tracking**  
  - `data/shows.xlsx` → Master list of favorite shows  
  - Two playback modes:  
    - **Marathon Mode** → Most shows run continuously, tracked via `last_watched.json`  
    - **Episode Selection Mode** → Some shows link to `EPISODE_SELECTION.xlsx` for season/episode navigation  

- **Supported Platforms**  
  - Plex (best navigation, supports media keys)  
  - Netflix, Hulu, Disney+, Paramount+, HBO Max  
  - YouTube  
  - Spotify  

- **Control Bar (`control_bar.py`)**  
  - Always-on-top playback bar over Chrome  
  - Play/Pause, Volume, Previous/Next Episode, Exit  

### Games (`games/`)

- `Concentration.py` → Memory game  
- `TicTacToe.py` → Classic tic tac toe  
- `WordJumble.py` → Word scramble  
- `TowerDefense.py` → Simple tower defense  
- `MiniGolf.py` → Mini golf with sound effects  
- `baseball.py` → Probability-based baseball with animations  
- `Trivia.py` → Pulls questions from `trivia_questions.xlsx`
- 'Bennysays.html' → Game like "simon" with easy, medium, hard modes.

### Search Function (`search/`)

- 'narbe_scan_browser.py' allows the user to use scan/select to type and say phrases with kenlm predictive text and search. Search brings up a slide-show style browser of images/videos.

### Communication Phrases

- Stored in `data/communication.xlsx`  
- Customizable with new phrases for fast TTS playback  

### System Controls

- Emergency alert  
- Volume up/down  
- Sleep timer (set/cancel)  
- Display off / lock / restart / shutdown  

---

## Installation

```bash
# Clone this repository
git clone https://github.com/acroz3n/ben-s-software.git

# Navigate into the repo
cd "Ben's Python Computer Software"

# Install required dependencies
pip install -r requirements.txt

# Run the main software
python comm-v10.py
````

---

## Configuration

* **Shows** → Edit `data/shows.xlsx`
* **Episodes** → Populate `data/EPISODE_SELECTION.xlsx` for detailed navigation
* **Quick Phrases** → Edit `data/communication.xlsx`
* **Trivia Questions** → Add to `data/trivia_questions.xlsx`
* **Word Jumble** → Add words in `data/wordjumble.xlsx`

⚠️ A **web scraper** (`scripts/`) was used to collect episodes but is **not included as part of the main repo**.

---

## Dependencies

* Python 3.8+
* `pyautogui`
* `keyboard`
* `pyttsx3` (TTS)
* `pygame`
* `pymunk`
* `flask` (optional, web interface)

---

## Contributing

This project still contains **duplicate functions** and quick patches.
It’s meant to show what’s possible with AI-assisted code, not perfect engineering.

Pull requests to improve stability, refactor code, or add features are welcome.

---

## License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

* **Ben** — inspiration and primary user
* **Nancy & Ari** — caregiving and development
* **OpenAI’s ChatGPT** — AI-assisted coding partner
* **Predictive Keyboard (`keyboard.py`)** — developed by Ari Rosenberg
* **Accessibility & open-source community** — proof that collaboration makes technology better

---

## Purpose

This is more than just one program.
It’s an **open-source example** of how AI + caregiving can create **accessible, personalized tools** for people with severe disabilities.

We hope it inspires others to build and share similar projects.

