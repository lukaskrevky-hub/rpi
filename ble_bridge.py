import asyncio
from bleak import BleakClient
import paho.mqtt.client as mqtt
import sys

# ==========================================
# ZJIŠTĚNÁ MAC ADRESA
TARGET_MAC = "38:18:2B:B3:80:8E"
# ==========================================

# Standardní Nordic UART Service UUID (TX charakteristika)
UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# MQTT Konfigurace
MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"
TOPIC_STATUS = "joystick/status"  # <--- NOVÉ: Téma pro stav

# --- MQTT SETUP ---
# VERSION2 pro potlačení varování
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

try:
    mqtt_client.connect(MQTT_BROKER, 1883, 60)
    mqtt_client.loop_start()
    print("MQTT připojeno.")
except Exception as e:
    print(f"Chyba MQTT: {e}")
    sys.exit(1)

# --- POMOCNÉ FUNKCE ---

def publish_status(status):
    """Odeslání stavu do MQTT pro webové rozhraní"""
    # print(f"STAV: {status}") # Pro debug
    mqtt_client.publish(TOPIC_STATUS, status, retain=True)

# --- CALLBACK FUNKCE ---

def notification_handler(sender, data):
    """Tato funkce se spustí, když joystick pošle data."""
    try:
        command = data.decode('utf-8').strip()
        # print(f"--> Přijato: {command}")
        mqtt_client.publish(MQTT_TOPIC, command)
    except Exception as e:
        print(f"Chyba dat: {e}")

def disconnected_callback(client):
    """Informace o odpojení (např. když joystick usne)"""
    print("Joystick odpojen/uspal se.")
    publish_status("SLEEP") # <--- NOVÉ: Odeslat info, že spíme

# --- HLAVNÍ SMYČKA ---

async def main():
    print(f"Startuji Direct Connect na {TARGET_MAC}...")
    publish_status("SLEEP") # <--- NOVÉ: Výchozí stav
    
    # Nekonečná smyčka, která se snaží připojit
    while True:
        try:
            print(f"Čekám na probuzení joysticku ({TARGET_MAC})...")
            # Pokud čekáme, joystick asi spí (nebo se probouzí)
            # publish_status("SLEEP") # (Volitelné, pro jistotu)
            
            # timeout=15.0: RPi bude 15 sekund aktivně poslouchat na této adrese.
            # Jakmile se ESP32 probudí a pípne, RPi ho chytí.
            async with BleakClient(TARGET_MAC, disconnected_callback=disconnected_callback, timeout=15.0) as client:
                
                print("PŘIPOJENO! Ovladač je aktivní.")
                publish_status("READY") # <--- NOVÉ: Jsme připojeni!
                
                # Zapneme příjem dat z joysticku
                await client.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Smyčka udržující spojení naživu, dokud se ESP neodpojí
                while client.is_connected:
                    await asyncio.sleep(0.5)
            
            # Sem se dostaneme, když se 'async with' blok ukončí (odpojení)

        except Exception as e:
            # Pokud se připojení nepovede (joystick spí), vyhodí to chybu.
            # To je v pořádku. Jen chvíli počkáme a zkusíme to znovu.
            # print(f"Info: {e}") # Pro debug
            await asyncio.sleep(0.1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Ukončuji...")
        mqtt_client.loop_stop()
