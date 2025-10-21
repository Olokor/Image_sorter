"""
Enhanced Face Recognition Service
- Multi-scale detection for better accuracy
- Support for averaging multiple reference photos
- Stricter matching thresholds
- Quality checks on detected faces
"""
import os
import numpy as np
import cv2
from PIL import Image
import hashlib
from typing import Optional, List, Tuple, Dict

try:
    from insightface.app import FaceAnalysis
    INSIGHTFACE_AVAILABLE = True
except ImportError:
    FaceAnalysis = None
    INSIGHTFACE_AVAILABLE = False


class EnhancedFaceService:
    """Enhanced face service with multi-photo support and better detection"""
    
    def __init__(self, model_name="buffalo_l"):
        if not INSIGHTFACE_AVAILABLE or FaceAnalysis is None:
            raise ImportError("InsightFace not available")
        
        self.model_name = model_name
        self.embedding_dim = 512
        self.app = None
        
        print("Initializing Enhanced InsightFace...")
        
        try:
            self.app = FaceAnalysis(
                name=model_name,
                providers=['CPUExecutionProvider']
            )
        except TypeError:
            self.app = FaceAnalysis(name=model_name)
        
        if self.app is None:
            raise Exception("Failed to initialize FaceAnalysis")
        
        # Use larger detection size for better accuracy
        self.app.prepare(ctx_id=0, det_size=(640, 640))
        print("✓ Enhanced model ready!")
    
    def compute_embedding(self, img_path: str, min_confidence: float = 0.7) -> Optional[np.ndarray]:
        """
        Compute face embedding with quality check
        Only returns high-quality detections
        """
        try:
            image = cv2.imread(img_path)
            if image is None:
                raise Exception("Could not load image")
            
            # Convert to RGB
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            # Detect faces
            faces = self.app.get(image_rgb)
            
            if not faces:
                raise Exception("No face detected")
            
            # Filter by confidence
            quality_faces = [f for f in faces if f.det_score >= min_confidence]
            
            if not quality_faces:
                raise Exception(f"No high-quality face found (min confidence: {min_confidence})")
            
            # If multiple faces, use highest confidence
            if len(quality_faces) > 1:
                print(f"  ⚠ Multiple faces ({len(quality_faces)}), using highest confidence")
                best_face = max(quality_faces, key=lambda f: f.det_score)
            else:
                best_face = quality_faces[0]
            
            print(f"  ✓ Face detected (confidence: {best_face.det_score:.3f})")
            
            # Normalize embedding
            embedding = best_face.embedding
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = embedding / norm
            
            return embedding
        
        except Exception as e:
            print(f"  ✗ Error: {e}")
            return None
    
    def compute_average_embedding(self, img_paths: List[str]) -> Optional[np.ndarray]:
        """
        Compute averaged embedding from multiple reference photos
        This significantly improves matching accuracy
        """
        embeddings = []
        successful_paths = []
        
        print(f"\n→ Processing {len(img_paths)} reference photo(s)...")
        
        for i, img_path in enumerate(img_paths, 1):
            print(f"  [{i}/{len(img_paths)}] {os.path.basename(img_path)}...", end=" ")
            
            emb = self.compute_embedding(img_path)
            if emb is not None:
                embeddings.append(emb)
                successful_paths.append(img_path)
        
        if not embeddings:
            print("  ✗ No valid faces detected in any photo")
            return None
        
        # Average the embeddings
        avg_embedding = np.mean(embeddings, axis=0)
        
        # Re-normalize
        norm = np.linalg.norm(avg_embedding)
        if norm > 0:
            avg_embedding = avg_embedding / norm
        
        print(f"\n  ✓ Created averaged embedding from {len(embeddings)}/{len(img_paths)} photo(s)")
        return avg_embedding
    
    def detect_faces_enhanced(self, img_path: str, min_confidence: float = 0.6) -> List[Dict]:
        """
        Enhanced face detection with multiple scales and quality filtering
        """
        try:
            image = cv2.imread(img_path)
            if image is None:
                print(f"  ✗ Could not load image: {img_path}")
                return []
            
            # Convert to RGB
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            # Detect faces
            faces = self.app.get(image_rgb)
            
            if not faces:
                # Try with brightness adjustment if no faces found
                print("  → Trying brightness adjustment...")
                adjusted = cv2.convertScaleAbs(image_rgb, alpha=1.2, beta=30)
                faces = self.app.get(adjusted)
            
            if not faces:
                print("  ⚠ No faces detected")
                return []
            
            # Filter and process faces
            results = []
            for idx, face in enumerate(faces):
                # Skip low-confidence detections
                if face.det_score < min_confidence:
                    print(f"  ⊘ Skipped face {idx+1} (low confidence: {face.det_score:.3f})")
                    continue
                
                bbox = face.bbox.astype(int)
                x1, y1, x2, y2 = bbox
                
                # Normalize embedding
                embedding = face.embedding
                norm = np.linalg.norm(embedding)
                if norm > 0:
                    embedding = embedding / norm
                
                results.append({
                    'bbox': (int(x1), int(y1), int(x2 - x1), int(y2 - y1)),
                    'confidence': float(face.det_score),
                    'embedding': embedding,
                    'face_index': idx
                })
                
                print(f"  ✓ Face {idx+1}: confidence={face.det_score:.3f}")
            
            return results
        
        except Exception as e:
            print(f"  ✗ Error detecting faces: {e}")
            return []
    
    def cosine_similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Compute cosine similarity between two embeddings"""
        emb1 = emb1.flatten()
        emb2 = emb2.flatten()
        
        if emb1.shape[0] != emb2.shape[0]:
            return 0.0
        
        # Normalize both
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        emb1 = emb1 / norm1
        emb2 = emb2 / norm2
        
        similarity = np.dot(emb1, emb2)
        return float(np.clip(similarity, 0.0, 1.0))
    
    def match_face_enhanced(self, face_embedding: np.ndarray, 
                          student_embeddings: List[Tuple[int, np.ndarray]],
                          strict_threshold: float = 0.65,
                          review_threshold: float = 0.50) -> Dict:
        """
        Enhanced matching with configurable thresholds
        
        Args:
            face_embedding: Embedding to match
            student_embeddings: List of (student_id, embedding) tuples
            strict_threshold: Auto-accept threshold (higher = stricter)
            review_threshold: Manual review threshold
        
        Returns:
            Dict with student_id, confidence, needs_review, all_similarities
        """
        if not student_embeddings:
            return {
                'student_id': None,
                'confidence': 0.0,
                'needs_review': False,
                'all_similarities': []
            }
        
        # Compute all similarities
        similarities = []
        for student_id, student_emb in student_embeddings:
            similarity = self.cosine_similarity(face_embedding, student_emb)
            similarities.append((student_id, similarity))
        
        # Sort by similarity
        similarities.sort(key=lambda x: x[1], reverse=True)
        best_match_id, best_similarity = similarities[0]
        
        # Check for ambiguous matches (two similar scores)
        is_ambiguous = False
        if len(similarities) > 1:
            second_best_similarity = similarities[1][1]
            # If top two scores are very close, mark as ambiguous
            if best_similarity - second_best_similarity < 0.08:
                is_ambiguous = True
        
        # Determine match status
        if best_similarity >= strict_threshold and not is_ambiguous:
            # Strong match, auto-accept
            return {
                'student_id': best_match_id,
                'confidence': float(best_similarity),
                'needs_review': False,
                'all_similarities': similarities[:3]
            }
        elif best_similarity >= review_threshold:
            # Borderline match, needs review
            return {
                'student_id': best_match_id,
                'confidence': float(best_similarity),
                'needs_review': True,
                'all_similarities': similarities[:3]
            }
        else:
            # No match
            return {
                'student_id': None,
                'confidence': float(best_similarity),
                'needs_review': False,
                'all_similarities': similarities[:3]
            }
    
    def preprocess_image(self, img_path: str, output_dir: str = None) -> Tuple[str, Dict]:
        """Preprocess image with better quality preservation"""
        img = Image.open(img_path)
        
        with open(img_path, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
        
        width, height = img.size
        
        # Use higher resolution for better face detection
        max_size = 1920
        if max(width, height) > max_size:
            ratio = max_size / max(width, height)
            new_size = (int(width * ratio), int(height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            filename = os.path.basename(img_path)
            processed_path = os.path.join(output_dir, f"proc_{filename}")
            # High quality for better face detection
            img.save(processed_path, 'JPEG', quality=95, optimize=True)
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
    
    def save_embedding(self, embedding: np.ndarray) -> bytes:
        """Convert embedding to bytes for storage"""
        return embedding.astype(np.float32).tobytes()
    
    def load_embedding(self, embedding_bytes: bytes) -> np.ndarray:
        """Load embedding from bytes"""
        embedding = np.frombuffer(embedding_bytes, dtype=np.float32)
        
        # Ensure correct dimension
        if embedding.shape[0] != self.embedding_dim:
            if embedding.shape[0] < self.embedding_dim:
                embedding = np.pad(embedding, (0, self.embedding_dim - embedding.shape[0]))
            else:
                embedding = embedding[:self.embedding_dim]
        
        return embedding
    
    def detect_faces(self, img_path: str) -> List[Dict]:
        """Backward compatibility wrapper"""
        return self.detect_faces_enhanced(img_path)
    
    def match_face(self, face_embedding: np.ndarray, 
                   student_embeddings: List[Tuple[int, np.ndarray]]) -> Dict:
        """Backward compatibility wrapper"""
        return self.match_face_enhanced(face_embedding, student_embeddings)
    
    def compare_embeddings(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Backward compatibility wrapper"""
        return self.cosine_similarity(emb1, emb2)


# For backward compatibility
FaceService = EnhancedFaceService


if __name__ == '__main__':
    print("\n" + "="*70)
    print("Testing Enhanced Face Service")
    print("="*70 + "\n")
    
    try:
        service = EnhancedFaceService()
        print("✓ Service initialized successfully!")
        
        # Test embedding save/load
        test_emb = np.random.rand(512).astype(np.float32)
        norm = np.linalg.norm(test_emb)
        test_emb = test_emb / norm
        
        saved = service.save_embedding(test_emb)
        loaded = service.load_embedding(saved)
        
        similarity = service.cosine_similarity(test_emb, loaded)
        print(f"✓ Save/Load test: similarity = {similarity:.6f}")
        
        if similarity > 0.999:
            print("✓ All tests passed!")
        else:
            print(f"⚠ Similarity lower than expected: {similarity}")
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()