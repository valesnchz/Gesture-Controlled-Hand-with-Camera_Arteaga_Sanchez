import cv2
import os
import shutil
import numpy as np

def calculate_brightness(image_path):
    img = cv2.imread(image_path)
    if img is None:
        return -1
    
    # Convert to HSV and get the V channel (brightness)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    brightness = np.mean(hsv[:, :, 2])
    return brightness

def clean_bright_images(dataset_dir, output_dir, threshold=180):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    moved_count = 0
    total_count = 0
    
    for root, dirs, files in os.walk(dataset_dir):
        for file in files:
            if file.lower().endswith(('.jpg', '.png', '.jpeg')):
                total_count += 1
                file_path = os.path.join(root, file)
                
                brightness = calculate_brightness(file_path)
                
                if brightness > threshold:
                    # Move to discarded folder
                    # Maintain class folder structure
                    class_name = os.path.basename(root)
                    target_class_dir = os.path.join(output_dir, class_name)
                    if not os.path.exists(target_class_dir):
                        os.makedirs(target_class_dir)
                    
                    target_path = os.path.join(target_class_dir, file)
                    shutil.move(file_path, target_path)
                    moved_count += 1
                    
    print(f"Total images checked: {total_count}")
    print(f"Images too bright (> {threshold}) moved: {moved_count}")
    print(f"Discarded images are in: {output_dir}")

if __name__ == '__main__':
    # You can change the threshold here. 
    # Normal images are usually 100-150. Very bright might be > 180 or 200.
    DATASET_DIR = "dataset_fotos_final"
    DISCARD_DIR = "fotos_descartadas_brillantes"
    THRESHOLD = 190
    
    clean_bright_images(DATASET_DIR, DISCARD_DIR, THRESHOLD)
