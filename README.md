# VTOL KRTI - Sistem Kalibrasi dan Navigasi Otonom WP1-WP5

Sistem ini dibuat untuk menyelesaikan misi pertandingan VTOL KRTI yang mensyaratkan drone melewati *gate* dan titik *waypoint* (WP). Terdapat dua fase utama dari sistem ini: **Fase Kalibrasi (Web Dashboard)** dan **Fase Eksekusi Navigasi Otonom (Pymavlink & ArUco)**.

---

## 1. Persiapan Awal (Konfigurasi)

Sebelum menjalankan apa pun, pastikan Anda telah mengatur konfigurasi perangkat keras di file JSON:
**File:** `main/config/krti_config.json`

Atur parameter berikut sesuai perangkat Anda:
- `"pixhawk_port"`: Port serial ke Pixhawk (Contoh di Windows: `"COM3"`, di Linux/RPi: `"/dev/ttyACM0"`).
- `"esp32_port"`: Port serial ke ESP32 yang membaca ultrasonik (Contoh: `"COM5"`).
- `"camera_index"`: Indeks kamera yang digunakan (0 untuk webcam internal/default, 1 untuk eksternal).
- `"drone_speed"`: Kecepatan maju drone secara otonom (dalam m/s).
- `"target_altitude"`: Target ketinggian (dalam meter).

---

## 2. Fase Kalibrasi Lapangan

Fase kalibrasi **wajib** dilakukan sebelum pertandingan dimulai untuk menetapkan titik presisi GPS, ketinggian ESP32, dan arah hadap drone (*Yaw/Heading*).

### Cara Kalibrasi:
1. Nyalakan Drone dan Pixhawk, serta sambungkan kabel USB/Telemetri ke Laptop atau *Ground Control Station* (GCS). Pastikan Pixhawk sudah mendapat *GPS 3D Fix*.
2. Nyalakan koneksi ESP32.
3. Buka Terminal/Command Prompt, masuk ke folder project, lalu jalankan Web Server:
   ```bash
   cd main/main-go
   python main-utama.py
   ```
4. Buka Browser (Chrome/Edge) dan akses alamat: `http://localhost:5000`
5. Pada Dashboard Web:
   - Pilih Tim Anda (**Tim Biru** atau **Tim Merah**) di menu dropdown kiri atas. Background lapangan akan berubah menyesuaikan titik acuan tim.
   - Pindahkan drone secara fisik ke titik **WP1**. Posisikan drone tepat di atas *ArUco Marker* WP1, dan arahkan hadap kepalanya (*yaw*) sesuai arah yang diinginkan.
   - Tekan tombol **Kalibrasi** pada kotak WP1 di Dashboard Web.
   - Ulangi proses ini dengan memindahkan drone secara fisik ke titik WP2, WP3, WP4, dan WP5, lalu menekan tombol Kalibrasi pada masing-masing titik.
6. Cek terminal, atau lihat di dashboard apakah koordinat, *alt*, dan *yaw* sudah diperbarui nilainya.
7. Web Server bisa Anda matikan (`Ctrl+C`) jika kalibrasi sudah selesai. Koordinat otomatis tersimpan di `krti_config.json`.

---

## 3. Fase Eksekusi Misi / Penerbangan

Script navigasi dipisahkan menjadi per-segmen (WP1->WP2, WP2->WP3, dsb.) untuk memudahkan Anda melakukan eksekusi bertahap atau sekadar *debugging* per segmen titik. 

### Alur Navigasi Segmen:
Di setiap script, drone secara otomatis akan:
1. Berputar (*Condition Yaw*) di titik keberangkatan hingga arah kompas/kepalanya sejajar dengan sudut *Yaw* target yang dikalibrasi.
2. Maju (*Navigate*) menuju koordinat GPS target.
3. Begitu mendekati target GPS (< 2 meter), drone mengaktifkan kamera untuk mendeteksi ID ArUco dan melakukan *Visual Centering*.
4. Jika sudah stabil (*Locked*), status segmen selesai (Khusus untuk WP5, drone akan otomatis **LAND**).

### Cara Menjalankan Drone:
1. Terbangkan drone secara manual (mode LOITER atau STABILIZE) ke udara menuju atas WP awal.
2. Pindahkan *flight mode* di *Remote Control* ke mode **GUIDED**. (Semua script di bawah hanya bekerja jika mendeteksi mode GUIDED aktif).
3. Buka terminal (di dalam folder `main/main-go`), jalankan script sesuai segmen target:

**A. Navigasi menuju WP2 (Mulai dari WP1):**
```bash
python wp1-wp2.py
```
*(Tunggu hingga muncul pesan Misi Selesai / Hover di terminal)*

**B. Navigasi menuju WP3:**
```bash
python wp2-wp3.py
```

**C. Navigasi menuju WP4:**
```bash
python wp3-wp4.py
```

**D. Navigasi menuju WP5 dan Pendaratan Otomatis (LAND):**
```bash
python wp4-wp5.py
```

> **Catatan Debugging:**
> Bila di pertengahan jalan (misal menuju WP3) drone gagal mendeteksi kamera, Anda bisa langsung mengambil alih (Ubah ke LOITER), pindahkan ke atas wp, ubah kembali ke GUIDED, dan cukup jalankan ulang `python wp2-wp3.py`. Tidak perlu mereset kalibrasi dan terbang dari awal.
