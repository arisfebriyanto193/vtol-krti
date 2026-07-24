import time
import busio
import digitalio
import board
import adafruit_rgb_display.ili9341 as ili9341
from PIL import Image, ImageDraw, ImageFont

# Konfigurasi Pin sesuai dengan skema wiring:
# CS: Pin 24 / GPIO8 (SPI0 CE0)
cs_pin = digitalio.DigitalInOut(board.CE0)

# DC: Pin 22 / GPIO25
dc_pin = digitalio.DigitalInOut(board.D25)

# RST: Pin 18 / GPIO24
reset_pin = digitalio.DigitalInOut(board.D24)

# Konfigurasi SPI 
# SCL (SCLK): Pin 23 / GPIO11
# SDA (MOSI): Pin 19 / GPIO10
spi = board.SPI()

# Inisialisasi display ILI9341 (Chip kontroler yang paling umum untuk TFT 2.8 inci)
# Jika chip display Anda berbeda (misal ST7789), library perlu disesuaikan.
BAUDRATE = 24000000

display = ili9341.ILI9341(
    spi,
    rotation=0, # Set rotasi ke 0 agar resolusi tetap 240x320 (Portrait)
    cs=cs_pin,
    dc=dc_pin,
    rst=reset_pin,
    baudrate=BAUDRATE,
)

# Gunakan ukuran fisik hardware untuk PIL Image
width = 240
height = 320
image = Image.new("RGB", (width, height))
draw = ImageDraw.Draw(image)

# Bersihkan layar (isi dengan warna hitam)
draw.rectangle((0, 0, width, height), outline=0, fill=(0, 0, 0))
display.image(image)
print("Menjalankan test LCD TFT 2.8 inci...")

# Gambar kotak merah dengan isian biru
draw.rectangle((10, 10, width - 10, height - 10), outline=(255, 0, 0), fill=(0, 0, 255))

# Tulis teks
try:    
    # Coba gunakan font sistem
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
except IOError:
    # Jika gagal, gunakan font default
    font = ImageFont.load_default()

text = "Hello KRTI!"
# Dapatkan ukuran text untuk menempatkan di tengah
left, top, right, bottom = font.getbbox(text)
font_width = right - left
font_height = bottom - top

x = width // 2 - font_width // 2
y = height // 2 - font_height // 2

# Tulis teks dengan warna kuning
draw.text((x, y), text, font=font, fill=(255, 255, 0))

# Tampilkan ke layar LCD
display.image(image)

print("Tampilan berhasil dirender. Menunggu 5 detik...")
time.sleep(5)

# Bersihkan layar kembali sebelum keluar
draw.rectangle((0, 0, width, height), outline=0, fill=(0, 0, 0))
display.image(image)
print("Test Selesai.")