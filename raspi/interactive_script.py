import pexpect
import base64
import sys

script_content = """#!/bin/bash

echo "==================================="
echo "       PENGATURAN WIFI RASPI       "
echo "==================================="

# Meminta input SSID
read -p "Masukkan nama WiFi (SSID): " SSID

if [ -z "$SSID" ]; then
    echo "Nama WiFi tidak boleh kosong!"
    exit 1
fi

# Meminta input Password
read -p "Masukkan Password (tekan Enter jika tanpa password): " PASSWORD

echo ""
echo "Menghubungkan ke WiFi: $SSID ..."

# Hapus koneksi lama jika ada
sudo nmcli con delete "$SSID" 2>/dev/null

# Buat profil baru
sudo nmcli con add type wifi ifname wlan0 con-name "$SSID" ssid "$SSID"

# Jika password diisi, atur keamanan WPA
if [ -n "$PASSWORD" ]; then
    sudo nmcli con modify "$SSID" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PASSWORD"
fi

# Mulai koneksi
sudo nmcli con up "$SSID"

if [ $? -eq 0 ]; then
    echo -e "\n✅ Berhasil terkoneksi ke $SSID!"
    echo "IP Address kamu saat ini:"
    ip -4 a show wlan0 | grep inet
else
    echo -e "\n❌ Gagal terkoneksi ke $SSID! Cek kembali nama WiFi dan password."
fi
"""

b64 = base64.b64encode(script_content.encode()).decode()

def run_ssh():
    print("Membuka koneksi SSH untuk update script interaktif...")
    child = pexpect.spawn('ssh -o StrictHostKeyChecking=no pi@192.168.6.200', encoding='utf-8')
    child.logfile = sys.stdout
    
    i = child.expect(['password:', pexpect.EOF, pexpect.TIMEOUT], timeout=10)
    if i == 0:
        child.sendline('pi')
        child.expect(r'pi@raspberrypi', timeout=5)
        
        cmd = f"echo '{b64}' | base64 -d > /home/pi/ganti_wifi.sh"
        child.sendline(cmd)
        child.expect(r'pi@raspberrypi', timeout=5)
        
        child.sendline('chmod +x /home/pi/ganti_wifi.sh')
        child.expect(r'pi@raspberrypi', timeout=5)
        
        child.sendline('exit')
        child.expect(pexpect.EOF)

if __name__ == '__main__':
    run_ssh()
