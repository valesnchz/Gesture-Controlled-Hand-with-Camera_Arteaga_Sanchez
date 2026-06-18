#include <WiFi.h>
#include <WebServer.h>
#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// Configuración de la red WiFi que va a crear el ESP32
const char* ssid = "CamaraESP32"; // Usamos el mismo nombre para no tener que reconectar la PC
const char* password = "";        // Sin contraseña, igual que un AP simple

// El script de Python envía peticiones al puerto 82
WebServer server(82);

// Objeto PCA9685 en dirección por defecto 0x40
Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(0x40);

// Calibración de los servos (0 = Pulgar, 1 = Índice, 2 = Medio, 3 = Anular, 4 = Meñique)
const int ABIERTO[5] = { 150, 150, 150, 150, 150 };  // Valores para dedo extendido
const int CERRADO[5] = { 450, 500, 500, 500, 500 };  // Valores para dedo doblado

// ── FUNCIONES DE SERVOS ─────────────────────────────────────────

void moverServo(int canal, int valorPulso) {
  valorPulso = constrain(valorPulso, 100, 650);
  pca.setPWM(canal, 0, valorPulso);
}

void actualizarDedo(int canal, int estado) {
  int pulso = (estado == 1) ? ABIERTO[canal] : CERRADO[canal];
  moverServo(canal, pulso);
}

// ── SERVIDOR WEB ────────────────────────────────────────────────

// Esta función se ejecuta cuando llega una petición tipo: /dedos?estado=1,0,1,1,0
void handleDedos() {
  if (server.hasArg("estado")) {
    String estadoStr = server.arg("estado");
    
    // Esperamos un formato exacto como "1,0,1,1,0" (mínimo 9 caracteres)
    if (estadoStr.length() >= 9) {
      int pulgar  = estadoStr.charAt(0) - '0';
      int indice  = estadoStr.charAt(2) - '0';
      int medio   = estadoStr.charAt(4) - '0';
      int anular  = estadoStr.charAt(6) - '0';
      int menique = estadoStr.charAt(8) - '0';

      actualizarDedo(0, pulgar);
      actualizarDedo(1, indice);
      actualizarDedo(2, medio);
      actualizarDedo(3, anular);
      actualizarDedo(4, menique);
      
      server.send(200, "text/plain", "OK: " + estadoStr);
      Serial.println("Comando: " + estadoStr);
      return;
    }
  }
  server.send(400, "text/plain", "Error");
}

void setup() {
  Serial.begin(115200);

  // Iniciar comunicación I2C para el PCA9685
  // OJO: En ESP32 normales (NodeMCU-32S, etc) suele ser SDA=21, SCL=22.
  // En ESP32-CAM suele usarse SDA=14, SCL=15 o similares. Ajusta según tu hardware.
  Wire.begin(21, 22); 
  
  pca.begin();
  pca.setPWMFreq(50); // Frecuencia estándar para servos
  delay(100);

  // Iniciar la mano en posición abierta
  for(int i = 0; i < 5; i++) {
    moverServo(i, ABIERTO[i]);
    delay(50);
  }

  // Configurar ESP32 como Punto de Acceso WiFi (Access Point)
  Serial.println("Iniciando AP WiFi...");
  WiFi.softAP(ssid, password);
  
  IPAddress IP = WiFi.softAPIP(); // Por defecto será 192.168.4.1
  Serial.print("IP del ESP32: ");
  Serial.println(IP);

  // Configurar rutas del servidor web
  server.on("/dedos", HTTP_GET, handleDedos);
  server.begin();
  
  Serial.println("Servidor de comandos iniciado en el puerto 82.");
}

void loop() {
  // Escuchar a clientes web que envían peticiones
  server.handleClient();
}
