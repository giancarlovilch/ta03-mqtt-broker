// Prueba: PIR único (GPIO27) con dos mediciones derivadas:
//   - movimiento: estado instantáneo (0/1)
//   - conteo_eventos: detecciones nuevas (flancos 0->1) en ventana de 10s
// Clasifica demanda: 0 = sin demanda, 1 = baja, 2 = media, >=3 = alta.
// Umbrales calibrados empíricamente: el módulo PIR tiene un tiempo de
// bloqueo (~2-3s) entre detecciones, por lo que en 10s rara vez supera 3-4 eventos.

const int PIR_PIN = 27;
const unsigned long VENTANA_MS = 10000;

int estadoAnterior = LOW;
int conteoEventos = 0;
unsigned long inicioVentana = 0;

void setup() {
  Serial.begin(115200);
  pinMode(PIR_PIN, INPUT);
  delay(1000);
  inicioVentana = millis();
  Serial.println("Lector PIR listo. Reportando cada 10s.");
}

void loop() {
  int estadoActual = digitalRead(PIR_PIN);

  // Cuenta solo detecciones nuevas (flanco de subida), no todo el tiempo que esté en HIGH
  if (estadoActual == HIGH && estadoAnterior == LOW) {
    conteoEventos++;
  }
  estadoAnterior = estadoActual;

  if (millis() - inicioVentana >= VENTANA_MS) {
    String demanda;
    if (conteoEventos == 0) {
      demanda = "sin demanda";
    } else if (conteoEventos == 1) {
      demanda = "baja";
    } else if (conteoEventos == 2) {
      demanda = "media";
    } else {
      demanda = "alta";
    }

    bool alertaActiva = (conteoEventos >= 2); // true si demanda es "media" o "alta"
    String motivo = alertaActiva
      ? "Demanda media o alta: posible acumulacion de visitantes"
      : "Flujo normal";

    Serial.print("movimiento=");
    Serial.print(estadoActual);
    Serial.print("  conteo_eventos=");
    Serial.print(conteoEventos);
    Serial.print("  demanda=");
    Serial.print(demanda);
    Serial.print("  alerta.activa=");
    Serial.print(alertaActiva ? "true" : "false");
    Serial.print("  motivo=");
    Serial.println(motivo);

    conteoEventos = 0;
    inicioVentana = millis();
  }

  delay(50); // lectura frecuente para no perder pulsos cortos
}
