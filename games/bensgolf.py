import pygame
import pyttsx3
import math
import time
import ctypes
import threading
import win32gui  # requires pywin32 package

# Initialize pygame and TTS engine
pygame.init()
tts_engine = pyttsx3.init()
tts_engine.setProperty('rate', 150)

# Fixed virtual game dimensions
VIRTUAL_WIDTH = 1200
VIRTUAL_HEIGHT = 800

# Create a virtual surface that holds all the game drawing
virtual_surface = pygame.Surface((VIRTUAL_WIDTH, VIRTUAL_HEIGHT))

# Set up the actual display. We'll use FULLSCREEN.
screen = pygame.display.set_mode(
    (pygame.display.Info().current_w, pygame.display.Info().current_h),
    pygame.FULLSCREEN
)
pygame.display.set_caption("Ben's Mini Golf")

# For scaling purposes, our game logic uses the fixed virtual resolution.
WIDTH, HEIGHT = VIRTUAL_WIDTH, VIRTUAL_HEIGHT
BALL_SPEED = WIDTH  # Ball speed based on virtual width

# Constants (base values)
BORDER_THICKNESS = 50
BASE_BALL_RADIUS = 45
BASE_HOLE_RADIUS = 45
FRICTION = 0.9875
ANGLE_SPEED = 20
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

# Global game state variables
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
TOTAL_LEVELS = 9
current_hole_radius = BASE_HOLE_RADIUS

# Hazards (using virtual resolution coordinates)
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

    play_x0 = BORDER_THICKNESS
    play_y0 = BORDER_THICKNESS
    play_width = WIDTH - 2 * BORDER_THICKNESS
    play_height = HEIGHT - 2 * BORDER_THICKNESS

    if level == 1:
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

    # [Level-specific layouts for levels 2..9 as before...]
    # For brevity, they remain unchanged in this snippet.
    elif level == 2:
        current_walls = [(489, 279, 120, 240)]
        current_waters = []
        current_sands = []
        ball_x, ball_y = (112, 372)
        hole_x, hole_y = (1068, 398)
        current_hole_radius = BASE_HOLE_RADIUS
    # ... (levels 3 through 9 omitted for brevity)

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

# --- Menu and Pause Functions ---

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
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    selected_option = 1 - selected_option
                    speak("Play" if selected_option == 0 else "Exit")
                elif event.key == pygame.K_RETURN:
                    if selected_option == 0:
                        menu_running = False
                    else:
                        # Launch comm-v9.py from the root folder.
                        subprocess.Popen(["python", "../comm-v9.py"])
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
    selected_option = 0
    pause_font = pygame.font.Font(None, 48)
    speak("Paused")
    pygame.event.clear(pygame.KEYDOWN)
    pygame.event.clear(pygame.KEYUP)
    while pause_running:
        virtual_surface.fill(GREEN)
        draw_text("Pause Menu", font, WHITE, WIDTH // 2, HEIGHT // 4)
        continue_color = RED if selected_option == 0 else WHITE
        main_menu_color = RED if selected_option == 1 else WHITE
        draw_text("Continue Game", pause_font, continue_color, WIDTH // 2, HEIGHT // 2)
        draw_text("Main Menu", pause_font, main_menu_color, WIDTH // 2, HEIGHT // 2 + 60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                quit()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    selected_option = 1 - selected_option
                    speak("Continue Game" if selected_option == 0 else "Main Menu")
                elif event.key == pygame.K_RETURN:
                    if selected_option == 0:
                        pause_running = False
                    else:
                        pause_running = False
                        speak("Main menu")
                        reset_game_state()
                        menu()
        scaled_surface = pygame.transform.scale(virtual_surface, screen.get_size())
        screen.blit(scaled_surface, (0, 0))
        pygame.display.flip()

# --- Main Game Loop ---
menu()
reset_game_state()

running = True
while running:
    dt = clock.tick(60) / 1000
    virtual_surface.fill(GREEN)
    BALL_SPEED = WIDTH

    ball_x = max(BORDER_THICKNESS + BASE_BALL_RADIUS, min(WIDTH - BORDER_THICKNESS - BASE_BALL_RADIUS, ball_x))
    ball_y = max(BORDER_THICKNESS + BASE_BALL_RADIUS, min(HEIGHT - BORDER_THICKNESS - BASE_BALL_RADIUS, ball_y))

    pygame.draw.rect(virtual_surface, GREY, (0, 0, WIDTH, BORDER_THICKNESS))
    pygame.draw.rect(virtual_surface, GREY, (0, HEIGHT - BORDER_THICKNESS, WIDTH, BORDER_THICKNESS))
    pygame.draw.rect(virtual_surface, GREY, (0, 0, BORDER_THICKNESS, HEIGHT))
    pygame.draw.rect(virtual_surface, GREY, (WIDTH - BORDER_THICKNESS, 0, BORDER_THICKNESS, HEIGHT))

    for wall in current_walls:
        pygame.draw.rect(virtual_surface, DARK_GREY, wall)
    for water in current_waters:
        pygame.draw.rect(virtual_surface, BLUE, water)
    for sand in current_sands:
        pygame.draw.rect(virtual_surface, SAND, sand)

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

    if rotating:
        angle += rotate_direction * ANGLE_SPEED * dt
        angle %= 360
    if charging:
        power = min(power + dt, MAX_POWER)

    ball_x += ball_velocity[0] * dt
    ball_y += ball_velocity[1] * dt
    ball_velocity[0] *= FRICTION
    ball_velocity[1] *= FRICTION

    if ball_x - BASE_BALL_RADIUS < BORDER_THICKNESS or ball_x + BASE_BALL_RADIUS > WIDTH - BORDER_THICKNESS:
        ball_velocity[0] *= -0.8
    if ball_y - BASE_BALL_RADIUS < BORDER_THICKNESS or ball_y + BASE_BALL_RADIUS > HEIGHT - BORDER_THICKNESS:
        ball_velocity[1] *= -0.8

    for wall in current_walls:
        ball_x, ball_y = bounce_off_hazard_wall(ball_x, ball_y, ball_velocity, BASE_BALL_RADIUS, wall)

    hit_water = False
    for water in current_waters:
        if circle_rect_collision(ball_x, ball_y, BASE_BALL_RADIUS, *water):
            hit_water = True
            break
    if hit_water:
        stroke_count += 1
        load_level(current_level)

    for sand in current_sands:
        if circle_rect_collision(ball_x, ball_y, BASE_BALL_RADIUS, *sand):
            ball_velocity[0] *= 0.7
            ball_velocity[1] *= 0.7

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

    pygame.draw.circle(virtual_surface, BLACK, (int(hole_x), int(hole_y)), current_hole_radius)
    pygame.draw.circle(virtual_surface, WHITE, (int(ball_x), int(ball_y)), BASE_BALL_RADIUS)
    if can_shoot or rotating:
        aim_x = ball_x + math.cos(math.radians(angle)) * 350
        aim_y = ball_y + math.sin(math.radians(angle)) * 350
        pygame.draw.line(virtual_surface, RED, (ball_x, ball_y), (aim_x, aim_y), 10)
    power_color = (0, 255, 0) if power < MAX_POWER * 0.33 else (255, 255, 0) if power < MAX_POWER * 0.66 else (255, 0, 0)
    pygame.draw.rect(virtual_surface, power_color, (WIDTH // 3, HEIGHT - 50, int((WIDTH // 3) * (power / MAX_POWER)), 60))
    pygame.draw.rect(virtual_surface, WHITE, (WIDTH // 3, HEIGHT - 50, WIDTH // 3, 60), 2)
    stroke_text = font.render(f"Strokes: {stroke_count}", True, WHITE)
    virtual_surface.blit(stroke_text, (WIDTH // 2 - 50, 10))
    level_text = font.render(f"Level: {current_level}/{TOTAL_LEVELS}", True, WHITE)
    virtual_surface.blit(level_text, (10, 10))

    scaled_surface = pygame.transform.scale(virtual_surface, screen.get_size())
    screen.blit(scaled_surface, (0, 0))
    pygame.display.flip()

pygame.quit()
