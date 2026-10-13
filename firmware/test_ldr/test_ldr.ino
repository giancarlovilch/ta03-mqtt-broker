// Prueba: módulo LDR (VCC->3V3, GND->GND, DO->GPIO34)
// Objetivo: confirmar que detecta luz/oscuridad y calibrar la perilla del módulo.

const int LDR_PIN = 34;

void setup() {
  Serial.begin(115200);
  pinMode(LDR_PIN, INPUT);
  delay(1000);
  Serial.println("Lector LDR listo. Tapa y destapa el sensor con la mano.");
}

void loop() {
  int estado = digitalRead(LDR_PIN); // 0 = LOW, 1 = HIGH

  Serial.print("DO = ");
  Serial.print(estado);
  Serial.print("  ->  ");
  Serial.println(estado == HIGH ? "OSCURO" : "LUMINOSO");

  delay(500);
}
