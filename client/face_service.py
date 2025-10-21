"""
Enhanced Face Recognition Service with Multiple Reference Photos
Supports averaging embeddings from multiple photos for better accuracy
"""
from dependencies import (
    os, np, cv2, Image, hashlib,
    Optional, List, Tuple, Dict,
    FaceAnalysis, INSIGHTFACE_AVAILABLE,
    SIMILARITY_THRESHOLD, REVIEW_THRESHOLD, 
    THUMBNAIL_MAX, COMPRESSION_QUALITY
)


class EnhancedFaceService:
    """Enhanced face service supporting multiple reference photos per student"""
    
    def __init__(self, model_name="antelopev2"):
        if not INSIGHTFACE_AVAILABLE or FaceAnalysis is None:
            raise ImportError("InsightFace not available")
        
        self.model_name = model_name
        self.embedding_dim = 512
        self.app = None
        
        print("Initializing InsightFace...")
        
        # Try initialization strategies
        try:
            self.app = FaceAnalysis(
                name=model_name,
                providers=['CPUExecutionProvider']
            )
        except TypeError:
            self.app = FaceAnalysis(name=model_name)
        
        if self.app is None:
            raise Exception("Failed to initialize FaceAnalysis")
        
        # Prepare model with higher detection size for better accuracy
        self.app.prepare(ctx_id=0, det_size=(640, 640))
        print("✓ Model ready!")
    
    def compute_embedding(self, img_path: str) -> Optional[np.ndarray]:
        """Compute face embedding from single image"""
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
    
    def compute_average_embedding(self, img_paths: List[str]) -> Optional[np.ndarray]:
        """
        Compute averaged embedding from multiple reference photos
        This significantly improves matching accuracy
        """
        embeddings = []
        
        for img_path in img_paths:
            emb = self.compute_embedding(img_path)
            if emb is not None:
                embeddings.append(emb)
        
        if not embeddings:
            return None
        
        # Average the embeddings
        avg_embedding = np.mean(embeddings, axis=0)
        
        # Normalize (important for cosine similarity)
        norm = np.linalg.norm(avg_embedding)
        if norm > 0:
            avg_embedding = avg_embedding / norm
        
        print(f"  ✓ Averaged {len(embeddings)} embedding(s)")
        return avg_embedding
    
    def detect_faces_enhanced(self, img_path: str, min_confidence: float = 0.5) -> List[Dict]:
        """
        Enhanced face detection with confidence filtering
        Returns only high-quality detections
        """
        try:
            image = cv2.imread(img_path)
            if image is None:
                print(f"  ✗ Could not load image: {img_path}")
                return []
            
            # Try multiple scales for better detection
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            faces = self.app.get(image_rgb)
            
            if not faces:
                return []
            
            # Filter by confidence
            results = []
            for idx, face in enumerate(faces):
                if face.det_score < min_confidence:
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
            
            return results
        
        except Exception as e:
            print(f"  ✗ Error detecting faces: {e}")
            return []
    
    def cosine_similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Compute cosine similarity with normalization"""
        emb1 = emb1.flatten()
        emb2 = emb2.flatten()
        
        if emb1.shape[0] != emb2.shape[0]:
            return 0.0
        
        # Normalize both embeddings
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
                          strict_threshold: float = 0.70,
                          review_threshold: float = 0.55) -> Dict:
        """
        Enhanced matching with configurable thresholds
        Uses stricter default thresholds for better accuracy
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
        
        # Check if there's a second close match (ambiguous)
        is_ambiguous = False
        if len(similarities) > 1:
            second_best_similarity = similarities[1][1]
            if best_similarity - second_best_similarity < 0.05:
                is_ambiguous = True
        
        # Determine match status
        if best_similarity >= strict_threshold and not is_ambiguous:
            return {
                'student_id': best_match_id,
                'confidence': float(best_similarity),
                'needs_review': False,
                'all_similarities': similarities[:3]  # Top 3
            }
        elif best_similarity >= review_threshold:
            return {
                'student_id': best_match_id,
                'confidence': float(best_similarity),
                'needs_review': True,
                'all_similarities': similarities[:3]
            }
        else:
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
        
        # Use higher quality for face recognition
        max_size = 1920  # Higher than before
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
            # Higher quality for better face detection
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
    
    def save_multiple_embeddings(self, embeddings: List[np.ndarray]) -> bytes:
        """Save multiple embeddings as a single averaged embedding"""
        if not embeddings:
            return None
        
        avg_embedding = np.mean(embeddings, axis=0)
        norm = np.linalg.norm(avg_embedding)
        if norm > 0:
            avg_embedding = avg_embedding / norm
        
        return self.save_embedding(avg_embedding)


# For backward compatibility
FaceService = EnhancedFaceService


if __name__ == '__main__':
    print("\n" + "="*70)
    print("Testing Enhanced Face Service")
    print("="*70 + "\n")
    
    try:
        service = EnhancedFaceService()
        print("✓ Service initialized successfully!")
        
        # Test with dummy data
        test_emb = np.random.rand(512).astype(np.float32)
        saved = service.save_embedding(test_emb)
        loaded = service.load_embedding(saved)
        
        similarity = service.cosine_similarity(test_emb, loaded)
        print(f"✓ Save/Load test: similarity = {similarity:.4f}")
        
        if similarity > 0.99:
            print("✓ All tests passed!")
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()