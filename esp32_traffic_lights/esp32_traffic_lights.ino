#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ---------------------------------------------------------
// Wi-Fi Configuration
// ---------------------------------------------------------
const char* ssid = "MG";
const char* password = "22220000";

// ---------------------------------------------------------
// MQTT Configuration
// ---------------------------------------------------------
const char* mqtt_server = "broker.hivemq.com";
const int mqtt_port = 1883;
const char* mqtt_topic = "iot/traffic/lights/faraj123"; // Unique topic name

WiFiClient espClient;
PubSubClient client(espClient);

// ---------------------------------------------------------
// Pin Mapping for NodeMCU-32S
// ---------------------------------------------------------

// North Lane
const int NORTH_RED   = 13;
const int NORTH_YEL   = 12;
const int NORTH_GRN   = 14;

// South Lane
const int SOUTH_RED   = 27;
const int SOUTH_YEL   = 26;
const int SOUTH_GRN   = 25;

// East Lane
const int EAST_RED    = 33;
const int EAST_YEL    = 32;
const int EAST_GRN    = 5;

// West Lane
const int WEST_RED    = 18;
const int WEST_YEL    = 19;
const int WEST_GRN    = 21;


void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Connecting to ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("");
  Serial.println("WiFi connected");
  Serial.println("IP address: ");
  Serial.println(WiFi.localIP());
}

// Function to handle incoming MQTT messages
void callback(char* topic, byte* payload, unsigned int length) {
  Serial.print("Message arrived [");
  Serial.print(topic);
  Serial.print("] ");
  
  String msg = "";
  for (int i = 0; i < length; i++) {
    msg += (char)payload[i];
  }
  Serial.println(msg);

  // Parse JSON
  StaticJsonDocument<256> doc;
  DeserializationError error = deserializeJson(doc, msg);

  if (error) {
    Serial.print(F("deserializeJson() failed: "));
    Serial.println(error.f_str());
    return;
  }

  // Extract Light States
  const char* north_state = doc["North"];
  const char* south_state = doc["South"];
  const char* east_state  = doc["East"];
  const char* west_state  = doc["West"];
  int duration = doc["Duration"];

  Serial.print("Green Duration: ");
  Serial.println(duration);

  // Set Pins for North
  digitalWrite(NORTH_RED, strcmp(north_state, "RED") == 0 ? HIGH : LOW);
  digitalWrite(NORTH_GRN, strcmp(north_state, "GREEN") == 0 ? HIGH : LOW);
  digitalWrite(NORTH_YEL, strcmp(north_state, "YELLOW") == 0 ? HIGH : LOW);

  // Set Pins for South
  digitalWrite(SOUTH_RED, strcmp(south_state, "RED") == 0 ? HIGH : LOW);
  digitalWrite(SOUTH_GRN, strcmp(south_state, "GREEN") == 0 ? HIGH : LOW);
  digitalWrite(SOUTH_YEL, strcmp(south_state, "YELLOW") == 0 ? HIGH : LOW);

  // Set Pins for East
  digitalWrite(EAST_RED, strcmp(east_state, "RED") == 0 ? HIGH : LOW);
  digitalWrite(EAST_GRN, strcmp(east_state, "GREEN") == 0 ? HIGH : LOW);
  digitalWrite(EAST_YEL, strcmp(east_state, "YELLOW") == 0 ? HIGH : LOW);

  // Set Pins for West
  digitalWrite(WEST_RED, strcmp(west_state, "RED") == 0 ? HIGH : LOW);
  digitalWrite(WEST_GRN, strcmp(west_state, "GREEN") == 0 ? HIGH : LOW);
  digitalWrite(WEST_YEL, strcmp(west_state, "YELLOW") == 0 ? HIGH : LOW);
}

void reconnect() {
  // Loop until we're reconnected
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    // Create a random client ID
    String clientId = "ESP32Client-";
    clientId += String(random(0xffff), HEX);
    // Attempt to connect
    if (client.connect(clientId.c_str())) {
      Serial.println("connected");
      // Once connected, publish an announcement...
      client.publish("iot/traffic/status", "ESP32 Traffic Lights Connected");
      // ... and resubscribe
      client.subscribe(mqtt_topic);
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      // Wait 5 seconds before retrying
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(115200);

  // Initialize Pins as Outputs
  pinMode(NORTH_RED, OUTPUT); pinMode(NORTH_YEL, OUTPUT); pinMode(NORTH_GRN, OUTPUT);
  pinMode(SOUTH_RED, OUTPUT); pinMode(SOUTH_YEL, OUTPUT); pinMode(SOUTH_GRN, OUTPUT);
  pinMode(EAST_RED, OUTPUT);  pinMode(EAST_YEL, OUTPUT);  pinMode(EAST_GRN, OUTPUT);
  pinMode(WEST_RED, OUTPUT);  pinMode(WEST_YEL, OUTPUT);  pinMode(WEST_GRN, OUTPUT);

  // Ensure all are initially RED
  digitalWrite(NORTH_RED, HIGH); digitalWrite(SOUTH_RED, HIGH);
  digitalWrite(EAST_RED, HIGH);  digitalWrite(WEST_RED, HIGH);

  setup_wifi();
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();
}
