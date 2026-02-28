#!/bin/bash

# ==========================================
# Asistivní Hub - Instalační Skript (Setup)
# Autor: Lukáš Křevký
# Popis: Připraví čisté Raspberry Pi pro běh Asistivního Hubu.
#        Instaluje závislosti a konfiguruje MQTT.
# ==========================================

echo ">>> ZAČÍNÁM INSTALACI ASISTIVNÍHO HUBU <<<"

echo ">>> Krok 1: Aktualizace systému..."
sudo apt-get update && sudo apt-get upgrade -y

echo ">>> Krok 2: Instalace systémových balíčků..."
# Instalace MQTT brokeru, grafiky (Tkinter) a nástrojů pro IR
sudo apt-get install -y mosquitto mosquitto-clients python3-tk python3-pip v4l-utils lirc

echo ">>> Krok 3: Konfigurace MQTT Brokeru (Mosquitto)..."
CONFIG_FILE="/etc/mosquitto/mosquitto.conf"

# Kontrola, zda už konfigurace existuje, abychom ji nepsali dvakrát
if grep -q "listener 1883" "$CONFIG_FILE"; then
    echo "   - Konfigurace MQTT již existuje, přeskakuji."
else
    echo "   - Upravuji $CONFIG_FILE pro povolení externího přístupu (pro ESP32)..."
    # Přidání konfigurace na konec souboru
    echo "" | sudo tee -a "$CONFIG_FILE"
    echo "# --- Asistivní Hub Konfigurace ---" | sudo tee -a "$CONFIG_FILE"
    echo "listener 1883" | sudo tee -a "$CONFIG_FILE"
    echo "allow_anonymous true" | sudo tee -a "$CONFIG_FILE"
    echo "   - Hotovo."
fi

echo ">>> Krok 4: Restartování služby Mosquitto..."
sudo systemctl enable mosquitto
sudo systemctl restart mosquitto

echo ""
echo "=========================================="
echo "SYSTÉMOVÁ INSTALACE DOKONČENA!"
echo "=========================================="
echo "Nyní nainstalujte Python knihovny příkazem:"
echo "pip3 install -r requirements.txt --break-system-packages"
echo ""
echo "IP Adresa tohoto Raspberry Pi je:"
hostname -I
echo "=========================================="