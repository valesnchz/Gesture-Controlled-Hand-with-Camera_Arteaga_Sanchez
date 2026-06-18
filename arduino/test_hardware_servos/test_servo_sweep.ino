/*
 ================================================================
  TEST DE BARRIDO - Encuentra el rango de tus servos
  ESP32 + PCA9685
 ================================================================
  Este sketch mueve el servo del Canal 0 (Pulgar) desde el
  valor minimo hasta el maximo lentamente para que puedas
  ver en que punto empieza y termina de moverse.

  Observa el Monitor Serial (115200 baud) para ver el valor
  actual mientras el servo se mueve.

  Si el servo NO SE MUEVE NI HACE RUIDO: problema de alimentacion.
  Si el servo SE MUEVE: apunta el valor minimo y maximo donde se mueve.
 ================================================================
*/

#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(0x40);

void setup() {
  Serial.begin(115200);
  Serial.println("=== TEST DE BARRIDO DE SERVOS ===");
  Serial.println("Mirando Canal 0 (primer servo)...");
  Serial.println("Si el servo no se mueve ni zumba -> problema de alimentacion");
  Serial.println("");

  Wire.begin(); // GPIO 21 SDA, GPIO 22 SCL
  pca.begin();
  pca.setPWMFreq(50); // 50Hz para servos estandar
  delay(500);

  Serial.println("Posicion inicial: pulso = 150 (esperando 2 seg)...");
  pca.setPWM(0, 0, 150);
  delay(2000);
}

void loop() {
  // ── BARRIDO DE SUBIDA (100 → 650) ──────────────────────────
  Serial.println("\n>> SUBIENDO de 100 a 650...");
  for (int pulso = 100; pulso <= 650; pulso += 10) {
    pca.setPWM(0, 0, pulso);
    Serial.print("Pulso: ");
    Serial.println(pulso);
    delay(150); // Pausa entre pasos para ver el movimiento
  }

  delay(1000);

  // ── BARRIDO DE BAJADA (650 → 100) ──────────────────────────
  Serial.println("\n>> BAJANDO de 650 a 100...");
  for (int pulso = 650; pulso >= 100; pulso -= 10) {
    pca.setPWM(0, 0, pulso);
    Serial.print("Pulso: ");
    Serial.println(pulso);
    delay(150);
  }

  delay(1000);
}
