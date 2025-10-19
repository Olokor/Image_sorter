import os
import cv2
from face_service import FaceService

if __name__ == '__main__':
    print("Testing FaceService...")
    service = FaceService()

    # --- STEP 1: Reference image (the person you want to find)
    reference_path = "C:/Users/oloko/Desktop/Image_sorter/images2/images (3).jpeg"
    reference_embedding = service.compute_embedding(reference_path)
    if reference_embedding is None:
        print("❌ Failed to compute reference embedding")
        exit()

    # --- STEP 2: Directory of images to check
    image_dir = "C:/Users/oloko/Desktop/Image_sorter/images2"
    image_files = [
        os.path.join(image_dir, f)
        for f in os.listdir(image_dir)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ]

    # --- STEP 3: Prepare embeddings list for matching
    student_embeddings = [(1, reference_embedding)]  # pretend ID 1 is our reference person

    print(f"🔍 Matching reference face against {len(image_files)} images.../n")

    total_matches = 0  # total identical faces found
    image_match_counts = {}  # store match counts per image

    for img_path in image_files:
        if img_path == reference_path:
            continue  # skip self-comparison

        print(f"🖼️ Testing: {os.path.basename(img_path)}")

        faces = service.detect_faces(img_path)
        if not faces:
            print("   ⚠️ No faces detected in this image./n")
            continue

        image_match_count = 0  # matches in current image
        for face in faces:
            match_result = service.match_face(face["embedding"], student_embeddings)
            conf = match_result["confidence"]

            if match_result["student_id"]:
                image_match_count += 1
                total_matches += 1
                print(f"   ✅ Match found! Confidence: {conf:.4f}")
                print(f"      → Face index: {face['face_index']} Bounding Box: {face['bbox']}")
            else:
                print(f"   ❌ Not a match (confidence: {conf:.4f})")

        image_match_counts[os.path.basename(img_path)] = image_match_count

        print(f"👉 Matches found in this image: {image_match_count}/n")

    # --- STEP 5: Summary
    print("✅ Test completed!")
    print(f"/n📸 Total identical faces found: {total_matches}")

    if total_matches > 0:
        print("/n📊 Breakdown by image:")
        for img_name, count in image_match_counts.items():
            if count > 0:
                print(f"   - {img_name}: {count} identical face(s)")
    else:
        print("❌ No identical faces found in any image.")
