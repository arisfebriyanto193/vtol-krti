"""
Konfigurasi Global untuk sistem KRTI VTOL.
"""

# Konfigurasi Koneksi Pixhawk
# Ganti '/dev/ttyACM0' dengan 'COMx' jika menggunakan Windows
PIXHAWK_PORT = '/dev/ttyACM0'

# Baudrate koneksi Pixhawk
PIXHAWK_BAUD = 115200

# Konfigurasi Kamera
# 0 biasanya untuk kamera bawaan/laptop, 1 untuk USB camera eksternal
CAMERA_INDEX = 0