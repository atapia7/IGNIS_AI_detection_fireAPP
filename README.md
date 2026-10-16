# 🔥 IgnisAI — MVP

**Sistema de Detección Temprana de Incendios Forestales con Redes Neuronales Convolucionales (CNN — YOLOv8n)**
Región Cusco, Perú · Tesis UPC — Rojas Chuman, Cristhian / Tapia Almidón, Andree

MVP funcional que implementa las **12 historias de usuario** de los **4 sprints** del Product Backlog (Tabla 31 de la tesis), con el stack definido en el informe: **Python + YOLOv8n (Ultralytics) + OpenCV + Streamlit + SQLite + SMTP**.

---

## 🚀 Instalación y ejecución

```bash
# 1. Crear entorno e instalar dependencias
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python.exe -m pip install --upgrade pip

# 2. Ejecutar la plataforma
streamlit run app.py
```

**Usuario inicial:** `admin@ignisai.pe` / `admin123` (cámbielo tras el primer acceso).

**Correo de alertas (HU06, opcional):** ya no requiere variables de entorno.
Se configura desde la web, en **Configuración → Correo de alertas**:

1. Genere una **Contraseña de Aplicación de Google** de 16 caracteres en
   `myaccount.google.com/apppasswords` (requiere verificación en dos pasos
   activa en la cuenta).
2. Ingrese el correo remitente, la Contraseña de Aplicación y los
   destinatarios; habilite el envío y guarde.
3. Use **"Guardar y enviar correo de prueba"** para verificar la conexión
   SMTP antes de dejarlo en producción.

La contraseña se cifra (Fernet/AES) antes de guardarse en SQLite y nunca
se muestra en texto plano en la interfaz. Como alternativa de despliegue,
sigue siendo posible predefinirla por variables de entorno
(`IGNISAI_SMTP_USER`, `IGNISAI_SMTP_PASSWORD`, `IGNISAI_ALERT_TO`); la
configuración guardada desde la web tiene prioridad si ambas existen.

**Datos de demostración (opcional):** `python seed_demo.py` precarga
historial y reportes de ejemplo.

### Modelo de IA (HU01)
- Coloque sus pesos entrenados en `models/best.pt`, o súbalos desde **Configuración** (solo Administrador, ≤ 150 MB, extensión `.pt`).
- Para entrenar el modelo en Google Colab con GPU: use `train_model.py` con un dataset YOLO de clases `fuego`/`humo` (D-Fire, FASDD o Roboflow Universe). Objetivo de la tesis: **mAP@0.5 ≥ 70%**.
- Sin pesos ni `ultralytics` instalado, el sistema opera en **modo simulación** (heurística HSV) para demostrar el pipeline completo: interfaz, alertas, historial y reportería.

---

## 📋 Trazabilidad: Sprints → Historias de Usuario → Implementación

### Sprint 1 — Épica 1: Entrenamiento y Detección Local
| HU | Historia | Implementación | Criterios cubiertos |
|----|----------|----------------|---------------------|
| HU01 | Disposición de IA para reconocimiento de amenazas | `detector.py`, `train_model.py` | Carga local de pesos YOLOv8; inferencia por imagen ≤ 15 s; log de arranque en `logs/ignisai.log` |
| HU02 | Visualización continua del entorno en vivo | `views/dashboard.py` | Captura de cámara USB con OpenCV; resolución 640×480; indicador de FPS (objetivo ≥ 15) |
| HU03 | Resaltado automático de focos de incendio | `detector.py::draw` | Recuadro rojo (fuego) / amarillo (humo); seguimiento fluido; solo predicciones ≥ 50% |

### Sprint 2 — Épica 2: Gestión de Accesos y Actualización
| HU | Historia | Implementación | Criterios cubiertos |
|----|----------|----------------|---------------------|
| HU04 | Gestión de múltiples usuarios y roles | `views/usuarios.py`, `auth.py`, `database.py` | CRUD exclusivo del Administrador; campos obligatorios Nombre/Correo/Contraseña/Rol; RBAC con bloqueo y redirección de Operadores; contraseñas con PBKDF2-SHA256 |
| HU05 | Configuración y actualización del modelo | `views/configuracion.py` | Subida restringida a administradores; validación extensión YOLO y ≤ 150 MB; mensaje "Modelo actualizado correctamente"; recarga en caliente del motor |
| HU06 | Alerta automática vía correo, configurable desde la web | `alerting.py`, `database.py`, `crypto_utils.py`, `views/configuracion.py` | Disparo tras detección sostenida > 5 s; asunto "ALERTA IGNISAI: Posible incendio detectado"; fotograma anotado + fecha/hora adjuntos; cooldown anti-spam. Contraseña de Aplicación de Google (16 caracteres) configurada y validada desde la web, cifrada en SQLite; botón de correo de prueba |

### Sprint 3 — Épica 3: Verificación Operativa y Control
| HU | Historia | Implementación | Criterios cubiertos |
|----|----------|----------------|---------------------|
| HU07 | Dashboard Centralizado de Monitoreo | `views/dashboard.py` | Bloque central de video + panel lateral con las últimas 10 alertas (recientes primero); operable en Chrome/Edge sin complementos |
| HU08 | Clasificación de veracidad de la alerta | `views/dashboard.py`, `database.py` | Botones "Confirmar Incendio" / "Falsa Alarma" por alerta; actualización inmediata en SQLite; los botones desaparecen y muestran el estado final |
| HU09 | Visualización de métricas de confianza | `detector.py::draw` + panel | % de confianza en el borde superior del recuadro con fondo de contraste; % máximo almacenado por alerta en el panel |

### Sprint 4 — Épica 4: Reportería y Exportación de Datos
| HU | Historia | Implementación | Criterios cubiertos |
|----|----------|----------------|---------------------|
| HU10 | Registro histórico y vulnerabilidad temporal | `views/historial.py` | Tabla paginada con ID, Fecha, Hora, % Confianza y Estado de Veracidad; doble selector de calendario (Inicio/Fin) con filtrado dinámico |
| HU11 | Reporte de efectividad y precisión | `views/reportes.py` | Gráfico circular y de barras separando confirmadas vs falsas alarmas; consulta automática del mes en curso; etiquetas con conteo numérico; cálculo de FPR (objetivo tesis ≤ 20%) |
| HU12 | Exportación de datos operativos | `views/historial.py` | Botón "Exportar a CSV"; descarga exactamente los registros filtrados; nombre autogenerado `reporte_ignisai_DDMMYYYY.csv` |

---

## 🏗️ Arquitectura (alineada a la tesis)

```
ignisai/
├── app.py               # Entrada Streamlit: login, navegación, RBAC
├── config.py            # Parámetros del sistema (umbral 50%, 640x480, 5 s, etc.)
├── auth.py              # Autenticación y control de acceso por roles (HU04)
├── database.py          # Capa de Almacenamiento y Lógica (SQLite)
├── crypto_utils.py      # Cifrado (Fernet) de la Contraseña de Aplicación (HU06)
├── detector.py          # Motor de inferencia YOLOv8 + fallback simulación (HU01)
├── alerting.py          # Alertas SMTP con detección sostenida (HU06)
├── train_model.py       # Entrenamiento YOLOv8n (Colab/GPU) — Sprint 1
├── seed_demo.py         # Datos de demostración (Sprints 3-4)
├── views/
│   ├── dashboard.py     # HU02, HU03, HU07, HU08, HU09
│   ├── historial.py     # HU10, HU12
│   ├── reportes.py      # HU11
│   ├── usuarios.py      # HU04
│   └── configuracion.py # HU05 + correo de alertas HU06 + log HU01
├── models/              # Pesos entrenados (best.pt)
├── assets/              # Evidencias (fotogramas de alertas)
└── logs/                # ignisai.log (arranque del modelo)
```

**Roles y permisos (RBAC):**
- **Administrador:** todas las vistas.
- **Operador de Centro de Monitoreo:** Dashboard e Historial.
- **Gestor Estratégico:** Dashboard, Historial y Reportes.

## ✅ Pruebas internas ejecutadas
Se validaron programáticamente: autenticación y CRUD (HU04), inferencia ≤ 15 s con recuadros ≥ 50% (HU01/HU03), disparo de alerta tras 5 s sostenidos (HU06), últimas 10 alertas y clasificación de veracidad (HU07-HU09), tabla histórica con columnas requeridas y resumen de efectividad (HU10-HU11), y registro del arranque del modelo en log (HU01).
