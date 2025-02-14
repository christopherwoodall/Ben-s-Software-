import pygame
import pyttsx3
import math
import time
import subprocess
import threading
import ctypes
import win32gui
import os

# Initialize pygame and TTS engine
pygame.init()
tts_engine = pyttsx3.init()
tts_engine.setProperty('rate', 150)

# Fixed virtual game dimensions
VIRTUAL_WIDTH = 1200
VIRTUAL_HEIGHT = 800

# Create a virtual surface that holds all the game drawing
virtual_surface = pygame.Surface((VIRTUAL_WIDTH, VIRTUAL_HEIGHT))

# Set up the actual display. We'll use FULLSCREEN or windowed, but our game logic works on the virtual surface.
screen = pygame.display.set_mode((pygame.display.Info().current_w, pygame.display.Info().current_h), pygame.FULLSCREEN)
pygame.display.set_caption("Mini Golf")

# For scaling purposes, we always know our virtual resolution.
WIDTH, HEIGHT = VIRTUAL_WIDTH, VIRTUAL_HEIGHT  # these remain fixed for game logic
BALL_SPEED = WIDTH  # Ball speed based on virtual width

# Constants (base values)
BORDER_THICKNESS = 50  # Thickness of the outer gray walls
BASE_BALL_RADIUS = 45
BASE_HOLE_RADIUS = 45
FRICTION = 0.9875
ANGLE_SPEED = 5
MAX_POWER = 3
PAUSE_HOLD_TIME = 6000

# Colors
WHITE     = (255, 255, 255)
GREEN     = (0, 128, 0)
RED       = (255, 0, 0)
BLACK     = (0, 0, 0)
GREY      = (50, 50, 50)
DARK_GREY = (50, 50, 50)
BLUE      = (0, 0, 255)
SAND      = (194, 178, 128)

# Global game state variables (using virtual resolution coordinates)
ball_x = 0
ball_y = 0
hole_x, hole_y = 0, 0
ball_velocity = [0, 0]
can_shoot = True
stroke_count = 0

# Aiming
angle = 0
rotate_direction = 1
rotating = False
power = 0
charging = False

# For detecting long-press on Return (Enter)
return_key_hold_start = None
pause_triggered = False

# Level variables
current_level = 1
TOTAL_LEVELS = 9  # Only 2 levels as requested
current_hole_radius = BASE_HOLE_RADIUS

# Hazards (coordinates in virtual resolution)
current_walls = []
current_waters = []
current_sands = []

# Font for text (drawn on virtual surface)
font = pygame.font.Font(None, 36)

clock = pygame.time.Clock()


# --- TTS and Utility Functions ---

def speak(text):
    tts_engine.say(text)
    tts_engine.runAndWait()


def clamp(val, min_val, max_val):
    return max(min_val, min(val, max_val))


def circle_rect_collision(cx, cy, radius, rx, ry, rw, rh):
    closest_x = clamp(cx, rx, rx + rw)
    closest_y = clamp(cy, ry, ry + rh)
    distance = math.hypot(cx - closest_x, cy - closest_y)
    return distance < radius


def bounce_off_hazard_wall(cx, cy, vel, radius, rect):
    rx, ry, rw, rh = rect
    if not circle_rect_collision(cx, cy, radius, rx, ry, rw, rh):
        return cx, cy
    closest_x = clamp(cx, rx, rx + rw)
    closest_y = clamp(cy, ry, ry + rh)
    dx = cx - closest_x
    dy = cy - closest_y
    dist = math.hypot(dx, dy)
    if dist == 0:
        dx, dy = 1, 0
        dist = 1
    n_x, n_y = dx / dist, dy / dist
    penetration = radius - dist
    cx += n_x * penetration
    cy += n_y * penetration
    dot = vel[0] * n_x + vel[1] * n_y
    vel[0] = (vel[0] - 2 * dot * n_x) * 0.8
    vel[1] = (vel[1] - 2 * dot * n_y) * 0.8
    return cx, cy


def announce_level(level):
    if level == 1:
        speak("Ben's Mini Golf")
    else:
        speak(f"Level {level}")



def load_level(level):
    global ball_x, ball_y, hole_x, hole_y, current_hole_radius
    global ball_velocity, can_shoot, rotating, power, charging, angle, rotate_direction
    global current_walls, current_waters, current_sands

    # Define the playable area in virtual coordinates.
    play_x0 = BORDER_THICKNESS
    play_y0 = BORDER_THICKNESS
    play_width = WIDTH - 2 * BORDER_THICKNESS
    play_height = HEIGHT - 2 * BORDER_THICKNESS

    if level == 1:
        # Level 1: default, no hazards.
        ball_vert_pct = 0.2
        hole_vert_pct = 0.8
        ball_x = play_x0 + BASE_BALL_RADIUS + 10
        ball_y = play_y0 + BASE_BALL_RADIUS + ball_vert_pct * (play_height - 2 * BASE_BALL_RADIUS)
        hole_x = play_x0 + play_width - BASE_HOLE_RADIUS - 10
        hole_y = play_y0 + BASE_HOLE_RADIUS + hole_vert_pct * (play_height - 2 * BASE_BALL_RADIUS)
        current_walls = []
        current_waters = []
        current_sands = []
        current_hole_radius = BASE_HOLE_RADIUS

    elif level == 2:
        # Level 2: custom layout (exported from level editor)
        current_walls = [
            (489, 279, 120, 240),
        ]
        current_waters = [
        ]
        current_sands = [
        ]
        ball_x, ball_y = (112, 372)
        hole_x, hole_y = (1068, 398)
        current_hole_radius = BASE_HOLE_RADIUS

    elif level == 3:
        # Level 2: custom layout (exported from level editor)
        current_walls = [
            (503, 509, 120, 240),
        ]
        current_waters = [
        ]
        current_sands = [
            (343, 110, 100, 60),
            (343, 50, 100, 60),
            (343, 169, 100, 60),
            (343, 228, 100, 60),
            (443, 198, 150, 90),
            (443, 108, 150, 90),
            (443, 50, 150, 90),
        ]
        ball_x, ball_y = (133, 617)
        hole_x, hole_y = (976, 159)
        current_hole_radius = BASE_HOLE_RADIUS     

    elif level == 4:
        # Level 2: custom layout (exported from level editor)
        current_walls = [
        ]
        current_waters = [
            (670, 660, 150, 90),
            (670, 571, 150, 90),
            (396, 49, 150, 90),
            (396, 137, 150, 90),
        ]
        current_sands = [
            (546, 48, 150, 90),
            (546, 137, 150, 90),
            (819, 660, 150, 90),
            (819, 571, 150, 90),
        ]
        ball_x, ball_y = (190, 260)
        hole_x, hole_y = (943, 170)
        current_hole_radius = BASE_HOLE_RADIUS  

    elif level == 5:
        # Level 2: custom layout (exported from level editor)
        current_walls = [
            (352, 492, 50, 100),
            (402, 444, 50, 100),
            (451, 392, 50, 100),
        ]
        current_waters = [
            (999, 51, 150, 90),
            (999, 139, 150, 90),
            (999, 225, 150, 90),
        ]
        current_sands = [
            (448, 50, 50, 30),
            (461, 79, 50, 30),
            (487, 107, 50, 30),
            (497, 50, 50, 30),
            (511, 77, 50, 30),
            (502, 128, 50, 30),
            (528, 143, 50, 30),
            (552, 115, 50, 30),
            (536, 102, 50, 30),
            (560, 75, 50, 30),
            (545, 50, 50, 30),
            (589, 50, 50, 30),
            (597, 79, 50, 30),
            (582, 104, 50, 30),
            (570, 135, 50, 30),
            (594, 117, 50, 30),
            (612, 92, 50, 30),
            (625, 68, 50, 30),
            (637, 49, 50, 30),
            (550, 159, 50, 30),
        ]
        ball_x, ball_y = (254, 397)
        hole_x, hole_y = (666, 515)
        current_hole_radius = BASE_HOLE_RADIUS  

    elif level == 6:
        # Level 2: custom layout (exported from level editor)
        current_walls = [
            (589, 49, 120, 240),
            (378, 510, 120, 240),
            (199, 322, 50, 100),
            (149, 372, 50, 100),
            (247, 263, 50, 100),
        ]
        current_waters = [
            (999, 51, 150, 90),
            (999, 139, 150, 90),
            (999, 225, 150, 90),
            (709, 50, 150, 90),
            (851, 50, 150, 90),
        ]
        current_sands = [
            (685, 691, 100, 60),
            (706, 633, 100, 60),
            (783, 690, 100, 60),
            (806, 630, 100, 60),
            (766, 575, 100, 60),
            (805, 521, 100, 60),
            (864, 577, 100, 60),
            (883, 635, 100, 60),
            (931, 691, 100, 60),
            (879, 691, 100, 60),
        ]
        ball_x, ball_y = (209, 128)
        hole_x, hole_y = (908, 213)
        current_hole_radius = BASE_HOLE_RADIUS   

    elif level == 7:
        # Level 2: custom layout (exported from level editor)
        current_walls = [
            (298, 510, 120, 240),
            (298, 323, 120, 240),
            (305, 49, 50, 100),
            (354, 49, 50, 100),
            (403, 49, 50, 100),
            (739, 173, 50, 100),
            (786, 222, 50, 100),
            (833, 269, 50, 100),
            (881, 313, 50, 100),
        ]
        current_waters = [
            (49, 660, 150, 90),
            (196, 660, 150, 90),
            (345, 660, 150, 90),
            (493, 660, 150, 90),
            (642, 660, 150, 90),
            (851, 660, 150, 90),
            (999, 660, 150, 90),
            (740, 660, 150, 90),
            (51, 49, 150, 90),
            (181, 49, 150, 90),
            (306, 49, 150, 90),
            (821, 50, 50, 30),
            (772, 50, 50, 30),
            (723, 50, 50, 30),
            (692, 50, 50, 30),
            (868, 50, 50, 30),
            (913, 50, 50, 30),
            (960, 50, 50, 30),
            (1006, 50, 50, 30),
            (1051, 50, 50, 30),
            (1100, 50, 50, 30),
            (1100, 77, 50, 30),
            (1100, 106, 50, 30),
        ]
        current_sands = [
            (49, 569, 150, 90),
            (199, 569, 150, 90),
            (349, 569, 150, 90),
            (499, 569, 150, 90),
            (648, 569, 150, 90),
            (798, 569, 150, 90),
            (946, 569, 150, 90),
            (1000, 569, 150, 90),
            (514, 143, 100, 60),
            (539, 92, 100, 60),
            (597, 49, 100, 60),
            (571, 108, 100, 60),
            (440, 84, 100, 60),
            (403, 49, 100, 60),
            (500, 49, 100, 60),
        ]
        ball_x, ball_y = (124, 403)
        hole_x, hole_y = (989, 176)
        current_hole_radius = BASE_HOLE_RADIUS 

    elif level == 8:
        current_walls = [
            (295, 258, 120, 240),
            (726, 450, 120, 240),
            (410, 258, 50, 100),
            (455, 258, 50, 100),
            (501, 258, 50, 100),
            (540, 258, 50, 100),
        ]
        current_waters = [
            (96, 467, 50, 30),
            (146, 467, 50, 30),
            (196, 467, 50, 30),
            (245, 467, 50, 30),
            (51, 467, 50, 30),
            (1001, 50, 150, 90),
            (1001, 138, 150, 90),
            (1001, 224, 150, 90),
            (1001, 310, 150, 90),
            (1001, 395, 150, 90),
            (1001, 482, 150, 90),
            (1001, 570, 150, 90),
            (1001, 660, 150, 90),
        ]
        current_sands = [
            (767, 50, 100, 60),
            (781, 103, 100, 60),
            (804, 148, 100, 60),
            (832, 181, 100, 60),
            (872, 205, 100, 60),
            (902, 233, 100, 60),
            (863, 50, 100, 60),
            (865, 104, 100, 60),
            (901, 50, 100, 60),
            (902, 109, 100, 60),
            (902, 181, 100, 60),
            (903, 146, 100, 60),
            (49, 99, 50, 30),
            (49, 129, 50, 30),
            (49, 70, 50, 30),
            (49, 48, 50, 30),
            (97, 49, 50, 30),
            (147, 49, 50, 30),
            (178, 49, 50, 30),
            (79, 74, 50, 30),
            (66, 98, 50, 30),
            (108, 64, 50, 30),
            (340, 690, 100, 60),
            (433, 691, 100, 60),
            (367, 655, 100, 60),
            (426, 661, 100, 60),
            (393, 633, 50, 30),
            (417, 619, 50, 30),
            (438, 634, 50, 30),
            (462, 642, 50, 30),
        ]
        ball_x, ball_y = (160, 352)
        hole_x, hole_y = (159, 656)
        current_hole_radius = BASE_HOLE_RADIUS

    elif level == 9:
        # Level 2: custom layout (exported from level editor)
        current_walls = [
        ]
        current_waters = [
            (76, 79, 50, 30),
            (119, 78, 50, 30),
            (157, 77, 50, 30),
            (199, 80, 50, 30),
            (67, 107, 50, 30),
            (65, 137, 50, 30),
            (65, 178, 50, 30),
            (63, 217, 50, 30),
            (63, 240, 50, 30),
            (64, 195, 50, 30),
            (67, 157, 50, 30),
            (98, 177, 50, 30),
            (123, 176, 50, 30),
            (150, 176, 50, 30),
            (271, 75, 50, 30),
            (268, 99, 50, 30),
            (272, 129, 50, 30),
            (276, 153, 50, 30),
            (281, 173, 50, 30),
            (292, 201, 50, 30),
            (307, 217, 50, 30),
            (336, 228, 50, 30),
            (369, 232, 50, 30),
            (396, 227, 50, 30),
            (416, 206, 50, 30),
            (421, 176, 50, 30),
            (420, 132, 50, 30),
            (417, 150, 50, 30),
            (418, 115, 50, 30),
            (417, 90, 50, 30),
            (417, 65, 50, 30),
        ]
        current_sands = [
            (378, 516, 150, 90),
            (501, 528, 150, 90),
            (634, 524, 150, 90),
            (670, 460, 150, 90),
            (687, 393, 150, 90),
            (556, 443, 150, 90),
            (424, 442, 150, 90),
            (367, 449, 150, 90),
            (363, 396, 150, 90),
            (420, 382, 150, 90),
            (568, 380, 150, 90),
            (377, 358, 100, 60),
            (610, 329, 100, 60),
            (610, 275, 100, 60),
            (611, 220, 100, 60),
            (610, 164, 100, 60),
            (610, 107, 100, 60),
            (611, 65, 100, 60),
            (717, 350, 100, 60),
            (762, 431, 100, 60),
            (715, 532, 100, 60),
            (751, 482, 100, 60),
            (476, 565, 150, 90),
            (595, 563, 150, 90),
            (492, 350, 100, 60),
            (497, 648, 100, 60),
            (557, 652, 100, 60),
            (635, 649, 100, 60),
            (502, 691, 100, 60),
            (560, 692, 100, 60),
            (629, 690, 100, 60),
        ]
        ball_x, ball_y = (118, 661)
        hole_x, hole_y = (1013, 236)
        current_hole_radius = BASE_HOLE_RADIUS

    ball_velocity = [0, 0]
    can_shoot = True
    rotating = False
    power = 0
    charging = False
    angle = 0
    rotate_direction = 1

    announce_level(level)

def reset_game_state():
    global stroke_count, current_level
    stroke_count = 0
    current_level = 1
    load_level(current_level)


def end_game_screen(strokes):
    message = f"Congratulations, you finished in {strokes} strokes!"
    speak(message)
    end_font = pygame.font.Font(None, 72)
    display_time = 3000
    start_ticks = pygame.time.get_ticks()
    while pygame.time.get_ticks() - start_ticks < display_time:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                quit()
        virtual_surface.fill(GREEN)
        text_surface = end_font.render(message, True, WHITE)
        text_rect = text_surface.get_rect(center=(WIDTH // 2, HEIGHT // 2))
        virtual_surface.blit(text_surface, text_rect)
        scaled_surface = pygame.transform.scale(virtual_surface, screen.get_size())
        screen.blit(scaled_surface, (0, 0))
        pygame.display.flip()
    menu()
    reset_game_state()


def draw_text(text, font, color, x, y):
    text_surface = font.render(text, True, color)
    text_rect = text_surface.get_rect(center=(x, y))
    virtual_surface.blit(text_surface, text_rect)


# --- Force Focus and Start Menu Monitoring Functions ---

def get_window_handle():
    # Get the underlying window handle from pygame
    info = pygame.display.get_wm_info()
    return info["window"]

def force_focus():
    hwnd = get_window_handle()
    try:
        # SW_RESTORE = 9; this restores a minimized window
        ctypes.windll.user32.ShowWindow(hwnd, 9)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception as e:
        print(f"Error forcing focus: {e}")


def monitor_focus():
    while True:
        time.sleep(0.5)
        hwnd = get_window_handle()
        fg_hwnd = ctypes.windll.user32.GetForegroundWindow()
        if hwnd != fg_hwnd:
            force_focus()

def send_esc_key():
    # ESC key (virtual-key code 0x1B)
    ctypes.windll.user32.keybd_event(0x1B, 0, 0, 0)
    ctypes.windll.user32.keybd_event(0x1B, 0, 2, 0)
    print("ESC key sent to close Start Menu.")

def is_start_menu_open():
    hwnd = win32gui.GetForegroundWindow()
    class_name = win32gui.GetClassName(hwnd)
    return class_name in ["Shell_TrayWnd", "Windows.UI.Core.CoreWindow"]

def monitor_start_menu():
    while True:
        time.sleep(0.5)
        try:
            if is_start_menu_open():
                print("Start Menu detected. Closing it now.")
                send_esc_key()
        except Exception as e:
            print(f"Error in monitor_start_menu: {e}")

# Start the focus-monitoring threads as daemon threads.
threading.Thread(target=monitor_focus, daemon=True).start()
threading.Thread(target=monitor_start_menu, daemon=True).start()


def menu():
    menu_running = True
    selected_option = 0
    title_font = pygame.font.Font(None, 72)
    button_font = pygame.font.Font(None, 48)
    while menu_running:
        virtual_surface.fill(GREEN)
        pygame.draw.circle(virtual_surface, WHITE, (WIDTH // 3, HEIGHT // 2), BASE_BALL_RADIUS)
        pygame.draw.circle(virtual_surface, BLACK, (2 * WIDTH // 3, HEIGHT // 2), BASE_HOLE_RADIUS)
        draw_text("Ben's Mini Golf", title_font, WHITE, WIDTH // 2, HEIGHT // 4)
        play_color = RED if selected_option == 0 else WHITE
        exit_color = RED if selected_option == 1 else WHITE
        draw_text("Play", button_font, play_color, WIDTH // 2, HEIGHT // 2)
        draw_text("Exit", button_font, exit_color, WIDTH // 2, HEIGHT // 2 + 60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                quit()
            elif event.type == pygame.KEYUP:
                if event.key == pygame.K_SPACE:
                    selected_option = 1 - selected_option
                    speak("Play" if selected_option == 0 else "Exit")
                elif event.key == pygame.K_RETURN:
                    if selected_option == 0:
                        menu_running = False
                    else:
                        # Get the directory of the current file (minigolf game)
                        current_dir = os.path.dirname(os.path.abspath(__file__))
                        # Build the absolute path to comm-v9.py in the root folder
                        comm_v9_path = os.path.join(current_dir, "..", "comm-v9.py")
                        subprocess.Popen(["python", comm_v9_path])
                        pygame.quit()
                        quit()

        scaled_surface = pygame.transform.scale(virtual_surface, screen.get_size())
        screen.blit(scaled_surface, (0, 0))
        pygame.display.flip()


def pause_menu():
    global power, charging, rotating, return_key_hold_start, pause_triggered
    power = 0
    charging = False
    rotating = False
    pause_running = True
    selected_option = None  # No option is selected initially
    pause_font = pygame.font.Font(None, 48)
    speak("Paused")
    pygame.event.clear(pygame.KEYDOWN)
    pygame.event.clear(pygame.KEYUP)
    while pause_running:
        virtual_surface.fill(GREEN)
        draw_text("Pause Menu", font, WHITE, WIDTH // 2, HEIGHT // 4)
        # If no option is selected, display default (non-highlighted) text.
        if selected_option is None:
            continue_color = WHITE
            main_menu_color = WHITE
        else:
            continue_color = RED if selected_option == 0 else WHITE
            main_menu_color = RED if selected_option == 1 else WHITE

        draw_text("Continue Game", pause_font, continue_color, WIDTH // 2, HEIGHT // 2)
        draw_text("Main Menu", pause_font, main_menu_color, WIDTH // 2, HEIGHT // 2 + 60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                quit()
            elif event.type == pygame.KEYUP:
                if event.key == pygame.K_SPACE:
                    # If no option selected, set it to 0 on first spacebar release.
                    if selected_option is None:
                        selected_option = 0
                    else:
                        selected_option = 1 - selected_option  # Toggle selection
                    speak("Continue Game" if selected_option == 0 else "Main Menu")
                elif event.key == pygame.K_RETURN:
                    if selected_option is None:
                        # Do nothing if no option has been selected yet.
                        pass
                    elif selected_option == 0:
                        pause_running = False
                    else:
                        pause_running = False
                        speak("Main menu")
                        reset_game_state()
                        menu()
        scaled_surface = pygame.transform.scale(virtual_surface, screen.get_size())
        screen.blit(scaled_surface, (0, 0))
        pygame.display.flip()


# Start with main menu and load level 1.
menu()
reset_game_state()

running = True
while running:
    dt = clock.tick(60) / 1000
    virtual_surface.fill(GREEN)
    BALL_SPEED = WIDTH

    # Keep ball inside outer boundaries.
    ball_x = max(BORDER_THICKNESS + BASE_BALL_RADIUS, min(WIDTH - BORDER_THICKNESS - BASE_BALL_RADIUS, ball_x))
    ball_y = max(BORDER_THICKNESS + BASE_BALL_RADIUS, min(HEIGHT - BORDER_THICKNESS - BASE_BALL_RADIUS, ball_y))

    # Draw outer gray walls.
    pygame.draw.rect(virtual_surface, GREY, (0, 0, WIDTH, BORDER_THICKNESS))
    pygame.draw.rect(virtual_surface, GREY, (0, HEIGHT - BORDER_THICKNESS, WIDTH, BORDER_THICKNESS))
    pygame.draw.rect(virtual_surface, GREY, (0, 0, BORDER_THICKNESS, HEIGHT))
    pygame.draw.rect(virtual_surface, GREY, (WIDTH - BORDER_THICKNESS, 0, BORDER_THICKNESS, HEIGHT))

    # Draw hazards.
    for wall in current_walls:
        pygame.draw.rect(virtual_surface, DARK_GREY, wall)
    for water in current_waters:
        pygame.draw.rect(virtual_surface, BLUE, water)
    for sand in current_sands:
        pygame.draw.rect(virtual_surface, SAND, sand)

    # --- Event Processing ---
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                if return_key_hold_start is None:
                    return_key_hold_start = pygame.time.get_ticks()
                if can_shoot:
                    charging = True
                    power = 0
            elif event.key == pygame.K_SPACE and can_shoot:
                rotating = True
                rotate_direction *= -1

        elif event.type == pygame.KEYUP:
            if event.key == pygame.K_RETURN:
                if pause_triggered:
                    pause_triggered = False
                else:
                    if return_key_hold_start is not None:
                        hold_duration = pygame.time.get_ticks() - return_key_hold_start
                        if hold_duration < PAUSE_HOLD_TIME and can_shoot:
                            ball_velocity[0] = math.cos(math.radians(angle)) * BALL_SPEED * (power / MAX_POWER)
                            ball_velocity[1] = math.sin(math.radians(angle)) * BALL_SPEED * (power / MAX_POWER)
                            charging = False
                            power = 0
                            can_shoot = False
                            stroke_count += 1
                return_key_hold_start = None
            elif event.key == pygame.K_SPACE:
                rotating = False

    if return_key_hold_start is not None:
        if pygame.time.get_ticks() - return_key_hold_start >= PAUSE_HOLD_TIME:
            return_key_hold_start = None
            pause_triggered = True
            pause_menu()

    # --- Aiming and Shot Charging ---
    if rotating:
        angle += rotate_direction * ANGLE_SPEED * dt
        angle %= 360
    if charging:
        power = min(power + dt, MAX_POWER)

    # --- Ball Movement with Friction ---
    ball_x += ball_velocity[0] * dt
    ball_y += ball_velocity[1] * dt
    ball_velocity[0] *= FRICTION
    ball_velocity[1] *= FRICTION

    # Bounce off outer walls.
    if ball_x - BASE_BALL_RADIUS < BORDER_THICKNESS or ball_x + BASE_BALL_RADIUS > WIDTH - BORDER_THICKNESS:
        ball_velocity[0] *= -0.8
    if ball_y - BASE_BALL_RADIUS < BORDER_THICKNESS or ball_y + BASE_BALL_RADIUS > HEIGHT - BORDER_THICKNESS:
        ball_velocity[1] *= -0.8

    # Bounce off hazard walls.
    for wall in current_walls:
        ball_x, ball_y = bounce_off_hazard_wall(ball_x, ball_y, ball_velocity, BASE_BALL_RADIUS, wall)

    # Check collisions with water hazards.
    hit_water = False
    for water in current_waters:
        if circle_rect_collision(ball_x, ball_y, BASE_BALL_RADIUS, *water):
            hit_water = True
            break
    if hit_water:
        stroke_count += 1
        load_level(current_level)

    # Check collisions with sand hazards.
    for sand in current_sands:
        if circle_rect_collision(ball_x, ball_y, BASE_BALL_RADIUS, *sand):
            ball_velocity[0] *= 0.7
            ball_velocity[1] *= 0.7

    # Check if ball is in the hole.
    if math.hypot(ball_x - hole_x, ball_y - hole_y) < current_hole_radius:
        pygame.time.delay(500)
        if current_level < TOTAL_LEVELS:
            current_level += 1
            load_level(current_level)
        else:
            end_game_screen(stroke_count)

    if abs(ball_velocity[0]) < 0.1 and abs(ball_velocity[1]) < 0.1:
        ball_velocity = [0, 0]
        can_shoot = True

    # --- Drawing the ball, hole, and aiming line ---
    pygame.draw.circle(virtual_surface, BLACK, (int(hole_x), int(hole_y)), current_hole_radius)
    pygame.draw.circle(virtual_surface, WHITE, (int(ball_x), int(ball_y)), BASE_BALL_RADIUS)
    if can_shoot or rotating:
        aim_x = ball_x + math.cos(math.radians(angle)) * 500
        aim_y = ball_y + math.sin(math.radians(angle)) * 500
        pygame.draw.line(virtual_surface, WHITE, (ball_x, ball_y), (aim_x, aim_y), 25)
    power_color = (0, 255, 0) if power < MAX_POWER * 0.33 else (255, 255, 0) if power < MAX_POWER * 0.66 else (255, 0, 0)
    pygame.draw.rect(virtual_surface, power_color, (WIDTH // 3, HEIGHT - 50, int((WIDTH // 3) * (power / MAX_POWER)), 60))
    pygame.draw.rect(virtual_surface, WHITE, (WIDTH // 3, HEIGHT - 50, WIDTH // 3, 60), 2)
    stroke_text = font.render(f"Strokes: {stroke_count}", True, WHITE)
    virtual_surface.blit(stroke_text, (WIDTH // 2 - 50, 10))
    level_text = font.render(f"Level: {current_level}/{TOTAL_LEVELS}", True, WHITE)
    virtual_surface.blit(level_text, (10, 10))

    # Scale the virtual surface to the actual screen resolution and display.
    scaled_surface = pygame.transform.scale(virtual_surface, screen.get_size())
    screen.blit(scaled_surface, (0, 0))
    pygame.display.flip()

pygame.quit()