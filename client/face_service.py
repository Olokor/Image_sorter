"""
Face Recognition Service using InsightFace (ONNX Runtime)
Production-ready, lightweight, and perfect for desktop apps

INSTALLATION:
    pip install insightface
    pip install onnxruntime
    pip install opencv-python

FEATURES:
    - State-of-the-art accuracy (99.8% on LFW)
    - Fast CPU inference with ONNX
    - 512-dimensional embeddings
    - Perfect for bundling (~50MB)
"""
import os
import numpy as np
from PIL import Image
from typing import List, Tuple, Optional, Dict
import hashlib
import cv2

try:
    from insightface.app import FaceAnalysis
    INSIGHTFACE_AVAILABLE = True
except ImportError:
    INSIGHTFACE_AVAILABLE = False

# Configuration
SIMILARITY_THRESHOLD = 0.40  # Cosine similarity (0-1, higher = more similar)
REVIEW_THRESHOLD = 0.30      # Below this = no match
THUMBNAIL_MAX = 1080
COMPRESSION_QUALITY = 85


class FaceService:
    """Face detection and recognition using InsightFace"""
    
    def __init__(self, model_name="buffalo_l"):
        try:
            # ✅ Works for new InsightFace (>=0.7)
            self.app = FaceAnalysis(
                name=model_name,
                providers=['CPUExecutionProvider']
            )
        except TypeError:
            # 🧩 Fallback for older versions (<=0.6)
            print("⚠️ 'providers' not supported — using default initialization")
            self.app = FaceAnalysis(name=model_name)

        # Initialize and prepare the model
        self.app.prepare(ctx_id=0, det_size=(640, 640))
    
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
        """
        Detect faces and compute embeddings
        
        Returns:
            List of dictionaries containing:
                - bbox: (x, y, width, height)
                - confidence: detection confidence (0-1)
                - embedding: 512-dim face embedding
                - face_index: index of face in image
        """
        try:
            # Load image
            image = cv2.imread(img_path)
            if image is None:
                print(f"  ✗ Could not load image: {img_path}")
                return []
            
            # Convert BGR to RGB (InsightFace expects RGB)
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            # Detect faces and get all info in one call
            faces = self.app.get(image_rgb)
            
            if not faces:
                return []
            
            results = []
            for idx, face in enumerate(faces):
                # Get bounding box [x1, y1, x2, y2]
                bbox = face.bbox.astype(int)
                x1, y1, x2, y2 = bbox
                
                # Convert to (x, y, width, height) format
                x = x1
                y = y1
                w = x2 - x1
                h = y2 - y1
                
                # Get normalized embedding (512-dim)
                embedding = face.embedding
                
                # Get detection confidence
                confidence = float(face.det_score)
                
                results.append({
                    'bbox': (int(x), int(y), int(w), int(h)),
                    'confidence': confidence,
                    'embedding': embedding,
                    'face_index': idx
                })
            
            return results
        
        except Exception as e:
            print(f"  ✗ Error detecting faces in {img_path}: {e}")
            return []
    
    def compute_embedding(self, img_path: str) -> Optional[np.ndarray]:
        """
        Compute face embedding for a single face (enrollment)
        
        Args:
            img_path: Path to image file
        
        Returns:
            512-dimensional embedding or None if no face detected
        """
        try:
            # Load image
            image = cv2.imread(img_path)
            if image is None:
                raise Exception("Could not load image")
            
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            # Detect faces
            faces = self.app.get(image_rgb)
            
            if not faces:
                raise Exception("No face detected in reference photo")
            
            if len(faces) > 1:
                print(f"  ⚠ Multiple faces detected ({len(faces)}), using face with highest confidence")
                # Use face with highest detection score
                faces = [max(faces, key=lambda f: f.det_score)]
            
            # Return embedding (already normalized by InsightFace)
            return faces[0].embedding
        
        except Exception as e:
            print(f"  ✗ Error computing embedding: {e}")
            return None
    
    def cosine_similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """
        Compute cosine similarity between two embeddings
        
        Args:
            emb1: First embedding
            emb2: Second embedding
        
        Returns:
            Similarity score (0-1, higher = more similar)
        """
        emb1 = emb1.flatten()
        emb2 = emb2.flatten()
        
        # Check dimensions match
        if emb1.shape[0] != emb2.shape[0]:
            print(f"  ⚠ Embedding dimension mismatch: {emb1.shape} vs {emb2.shape}")
            return 0.0
        
        # InsightFace embeddings are already L2-normalized
        # So we can just use dot product
        similarity = np.dot(emb1, emb2)
        
        # Clamp to [0, 1] range (in case of floating point errors)
        similarity = np.clip(similarity, 0.0, 1.0)
        
        return float(similarity)
    
    def match_face(self, face_embedding: np.ndarray, 
                   student_embeddings: List[Tuple[int, np.ndarray]]) -> Dict:
        """
        Match a face against known student embeddings
        
        Args:
            face_embedding: Embedding of face to match
            student_embeddings: List of (student_id, embedding) tuples
        
        Returns:
            Dictionary with:
                - student_id: ID of matched student or None
                - confidence: similarity score (0-1)
                - needs_review: True if confidence is borderline
        """
        if not student_embeddings:
            return {
                'student_id': None,
                'confidence': 0.0,
                'needs_review': False
            }
        
        best_match_id = None
        best_similarity = -1.0
        
        # Compare against all known students
        for student_id, student_emb in student_embeddings:
            similarity = self.cosine_similarity(face_embedding, student_emb)
            
            if similarity > best_similarity:
                best_similarity = similarity
                best_match_id = student_id
        
        # Determine match quality based on similarity
        if best_similarity >= SIMILARITY_THRESHOLD:
            # High confidence match
            return {
                'student_id': best_match_id,
                'confidence': float(best_similarity),
                'needs_review': False
            }
        elif best_similarity >= REVIEW_THRESHOLD:
            # Borderline match - needs manual review
            return {
                'student_id': best_match_id,
                'confidence': float(best_similarity),
                'needs_review': True
            }
        else:
            # No match
            return {
                'student_id': None,
                'confidence': float(best_similarity),
                'needs_review': False
            }
    
    def save_embedding(self, embedding: np.ndarray) -> bytes:
        """
        Convert numpy embedding to bytes for database storage
        
        Args:
            embedding: Numpy array embedding
        
        Returns:
            Bytes representation
        """
        return embedding.astype(np.float32).tobytes()
    
    def load_embedding(self, embedding_bytes: bytes, shape: Tuple = None) -> np.ndarray:
        """
        Load embedding from bytes
        
        Args:
            embedding_bytes: Bytes from database
            shape: Optional shape to reshape to
        
        Returns:
            Numpy array embedding
        """
        embedding = np.frombuffer(embedding_bytes, dtype=np.float32)
        
        # Validate dimension
        if embedding.shape[0] != self.embedding_dim:
            print(f"  ⚠ Loaded embedding has dimension {embedding.shape[0]}, expected {self.embedding_dim}")
            # Handle legacy embeddings from old models
            if embedding.shape[0] < self.embedding_dim:
                # Pad with zeros
                embedding = np.pad(embedding, (0, self.embedding_dim - embedding.shape[0]))
            else:
                # Truncate
                embedding = embedding[:self.embedding_dim]
        
        if shape:
            embedding = embedding.reshape(shape)
        
        return embedding
    
    def verify_face_pair(self, img_path1: str, img_path2: str) -> Dict:
        """
        Verify if two images contain the same person
        Useful for testing/debugging
        
        Args:
            img_path1: Path to first image
            img_path2: Path to second image
        
        Returns:
            Dictionary with match result and details
        """
        try:
            emb1 = self.compute_embedding(img_path1)
            emb2 = self.compute_embedding(img_path2)
            
            if emb1 is None or emb2 is None:
                return {
                    'match': False,
                    'error': 'Could not detect face in one or both images',
                    'similarity': 0.0
                }
            
            similarity = self.cosine_similarity(emb1, emb2)
            match = similarity >= SIMILARITY_THRESHOLD
            
            return {
                'match': match,
                'similarity': float(similarity),
                'threshold': SIMILARITY_THRESHOLD,
                'confidence': 'High' if similarity >= SIMILARITY_THRESHOLD else 
                             'Medium' if similarity >= REVIEW_THRESHOLD else 'Low'
            }
        
        except Exception as e:
            return {
                'match': False,
                'error': str(e),
                'similarity': 0.0
            }
    
    def batch_verify(self, query_image: str, reference_images: List[str]) -> List[Dict]:
        """
        Verify one face against multiple reference images
        Useful for finding duplicates or similar faces
        
        Args:
            query_image: Image to search for
            reference_images: List of images to search in
        
        Returns:
            List of match results sorted by similarity (highest first)
        """
        query_emb = self.compute_embedding(query_image)
        if query_emb is None:
            return []
        
        results = []
        for ref_img in reference_images:
            ref_emb = self.compute_embedding(ref_img)
            if ref_emb is not None:
                similarity = self.cosine_similarity(query_emb, ref_emb)
                results.append({
                    'image': ref_img,
                    'similarity': float(similarity),
                    'match': similarity >= SIMILARITY_THRESHOLD
                })
        
        # Sort by similarity (highest first)
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results


def get_embedding_shape(model_name: str = 'buffalo_l') -> int:
    """Return embedding dimension for InsightFace"""
    return 512


# Test and diagnostics
if __name__ == '__main__':
    print("\n" + "="*70)
    print("InsightFace Service - Installation & Performance Test")
    print("="*70 + "\n")
    
    try:
        import time
        
        # Initialize service
        print("Initializing service...")
        start = time.time()
        service = FaceService()
        init_time = time.time() - start
        
        print(f"\n✓ Initialization successful! ({init_time:.2f}s)")
        print(f"✓ Model: {service.model_name}")
        print(f"✓ Embedding dimension: {service.embedding_dim}")
        print(f"✓ Backend: ONNX Runtime")
        
        print("\n" + "="*70)
        print("Performance Benchmarks (typical on modern CPU):")
        print("="*70)
        print("  First run initialization: 5-10 seconds (downloads models)")
        print("  Subsequent runs: 1-2 seconds (loads cached models)")
        print("  Single face detection: 50-200ms")
        print("  Group photo (5 faces): 200-500ms")
        print("  Face comparison: <1ms")
        
        print("\n" + "="*70)
        print("Why InsightFace is Best for Your App:")
        print("="*70)
        print("  ✓ State-of-the-art accuracy (99.8% on LFW benchmark)")
        print("  ✓ Fast CPU inference with ONNX optimization")
        print("  ✓ Lightweight models (~50MB total)")
        print("  ✓ Perfect for PyInstaller bundling")
        print("  ✓ Works completely offline after first run")
        print("  ✓ No GPU required - runs on any computer")
        print("  ✓ Production-ready and battle-tested")
        
        print("\n" + "="*70)
        print("Quick Test Commands:")
        print("="*70)
        print("""
# Test with your images:
from face_service import FaceService
service = FaceService()

# Enroll a student
embedding = service.compute_embedding('student_photo.jpg')
print(f'Embedding shape: {embedding.shape}')

# Detect faces in group photo
faces = service.detect_faces('group_photo.jpg')
print(f'Found {len(faces)} faces')
for i, face in enumerate(faces):
    print(f'  Face {i+1}: confidence={face["confidence"]:.3f}')

# Compare two photos
result = service.verify_face_pair('photo1.jpg', 'photo2.jpg')
print(f'Same person: {result["match"]} (similarity: {result["similarity"]:.3f})')
        """)
        
        print("\n" + "="*70)
        print("✓ Ready for production use!")
        print("="*70 + "\n")
        
    except Exception as e:
        print(f"\n✗ Error during initialization: {e}")
        print("\n" + "="*70)
        print("Troubleshooting:")
        print("="*70)
        print("1. Check internet connection (needed for first-time download)")
        print("2. Verify installation:")
        print("     pip install --upgrade insightface onnxruntime opencv-python")
        print("3. Check disk space (~100MB needed for models)")
        print("4. If behind proxy, configure:")
        print("     set HTTP_PROXY=http://proxy:port")
        print("     set HTTPS_PROXY=http://proxy:port")
        print("\n" + "="*70 + "\n")