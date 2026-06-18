/*
  ================================================================
   EJEMPLO: RECIBIR CLASIFICACIÓN DESDE PYTHON (ARDUINO ESTÁNDAR)
  ================================================================
   Este sketch es para placas Arduino estándar (UNO, Nano, Mega, etc.)
   usando la librería nativa <Servo.h> y conectando los servos
   directamente a los pines digitales de la placa (sin PCA9685).
   
   Conexiones sugeridas (Arduino UNO / Nano):
     Pin 3  ──> Servo Pulgar
     Pin 5  ──> Servo Índice
     Pin 6  ──> Servo Medio
     Pin 9  ──> Servo Anular
     Pin 10 ──> Servo Meñique
     GND    ──> GND común con la fuente de poder de los servos
     
   ⚠️ IMPORTANTE: Alimenta los servos con una fuente externa de 5V.
      Une el GND de la fuente externa con el GND del Arduino.
  ================================================================
*/

#include <Servo.h>

// Crear objetos Servo para cada dedo
Servo servoPulgar;
Servo servoIndice;
Servo servoMedio;
Servo servoAnular;
Servo servoMenique;

// Pines digitales PWM en Arduino UNO / Nano
#define PIN_PULGAR   3
#define PIN_INDICE   5
#define PIN_MEDIO    6
#define PIN_ANULAR   9
#define PIN_MENIQUE  10

// Calibración de ángulos (en grados de 0 a 180)
// Ajusta estos valores según la respuesta física de tu mano 3D
const int ABIERTO[5] = { 10,  10,  10,  10,  10 };  // Dedos extendidos (casi 0°)
const int CERRADO[5] = { 150, 160, 160, 160, 160 }; // Dedos doblados (apriete)

// LED integrado en Arduino UNO/Nano (Pin 13)
#define LED_INDICADOR 13

// Variables para lectura serial
String entradaSerial = "";
bool datoCompleto = false;

// ================================================================
//  Función para mover un dedo individual a su posición (Abierto/Cerrado)
// ================================================================
void moverDedo(Servo &unServo, int canal, int estado) {
  int angulo = (estado == 1) ? ABIERTO[canal] : CERRADO[canal];
  angulo = constrain(angulo, 0, 180); // Rango seguro para el servo
  unServo.write(angulo);
}

// ================================================================
//  Función que ejecuta un GESTO COMPLETO (combinación de 5 dedos)
// ================================================================
void ejecutarGesto(int pulgar, int indice, int medio, int anular, int menique) {
  moverDedo(servoPulgar,  0, pulgar);
  moverDedo(servoIndice,  1, indice);
  moverDedo(servoMedio,   2, medio);
  moverDedo(servoAnular,  3, anular);
  moverDedo(servoMenique, 4, menique);
}

// ================================================================
//  Función para procesar la clasificación recibida
// ================================================================
void procesarClasificacion(String gesto) {
  gesto.trim(); // Limpiar espacios y saltos de línea
  
  if (gesto.length() == 0) return;

  Serial.print("Gesto Recibido: ");
  Serial.println(gesto);

  // Parpadeo rápido del LED al recibir datos
  digitalWrite(LED_INDICADOR, HIGH);

  // --- Mapeo de Clasificaciones a Movimientos ---
  if (gesto == "MANO_ABIERTA") {
    ejecutarGesto(1, 1, 1, 1, 1); // Todos abiertos
    Serial.println("-> Acción: Mano Abierta");
  } 
  else if (gesto == "PUNO") {
    ejecutarGesto(0, 0, 0, 0, 0); // Todos cerrados
    Serial.println("-> Acción: Cerrar Puño");
  } 
  else if (gesto == "LIKE") {
    ejecutarGesto(1, 0, 0, 0, 0); // Solo pulgar abierto
    Serial.println("-> Acción: Like / Pulgar arriba");
  } 
  else if (gesto == "ROCK") {
    ejecutarGesto(1, 1, 0, 0, 1); // Pulgar, índice y meñique abiertos
    Serial.println("-> Acción: Rock and Roll");
  } 
  else if (gesto == "NUMERO_2") {
    ejecutarGesto(0, 1, 1, 0, 0); // Índice y medio abiertos
    Serial.println("-> Acción: Símbolo de Paz / Número 2");
  } 
  else {
    Serial.print("-> Advertencia: Clasificación no definida: ");
    Serial.println(gesto);
  }

  delay(80);
  digitalWrite(LED_INDICADOR, LOW);
}

// ================================================================
void setup() {
  // Configurar puerto serial a 9600 baudios (igual que en Python)
  Serial.begin(9600);
  entradaSerial.reserve(30);

  pinMode(LED_INDICADOR, OUTPUT);
  digitalWrite(LED_INDICADOR, LOW);

  // Asociar los objetos Servo a sus pines físicos correspondientes
  servoPulgar.attach(PIN_PULGAR);
  servoIndice.attach(PIN_INDICE);
  servoMedio.attach(PIN_MEDIO);
  servoAnular.attach(PIN_ANULAR);
  servoMenique.attach(PIN_MENIQUE);

  delay(200);

  // Posición inicial: todos los dedos abiertos
  ejecutarGesto(1, 1, 1, 1, 1);
  
  Serial.println("Arduino Listo. Esperando clasificaciones...");
}

// ================================================================
void loop() {
  // 1. Leer caracteres del puerto serial
  while (Serial.available() > 0) {
    char caracter = (char)Serial.read();
    
    if (caracter == '\n') {
      datoCompleto = true;
    } else {
      entradaSerial += caracter;
    }
  }

  // 2. Procesar el comando al recibir la línea completa
  if (datoCompleto) {
    procesarClasificacion(entradaSerial);
    
    // Enviar confirmación de regreso a Python
    Serial.print("ACK_ARDUINO:");
    Serial.println(entradaSerial);

    entradaSerial = "";
    datoCompleto = false;
  }
}
