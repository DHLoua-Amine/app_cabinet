import numpy as np
import cv2

def evaluate_face_quality(crop) -> float:
    if crop is None or crop.size == 0:
        return 0.0
    try:
        crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
        h, w = crop_gray.shape
        if h < 20 or w < 20:
            return 0.0
        
        # 1. Sharpness (Laplacian variance)
        sharpness = cv2.Laplacian(crop_gray, cv2.CV_64F).var()
        
        # 2. Lighting & Brightness balance (ideal around 130)
        mean_b = np.mean(crop_gray)
        std_b = np.std(crop_gray)
        lighting_score = max(0.0, 100.0 - abs(mean_b - 130.0))
        
        # 3. Resolution factor
        resolution_score = min((w * h) / 1000.0, 50.0)
        
        # Total composite quality score
        total_score = (sharpness * 1.5) + (lighting_score * 0.5) + (std_b * 0.8) + resolution_score
        return float(total_score)
    except Exception as e:
        print("Error evaluating face quality:", e)
        return 0.0

if __name__ == "__main__":
    # Test 1: Blurry image (low variance)
    blurry = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.GaussianBlur(blurry, (15, 15), 0, dst=blurry)
    
    # Test 2: Sharp image (textured/edges)
    sharp = np.random.randint(50, 200, (100, 100, 3), dtype=np.uint8)
    
    s_blurry = evaluate_face_quality(blurry)
    s_sharp = evaluate_face_quality(sharp)
    
    print(f"Blurry face quality score: {s_blurry:.2f}")
    print(f"Sharp face quality score:  {s_sharp:.2f}")
    assert s_sharp > s_blurry, "Sharp image must score higher than blurry image!"
    print("ALL TESTS PASSED SUCCESSFULLY!")
