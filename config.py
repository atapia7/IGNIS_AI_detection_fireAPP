"""
IgnisAI - Configuración central del sistema
Sistema de Detección Temprana de Incendios Forestales (CNN - YOLOv8n)
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Base de datos (SQLite - Capa de Almacenamiento y Lógica) ---
DB_PATH = os.environ.get("IGNISAI_DB_PATH", os.path.join(BASE_DIR, "ignisai.db"))

# --- Modelo de IA (HU01 / HU05) ---
MODELS_DIR = os.path.join(BASE_DIR, "models")
DEFAULT_MODEL_PATH = os.path.join(MODELS_DIR, "best.pt")   # pesos entrenados YOLOv8n
MAX_MODEL_SIZE_MB = 150                                     # HU05: tamaño máximo 150 MB
VALID_MODEL_EXTENSIONS = (".pt", ".onnx")                   # HU05: extensiones válidas YOLO

# Clases objetivo del modelo — usadas como fallback de índice en detector.py.
# NOTA: los modelos incluidos (best.pt / fire_8n.pt) solo tienen clase 0 = "fire".
# Si se carga un modelo con 2 clases (fuego + humo), agregar {0: "fire", 1: "smoke"}.
TARGET_CLASSES = {0: "fire", 1: "smoke"}

# --- Video / Detección (HU02 / HU03) ---
CAMERA_INDEX = 0            # cámara USB
FRAME_WIDTH = 640           # HU02: resolución mínima 640x480
FRAME_HEIGHT = 480
MIN_FPS = 15                # HU02: mínimo 15 FPS
CONFIDENCE_THRESHOLD = 0.50 # HU03: umbral 50% para dibujar recuadro

# Colores BGR de los recuadros (HU03)
BOX_COLORS = {"fuego": (0, 0, 255), "humo": (0, 255, 255)}  # rojo / amarillo

# --- Alertas (HU06) ---
ALERT_SUSTAIN_SECONDS = 5   # HU06: detección sostenida > 5 s dispara correo
ALERT_COOLDOWN_SECONDS = 60 # anti-spam entre correos consecutivos
EMAIL_SUBJECT = "ALERTA IGNISAI: Posible incendio detectado"

# Configuración SMTP de fábrica / respaldo (variables de entorno).
# HU06 permite configurar el correo de alertas directamente desde la web
# (ver Configuración → Correo de alertas); esa configuración, guardada
# cifrada en la base de datos, tiene prioridad sobre estas variables.
# Estas solo se usan si nadie ha configurado nada aún desde la interfaz.
SMTP_HOST = os.environ.get("IGNISAI_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("IGNISAI_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("IGNISAI_SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("IGNISAI_SMTP_PASSWORD", "")
ALERT_RECIPIENTS = [r for r in os.environ.get("IGNISAI_ALERT_TO", "").split(",") if r]

# --- Logs (HU01: registro de arranque del modelo) ---
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "ignisai.log")

# --- Roles del sistema (HU04) ---
ROLES = ("Administrador", "Operador", "Gestor")

# --- Dashboard (HU09/HU07 según Product Backlog) ---
DASHBOARD_LAST_ALERTS = 10  # últimas 10 detecciones en panel lateral
HISTORY_PAGE_SIZE = 10      # paginación del registro histórico (HU10)
