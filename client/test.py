# from deepface import DeepFace

# # Paths to two face images
# img1 = "C:/Users/oloko/Desktop/Image_sorter/images/20250804_120936.jpg"
# img2 = "C:/Users/oloko/Desktop/Image_sorter/images/20250805_154446.jpg"

# # Perform face verification
# result = DeepFace.verify(
#     img1_path=img1,
#     img2_path=img2,
#     model_name="Facenet",      # or "VGG-Face", "ArcFace", etc.
#     detector_backend="retinaface",  # options: mtcnn, opencv, ssd, mediapipe
#     enforce_detection=True     # set False if some images may not have faces
# )

# # Print the result
# print("Are they the same person?:", result["verified"])
# print("Similarity score:", result["distance"])
# print("Model used:", result["model"])


from deepface import DeepFace
from numpy import dot
from numpy.linalg import norm
import time

# --- STEP 1: Load model (optional, DeepFace can handle internally) ---
print("🚀 Loading model (Facenet)...")
model = DeepFace.build_model("Facenet")
print("✅ Model loaded!/n")

# --- STEP 2: Image paths ---
img1_path = "C:/Users/oloko/Desktop/Image_sorter/images/20250804_120936.jpg"
img2_path = "C:/Users/oloko/Desktop/Image_sorter/images/20250805_154446.jpg"
# img2_path = "C:/Users/oloko/Desktop/Image_sorter/images/20250804_134212.jpg"


# --- STEP 3: Compute embeddings ---
print("🧠 Computing embeddings...")
start_time = time.time()

embedding1 = DeepFace.represent(
    img_path=img1_path,
    model_name="Facenet",
    detector_backend="opencv",
    enforce_detection=False
)[0]["embedding"]

embedding2 = DeepFace.represent(
    img_path=img2_path,
    model_name="Facenet",
    detector_backend="opencv",
    enforce_detection=False
)[0]["embedding"]

print(f"⏱️ Embeddings computed in {time.time() - start_time:.2f}s")

# --- STEP 4: Compare embeddings ---
def cosine_similarity(vec1, vec2):
    return dot(vec1, vec2) / (norm(vec1) * norm(vec2))

similarity = cosine_similarity(embedding1, embedding2)
threshold = 0.65

# --- STEP 5: Result ---
print("/n--- RESULT ---")
print(f"Similarity score (cosine): {similarity:.4f}")
print(f"Are they the same person?: {'✅ YES' if similarity > threshold else '❌ NO'}")
