import tkinter as tk
from functools import partial
import random
import time
import subprocess
import pyttsx3
import threading

class MemoryGame(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Memory Game for Ben")
        self.attributes("-fullscreen", True)  # Fullscreen window
        self.configure(bg="red")  # Overall background is red

        # Initialize TTS engine.
        self.tts_engine = pyttsx3.init()

        # Mapping from card symbol to a spoken name.
        self.symbol_names = {
            "●": "circle",
            "■": "square",
            "▲": "triangle",
            "◆": "diamond",
            "★": "star",
            "☀": "sun",
            "☂": "umbrella",
            "♣": "club",
            "♠": "spade",
            "♥": "heart",
            "♦": "diamond",
            "☯": "yin yang",
            "☮": "peace",
            "✿": "flower",
            "☘": "clover",
            "⚽": "soccer ball",
            "☕": "coffee",
            "✈": "airplane"
        }

        # Top frame for window controls (minimize and close)
        top_frame = tk.Frame(self, bg="lightgray")
        top_frame.pack(side="top", fill="x")
        minimize_btn = tk.Button(top_frame, text="_", command=self.iconify, font=("Arial", 12))
        minimize_btn.pack(side="right", padx=5, pady=5)
        close_btn = tk.Button(top_frame, text="X", command=self.on_exit, font=("Arial", 12))
        close_btn.pack(side="right", padx=5, pady=5)

        # Container frame for switching between screens (main menu, game, pause)
        self.container = tk.Frame(self, bg="red")
        self.container.pack(expand=True, fill="both")
        self.current_frame = None

        # ----------------- Scanning State Variables ------------------
        # current_mode can be "main_menu", "game", or "pause"
        self.current_mode = None

        # For game scanning:
        self.scan_mode = "row"       # "row" or "col" – used only in game mode.
        self.current_row = 0         # Current row pointer (0-indexed) in game mode.
        self.current_col = 0         # Current column pointer (in "col" mode of game).

        # For main menu scanning:
        self.menu_buttons = []       # List of menu buttons (set in show_main_menu).
        self.menu_scan_index = 0      # Current pointer (index) into self.menu_buttons.

        # For pause menu scanning:
        self.pause_buttons = []      # List of pause menu buttons.
        self.pause_scan_index = 0     # Current pointer for pause menu.
        self.pause_just_opened = False  # Flag to prevent immediate selection

        # For key hold timing (used in all modes).
        self.space_press_time = None
        self.spacebar_held = False
        self.space_backward_active = False
        self.space_backwards_timer_id = None
        self.return_press_time = None
        self.return_held = False
        self.return_pause_timer_id = None
        self.pause_triggered = False

        # ----------------- Game State Variables ------------------
        self.buttons = {}            # In game mode: mapping (row, col) -> card info.
        self.rows = 0
        self.cols = 0
        self.inactive_cell = False   # For odd-sized grids. (A 5×5 grid is odd,
                                    # so one cell is disabled to ensure every card has a pair.)
        self.first_selection = None
        self.busy = False
        self.matched_pairs = 0
        self.start_time = 0
        self.tts_lock = threading.Lock()


        # Bind keys (active in main menu, game, and pause modes)
        self.bind("<KeyPress-space>", self.on_space_press)
        self.bind("<KeyRelease-space>", self.on_space_release)
        self.bind("<KeyPress-Return>", self.on_return_press)
        self.bind("<KeyRelease-Return>", self.on_return_release)

        self.show_main_menu()

    # ----------------- TTS Methods -----------------
    def say_text(self, text):
        """Speak the given text in a separate thread so as not to block the UI."""
        threading.Thread(target=self._speak, args=(text,)).start()

    def _speak(self, text):
        with self.tts_lock:
            self.tts_engine.say(text)
            self.tts_engine.runAndWait()

    def create_tts_button(self, parent, text, command, font_size=36, pady=10):
        """Helper to create a large, light-gray button that speaks its text on hover."""
        btn = tk.Button(parent, text=text, command=command,
                        font=("Arial", font_size),
                        bg="gray", activebackground="gray")
        btn.pack(pady=pady)
        btn.bind("<Enter>", lambda e: self.say_text(text))
        return btn

    def get_symbol_name(self, symbol):
        """Return a descriptive name for the given symbol."""
        return self.symbol_names.get(symbol, symbol)

    # ----------------- Main Menu -----------------
    def show_main_menu(self):
        self.current_mode = "main_menu"
        if self.current_frame is not None:
            self.current_frame.destroy()
        self.current_frame = tk.Frame(self.container, bg="red")
        self.current_frame.pack(expand=True, fill="both")
        title = tk.Label(self.current_frame, text="CONCENTRATION", font=("Arial Black", 60), bg="red", fg="white",)
        title.pack(pady=20)
        self.menu_buttons = []
        btn = self.create_tts_button(self.current_frame, "Easy", lambda: self.start_game("easy"))
        self.menu_buttons.append(btn)
        btn = self.create_tts_button(self.current_frame, "Medium", lambda: self.start_game("medium"))
        self.menu_buttons.append(btn)
        btn = self.create_tts_button(self.current_frame, "Hard", lambda: self.start_game("hard"))
        self.menu_buttons.append(btn)
        btn = self.create_tts_button(self.current_frame, "Exit", self.on_exit)
        self.menu_buttons.append(btn)
        self.menu_scan_index = 0
        self.update_menu_scan_highlight()

    def update_menu_scan_highlight(self):
        for idx, btn in enumerate(self.menu_buttons):
            if idx == self.menu_scan_index:
                btn.config(bg="white", activebackground="white")
            else:
                btn.config(bg="gray", activebackground="gray")
        if self.current_mode == "main_menu" and self.menu_buttons:
            text = self.menu_buttons[self.menu_scan_index].cget("text")
            self.say_text(text)

    def move_menu_scan_forward(self):
        self.menu_scan_index = (self.menu_scan_index + 1) % len(self.menu_buttons)
        self.update_menu_scan_highlight()

    def move_menu_scan_backward(self):
        self.menu_scan_index = (self.menu_scan_index - 1) % len(self.menu_buttons)
        self.update_menu_scan_highlight()

    # ----------------- Pause Menu Scanning -----------------
    def update_pause_menu_scan_highlight(self):
        for idx, btn in enumerate(self.pause_buttons):
            if idx == self.pause_scan_index:
                btn.config(bg="white", activebackground="white")
            else:
                btn.config(bg="gray", activebackground="gray")
        if self.current_mode == "pause" and self.pause_buttons:
            text = self.pause_buttons[self.pause_scan_index].cget("text")
            self.say_text(text)

    def move_pause_menu_scan_forward(self):
        self.pause_scan_index = (self.pause_scan_index + 1) % len(self.pause_buttons)
        self.update_pause_menu_scan_highlight()

    def move_pause_menu_scan_backward(self):
        self.pause_scan_index = (self.pause_scan_index - 1) % len(self.pause_buttons)
        self.update_pause_menu_scan_highlight()

    # ----------------- Game Setup -----------------
    def start_game(self, difficulty):
        self.current_mode = "game"
        if self.current_frame is not None:
            self.current_frame.destroy()
        self.scan_mode = "row"
        self.current_frame = tk.Frame(self.container, bg="red")
        self.current_frame.pack(expand=True, fill="both")
        # Create a grid frame that will hold fixed-size cells.
        grid_frame = tk.Frame(self.current_frame, bg="red")
        grid_frame.pack(expand=False)
        # Set grid dimensions based on difficulty.
        if difficulty == "easy":
            self.rows, self.cols = 4, 4
        elif difficulty == "medium":
            self.rows, self.cols = 4, 5
        elif difficulty == "hard":
            self.rows, self.cols = 6, 5
        total_cells = self.rows * self.cols
        # If total cells is odd, disable one random cell.
        if total_cells % 2 != 0:
            active_cells = total_cells - 1
            self.inactive_cell = True
            inactive_index = random.randint(0, total_cells - 1)
        else:
            active_cells = total_cells
            self.inactive_cell = False
            inactive_index = None
        num_pairs = active_cells // 2
        card_designs = [
            ("●", "blue"),
            ("■", "red"),
            ("▲", "lime"),
            ("◆", "purple"),
            ("★", "gold"),
            ("☀", "yellow"),
            ("☂", "cyan"),
            ("♣", "lime"),
            ("♠", "black"),
            ("♥", "red"),
            ("♦", "orange"),
            ("☯", "black"),
            ("☮", "purple"),
            ("✿", "violet"),
            ("☘", "lime"),
            ("⚽", "black"),
            ("☕", "brown"),
            ("✈", "navy")
        ]
        random.shuffle(card_designs)
        selected_designs = card_designs[:num_pairs]
        cards = selected_designs * 2  # duplicate for pairs
        random.shuffle(cards)
        self.buttons = {}
        self.first_selection = None
        self.busy = False
        self.matched_pairs = 0
        self.start_time = time.time()
        # Calculate fixed cell dimensions based on screen size.
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        cell_width = screen_width // self.cols
        cell_height = screen_height // self.rows
        card_index = 0
        for r in range(self.rows):
            for c in range(self.cols):
                cell_index = r * self.cols + c
                cell_frame = tk.Frame(grid_frame, width=cell_width, height=cell_height, bg="red")
                cell_frame.grid(row=r, column=c)
                cell_frame.grid_propagate(False)
                if self.inactive_cell and cell_index == inactive_index:
                    lbl = tk.Label(cell_frame, text="", bg="gray", relief="sunken")
                    lbl.place(relx=0.5, rely=0.5, anchor="center", width=cell_width, height=cell_height)
                else:
                    card_value = cards[card_index]
                    card_index += 1
                    # Unrevealed card button uses a neutral background.
                    btn = tk.Button(cell_frame, text="",
                                    font=("Arial", 48),
                                    bg="dark gray", fg="black",
                                    activebackground="dark gray",
                                    bd=2, relief="solid",
                                    command=partial(self.reveal_card, r, c))
                    btn.place(relx=0.5, rely=0.5, anchor="center", width=cell_width, height=cell_height)
                    self.buttons[(r, c)] = {
                        "button": btn,
                        "value": card_value,   # (symbol, color)
                        "revealed": False,
                        "matched": False
                    }
        self.current_row = 0
        self.current_col = 0
        self.update_scan_highlight()

    def update_scan_highlight(self):
        for (r, c), info in self.buttons.items():
            btn = info["button"]
            # If the card is matched, its default background should be green.
            if info.get("matched"):
                default_color = "green"
            else:
                default_color = "dark gray"
            # If the cell is currently being scanned, show yellow.
            if self.scan_mode == "row":
                if r == self.current_row:
                    btn.config(bg="white", activebackground="white")
                else:
                    btn.config(bg=default_color, activebackground=default_color)
            elif self.scan_mode == "col":
                if r == self.current_row and c == self.current_col:
                    btn.config(bg="white", activebackground="white")
                else:
                    btn.config(bg=default_color, activebackground=default_color)

    def move_scan_forward(self):
        if self.scan_mode == "row":
            self.current_row = (self.current_row + 1) % self.rows
        elif self.scan_mode == "col":
            next_col = self.current_col
            for _ in range(self.cols):
                next_col = (next_col + 1) % self.cols
                if (self.current_row, next_col) in self.buttons:
                    self.current_col = next_col
                    break
        self.update_scan_highlight()

    def move_scan_backward(self):
        if self.scan_mode == "row":
            self.current_row = (self.current_row - 1) % self.rows
        elif self.scan_mode == "col":
            next_col = self.current_col
            for _ in range(self.cols):
                next_col = (next_col - 1) % self.cols
                if (self.current_row, next_col) in self.buttons:
                    self.current_col = next_col
                    break
        self.update_scan_highlight()

    # ----------------- Key Event Handlers -----------------
    def on_space_press(self, event):
        if self.current_mode not in ("game", "main_menu", "pause"):
            return
        if self.spacebar_held:
            return
        self.space_press_time = time.time()
        self.spacebar_held = True
        self.space_backward_active = False
        self.space_backwards_timer_id = self.after(3000, self.space_long_hold)

    def space_long_hold(self):
        if self.spacebar_held:
            self.space_backward_active = True
            if self.current_mode == "game":
                self.move_scan_backward()
            elif self.current_mode == "main_menu":
                self.move_menu_scan_backward()
            elif self.current_mode == "pause":
                self.move_pause_menu_scan_backward()
            self.space_backwards_timer_id = self.after(2000, self.space_long_hold)

    def on_space_release(self, event):
        if self.current_mode not in ("game", "main_menu", "pause"):
            return
        duration = time.time() - self.space_press_time if self.space_press_time else 0
        if self.space_backwards_timer_id:
            self.after_cancel(self.space_backwards_timer_id)
            self.space_backwards_timer_id = None
        self.spacebar_held = False
        if not self.space_backward_active:
            if 0.1 <= duration < 3:
                if self.current_mode == "game":
                    self.move_scan_forward()
                elif self.current_mode == "main_menu":
                    self.move_menu_scan_forward()
                elif self.current_mode == "pause":
                    self.move_pause_menu_scan_forward()
        self.space_backward_active = False

    def on_return_press(self, event):
        if self.current_mode not in ("game", "main_menu", "pause"):
            return
        if self.return_held:
            return
        self.return_press_time = time.time()
        self.return_held = True
        if self.current_mode == "game":
            self.return_pause_timer_id = self.after(3000, self.return_long_hold)

    def return_long_hold(self):
        if self.return_held:
            self.pause_triggered = True
            self.show_pause_screen()

    def on_return_release(self, event):
        if self.current_mode not in ("game", "main_menu", "pause"):
            return
        duration = time.time() - self.return_press_time if self.return_press_time else 0
        # In pause mode, if the menu was just opened, do nothing on Return release.
        if self.current_mode == "pause" and self.pause_just_opened:
            self.pause_just_opened = False
            self.return_held = False
            return
        if self.current_mode == "game":
            if self.return_pause_timer_id:
                self.after_cancel(self.return_pause_timer_id)
                self.return_pause_timer_id = None
            self.return_held = False
            if self.pause_triggered:
                self.pause_triggered = False
                return
            if 0.1 <= duration < 3:
                if self.scan_mode == "row":
                    self.scan_mode = "col"
                    for col in range(self.cols):
                        if (self.current_row, col) in self.buttons:
                            self.current_col = col
                            break
                    self.update_scan_highlight()
                elif self.scan_mode == "col":
                    row, col = self.current_row, self.current_col
                    if (row, col) in self.buttons:
                        self.reveal_card(row, col)
                    self.scan_mode = "row"
                    self.update_scan_highlight()
        elif self.current_mode == "main_menu":
            self.return_held = False
            self.menu_buttons[self.menu_scan_index].invoke()
        elif self.current_mode == "pause":
            self.return_held = False
            self.pause_buttons[self.pause_scan_index].invoke()

    # ----------------- Pause Screen -----------------
    def show_pause_screen(self):
        self.current_mode = "pause"
        self.return_held = False
        self.return_press_time = None
        self.pause_just_opened = True
        self.pause_frame = tk.Frame(self.current_frame, bg="black")
        self.pause_frame.place(relx=0.5, rely=0.5, anchor="center")
        label = tk.Label(self.pause_frame, text="Pause Menu", font=("Arial", 40), fg="white", bg="black")
        label.pack(pady=20)
        self.pause_buttons = []
        # Add a "Continue Game" option.
        btn = self.create_tts_button(self.pause_frame, "Continue Game", self.continue_game, font_size=36)
        self.pause_buttons.append(btn)
        btn = self.create_tts_button(self.pause_frame, "Return to Menu", self.return_to_menu, font_size=36)
        self.pause_buttons.append(btn)
        btn = self.create_tts_button(self.pause_frame, "Exit", self.on_exit, font_size=36)
        self.pause_buttons.append(btn)
        self.pause_scan_index = 0
        # (Do not preselect any button immediately; let the user start scanning.)

    def continue_game(self):
        # Close the pause overlay and resume game mode.
        self.pause_frame.destroy()
        self.current_mode = "game"

    def return_to_menu(self):
        self.pause_frame.destroy()
        self.show_main_menu()

    # ----------------- Game Logic (Reveal / Match) -----------------
    def reveal_card(self, r, c):
        if self.busy:
            return
        card_info = self.buttons.get((r, c))
        if not card_info:
            return
        if card_info["matched"] or card_info["revealed"]:
            return
        symbol, color = card_info["value"]
        # Show the card's symbol and speak its details.
        card_info["button"].config(text=symbol, fg=color, font=("Arial", 172))
        card_info["revealed"] = True
        text_to_speak = f"{color} {self.get_symbol_name(symbol)}"
        self.say_text(text_to_speak)
        if self.first_selection is None:
            self.first_selection = (r, c)
        else:
            first_r, first_c = self.first_selection
            first_card = self.buttons.get((first_r, first_c))
            if first_card and first_card["value"] == card_info["value"]:
                # Match found!
                first_card["matched"] = True
                card_info["matched"] = True
                self.matched_pairs += 1
                # Delay the match announcement slightly.
                self.after(100, lambda: self.say_text("that's a match!"))
                # Instead of setting a check mark, change both cards' backgrounds to green.
                first_card["button"].config(bg="green", activebackground="green")
                card_info["button"].config(bg="green", activebackground="green")
                self.first_selection = None
                if self.matched_pairs == len(self.buttons) // 2:
                    elapsed = time.time() - self.start_time
                    self.show_win_message(elapsed)

            else:
                self.busy = True
                self.after(1000, self.hide_cards, (first_r, first_c), (r, c))
                self.first_selection = None


    def hide_cards(self, pos1, pos2):
        for pos in [pos1, pos2]:
            card = self.buttons.get(pos)
            if card:
                card["button"].config(text="", font=("Arial", 48))
                card["revealed"] = False
        self.busy = False

    def show_win_message(self, elapsed):
        # Clear all widgets in the current frame so the win message isn’t hidden.
        for widget in self.current_frame.winfo_children():
            widget.destroy()
        win_msg = f"Congratulations! You won in {elapsed:.2f} seconds!"
        self.say_text(win_msg)
        # Create and center the win message label.
        win_label = tk.Label(self.current_frame, text=win_msg, font=("Arial Black", 42), fg="purple", bg="yellow")
        win_label.place(relx=0.5, rely=0.5, anchor="center")
        # After 5 seconds, return to the main menu.
        self.after(5000, self.show_main_menu)

    # ----------------- Window Exit -----------------
    def on_exit(self):
        self.destroy()
        try:
            subprocess.Popen(["python", "Comm-v9.py"])
        except Exception as e:
            print("Failed to launch Comm-v9.py:", e)

if __name__ == "__main__":
    app = MemoryGame()
    app.mainloop()
