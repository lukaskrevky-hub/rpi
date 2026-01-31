import machine
import time
import network
from umqtt.simple import MQTTClient

# --- KONFIGURACE ---
WIFI_SSID = ""				# nazev APcka
WIFI_PASS = ""           # heslo na WiFi
MQTT_SERVER = "192.168."       # IP adresa Raspberry Pi
MQTT_TOPIC = b"joystick/command"

# --- PINY ---
# ZAPOJENÍ:
# VRx ---> GPIO 32
# VRy ---> GPIO 33
# SW  ---> GPIO 26
# VCC ---> 3.3V
# GND ---> GND

adc_x = machine.ADC(machine.Pin(32))
adc_y = machine.ADC(machine.Pin(33))
btn_sw = machine.Pin(26, machine.Pin.IN, machine.Pin.PULL_UP)

adc_x.atten(machine.ADC.ATTN_11DB)
adc_y.atten(machine.ADC.ATTN_11DB)

# --- SETUP SÍTĚ ---
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print('Pripojuji Wi-Fi...')
        wlan.connect(WIFI_SSID, WIFI_PASS)
        while not wlan.isconnected():
            time.sleep_ms(500)
    print('Wi-Fi OK, IP:', wlan.ifconfig()[0])

def connect_mqtt():
    try:
        client = MQTTClient("ESP32_Debug", MQTT_SERVER, keepalive=60)
        client.connect()
        print("MQTT OK.")
        return client
    except:
        print("MQTT selhalo (nevadí pro kalibraci).")
        return None

connect_wifi()
mqtt = connect_mqtt()

print("--- REŽIM KALIBRACE ---")
print("Hodnoty X a Y v konzoli!")

last_cmd = "CENTER"

while True:
    # Čtení hodnot
    x = adc_x.read()
    y = adc_y.read()
    btn = btn_sw.value() == 0
    
    # Výpis pro diagnostiku (každých 0.5s)
    print(f"X: {x} | Y: {y} | Tlacitko: {btn}")
    
    # --- PŮVODNÍ LOGIKA ---
    cmd = "CENTER"
    # Zde můžete upravit čísla podle toho, co naměříte
    # Původně: < 1000 (Jeden směr), > 3000 (Druhý směr)
    if btn: cmd = "SELECT"
    elif y < 1600: cmd = "UP"
    elif y > 2500: cmd = "DOWN"
    elif x < 1000: cmd = "LEFT"
    elif x > 3000: cmd = "RIGHT"

    if cmd != last_cmd:
        if cmd != "CENTER":
            print(f"!!! ZMĚNA STAVU NA: {cmd} !!!")
            if mqtt: mqtt.publish(MQTT_TOPIC, cmd)
        last_cmd = cmd
        time.sleep_ms(200)


    time.sleep_ms(500) # Zpomalení výpisu, ať to stíháte číst
