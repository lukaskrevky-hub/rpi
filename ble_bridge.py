import asyncio
import sys
from bleak import BleakScanner, BleakClient
import paho.mqtt.client as mqtt

# ==========================
# VAŠE MAC ADRESA (Upravte, pokud se změnila)
TARGET_MAC = "38:18:2B:B3:80:8E"
# ==========================

UART_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
TOPIC = "joystick/command"
BROKER = "localhost"

# --- MQTT SETUP ---
# Používáme VERSION2 pro moderní Paho knihovnu
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

try:
    client.connect(BROKER, 1883, 60)
    client.loop_start()
    print(f"MQTT připojeno k {BROKER}")
except Exception as e:
    print(f"Chyba MQTT: {e}")
    sys.exit(1)

# --- FUNKCE ---

def handler(sender, data):
    """Zpracuje příchozí data z joysticku a pošle je do MQTT"""
    try:
        cmd = data.decode('utf-8').strip()
        # print(f"-> {cmd}") # Odkomentujte pro detailní výpis
        client.publish(TOPIC, cmd)
    except:
        pass

def disconnected(client):
    """Callback při ztrátě spojení"""
    print("Odpojeno (Joystick usnul).")

# --- HLAVNÍ SMYČKA ---

async def main():
    print(f"Startuji Bridge pro {TARGET_MAC}...")
    
    # Nekonečná smyčka, která se nikdy nezastaví
    while True:
        try:
            # 1. ČÍHÁNÍ (PASIVNÍ SKENOVÁNÍ)
            # Čekáme, až se zařízení objeví v éteru. 
            # Timeout 20s znamená, že každých 20s se skener restartuje (úklid).
            print("Čekám na signál joysticku...")
            device = await BleakScanner.find_device_by_address(TARGET_MAC, timeout=20.0)
            
            if not device:
                # Timeout vypršel (joystick stále spí), zkusíme to znovu
                continue

            # 2. PŘIPOJENÍ
            print("Signál nalezen! Připojuji...")
            
            # timeout=10.0: Dáváme mu 10s na navázání spojení
            async with BleakClient(device, disconnected_callback=disconnected, timeout=10.0) as ble:
                print("PŘIPOJENO! Ovladač aktivní.")
                
                # Zapneme odběr notifikací (tím začnou chodit data)
                await ble.start_notify(UART_UUID, handler)
                
                # 3. UDRŽOVÁNÍ SPOJENÍ
                # Tady program "visí" a čeká, dokud je spojení aktivní.
                # Jakmile se ESP32 odpojí (uspí), tato smyčka skončí.
                while ble.is_connected:
                    await asyncio.sleep(1.0)
            
            # Zde se kód dostane po odpojení. Smyčka while True ho vrátí na začátek (Číhání).
            
        except Exception as e:
            # Ignorujeme běžné chyby připojení (např. když joystick usne těsně před spojením)
            # print(f"Info: {e}")
            await asyncio.sleep(0.5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Ukončuji...")
        client.loop_stop()
