"""
IgnisAI - Entrenamiento del modelo YOLOv8n (HU01 - Sprint 1)
Pensado para ejecutarse en Google Colab con GPU (según la tesis) o en
un entorno local con `ultralytics` instalado.

Dataset esperado (formato YOLO):
    dataset/
    ├── data.yaml        (names: [fuego, humo])
    ├── train/images + train/labels
    └── valid/images + valid/labels

Datasets públicos sugeridos: D-Fire, FASDD, o el dataset "fire-smoke"
de Roboflow Universe.

Criterios de la tesis:
    - Transfer learning sobre YOLOv8n.
    - mAP@0.5 objetivo >= 70-75% en el conjunto de validación.
"""
from ultralytics import YOLO


def main():
    # Transfer learning desde pesos preentrenados en COCO
    model = YOLO("yolov8n.pt")

    results = model.train(
        data="dataset/data.yaml",   # ajustar a la ruta real del dataset
        epochs=100,
        imgsz=640,
        batch=16,
        patience=20,
        device=0,                   # GPU (Colab). Usar 'cpu' si no hay GPU
        project="runs_ignisai",
        name="yolov8n_fuego_humo",
    )

    # Validación: verificar mAP@0.5 frente al umbral de la tesis
    metrics = model.val()
    map50 = metrics.box.map50
    print(f"\nmAP@0.5 = {map50*100:.2f}%  (objetivo tesis: >= 70%)")
    print("Pesos finales: runs_ignisai/yolov8n_fuego_humo/weights/best.pt")
    print("Copie best.pt a la carpeta models/ del proyecto IgnisAI.")


if __name__ == "__main__":
    main()
