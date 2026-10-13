#include <WiFi.h>
#include <PsychicMqttClient.h>

// --- WiFi ---
const char* ssid = "SB";
const char* password = "soloboticas";

// --- MQTT (por internet, via Cloudflare Tunnel) ---
const char* mqtt_url = "wss://domotica.solodata.cc";
const char* mqtt_user = "esp32";
const char* mqtt_pass = "a12345A";
const char* topic_semaforo = "oficina/semaforo";
const char* topic_demanda = "oficina/demanda";

// --- Pines ---
const int PIR_PIN = 27;
const int RGB_R_PIN = 13;
const int RGB_G_PIN = 12;
const int RGB_B_PIN = 14;

const unsigned long VENTANA_MS = 10000;

int estadoAnterior = LOW;
int conteoEventos = 0;
unsigned long inicioVentana = 0;

PsychicMqttClient mqttClient;

const char* root_ca = R"EOF(
-----BEGIN CERTIFICATE-----
MIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw
TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh
cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTUwNjA0MTEwNDM4
WhcNMzUwNjA0MTEwNDM4WjBPMQswCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJu
ZXQgU2VjdXJpdHkgUmVzZWFyY2ggR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBY
MTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAK3oJHP0FDfzm54rVygc
h77ct984kIxuPOZXoHj3dcKi/vVqbvYATyjb3miGbESTtrFj/RQSa78f0uoxmyF+
0TM8ukj13Xnfs7j/EvEhmkvBioZxaUpmZmyPfjxwv60pIgbz5MDmgK7iS4+3mX6U
A5/TR5d8mUgjU+g4rk8Kb4Mu0UlXjIB0ttov0DiNewNwIRt18jA8+o+u3dpjq+sW
T8KOEUt+zwvo/7V3LvSye0rgTBIlDHCNAymg4VMk7BPZ7hm/ELNKjD+Jo2FR3qyH
B5T0Y3HsLuJvW5iB4YlcNHlsdu87kGJ55tukmi8mxdAQ4Q7e2RCOFvu396j3x+UC
B5iPNgiV5+I3lg02dZ77DnKxHZu8A/lJBdiB3QW0KtZB6awBdpUKD9jf1b0SHzUv
KBds0pjBqAlkd25HN7rOrFleaJ1/ctaJxQZBKT5ZPt0m9STJEadao0xAH0ahmbWn
OlFuhjuefXKnEgV4We0+UXgVCwOPjdAvBbI+e0ocS3MFEvzG6uBQE3xDk3SzynTn
jh8BCNAw1FtxNrQHusEwMFxIt4I7mKZ9YIqioymCzLq9gwQbooMDQaHWBfEbwrbw
qHyGO0aoSCqI3Haadr8faqU9GY/rOPNk3sgrDQoo//fb4hVC1CLQJ13hef4Y53CI
rU7m2Ys6xt0nUW7/vGT1M0NPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNV
HRMBAf8EBTADAQH/MB0GA1UdDgQWBBR5tFnme7bl5AFzgAiIyBpY9umbbjANBgkq
hkiG9w0BAQsFAAOCAgEAVR9YqbyyqFDQDLHYGmkgJykIrGF1XIpu+ILlaS/V9lZL
ubhzEFnTIZd+50xx+7LSYK05qAvqFyFWhfFQDlnrzuBZ6brJFe+GnY+EgPbk6ZGQ
3BebYhtF8GaV0nxvwuo77x/Py9auJ/GpsMiu/X1+mvoiBOv/2X/qkSsisRcOj/KK
NFtY2PwByVS5uCbMiogziUwthDyC3+6WVwW6LLv3xLfHTjuCvjHIInNzktHCgKQ5
ORAzI4JMPJ+GslWYHb4phowim57iaztXOoJwTdwJx4nLCgdNbOhdjsnvzqvHu7Ur
TkXWStAmzOVyyghqpZXjFaH3pO3JLF+l+/+sKAIuvtd7u+Nxe5AW0wdeRlN8NwdC
jNPElpzVmbUq4JUagEiuTDkHzsxHpFKVK7q4+63SM1N95R1NbdWhscdCb+ZAJzVc
oyi3B43njTOQ5yOf+1CceWxG1bQVs5ZufpsMljq4Ui0/1lvh+wjChP4kqKOJ2qxq
4RgqsahDYVvTH9w7jXbyLeiNdd8XM2w9U/t7y0Ff/9yi0GE44Za4rF2LN9d11TPA
mRGunUHBcnWEvgJBQl9nJEiU0Zsnvgc/ubhPgXRR4Xq37Z0j4r7g1SgEEzwxA57d
emyPxgcYxn/eR44/KJ4EBs+lVDR3veyJm+kXQ99b21/+jh5Xos1AnX5iItreGCc=
-----END CERTIFICATE-----
)EOF";

void ponerColor(bool r, bool g, bool b) {
  digitalWrite(RGB_R_PIN, r ? HIGH : LOW);
  digitalWrite(RGB_G_PIN, g ? HIGH : LOW);
  digitalWrite(RGB_B_PIN, b ? HIGH : LOW);
}

void setup_wifi() {
  Serial.print("Conectando a WiFi: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("WiFi conectado, IP: ");
  Serial.println(WiFi.localIP());
}

void setup() {
  Serial.begin(115200);

  pinMode(PIR_PIN, INPUT);
  pinMode(RGB_R_PIN, OUTPUT);
  pinMode(RGB_G_PIN, OUTPUT);
  pinMode(RGB_B_PIN, OUTPUT);
  ponerColor(false, false, false); // apagado al inicio

  setup_wifi();

  mqttClient.setServer(mqtt_url);
  mqttClient.setCredentials(mqtt_user, mqtt_pass);
  mqttClient.setCACert(root_ca);

  mqttClient.onConnect([](bool sessionPresent) {
    Serial.println("MQTT conectado via WSS");
    mqttClient.subscribe(topic_semaforo, 0);
  });

  mqttClient.onDisconnect([](bool sessionPresent) {
    Serial.println("MQTT desconectado, reintentando...");
  });

  mqttClient.onTopic(topic_semaforo, 0, [](char *topic, char *payload, int retain, int qos, bool dup) {
    String mensaje = String(payload);
    Serial.print("Semaforo recibido: ");
    Serial.println(mensaje);
    if (mensaje == "ROJO") {
      ponerColor(true, false, false);
    } else if (mensaje == "VERDE") {
      ponerColor(false, true, false);
    }
  });

  Serial.println("Conectando a MQTT...");
  mqttClient.connect();

  delay(1000);
  inicioVentana = millis();
  Serial.println("Lector PIR listo. Reportando cada 10s.");
}

void loop() {
  int estadoActual = digitalRead(PIR_PIN);

  // Cuenta solo detecciones nuevas (flanco de subida), no todo el tiempo que este en HIGH
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

    Serial.print("conteo_eventos=");
    Serial.print(conteoEventos);
    Serial.print("  demanda=");
    Serial.println(demanda);

    if (mqttClient.connected()) {
      mqttClient.publish(topic_demanda, 0, false, demanda.c_str());
    }

    conteoEventos = 0;
    inicioVentana = millis();
  }

  delay(50); // lectura frecuente para no perder pulsos cortos
}
