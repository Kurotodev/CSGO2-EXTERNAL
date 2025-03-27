import pymem
import pymem.process
import requests
import time
import math
import ctypes, sys
import win32api
import win32gui
import win32con
from threading import Thread
from PySide6.QtWidgets import QApplication, QWidget, QGraphicsView, QGraphicsScene
from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QPen, QColor, QFont, QPainter
CIRCLE_RADIUS = 30
# Constants
ESP_UPDATE_INTERVAL = 1
FULLSCREEN_WIDTH = 1920
FULLSCREEN_HEIGHT = 1080
CENTER_DOT_SIZE = 2
FPS_FONT_SIZE = 10
DISTANCE_FONT_SIZE = 9
BOX_COLOR = QColor(255, 0, 0)
HEALTH_BAR_BG_COLOR = QColor(0, 0, 0, 128)
HEALTH_BAR_COLOR = QColor(0, 255, 0, 200)
DISTANCE_UNIT_CONVERSION = 0.0254

class ESPSignals(QObject):
    toggle_signal = Signal()

class ESPOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.x, self.y, self.width, self.height = get_window_info()
        self.esp_active = True
        self.signals = ESPSignals()
        self.signals.toggle_signal.connect(self._toggle_esp)
        self.setGeometry(self.x, self.y, self.width, self.height)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setup_transparency()
        
        self.scene = QGraphicsScene(0, 0, self.width, self.height, self)
        self.view = QGraphicsView(self.scene, self)
        self.view.setGeometry(0, 0, self.width, self.height)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setStyleSheet("background: transparent;")
        self.view.setFrameShape(QGraphicsView.NoFrame)
        self.view.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.view.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_esp)
        self.timer.start(ESP_UPDATE_INTERVAL)
        
        # Initialize memory
        self.pm = pymem.Pymem("cs2.exe")
        self.client = pymem.process.module_from_name(self.pm.process_handle, "client.dll").lpBaseOfDll
        self.offsets, self.client_dll = get_offsets()
        
    def setup_transparency(self):
        hwnd = int(self.winId())
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, 
                             win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) | 
                             win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT)
    
    def update_esp(self):
        if self.esp_active:
            # Update window position
            new_x, new_y, new_width, new_height = get_window_info()
            if (new_x != self.x or new_y != self.y or
                new_width != self.width or new_height != self.height):
                self.x, self.y = new_x, new_y
                self.width, self.height = new_width, new_height
                self.setGeometry(self.x, self.y, self.width, self.height)
                self.view.setGeometry(0, 0, self.width, self.height)
                self.scene.setSceneRect(-self.width/2, -self.height/2, self.width, self.height)
            
            self.scene.clear()

            draw_esp(self.scene, self.pm, self.client, self.offsets, self.client_dll, self.width, self.height)

    def toggle_esp(self):
        # This can be called from any thread
        self.signals.toggle_signal.emit()
        
    def _toggle_esp(self):
        # This runs in the main Qt thread
        self.esp_active = not self.esp_active
        if self.esp_active:
            self.show()
            self.timer.start(ESP_UPDATE_INTERVAL)
            print("ESP enabled")
        else:
            self.scene.clear()
            self.timer.stop()
            self.hide()
            print("ESP disabled")

def get_offsets():
    offsets = requests.get('https://raw.githubusercontent.com/a2x/cs2-dumper/main/output/offsets.json').json()
    client_dll = requests.get('https://raw.githubusercontent.com/a2x/cs2-dumper/main/output/client_dll.json').json()
    return offsets, client_dll

def get_window_info():
    hwnd = win32gui.FindWindow(None, "Counter-Strike 2")
    if hwnd:
        rect = win32gui.GetWindowRect(hwnd)
        # For fullscreen windowed, use the full window dimensions
        width = rect[2] - rect[0]
        height = rect[3] - rect[1]
        return rect[0], rect[1], width, height
    return 0, 0, FULLSCREEN_WIDTH, FULLSCREEN_HEIGHT

def w2s(matrix, x, y, z, width, height):
    w = matrix[12] * x + matrix[13] * y + matrix[14] * z + matrix[15]
    if w < 0.001:
        return [-1, -1]
    
    screen_x = matrix[0] * x + matrix[1] * y + matrix[2] * z + matrix[3]
    screen_y = matrix[4] * x + matrix[5] * y + matrix[6] * z + matrix[7]
    
    screen_x = (width / 2) + (width / 2) * screen_x / w
    screen_y = (height / 2) - (height / 2) * screen_y / w
    
    return [int(screen_x), int(screen_y)]

import ctypes
import time



def move_mouse_to_head(head_pos):
    if win32api.GetAsyncKeyState(win32con.VK_MENU) & 0x8000:  # Right-click pressed
        current_pos = win32api.GetCursorPos()
        head_pos[1] = head_pos[1] + 10  # Ajusta la posición Y si es necesario
        delta_x = head_pos[0] - current_pos[0]
        delta_y = head_pos[1] - current_pos[1]

        # Calcula la nueva posición del mouse (sólo el desplazamiento)
        new_x = current_pos[0] + delta_x * 1  # Ajusta el multiplicador para el movimiento suave
        new_y = current_pos[1] + delta_y * 1  # Ajusta el multiplicador para el movimiento suave

        # Mueve el mouse usando mouse_event para simular el movimiento
        newdatax =  int(new_x) - current_pos[0]
        newdatay =  int(new_y) - current_pos[1]
        win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, newdatax, newdatay, 0, 0)

def draw_esp(scene, pm, client, offsets, client_dll, width, height):
    # Get important offsets
    try:
        dwEntityList = offsets['client.dll']['dwEntityList']
        dwLocalPlayerPawn = offsets['client.dll']['dwLocalPlayerPawn']
        dwViewMatrix = offsets['client.dll']['dwViewMatrix']
        
        # Get important client_dll fields
        m_iTeamNum = client_dll['client.dll']['classes']['C_BaseEntity']['fields']['m_iTeamNum']
        m_iHealth = client_dll['client.dll']['classes']['C_BaseEntity']['fields']['m_iHealth']
        m_lifeState = client_dll['client.dll']['classes']['C_BaseEntity']['fields']['m_lifeState']
        m_pGameSceneNode = client_dll['client.dll']['classes']['C_BaseEntity']['fields']['m_pGameSceneNode']
        m_modelState = client_dll['client.dll']['classes']['CSkeletonInstance']['fields']['m_modelState']
        m_hPlayerPawn = client_dll['client.dll']['classes']['CCSPlayerController']['fields']['m_hPlayerPawn']
        
        # Get local player
        local_player = pm.read_longlong(client + dwLocalPlayerPawn)
        local_team = pm.read_int(local_player + m_iTeamNum)
        
        # Get view matrix
        view_matrix = [pm.read_float(client + dwViewMatrix + i * 4) for i in range(16)]
        
        # Get entity list
        entity_list = pm.read_longlong(client + dwEntityList)
        list_entry = pm.read_longlong(entity_list + 0x10)
        
        # Draw center indicator (1 pixel dot)
        scene.addEllipse(width/2-1, height/2-1, CENTER_DOT_SIZE, CENTER_DOT_SIZE, QPen(QColor(255,255,255)), QColor(255,255,255))
        
        # Draw FPS
        fps_text = scene.addText("F1 ENABLE/DESABLE ESP | F2 EXIT", QFont("Arial", FPS_FONT_SIZE))
        fps_text.setDefaultTextColor(QColor(255,255,255))
                            # Parámetros para un monitor 1080p
        center_x = 1920 // 2  # El centro horizontal (la mitad de 1920)
        center_y = 1080 // 2  # El centro vertical (la mitad de 1080)
           # Radio del círculo (puedes ajustarlo como prefieras)

                    # Dibuja el círculo en el centro de la pantalla
        scene.addEllipse(center_x - CIRCLE_RADIUS, center_y - CIRCLE_RADIUS, 2 * CIRCLE_RADIUS, 2 * CIRCLE_RADIUS, QPen(BOX_COLOR, 2), Qt.NoBrush)

        # Loop through entities
        for i in range(1, 64):
            # Get entity controller
            controller = pm.read_longlong(list_entry + 0x78 * (i & 0x1FF))
            if controller == 0:
                continue
            try:

                # Get pawn handle
                pawn_handle = pm.read_longlong(controller + m_hPlayerPawn)
                if pawn_handle == 0:
                    continue
                    
                # Get pawn entry and address
                list_entry2 = pm.read_longlong(entity_list + 0x8 * ((pawn_handle & 0x7FFF) >> 9) + 0x10)
                try:
                    pawn = pm.read_longlong(list_entry2 + 0x78 * (pawn_handle & 0x1FF))
                    
                    # Skip if pawn is local player or invalid
                    if pawn == 0 or pawn == local_player:
                        continue
                        
                    # Get entity info
                    team = pm.read_int(pawn + m_iTeamNum)
                    health = pm.read_int(pawn + m_iHealth)
                    state = pm.read_int(pawn + m_lifeState)
                    
                    # Skip teammates and dead players (enemy only ESP)
                    if   health <= 0 or state != 256:
                        continue
                    # Get bone matrix
                    game_scene = pm.read_longlong(pawn + m_pGameSceneNode)
                    bone_matrix = pm.read_longlong(game_scene + m_modelState + 0x80)
                        
                    # Get head and feet positions
                    head_x = pm.read_float(bone_matrix + 6 * 0x20)
                    head_y = pm.read_float(bone_matrix + 6 * 0x20 + 0x4)
                    head_z = pm.read_float(bone_matrix + 6 * 0x20 + 0x8) + 8
                    head_pos = w2s(view_matrix, head_x, head_y, head_z, width, height)
                    
                    feet_z = pm.read_float(bone_matrix + 0 * 0x20 + 0x8)
                    feet_pos = w2s(view_matrix, head_x, head_y, feet_z, width, height)
                    
                    # Skip if offscreen
                    if head_pos[0] <= 0 or head_pos[0] >= width or head_pos[1] <= 0:
                        continue
                        
                    # Calculate box dimensions
                    box_height = feet_pos[1] - head_pos[1]
                    box_width = box_height * 0.5
                    heal_text = scene.addText(f"HEAL: {health:.1f}", QFont("Arial", DISTANCE_FONT_SIZE))
                    heal_text.setDefaultTextColor(BOX_COLOR)
                    heal_text.setPos(head_pos[0] - 20, head_pos[1] - 20)

                    # Draw box
                    scene.addRect(head_pos[0] - box_width/2, head_pos[1], 
                                box_width, box_height, QPen(BOX_COLOR, 2), Qt.NoBrush)
                    
                    # Draw health bar
                    hp_height = box_height * (health/100)
                    scene.addRect(head_pos[0] - box_width/2 - 8, head_pos[1], 
                                5, box_height, QPen(QColor(0,0,0), 1), HEALTH_BAR_BG_COLOR)
                    scene.addRect(head_pos[0] - box_width/2 - 8, head_pos[1] + box_height - hp_height, 
                                5, hp_height, QPen(QColor(0,255,0), 1), HEALTH_BAR_COLOR)
                    
                    # Get local player position
                    local_scene = pm.read_longlong(local_player + m_pGameSceneNode)
                    local_bone = pm.read_longlong(local_scene + m_modelState + 0x80)
                    local_x = pm.read_float(local_bone + 0 * 0x20)
                    local_y = pm.read_float(local_bone + 0 * 0x20 + 0x4)
                    local_z = pm.read_float(local_bone + 0 * 0x20 + 0x8)
                    
                    # Calculate distance in meters (Source 2 uses inches as base unit)
                    distance = math.sqrt((head_x - local_x)**2 + (head_y - local_y)**2 + (feet_z - local_z)**2) * DISTANCE_UNIT_CONVERSION
                    
                    # Draw distance text
                    distance_text = scene.addText(f"{distance:.1f}m", QFont("Arial", DISTANCE_FONT_SIZE))
                    distance_text.setDefaultTextColor(BOX_COLOR)
                    distance_text.setPos(head_pos[0] + box_width/2 + 5, head_pos[1])

                    if distance < 50.0:
                        closest_distance = distance
                        closest_head_pos = head_pos
                # Check if the head position is within the circle
                        dx = head_pos[0] - center_x
                        dy = head_pos[1] - center_y
                        if dx ** 2 + dy ** 2 <= CIRCLE_RADIUS ** 2:
                            # Draw the POV circle around the closest player
                            move_mouse_to_head(closest_head_pos)
                except pymem.exception.MemoryReadError as e:
                    pass
            finally:
             pass
    finally:
        pass
        

def main():

    # Wait for CS2 process
    while True:
        try:
            pymem.Pymem("cs2.exe")
            break
        except Exception:
            MessageBox = ctypes.windll.user32.MessageBoxW
            MessageBox(None, 'Could not find the csgo.exe process !', 'Error', 16)
            time.sleep(1)
            sys.exit(app.exec())
        
    # Start overlay
    app = QApplication(sys.argv)
    esp = ESPOverlay()
    esp.show()
    
    # Key listener thread
    def key_listener():
        while True:
            global CIRCLE_RADIUS  # Declarar como global

            if win32api.GetAsyncKeyState(win32con.VK_F1) & 0x8000:
                esp.toggle_esp()
                time.sleep(0.3)
            if win32api.GetAsyncKeyState(win32con.VK_INSERT) & 0x8000:
                CIRCLE_RADIUS = CIRCLE_RADIUS + 1
                time.sleep(0.3)
            if win32api.GetAsyncKeyState(win32con.VK_DELETE) & 0x8000:
                CIRCLE_RADIUS = CIRCLE_RADIUS - 1
                time.sleep(0.3)
                    
            if win32api.GetAsyncKeyState(win32con.VK_F2) & 0x8000:
                app.quit()
                break
                
            time.sleep(0.1)
    
    # Start key listener
    Thread(target=key_listener, daemon=True).start()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()