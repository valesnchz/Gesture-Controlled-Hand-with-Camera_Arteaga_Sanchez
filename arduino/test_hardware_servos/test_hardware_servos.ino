/*
 ================================================================
  TEST HARDWARE - 5 DEDOS COMPLETOS (sin Python)
  ESP32 + PCA9685
 ================================================================
  Canal 0 = Pulgar
  Canal 1 = Indice
  Canal 2 = Medio
  Canal 3 = Anular
  Canal 4 = Menique
 ================================================================
*/

#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(0x40);

#define CANAL_PULGAR   0
#define CANAL_INDICE   1
#define CANAL_MEDIO    2
#define CANAL_ANULAR   3
#define CANAL_MENIQUE  4

#define ABIERTO  150
#define CERRADO  500

void setup() {
  Serial.begin(9600);
  Serial.println("=== TEST 5 DEDOS COMPLETOS ===");
  Serial.println("Pulgar(0) Indice(1) Medio(2) Anular(3) Menique(4)");

  Wire.begin(21, 22);
  pca.begin();
  pca.setPWMFreq(50);
  delay(500);

  // Todos abiertos al inicio
  for (int i = 0; i < 5; i++) {
    pca.setPWM(i, 0, ABIERTO);
    delay(100);
  }
  delay(1000);
  Serial.println("Iniciando ciclos abierto/cerrado...");
}

void loop() {
  Serial.println(">>> TODOS ABIERTOS");
  for (int i = 0; i < 5; i++) pca.setPWM(i, 0, ABIERTO);
  delay(2000);

  Serial.println(">>> TODOS CERRADOS");
  for (int i = 0; i < 5; i++) pca.setPWM(i, 0, CERRADO);
  delay(2000);
}
