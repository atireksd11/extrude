const int MOTOR_PIN = 12;
const int LIMIT_PIN = 4;

void setup() {
  pinMode(MOTOR_PIN, OUTPUT);
  pinMode(LIMIT_PIN, INPUT_PULLUP);
}

void loop() {
  const bool closed = digitalRead(LIMIT_PIN) == LOW;
  digitalWrite(MOTOR_PIN, closed ? LOW : HIGH);
}
