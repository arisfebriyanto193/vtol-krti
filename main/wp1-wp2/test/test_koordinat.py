import cv2
import numpy as np

def main():
    # Inisialisasi Kamera
    # Sesuaikan index kamera jika perlu (0, 1, dst)
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    if not cap.isOpened():
        print("❌ Gagal membuka kamera.")
        return

    # Inisialisasi ArUco Dictionary (Mendukung 7x7 seperti script Anda lainnya)
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_7X7_1000)
    aruco_params = cv2.aruco.DetectorParameters()

    # Mendukung OpenCV versi terbaru dan lama
    has_new_api = hasattr(cv2.aruco, 'ArucoDetector')
    if has_new_api:
        detector = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)

    print("🚀 Memulai Program Test Koordinat ArUco...")
    print("Tekan 'Ctrl+C' di terminal untuk keluar.")

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                print("⚠️ Gagal membaca frame dari kamera!")
                break
            
            h, w, _ = frame.shape
            center_x_frame = w // 2
            center_y_frame = h // 2

            # Deteksi Marker ArUco
            if has_new_api:
                corners, ids, rejected = detector.detectMarkers(frame)
            else:
                corners, ids, rejected = cv2.aruco.detectMarkers(frame, aruco_dict, parameters=aruco_params)

            if ids is not None and len(ids) > 0:
                # Ambil marker pertama yang dideteksi
                marker_id = ids[0][0]
                points = corners[0][0]
                
                # Hitung titik tengah marker (Pusat Koordinat / Center of Mass)
                cx = int(np.mean(points[:, 0]))
                cy = int(np.mean(points[:, 1]))
                
                # Hitung jarak/error posisi terhadap titik tengah frame
                error_x = cx - center_x_frame
                error_y = cy - center_y_frame
                
                # Logika Mengunci Koordinat (Toleransi 40 pixel dari titik tengah layar)
                if abs(error_x) < 40 and abs(error_y) < 40:
                    status = "✅ TERKUNCI (LOCKED)  "
                else:
                    status = "🔄 MENGARAH (TRACKING)"
                
                # Tampilkan di terminal dengan menimpa baris sebelumnya (\r) agar tidak spam
                msg = f"[{status}] Marker ID: {marker_id} | Koordinat (X: {cx:4d}, Y: {cy:4d}) | Jarak (Err X: {error_x:4d}, Err Y: {error_y:4d})"
                print(f"{msg:<100}", end='\r', flush=True)

            else:
                msg = "[❌ MARKER HILANG] Mencari marker 7x7..."
                print(f"{msg:<100}", end='\r', flush=True)

    except KeyboardInterrupt:
        print("\n🛑 Program dihentikan.")
    finally:
        cap.release()

if __name__ == '__main__':
    main()