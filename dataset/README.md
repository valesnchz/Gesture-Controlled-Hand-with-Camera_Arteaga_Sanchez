# Dataset — Gesture-Controlled Hand ESP32-CAM

Custom image dataset captured with the **ESP32-CAM** (OV2640 sensor) for training the FOMO-based hand gesture detection model deployed in this project.

## Classes

| Class | Description |
|-------|-------------|
| `close` | Closed fist — all five fingers retracted |
| `open` | Open palm — all five fingers fully extended |

## Dataset Split

| Subset | Close | Open | Total |
|--------|------:|-----:|------:|
| `training/` | 128 | 128 | 256 |
| `testing/` | 32 | 32 | 64 |
| **Total** | **160** | **160** | **320** |

> Images prefixed with `close_` belong to the Close class and `open_` to the Open class.  
> Augmented images in the training set are marked with the `_aug` suffix.

## Capture Conditions

- **Device:** ESP32-CAM with OV2640 camera module
- **Resolution:** Captured at native ESP32-CAM resolution, resized to 96×96 px for inference
- **Conditions varied:** Different backgrounds, lighting setups, hand orientations, and distances to reduce overfitting

## Citation

If you use this dataset, please cite:

```
Arteaga, S.; Sanchez, V. Gesture-Controlled Hand ESP32-CAM Dataset. 2026.
Available at: https://github.com/valesnchz/Gesture-Controlled-Hand-ESP32-CAM
```
