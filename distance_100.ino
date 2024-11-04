// Default values for pins.
const int led_pin = 8;
const int trigPin = 9;
const int echoPin = 10;

void setup() {

  // Set mode for the led pin.
  pinMode(led_pin, OUTPUT);

  // set modes for the trigger and echo pin:
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);

  // initialize serial communication:
  Serial.begin(9600);
}

void loop() {
  // take the trigger pin low to start a pulse:
  digitalWrite(trigPin, LOW);
  // delay 2 microseconds:
  delayMicroseconds(2);
  // take the trigger pin high:
  digitalWrite(trigPin, HIGH);
  // delay 10 microseconds:
  delayMicroseconds(10);
  // take the trigger pin low again to complete the pulse:
  digitalWrite(trigPin, LOW);

  // listen for a pulse on the echo pin:
  long duration = pulseIn(echoPin, HIGH);
  
  // calculate the distance in cm.
  // Sound travels approx.0.0343 microseconds per cm.,
  // and it's going to the target and back (hence the /2):
  int distance = (duration * 0.0343) / 2;
  // a short delay between readings:
  delay(10);

  if (distance < 100) {
    digitalWrite(led_pin, HIGH);  // turn the LED on (HIGH is the voltage level)
  } 
  else {
      digitalWrite(led_pin, LOW);   // turn the LED off by making the voltage LOW
  }
}