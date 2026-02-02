#include "SparkFun_Weather_Meter_Kit_Arduino_Library.h"  //http://librarymanager/All#SparkFun_Weather_Meter_Kit

//Hardware pin definitions
//-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
#if defined(ESP_PLATFORM)
const byte WSPEED = 14;  //Digital I/O pin for wind speed
const byte WDIR = 35;    //Analog pin for wind direction
const byte RAIN = 27;    //Digital I/O pin for rain fall
#elif defined(ARDUINO_RASPBERRY_PI_PICO)
const byte WSPEED = 6;  //Digital I/O pin for wind speed
const byte WDIR = A1;   //Analog pin for wind direction
const byte RAIN = 7;    //Digital I/O pin for rain fall
#elif defined(ARDUINO_TEENSY_MICROMOD)
const byte WSPEED = 4;  //Digital I/O pin for wind speed
const byte WDIR = A1;   //Analog pin for wind direction
const byte RAIN = 4;    //Digital I/O pin for rain fall
#else
const byte WSPEED = D0;  //Digital I/O pin for wind speed
const byte WDIR = A1;    //Analog pin for wind direction
const byte RAIN = D1;    //Digital I/O pin for rain fall
#endif
//-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=

//Global Variables
//-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
long lastSecond;  //The millis counter to see when a second rolls by

float wind_dir = 0;    // [degrees (Cardinal)]
float wind_speed = 0;  // [kph]
float rain = 0;        // [mm]
//-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=

SFEWeatherMeterKit myweatherMeterKit(WDIR, WSPEED, RAIN);  // Create an instance of the weather meter kit

#if defined(ESP32)
  #include <WiFiMulti.h>
  WiFiMulti wifiMulti;
  #define DEVICE "ESP32"
  #elif defined(ESP8266)
  #include <ESP8266WiFiMulti.h>
  ESP8266WiFiMulti wifiMulti;
  #define DEVICE "ESP8266"
  #endif
  
  #include "Configuration.h"
  #include <InfluxDbClient.h>
  #include <InfluxDbCloud.h>
  
  // Time zone info
  #define TZ_INFO "UTC-7"
  
  // Declare InfluxDB client instance with preconfigured InfluxCloud certificate
  InfluxDBClient client(INFLUXDB_URL, INFLUXDB_ORG, INFLUXDB_BUCKET, INFLUXDB_TOKEN, InfluxDbCloud2CACert);

  // Create your Data Point here
  Point sensor("climate");

void setup() {

    Serial.begin(115200);
  
    // Setup wifi
    WiFi.mode(WIFI_STA);
    wifiMulti.addAP(WIFI_SSID, WIFI_PASSWORD);
  
    Serial.print("Connecting to wifi");
    while (wifiMulti.run() != WL_CONNECTED) {
      Serial.print(".");
      delay(100);
    }
    Serial.println();
  
    // Accurate time is necessary for certificate validation and writing in batches
    // We use the NTP servers in your area as provided by: https://www.pool.ntp.org/zone/
    // Syncing progress and the time will be printed to Serial.
    timeSync(TZ_INFO, "pool.ntp.org", "time.nis.gov");
  
  
    // Check server connection
    if (client.validateConnection()) {
      Serial.print("Connected to InfluxDB: ");
      Serial.println(client.getServerUrl());
    } else {
      Serial.print("InfluxDB connection failed: ");
      Serial.println(client.getLastErrorMessage());
    }
  Serial.begin(115200);
  Serial.println("Example - Weather Meter Kit");

  pinMode(LED_BUILTIN, OUTPUT);  //Status LED Blue

  // The weather meter kit library assumes a 12-bit ADC
  // Configuring a 10-bit ADC resolution for the ATmega328 (RedBoard/Uno)
  myweatherMeterKit.setADCResolutionBits(10);

  // Begin weather meter kit
  myweatherMeterKit.begin();

  lastSecond = millis();

  Serial.println("Begin data collection!");

  sensor.addTag("device", DEVICE);
}

void loop() {
  //Keep track of which minute it is
  if (millis() - lastSecond >= 1000) {
    digitalWrite(LED_BUILTIN, HIGH);  //Blink stat LED

    lastSecond += 1000;

    //Report all readings every 5 seconds
    storeWeatherFields();
  }

  digitalWrite(LED_BUILTIN, LOW);  //Turn off stat LED

  delay(500);
}

//Calculates data from weather meter kit
void storeWeatherFields() {
      // Clear fields for reusing the point. Tags will remain the same as set above.
    sensor.clearFields();

    // Store sensor data in point
    sensor.addField("wind_direction", myweatherMeterKit.getWindDirection());
    sensor.addField("wind_speed", myweatherMeterKit.getWindSpeed());
    sensor.addField("total_rain", myweatherMeterKit.getTotalRainfall());
  
    // Print what are we exactly writing
    Serial.print("Writing: ");
    Serial.println(sensor.toLineProtocol());
  
    // Check WiFi connection and reconnect if needed
    if (wifiMulti.run() != WL_CONNECTED) {
      Serial.println("Wifi connection lost");
    }
    // Write point
    if (!client.writePoint(sensor)) {
      Serial.print("InfluxDB write failed: ");
      Serial.println(client.getLastErrorMessage());
    }
  
    Serial.println("Waiting 1 second");
    delay(1000);
}

