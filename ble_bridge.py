import asyncio
from bleak import BleakClient, BleakScanner, BleakError
import paho.mqtt.client as mqtt
import sys
import time
import subprocess

# ==========================================
# NASTAVENÍ
DEVICE_NAME = "ESP-JOY"
DEVICE_ADDRESS = "10:06:1C:B5:A7:36"
UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"
TOPIC_STATUS = "joystick/status"

# Časové limity (v sekundách)
SCAN_TIMEOUT = 5           # Doba skenování při hledání zařízení
CONNECT_TIMEOUT = 30       # Timeout pro připojení
RECONNECT_DELAY = 2        # Prodleva mezi pokusy o připojení
# ==========================================

# --- MQTT připojení ---
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
try:
    client.connect(MQTT_BROKER, 1883, 60)
    client.loop_start()
    print("MQTT připojeno.")
except Exception as e:
    print(f"Chyba MQTT: {e}")
    sys.exit(1)

def publish_status(status):
    print(f"STAV -> {status}")
    client.publish(TOPIC_STATUS, status, retain=True)

def notification_handler(sender, data):
    command = data.decode('utf-8').strip()
    if command == "PING":
        # Heartbeat, ignorujeme
        return
    print(f"Přijato z BLE: {command}")
    client.publish(MQTT_TOPIC, command)

def disconnected_callback(client):
    print(">>> Ztráta spojení (Joystick usnul nebo je mimo dosah).")
    publish_status("SLEEP")

async def find_device():
    """Nalezne zařízení dle jména (nebo MAC adresy, pokud je zadána)."""
    # Pokud máme MAC adresu, zkusíme ji přímo
    if 'DEVICE_ADDRESS' in globals():
        print(f"Používám předdefinovanou MAC: {DEVICE_ADDRESS}")
        # Můžeme zkusit, zda je zařízení dosažitelné (volitelně)
        return DEVICE_ADDRESS

    # Jinak skenujeme
    print(f"Skenuji zařízení '{DEVICE_NAME}' (timeout {SCAN_TIMEOUT}s)...")
    devices = await BleakScanner.discover(timeout=SCAN_TIMEOUT, return_adv=True)
    for addr, (dev, adv) in devices.items():
        if dev.name and dev.name == DEVICE_NAME:
            print(f"   Nalezeno: {dev.name} ({addr})")
            return addr
    return None

async def ensure_bluetooth_ready():
    """Pokusí se resetovat Bluetooth adaptér, pokud je třeba."""
    try:
        # Zkontrolujeme, zda je hci0 dostupné
        result = subprocess.run(["hciconfig"], capture_output=True, text=True)
        if "hci0" not in result.stdout:
            print("hci0 nenalezen, zkouším zvednout...")
            subprocess.run(["sudo", "hciconfig", "hci0", "up"], check=False)
        else:
            # Reset rozhraní (odpojit vše)
            subprocess.run(["sudo", "hciconfig", "hci0", "reset"], check=False)
    except Exception as e:
        print(f"Chyba při resetu BT: {e}")

async def connect_and_listen():
    print(f"--- BLE most spuštěn, hledám {DEVICE_NAME} ---")
    publish_status("SLEEP")

    # Před startem resetujeme BT adaptér (pro jistotu)
    await ensure_bluetooth_ready()

    while True:
        try:
            # 1. Najdi zařízení
            device_id = await find_device()
            if not device_id:
                print("Zařízení nenalezeno, čekám...")
                await asyncio.sleep(RECONNECT_DELAY)
                continue

            # 2. Pokus o připojení
            print(f"Připojuji se k {device_id}...")
            publish_status("CONNECTING")

            # Před připojením se ujistíme, že není staré spojení
            try:
                old_client = BleakClient(device_id)
                await old_client.disconnect()
            except:
                pass

            # Vytvoříme klienta s callbacky
            client_ble = BleakClient(device_id, 
                                     disconnected_callback=disconnected_callback,
                                     timeout=CONNECT_TIMEOUT)

            try:
                await client_ble.connect()
                print("Připojeno! Spouštím notifikace...")
                await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                print("PŘIPOJENO! Ovladač aktivní.")
                publish_status("READY")

                # Udržovací smyčka
                while client_ble.is_connected:
                    await asyncio.sleep(1)

                print("Spojení ztraceno, návrat do smyčky.")
                publish_status("SLEEP")

            except asyncio.TimeoutError:
                print("Timeout při připojování")
                await client_ble.disconnect()
            except Exception as e:
                print(f"Chyba při připojení: {e}")
                await client_ble.disconnect()
            finally:
                await asyncio.sleep(RECONNECT_DELAY)

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Neočekávaná chyba: {e}")
            await asyncio.sleep(RECONNECT_DELAY)

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)

