# Model — FOMO Gesture Detection (Edge Impulse)

Pre-trained FOMO object detection model for hand gesture recognition, developed in **Edge Impulse** and deployed on the **ESP32-CAM**.

## File

| File | Description |
|------|-------------|
| `ei-fomo2-arduino-1.0.9.zip` | Arduino-compatible C++ library with the trained FOMO model (EON Compiler, int8 quantized) |

## Model Details

| Parameter | Value |
|-----------|-------|
| **Project name** | fomo2 (ID: 1007427) |
| **Architecture** | FOMO — MobileNetV2 0.35 |
| **Input size** | 96 × 96 px, RGB |
| **Classes** | `close`, `open` |
| **Quantization** | int8 (EON Compiler) |
| **RAM usage** | ~133 KB (peak) |
| **Flash usage** | ~81.3 KB |
| **Inference time** | ~981 ms on ESP32-CAM |
| **Deploy version** | v9 (impulse #4) |
| **F1 Score** | 83.8% (non-background classes) |
| **Precision** | 0.88 |
| **Recall** | 0.80 |

## How to Use

1. Download `ei-fomo2-arduino-1.0.9.zip`
2. In Arduino IDE: **Sketch → Include Library → Add .ZIP Library**
3. Select the downloaded ZIP file
4. The library `fomo2_inferencing` will be available for your ESP32-CAM sketch

## Confidence Threshold

A confidence threshold of **0.60** is applied in firmware to filter uncertain detections:
- `>= 0.60` → sends servo command (open or close)
- `< 0.60` → holds current state, no movement

## Citation

If you use this model, please cite:

```
Arteaga, S.; Sanchez, V. A Dual Approach for Optimized Hand Gesture Recognition
Using MediaPipe and AI Edge Deployment with ESP32-CAM. IDEAL 2026.
Available at: https://github.com/valesnchz/Gesture-Controlled-Hand-ESP32-CAM
```
