import tkinter as tk
from functools import partial
import random
import time
import threading
import ctypes
import win32gui
import subprocess
import sys
import os
import pyttsx3

class MemoryGame(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Memory Game for Ben")
        self.attributes("-fullscreen", True)
        self.configure(bg="red")

        # --- Top window controls ---
        top = tk.Frame(self, bg="lightgray")
        top.pack(side="top", fill="x")
        tk.Button(top, text="_", command=self.iconify, font=("Arial",12)).pack(side="right", padx=5, pady=5)
        tk.Button(top, text="X", command=self.on_exit,   font=("Arial",12)).pack(side="right", padx=5, pady=5)

        # --- Focus & Start‐Menu monitors ---
        threading.Thread(target=self._monitor_focus,       daemon=True).start()
        threading.Thread(target=self._monitor_start_menu, daemon=True).start()

        # --- TTS engine ---
        self.tts_engine = pyttsx3.init()
        self.tts_lock   = threading.Lock()

        # --- Mode & player state ---
        self.mode_type      = 'single'   # 'single','two_casual','two_competitive'
        self.current_player = 1
        self.match_colors   = {1:"green", 2:"#FF00FF"}

        # --- Competitive tracking ---
        self.current_difficulty = "easy"
        self.games_on_diff      = 0
        self.last_game_winner   = None
        self.consec_wins        = 0
        self.points             = {1:0,2:0}
        self.difficulty_points  = {"easy":1,"medium":2,"hard":3}

        # --- Symbol→spoken‐name map ---
        self.symbol_names = {
            "●":"circle","■":"square","▲":"triangle","◆":"diamond",
            "★":"star","☀":"sun","☂":"umbrella","♣":"club",
            "♠":"spade","♥":"heart","♦":"diamond","☯":"yin yang",
            "☮":"peace","✿":"flower","☘":"clover","⚽":"soccer ball",
            "☕":"coffee","✈":"airplane"
        }

        # --- Scanning & input state ---
        self.current_mode      = None   # 'main_menu','game','pause'
        self.scan_mode         = "row"  # in game: 'row' or 'col'
        self.current_row       = 0
        self.current_col       = 0
        self.menu_buttons      = []
        self.menu_scan_index   = 0
        self.pause_buttons     = []
        self.pause_scan_index  = 0
        self.pause_scanned     = False

        # --- Debounce & hold timers ---
        self.space_debounce        = 1.0    # 1 second between scans
        self.last_space_scan_time  = 0
        self.space_press_time      = None
        self.spacebar_held         = False
        self.space_backward_active = False
        self.space_backwards_timer_id = None

        self.return_press_time     = None
        self.return_held           = False
        self.return_pause_timer_id = None
        self.pause_triggered       = False
        self.return_debounce     = 1   
        self.last_return_time    = 0


        # --- Game state ---
        self.buttons       = {}
        self.rows          = 0
        self.cols          = 0
        self.inactive_cell = False
        self.first_sel     = None
        self.busy          = False
        self.matched_pairs = 0
        self.start_time    = 0

        # --- Container & Key Binds ---
        self.container = tk.Frame(self, bg="red")
        self.container.pack(expand=True, fill="both")
        self.bind("<KeyPress-space>",    self.on_space_press)
        self.bind("<KeyRelease-space>",  self.on_space_release)
        self.bind("<KeyPress-Return>",   self.on_return_press)
        self.bind("<KeyRelease-Return>", self.on_return_release)

        # --- Launch ---
        self.show_player_mode_menu()


    # ----------------- Focus & Start‐Menu -----------------
    def _monitor_focus(self):
        while True:
            time.sleep(0.5)
            try:
                if ctypes.windll.user32.GetForegroundWindow() != self.winfo_id():
                    self.iconify(); self.deiconify()
                    ctypes.windll.user32.SetForegroundWindow(self.winfo_id())
            except: pass

    def _monitor_start_menu(self):
        while True:
            time.sleep(0.5)
            try:
                hwnd = win32gui.GetForegroundWindow()
                cls  = win32gui.GetClassName(hwnd)
                if cls in ("Shell_TrayWnd","Windows.UI.Core.CoreWindow"):
                    ctypes.windll.user32.keybd_event(0x1B,0,0,0)
                    ctypes.windll.user32.keybd_event(0x1B,0,2,0)
            except: pass


    # ----------------- TTS Helpers -----------------
    def say_text(self, txt):
        threading.Thread(target=self._speak, args=(txt,), daemon=True).start()
    def _speak(self, txt):
        with self.tts_lock:
            self.tts_engine.say(txt)
            self.tts_engine.runAndWait()
    def create_tts_button(self, parent, text, cmd, font_size=36, pady=10):
        btn = tk.Button(parent, text=text, command=cmd,
                        font=("Arial",font_size), bg="gray", activebackground="gray")
        btn.pack(pady=pady)
        btn.bind("<Enter>", lambda e: self.say_text(text))
        return btn


    # ----------------- Player-Mode Menu -----------------
    def show_player_mode_menu(self):
        self.current_mode = "main_menu"
        if getattr(self, 'current_frame', None):
            self.current_frame.destroy()
        f = tk.Frame(self.container, bg="red"); f.pack(expand=True, fill="both")
        tk.Label(f, text="CONCENTRATION", font=("Arial Black",60),
                 bg="red", fg="white").pack(pady=20)
        self.menu_buttons = [
            self.create_tts_button(f, "Single Player",          lambda: self.select_mode('single')),
            self.create_tts_button(f, "Two Player Casual",      lambda: self.select_mode('two_casual')),
            self.create_tts_button(f, "Two Player Competitive", lambda: self.select_mode('two_competitive')),
            self.create_tts_button(f, "Exit",                   self.on_exit)
        ]
        self.menu_scan_index = 0
        self.update_menu_scan_highlight()
        self.current_frame = f

    def update_menu_scan_highlight(self):
        for i,b in enumerate(self.menu_buttons):
            bg = "white" if i==self.menu_scan_index else "gray"
            b.config(bg=bg, activebackground=bg)
        self.say_text(self.menu_buttons[self.menu_scan_index].cget("text"))

    def move_menu_scan_forward(self):
        now = time.time()
        if now - self.last_space_scan_time < self.space_debounce:
            return
        self.last_space_scan_time = now

        self.menu_scan_index = (self.menu_scan_index + 1) % len(self.menu_buttons)
        self.update_menu_scan_highlight()

    def move_pause_menu_scan_forward(self):
        # skip debounce so pause always responds immediately
        if not self.pause_scanned:
            self.pause_scanned = True
        else:
            self.pause_scan_index = (self.pause_scan_index + 1) % len(self.pause_buttons)
        self.update_pause_menu_scan_highlight()

    def select_mode(self, mode):
        self.mode_type = mode
        if mode == 'two_competitive':
            self.current_difficulty = "easy"
            self.games_on_diff      = 0
            self.last_game_winner   = None
            self.consec_wins        = 0
            self.points             = {1:0,2:0}
            self.current_player     = 1
            self.say_text("Competitive mode: first to five points on easy. Player One's turn.")
            self.start_game("easy")
        else:
            self.show_difficulty_menu()


    # ----------------- Difficulty Menu -----------------
    def show_difficulty_menu(self):
        self.current_mode = "main_menu"
        self.current_frame.destroy()
        f = tk.Frame(self.container, bg="red"); f.pack(expand=True, fill="both")
        tk.Label(f, text="SELECT DIFFICULTY", font=("Arial Black",60),
                 bg="red", fg="white").pack(pady=20)
        self.menu_buttons = [
            self.create_tts_button(f, "Easy",   lambda: self.start_game("easy")),
            self.create_tts_button(f, "Medium", lambda: self.start_game("medium")),
            self.create_tts_button(f, "Hard",   lambda: self.start_game("hard")),
            self.create_tts_button(f, "Back",   self.show_player_mode_menu)
        ]
        self.menu_scan_index = 0
        self.update_menu_scan_highlight()
        self.current_frame = f


    # ----------------- Pause Menu -----------------
    def show_pause_screen(self):
        self.current_mode      = "pause"
        self.pause_scanned     = False
        self.pause_scan_index  = 0
        self.pause_frame       = tk.Frame(self.current_frame, bg="black")
        self.pause_frame.place(relx=0.5, rely=0.5, anchor="center")
        self.last_space_scan_time = 0  
        tk.Label(self.pause_frame, text="Pause Menu", font=("Arial",40),
                 fg="white", bg="black").pack(pady=20)
        self.pause_buttons = [
            self.create_tts_button(self.pause_frame, "Continue Game", self.continue_game),
            self.create_tts_button(self.pause_frame, "Return to Menu", self.show_player_mode_menu),
            self.create_tts_button(self.pause_frame, "Exit",           self.on_exit)
        ]
        # no initial highlight here

    def update_pause_menu_scan_highlight(self):
        for i,b in enumerate(self.pause_buttons):
            bg = "white" if i==self.pause_scan_index else "gray"
            b.config(bg=bg, activebackground=bg)
        self.say_text(self.pause_buttons[self.pause_scan_index].cget("text"))

    def move_pause_menu_scan_forward(self):
        now = time.time()
        # only apply debounce when not in pause
        if self.current_mode != "pause" and now - self.last_space_scan_time < self.space_debounce:
            return
        self.last_space_scan_time = now

        if not self.pause_scanned:
            self.pause_scanned = True
        else:
            self.pause_scan_index = (self.pause_scan_index + 1) % len(self.pause_buttons)

        self.update_pause_menu_scan_highlight()

    def move_pause_menu_scan_backward(self):
        now = time.time()
        if self.current_mode != "pause" and now - self.last_space_scan_time < self.space_debounce:
            return
        self.last_space_scan_time = now

        if not self.pause_scanned:
            self.pause_scanned = True
        else:
            self.pause_scan_index = (self.pause_scan_index - 1) % len(self.pause_buttons)

        self.update_pause_menu_scan_highlight()

    def continue_game(self):
        self.pause_frame.destroy()
        self.current_mode = "game"

    def start_game(self, difficulty):
        # switch to game mode
        self.current_mode = "game"
        self.scan_mode    = "row"
        # destroy previous screen
        if getattr(self, 'current_frame', None):
            self.current_frame.destroy()

        # new game frame
        f = tk.Frame(self.container, bg="red")
        f.pack(expand=True, fill="both")
        self.current_frame = f

        # competitive scoreboard
        if self.mode_type == 'two_competitive':
            lbl = tk.Label(f,
                        text=f"Score — P1:{self.points[1]}  P2:{self.points[2]}",
                        font=("Arial", 24), bg="red", fg="white")
            lbl.pack(pady=10)

        # choose grid dimensions
        self.rows, self.cols = {
            "easy":   (4, 4),
            "medium": (4, 5),
            "hard":   (6, 5)
        }[difficulty]

        # total cells and per-player majority threshold
        total = self.rows * self.cols
        if self.mode_type == 'two_competitive':
            # subtract one if odd, then half, then +1 for majority
            num_pairs = (total - (1 if total % 2 else 0)) // 2
            self.win_threshold = num_pairs // 2 + 1
            self.pairs_found   = {1: 0, 2: 0}

        # if odd, reserve one inactive cell
        inactive = None
        if total % 2:
            inactive = random.randint(0, total - 1)
            total -= 1

        pairs = total // 2

        # compute available drawing area (reserve 10% vertical margin)
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        avail_h  = int(screen_h * 0.90)
        cw = screen_w // self.cols
        ch = avail_h   // self.rows
        self.cell_w, self.cell_h = cw, ch

        # grid container
        grid_frame = tk.Frame(f, bg="red")
        grid_frame.pack()

        # prepare and shuffle cards
        designs = [
            ("●","blue"),("■","red"),("▲","lime"),("◆","purple"),
            ("★","gold"),("☀","yellow"),("☂","cyan"),("♣","lime"),
            ("♠","black"),("♥","red"),("♦","orange"),("☯","black"),
            ("☮","purple"),("✿","violet"),("☘","lime"),("⚽","black"),
            ("☕","brown"),("✈","navy")
        ]
        random.shuffle(designs)
        cards = designs[:pairs] * 2
        random.shuffle(cards)

        # reset per‐game state
        self.buttons       = {}
        self.first_sel     = None
        self.busy          = False
        self.matched_pairs = 0
        self.start_time    = time.time()

        # build the grid
        idx = 0
        for r in range(self.rows):
            for c in range(self.cols):
                frm = tk.Frame(grid_frame, width=cw, height=ch, bg="red")
                frm.grid(row=r, column=c)
                frm.grid_propagate(False)

                lin = r * self.cols + c
                if lin == inactive:
                    # inactive filler
                    tk.Label(frm, text="", bg="gray", relief="sunken").place(
                        relx=0.5, rely=0.5, anchor="center", width=cw, height=ch
                    )
                else:
                    sym, color = cards[idx]; idx += 1
                    btn = tk.Button(
                        frm, text="", bg="dark gray", fg="black",
                        activebackground="dark gray", bd=2, relief="solid",
                        command=partial(self.reveal_card, r, c)
                    )
                    btn.place(relx=0.5, rely=0.5, anchor="center", width=cw, height=ch)
                    self.buttons[(r, c)] = {
                        "button":   btn,
                        "value":    (sym, color),
                        "revealed": False,
                        "matched":  False
                    }

        # announce first turn
        if self.mode_type.startswith("two"):
            self.say_text(f"Player {self.current_player}'s turn")

        # start scanning
        self.current_row = self.current_col = 0
        self.update_scan_highlight()


    # ----------------- Scanning Highlight -----------------
    def update_scan_highlight(self):
        for (r,c),info in self.buttons.items():
            btn = info["button"]
            bg  = self.match_colors.get(info.get("matched_by"),"green") if info["matched"] else "dark gray"
            active = (self.scan_mode=="row" and r==self.current_row) or \
                     (self.scan_mode=="col" and r==self.current_row and c==self.current_col)
            btn.config(bg="white" if active else bg,
                       activebackground="white" if active else bg)

    def move_scan_forward(self):
        now = time.time()
        # enforce 1 s minimum between scans
        if now - self.last_space_scan_time < self.space_debounce:
            return
        self.last_space_scan_time = now

        # existing row/col logic:
        if self.scan_mode == "row":
            self.current_row = (self.current_row + 1) % self.rows
        else:
            prev = self.current_col
            for _ in range(self.cols):
                nxt = (prev + 1) % self.cols
                if (self.current_row, nxt) in self.buttons:
                    self.current_col = nxt
                    break
            if self.current_col < prev:
                self.scan_mode = "row"
        self.update_scan_highlight()

    def move_scan_backward(self):
        self.current_row = (self.current_row-1)%self.rows if self.scan_mode=="row" else self.current_row
        if self.scan_mode!="row":
            prev = self.current_col
            for _ in range(self.cols):
                nxt = (prev-1)%self.cols
                if (self.current_row,nxt) in self.buttons:
                    self.current_col = nxt
                    break
            if self.current_col > prev:
                self.scan_mode="row"
        self.update_scan_highlight()


    # ----------------- Space Key Handlers -----------------
    def on_space_press(self, event):
        if self.current_mode not in ("game","main_menu","pause"): return
        if self.spacebar_held: return
        self.space_press_time = time.time()
        self.spacebar_held    = True
        self.space_backward_active = False
        self.space_backwards_timer_id = self.after(3000, self.space_long_hold)

    def space_long_hold(self):
        if not self.spacebar_held: return
        self.space_backward_active = True
        if self.current_mode=="game":
            self.move_scan_backward()
        elif self.current_mode=="main_menu":
            self.move_menu_scan_backward()
        else:
            self.move_pause_menu_scan_backward()
        self.space_backwards_timer_id = self.after(2000, self.space_long_hold)

    def on_space_release(self, event):
        if self.current_mode not in ("game", "main_menu", "pause"):
            return

        # cancel any pending backward‐hold
        if self.space_backwards_timer_id:
            self.after_cancel(self.space_backwards_timer_id)
            self.space_backwards_timer_id = None

        # record hold length
        now  = time.time()
        held = now - (self.space_press_time or now)
        self.spacebar_held = False

        # only forward‐scan on taps under 3s
        if not self.space_backward_active and held < 3:
            if self.current_mode == "game":
                self.move_scan_forward()          # debounced in move_scan_forward
            elif self.current_mode == "main_menu":
                self.move_menu_scan_forward()     # debounced in move_menu_scan_forward
            else:  # pause
                self.move_pause_menu_scan_forward()  # no debounce inside

        self.space_backward_active = False

    # ----------------- Return Key Handlers -----------------
    def on_return_press(self, event):
        if self.current_mode!="game": return
        if self.return_held: return
        self.return_press_time = time.time()
        self.return_held       = True
        self.return_pause_timer_id = self.after(3000, self.return_long_hold)

    def return_long_hold(self):
        if self.return_held:
            self.pause_triggered = True
            self.show_pause_screen()

    def on_return_release(self, event):
        # cancel any pending long‑hold timer
        if self.return_pause_timer_id:
            self.after_cancel(self.return_pause_timer_id)
            self.return_pause_timer_id = None
        self.return_held = False

        # debounce: ignore if < self.return_debounce seconds since last
        now = time.time()
        if now - self.last_return_time < self.return_debounce:
            return
        self.last_return_time = now

        # then your existing logic…
        if self.current_mode=="main_menu":
            self.menu_buttons[self.menu_scan_index].invoke()
        elif self.current_mode=="pause":
            if self.pause_scanned:
                self.pause_buttons[self.pause_scan_index].invoke()
        elif self.current_mode=="game":
            if self.scan_mode=="row":
                self.scan_mode="col"
                for c in range(self.cols):
                    if (self.current_row,c) in self.buttons:
                        self.current_col = c
                        break
            else:
                self.reveal_card(self.current_row, self.current_col)
                self.scan_mode="row"
            self.update_scan_highlight()

    # ----------------- Game Logic -----------------
    def reveal_card(self, r, c):
        if self.busy:
            return
        info = self.buttons.get((r, c))
        if not info or info["matched"] or info["revealed"]:
            return

        sym, col = info["value"]
        btn = info["button"]

        # dynamically size the emoji
        fs = int(min(self.cell_w, self.cell_h) * 0.6)
        btn.config(
            text=sym,
            fg=col,
            font=("Segoe UI Emoji", fs)
        )

        info["revealed"] = True
        self.say_text(f"{col} {self.symbol_names.get(sym, sym)}")

        if self.first_sel is None:
            self.first_sel = (r, c)
        else:
            fr, fc = self.first_sel
            first = self.buttons.get((fr, fc))

            # match?
            if first and first["value"] == info["value"]:
                # mark matched
                for card in (first, info):
                    card["matched"] = True
                    if self.mode_type != "single":
                        card["matched_by"] = self.current_player

                # update counts
                self.matched_pairs += 1

                if self.mode_type == 'two_competitive':
                    # track pairs per player
                    self.pairs_found[self.current_player] += 1
                    # if they now have > half, end round immediately
                    if self.pairs_found[self.current_player] >= self.win_threshold:
                        return self.handle_round_end(self.current_player)

                # announce match
                self.after(100, lambda: self.say_text("that's a match!"))
                first["button"].config(
                    bg=self.match_colors[self.current_player],
                    activebackground=self.match_colors[self.current_player]
                )
                btn.config(
                    bg=self.match_colors[self.current_player],
                    activebackground=self.match_colors[self.current_player]
                )

                # next turn voice
                if self.mode_type.startswith("two"):
                    self.say_text(f"Player {self.current_player}'s turn")

                # if all pairs found (non-competitive) or game still going
                if self.matched_pairs == len(self.buttons) // 2:
                    if self.mode_type == 'two_competitive':
                        return self.handle_round_end(self.current_player)
                    else:
                        return self.show_win_message(time.time() - self.start_time)

            else:
                # mismatch → hide after delay
                self.busy = True
                self.after(1000, self.hide_cards, (fr, fc), (r, c))

            # reset selection
            self.first_sel = None   

    def hide_cards(self, p1, p2):
        for p in (p1,p2):
            b = self.buttons[p]["button"]
            b.config(text="", font=("Arial",48))
            self.buttons[p]["revealed"] = False
        self.busy=False
        if self.mode_type.startswith("two"):
            self.current_player = 2 if self.current_player==1 else 1
            self.say_text(f"Player {self.current_player}'s turn")

    def show_win_message(self, elapsed):
        for w in self.current_frame.winfo_children():
            w.destroy()
        msg = f"Congratulations! You won in {elapsed:.2f} seconds!"
        self.say_text(msg)
        tk.Label(self.current_frame, text=msg,
                 font=("Arial Black",42), fg="purple", bg="yellow")\
          .place(relx=0.5, rely=0.5, anchor="center")
        self.after(5000, self.show_player_mode_menu)


    # ----------------- Competitive Logic -----------------
    def handle_round_end(self, winner):
        # award points based on current difficulty
        pts = self.difficulty_points[self.current_difficulty]
        self.points[winner] += pts
        self.say_text(
            f"Player {winner} gets {pts} point{'s' if pts>1 else ''} for a {self.current_difficulty} win. "
            f"Score is {self.points[1]} to {self.points[2]}."
        )

        # match over?
        if self.points[winner] >= 5:
            self.say_text(f"Player {winner} wins the match!")
            return self.reset_match()

        # cycle difficulty: easy → medium → hard → easy
        if self.current_difficulty == "easy":
            self.current_difficulty = "medium"
        elif self.current_difficulty == "medium":
            self.current_difficulty = "hard"
        else:
            self.current_difficulty = "easy"

        # next round
        self.current_player = winner
        self.say_text(f"Next game on {self.current_difficulty}. Player {winner} starts.")
        self.start_game(self.current_difficulty)

    def reset_match(self):
        self.points={1:0,2:0}
        self.current_difficulty='easy'
        self.games_on_diff=0
        self.last_game_winner=None
        self.consec_wins=0
        self.show_player_mode_menu()

    # ----------------- Exit -----------------
    def on_exit(self):
        self.destroy()
        try:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(root, "Comm-v10.py")
            subprocess.Popen([sys.executable, path])
        except:
            pass


if __name__ == "__main__":
    app = MemoryGame()
    app.mainloop()
