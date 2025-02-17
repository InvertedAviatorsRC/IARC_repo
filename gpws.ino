// Default values for pins
const int led_pin = 8;
const int trigPin = 9;
const int echoPin = 10;

// Number of readings to average
const int numReadings = 5;

void setup() {
  // Initialize serial communication
  Serial.begin(9600);

  // Set mode for the LED pin
  pinMode(led_pin, OUTPUT);

  // Set modes for the trigger and echo pin
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);

  // Confirm initialization
  Serial.println("Ultrasonic Sensor Initialized");
}

void loop() {
  long totalDuration = 0;

  // Collect multiple readings
  for (int i = 0; i < numReadings; i++) {
    // Take the trigger pin LOW to start a pulse
    digitalWrite(trigPin, LOW);
    delayMicroseconds(2);

    // Take the trigger pin HIGH to send the ultrasonic pulse
    digitalWrite(trigPin, HIGH);
    delayMicroseconds(10);

    // Take the trigger pin LOW again to complete the pulse
    digitalWrite(trigPin, LOW);

    // Listen for a pulse on the echo pin
    long duration = pulseIn(echoPin, HIGH);

    // Add the reading to the total
    totalDuration += duration;

    // Short delay between individual readings
    delay(10);
  }

  // Calculate the average duration
  long averageDuration = totalDuration / numReadings;

  // Print the average duration to the Serial Monitor
  Serial.print("Average Duration: ");
  Serial.println(averageDuration);

  // Control the LED based on the average duration
  if (averageDuration < 10000) {
    digitalWrite(led_pin, HIGH);  // Turn the LED on
  } else {
    digitalWrite(led_pin, LOW);  // Turn the LED off
  }
}
