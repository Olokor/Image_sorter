"""
Simple face detection using OpenCV only - No TensorFlow or dlib!
Works on any system with minimal dependencies
"""
import os
import numpy as np
import cv2
from PIL import Image
from typing import List, Tuple, Optional, Dict
import hashlib

# Configuration
SIMILARITY_THRESHOLD = 0.85  # Histogram similarity threshold
REVIEW_THRESHOLD = 0.75
THUMBNAIL_MAX = 1080
COMPRESSION_QUALITY = 85

# Face cascade (comes with OpenCV)
FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')


class FaceService:
    """Simple face detection using OpenCV Haar Cascades"""
    
    def __init__(self, model_name='opencv'):
        self.model_name = model_name
        print(f"✓ FaceService initialized (Model: OpenCV Haar Cascades)")
        print("⚠ Note: Using basic histogram matching - accuracy may be lower than deep learning")
    
    def preprocess_image(self, img_path: str, output_dir: str = None) -> Tuple[str, Dict]:
        """Preprocess image: resize, compress, compute hash"""
        img = Image.open(img_path)
        
        with open(img_path, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
        
        width, height = img.size
        
        if max(width, height) > THUMBNAIL_MAX:
            ratio = THUMBNAIL_MAX / max(width, height)
            new_size = (int(width * ratio), int(height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            filename = os.path.basename(img_path)
            processed_path = os.path.join(output_dir, f"proc_{filename}")
            img.save(processed_path, 'JPEG', quality=COMPRESSION_QUALITY, optimize=True)
        else:
            processed_path = img_path
        
        metadata = {
            'file_hash': file_hash,
            'original_size': os.path.getsize(img_path),
            'width': width,
            'height': height,
            'processed_path': processed_path
        }
        
        return processed_path, metadata
    
    def detect_faces(self, img_path: str) -> List[Dict]:
        """Detect faces using Haar Cascades"""
        try:
            # Load image
            image = cv2.imread(img_path)
            if image is None:
                return []
            
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Detect faces
            faces = FACE_CASCADE.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(30, 30)
            )
            
            results = []
            for idx, (x, y, w, h) in enumerate(faces):
                # Extract face region
                face_roi = gray[y:y+h, x:x+w]
                
                # Compute simple histogram as "embedding"
                embedding = self._compute_face_features(face_roi)
                
                results.append({
                    'bbox': (int(x), int(y), int(w), int(h)),
                    'confidence': 0.9,
                    'embedding': embedding,
                    'face_index': idx
                })
            
            return results
        
        except Exception as e:
            print(f"Error detecting faces in {img_path}: {e}")
            return []
    
    def compute_embedding(self, img_path: str) -> Optional[np.ndarray]:
        """Compute features for enrollment photo"""
        try:
            image = cv2.imread(img_path)
            if image is None:
                return None
            
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            faces = FACE_CASCADE.detectMultiScale(gray, 1.1, 5)
            
            if len(faces) == 0:
                raise Exception("No face detected in reference photo")
            
            # Use the largest face
            faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
            x, y, w, h = faces[0]
            
            face_roi = gray[y:y+h, x:x+w]
            return self._compute_face_features(face_roi)
        
        except Exception as e:
            print(f"Error computing embedding: {e}")
            return None
    
    def _compute_face_features(self, face_roi: np.ndarray) -> np.ndarray:
        """
        Compute face features using multiple methods:
        1. Histogram
        2. LBP (Local Binary Patterns)
        3. HOG-like features
        """
        # Resize to standard size
        face_roi = cv2.resize(face_roi, (100, 100))
        
        # 1. Histogram features
        hist = cv2.calcHist([face_roi], [0], None, [64], [0, 256])
        hist = cv2.normalize(hist, hist).flatten()
        
        # 2. LBP features (simplified)
        lbp_features = self._compute_lbp(face_roi)
        
        # 3. Edge features
        edges = cv2.Canny(face_roi, 50, 150)
        edge_hist = cv2.calcHist([edges], [0], None, [32], [0, 256])
        edge_hist = cv2.normalize(edge_hist, edge_hist).flatten()
        
        # Combine all features
        features = np.concatenate([hist, lbp_features, edge_hist])
        
        return features
    
    def _compute_lbp(self, image: np.ndarray) -> np.ndarray:
        """Compute Local Binary Pattern features"""
        # Simple 3x3 LBP
        lbp = np.zeros_like(image)
        
        for i in range(1, image.shape[0] - 1):
            for j in range(1, image.shape[1] - 1):
                center = image[i, j]
                code = 0
                
                code |= (image[i-1, j-1] >= center) << 7
                code |= (image[i-1, j] >= center) << 6
                code |= (image[i-1, j+1] >= center) << 5
                code |= (image[i, j+1] >= center) << 4
                code |= (image[i+1, j+1] >= center) << 3
                code |= (image[i+1, j] >= center) << 2
                code |= (image[i+1, j-1] >= center) << 1
                code |= (image[i, j-1] >= center) << 0
                
                lbp[i, j] = code
        
        # Compute histogram of LBP
        hist = cv2.calcHist([lbp], [0], None, [32], [0, 256])
        hist = cv2.normalize(hist, hist).flatten()
        
        return hist
    
    def cosine_similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Compute cosine similarity"""
        emb1 = emb1.flatten()
        emb2 = emb2.flatten()
        
        dot_product = np.dot(emb1, emb2)
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def match_face(self, face_embedding: np.ndarray, student_embeddings: List[Tuple[int, np.ndarray]]) -> Dict:
        """Match face against known students"""
        if not student_embeddings:
            return {'student_id': None, 'confidence': 0.0, 'needs_review': False}
        
        best_match_id = None
        best_similarity = -1.0
        
        for student_id, student_emb in student_embeddings:
            similarity = self.cosine_similarity(face_embedding, student_emb)
            
            if similarity > best_similarity:
                best_similarity = similarity
                best_match_id = student_id
        
        # Determine match quality
        if best_similarity >= SIMILARITY_THRESHOLD:
            return {
                'student_id': best_match_id,
                'confidence': float(best_similarity),
                'needs_review': False
            }
        elif best_similarity >= REVIEW_THRESHOLD:
            return {
                'student_id': best_match_id,
                'confidence': float(best_similarity),
                'needs_review': True
            }
        else:
            return {
                'student_id': None,
                'confidence': float(best_similarity),
                'needs_review': False
            }
    
    def save_embedding(self, embedding: np.ndarray) -> bytes:
        """Convert numpy embedding to bytes"""
        return embedding.tobytes()
    
    def load_embedding(self, embedding_bytes: bytes, shape: Tuple = None) -> np.ndarray:
        """Load embedding from bytes"""
        embedding = np.frombuffer(embedding_bytes, dtype=np.float64)
        if shape:
            embedding = embedding.reshape(shape)
        return embedding


def get_embedding_shape(model_name: str = 'opencv') -> int:
    """Return embedding dimension"""
    return 128  # Combined features dimension


if __name__ == '__main__':
    print("Testing OpenCV FaceService...")
    service = FaceService()
    print("✓ Ready to use!")
    print("\nNote: This uses basic computer vision techniques.")
    print("For better accuracy, install face_recognition or use DeepFace with proper TensorFlow setup.")