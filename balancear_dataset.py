import pandas as pd
import numpy as np
import random
import os

def normalize_landmarks(coords):
    """
    Normaliza las coordenadas:
    1. Centra en la muñeca (punto 0).
    2. Escala para que la distancia muñeca-base del dedo medio (punto 9) sea 1.0.
    """
    wrist = coords[0].copy()
    coords_centered = coords - wrist
    
    # Calcular escala basada en la distancia muñeca-medio (puntos 0 y 9)
    # Esto hace que el modelo sea robusto al tamaño de la mano y distancia a la cámara
    dist_0_9 = np.linalg.norm(coords_centered[9])
    if dist_0_9 > 1e-6:
        coords_normalized = coords_centered / dist_0_9
    else:
        coords_normalized = coords_centered
        
    return coords_normalized

def augment_dataset(input_file, output_file, target_samples=500):
    """
    Lee el dataset, balancea las clases y aplica aumentos (ruido, escala, rotación).
    """
    if not os.path.exists(input_file):
        print(f"[ERROR] No se encontró el archivo {input_file}")
        return

    df = pd.read_csv(input_file)
    
    # --- FILTRO DE GESTOS ---
    # Solo trabajaremos con los que pidió el usuario
    gestos_permitidos = ['open', 'close', 'index']
    df = df[df['gesto'].isin(gestos_permitidos)]
    
    gestos = df['gesto'].unique()
    
    augmented_rows = []
    column_names = df.columns
    
    print("--- Distribución Original (Filtrada) ---")
    print(df['gesto'].value_counts())
    
    for gesto in gestos:
        df_gesto = df[df['gesto'] == gesto]
        samples = df_gesto.values.tolist()
        
        # Procesar y normalizar los originales primero
        normalized_originals = []
        for s in samples:
            coords = np.array(s[:-1], dtype=float).reshape(21, 3)
            # Normalizar (centrar y escalar)
            coords_norm = normalize_landmarks(coords)
            new_row = coords_norm.flatten().tolist() + [s[-1]]
            normalized_originals.append(new_row)
            augmented_rows.append(new_row)
        
        # Calcular cuántos faltan para llegar al objetivo
        num_to_add = target_samples - len(samples)
        
        if num_to_add > 0:
            print(f"Aumentando '{gesto}': generando {num_to_add} muestras nuevas...")
            for _ in range(num_to_add):
                # Elegir una muestra base (ya normalizada)
                base_sample = random.choice(normalized_originals)
                new_sample = list(base_sample)
                
                coords = np.array(new_sample[:-1], dtype=float).reshape(21, 3)
                
                # --- APLICAR TRANSFORMACIONES SOBRE ESPACIO NORMALIZADO ---
                
                # 1. Rotación pequeña (eje Z)
                angle = random.uniform(-0.3, 0.3) # aprox +/- 17 grados
                c, s = np.cos(angle), np.sin(angle)
                rotation_matrix = np.array([
                    [c, -s, 0],
                    [s,  c, 0],
                    [0,  0, 1]
                ])
                coords = coords.dot(rotation_matrix.T)
                
                # 2. Escalamiento pequeño
                scale = random.uniform(0.9, 1.1)
                coords *= scale
                
                # 3. Ruido aleatorio (jitter)
                noise = np.random.normal(0, 0.015, coords.shape)
                coords += noise
                
                # Guardar nueva muestra
                new_sample[:-1] = coords.flatten().tolist()
                augmented_rows.append(new_sample)
                
    # Crear el nuevo CSV
    new_df = pd.DataFrame(augmented_rows, columns=column_names)
    new_df.to_csv(output_file, index=False)
    
    print("\n--- Distribución Final (Normalizada y Balanceada) ---")
    print(new_df['gesto'].value_counts())
    print(f"\n[OK] Dataset guardado en: {output_file}")
    print("\nRECOMENDACIÓN:")
    print("1. Sube este nuevo archivo a Edge Impulse.")
    print("2. En Edge Impulse, asegúrate de que no haya otros pre-procesamientos de escalado que puedan interferir.")
    print("3. ¡IMPORTANTE! Al usar el modelo en Python, debes aplicar la misma NORMALIZACIÓN a los datos en tiempo real.")

if __name__ == "__main__":
    augment_dataset("dataset_landmarks_mano.csv", "dataset_balanceado_aumentado.csv", target_samples=600)
