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
    print("Tekan 'q' pada jendela video untuk keluar.")

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                print("⚠️ Gagal membaca frame dari kamera!")
                break
            
            h, w, _ = frame.shape
            center_x_frame = w // 2
            center_y_frame = h // 2
            
            # Gambar titik tengah layar kamera (crosshair biru)
            cv2.line(frame, (center_x_frame - 15, center_y_frame), (center_x_frame + 15, center_y_frame), (255, 0, 0), 2)
            cv2.line(frame, (center_x_frame, center_y_frame - 15), (center_x_frame, center_y_frame + 15), (255, 0, 0), 2)

            # Deteksi Marker ArUco
            if has_new_api:
                corners, ids, rejected = detector.detectMarkers(frame)
            else:
                corners, ids, rejected = cv2.aruco.detectMarkers(frame, aruco_dict, parameters=aruco_params)

            if ids is not None and len(ids) > 0:
                # Loop melalui semua marker yang terdeteksi
                for i in range(len(ids)):
                    marker_id = ids[i][0]
                    points = corners[i][0]
                    
                    # Hitung titik tengah marker (Pusat Koordinat / Center of Mass)
                    cx = int(np.mean(points[:, 0]))
                    cy = int(np.mean(points[:, 1]))
                    
                    # Gambar kotak marker (bounding box) dan titik tengahnya (merah)
                    cv2.aruco.drawDetectedMarkers(frame, corners, ids)
                    cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)
                    
                    # Tuliskan teks koordinat di dekat marker pada video
                    text_coord = f"ID:{marker_id} (X:{cx}, Y:{cy})"
                    cv2.putText(frame, text_coord, (cx - 50, cy - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                    
                    # Hitung jarak/error posisi terhadap titik tengah frame
                    error_x = cx - center_x_frame
                    error_y = cy - center_y_frame
                    
                    # Tampilkan di terminal: Koordinat Asli & Selisih dari tengah
                    print(f"Marker ID: {marker_id} | Koordinat (X: {cx}, Y: {cy}) | Jarak ke Tengah (Err X: {error_x}, Err Y: {error_y})")

            else:
                # Jika tidak ada marker terdeteksi
                cv2.putText(frame, "MENCARI MARKER 7x7...", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            # Tampilkan visual video
            cv2.imshow("Test Koordinat ArUco", frame)
            
            # Tekan 'q' untuk berhenti
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        print("\n🛑 Program dihentikan.")
    finally:
        cap.release()
        cv2.destroyAllWindows()

if __name__ == '__main__':
    main()