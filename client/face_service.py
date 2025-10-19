"""
Face Recognition Service using InsightFace (ONNX Runtime)
Production-ready, lightweight, and perfect for desktop apps

INSTALLATION:
    pip install insightface==0.7.3
    pip install onnxruntime==1.16.0
    pip install opencv-python
"""
import os
import sys
import numpy as np
from PIL import Image
from typing import List, Tuple, Optional, Dict
import hashlib
import cv2

# Try to import InsightFace with comprehensive error handling
INSIGHTFACE_AVAILABLE = False
FaceAnalysis = None
import_error_message = None

try:
    from insightface.app import FaceAnalysis
    INSIGHTFACE_AVAILABLE = True
except ImportError as e:
    import_error_message = str(e)
    INSIGHTFACE_AVAILABLE = False
except Exception as e:
    import_error_message = f"Unexpected error: {e}"
    INSIGHTFACE_AVAILABLE = False

# Configuration
SIMILARITY_THRESHOLD = 0.40  # Cosine similarity (0-1, higher = more similar)
REVIEW_THRESHOLD = 0.30      # Below this = no match
THUMBNAIL_MAX = 1080
COMPRESSION_QUALITY = 85


class FaceService:
    """Face detection and recognition using InsightFace"""
    
    def __init__(self, model_name="buffalo_l"):
        # CRITICAL: Check if InsightFace is available BEFORE trying to use it
        if not INSIGHTFACE_AVAILABLE or FaceAnalysis is None:
            error_msg = [
                "\n" + "="*70,
                "❌ CRITICAL ERROR: InsightFace is not properly installed!",
                "="*70,
            ]
            
            if import_error_message:
                error_msg.append(f"Import error: {import_error_message}")
            
            error_msg.extend([
                "",
                "To fix this issue:",
                "",
                "1. Open your terminal/command prompt",
                "2. Activate your virtual environment:",
                "   cd C:\\Users\\oloko\\Desktop\\Image_sorter",
                "   .venv\\Scripts\\activate",
                "",
                "3. Uninstall any broken installations:",
                "   pip uninstall insightface onnxruntime -y",
                "",
                "4. Install fresh versions:",
                "   pip install insightface==0.7.3",
                "   pip install onnxruntime==1.16.0",
                "   pip install opencv-python",
                "",
                "5. Test the installation:",
                "   python -c \"from insightface.app import FaceAnalysis; print('Success!')\"",
                "",
                "If step 4 fails with network errors, try:",
                "   pip install --no-cache-dir insightface==0.7.3",
                "",
                "="*70,
            ])
            
            full_error = "\n".join(error_msg)
            print(full_error)
            raise ImportError(full_error)
        
        self.model_name = model_name
        self.embedding_dim = 512
        self.app = None
        
        print("Initializing InsightFace...")
        
        # Try multiple initialization strategies
        initialization_successful = False
        last_error = None
        
        # Strategy 1: New API with providers
        if not initialization_successful:
            try:
                print("  → Attempting initialization with providers...")
                self.app = FaceAnalysis(
                    name=model_name,
                    providers=['CPUExecutionProvider']
                )
                initialization_successful = True
                print("  ✓ Initialized with providers")
            except TypeError:
                # Old version doesn't support providers parameter
                pass
            except Exception as e:
                last_error = e
        
        # Strategy 2: Legacy API without providers
        if not initialization_successful:
            try:
                print("  → Attempting legacy initialization...")
                self.app = FaceAnalysis(name=model_name)
                initialization_successful = True
                print("  ✓ Initialized (legacy mode)")
            except Exception as e:
                last_error = e
        
        # Strategy 3: Minimal initialization
        if not initialization_successful:
            try:
                print("  → Attempting minimal initialization...")
                self.app = FaceAnalysis(providers=['CPUExecutionProvider'])
                initialization_successful = True
                print("  ✓ Initialized (minimal mode)")
            except Exception as e:
                last_error = e
        
        # Check if any strategy worked
        if not initialization_successful or self.app is None:
            error_msg = f"Failed to initialize FaceAnalysis after trying all methods.\nLast error: {last_error}"
            print(f"\n✗ {error_msg}\n")
            raise Exception(error_msg)
        
        # Prepare the model
        print("  → Preparing model (downloading if needed)...")
        try:
            self.app.prepare(ctx_id=0, det_size=(640, 640))
            print("  ✓ Model ready!")
        except AssertionError as e:
            error_msg = [
                "\n" + "="*70,
                "❌ MODEL DOWNLOAD FAILED",
                "="*70,
                "InsightFace needs to download model files (~50MB) on first run.",
                f"Error: {e}",
                "",
                "Troubleshooting:",
                "",
                "1. Check internet connection",
                "2. Ensure ~100MB free disk space",
                "",
                "3. If behind a proxy, set these environment variables:",
                "   Windows:",
                "     set HTTP_PROXY=http://your-proxy:port",
                "     set HTTPS_PROXY=http://your-proxy:port",
                "   Linux/Mac:",
                "     export HTTP_PROXY=http://your-proxy:port",
                "     export HTTPS_PROXY=http://your-proxy:port",
                "",
                "4. Manual download (if internet fails):",
                "   a. Visit: https://github.com/deepinsight/insightface/releases",
                "   b. Download: buffalo_l.zip",
                "   c. Extract to one of these locations:",
                "      Windows: C:\\Users\\oloko\\.insightface\\models\\buffalo_l\\",
                "      Linux: ~/.insightface/models/buffalo_l/",
                "",
                "5. Then try running the app again",
                "="*70,
            ]
            full_error = "\n".join(error_msg)
            print(full_error)
            raise Exception(f"Failed to prepare InsightFace model: {e}")
        except Exception as e:
            print(f"\n✗ Unexpected error preparing model: {e}\n")
            raise
    
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
        """Detect faces and compute embeddings"""
        try:
            image = cv2.imread(img_path)
            if image is None:
                print(f"  ✗ Could not load image: {img_path}")
                return []
            
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            faces = self.app.get(image_rgb)
            
            if not faces:
                return []
            
            results = []
            for idx, face in enumerate(faces):
                bbox = face.bbox.astype(int)
                x1, y1, x2, y2 = bbox
                
                results.append({
                    'bbox': (int(x1), int(y1), int(x2 - x1), int(y2 - y1)),
                    'confidence': float(face.det_score),
                    'embedding': face.embedding,
                    'face_index': idx
                })
            
            return results
        
        except Exception as e:
            print(f"  ✗ Error detecting faces: {e}")
            return []
    
    def compute_embedding(self, img_path: str) -> Optional[np.ndarray]:
        """Compute face embedding for enrollment"""
        try:
            image = cv2.imread(img_path)
            if image is None:
                raise Exception("Could not load image")
            
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            faces = self.app.get(image_rgb)
            
            if not faces:
                raise Exception("No face detected")
            
            if len(faces) > 1:
                print(f"  ⚠ Multiple faces ({len(faces)}), using highest confidence")
                faces = [max(faces, key=lambda f: f.det_score)]
            
            return faces[0].embedding
        
        except Exception as e:
            print(f"  ✗ Error computing embedding: {e}")
            return None
    
    def cosine_similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Compute cosine similarity between embeddings"""
        emb1 = emb1.flatten()
        emb2 = emb2.flatten()
        
        if emb1.shape[0] != emb2.shape[0]:
            print(f"  ⚠ Dimension mismatch: {emb1.shape} vs {emb2.shape}")
            return 0.0
        
        similarity = np.dot(emb1, emb2)
        similarity = np.clip(similarity, 0.0, 1.0)
        
        return float(similarity)
    
    def match_face(self, face_embedding: np.ndarray, 
                   student_embeddings: List[Tuple[int, np.ndarray]]) -> Dict:
        """Match face against known students"""
        if not student_embeddings:
            return {
                'student_id': None,
                'confidence': 0.0,
                'needs_review': False
            }
        
        best_match_id = None
        best_similarity = -1.0
        
        for student_id, student_emb in student_embeddings:
            similarity = self.cosine_similarity(face_embedding, student_emb)
            if similarity > best_similarity:
                best_similarity = similarity
                best_match_id = student_id
        
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
        """Convert embedding to bytes for storage"""
        return embedding.astype(np.float32).tobytes()
    
    def load_embedding(self, embedding_bytes: bytes, shape: Tuple = None) -> np.ndarray:
        """Load embedding from bytes"""
        embedding = np.frombuffer(embedding_bytes, dtype=np.float32)
        
        if embedding.shape[0] != self.embedding_dim:
            print(f"  ⚠ Loaded dimension {embedding.shape[0]}, expected {self.embedding_dim}")
            if embedding.shape[0] < self.embedding_dim:
                embedding = np.pad(embedding, (0, self.embedding_dim - embedding.shape[0]))
            else:
                embedding = embedding[:self.embedding_dim]
        
        if shape:
            embedding = embedding.reshape(shape)
        
        return embedding
    
    def verify_face_pair(self, img_path1: str, img_path2: str) -> Dict:
        """Verify if two images contain the same person"""
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


# Test script
if __name__ == '__main__':
    print("\n" + "="*70)
    print("InsightFace Installation Test")
    print("="*70 + "\n")
    
    if not INSIGHTFACE_AVAILABLE:
        print("✗ InsightFace is NOT installed properly!")
        print(f"  Error: {import_error_message}")
        print("\nRun this to fix:")
        print("  pip install insightface==0.7.3 onnxruntime==1.16.0 opencv-python")
        sys.exit(1)
    
    print("✓ InsightFace package found")
    
    try:
        import time
        start = time.time()
        service = FaceService()
        init_time = time.time() - start
        
        print(f"\n✓ Initialization successful! ({init_time:.2f}s)")
        print(f"✓ Model: {service.model_name}")
        print(f"✓ Embedding dimension: {service.embedding_dim}")
        print("\n" + "="*70)
        print("✓ READY FOR USE!")
        print("="*70 + "\n")
        
    except Exception as e:
        print(f"\n✗ Initialization failed: {e}\n")
        sys.exit(1)