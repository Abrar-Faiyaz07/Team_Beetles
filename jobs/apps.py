from django.apps import AppConfig

class JobsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'jobs'
    
    def ready(self):
        """Pre-load the embedding model when Django starts."""
        print("\n" + "="*50)
        print("  CareerPilot Starting...")
        print("  Pre-loading embedding model...")
        print("="*50)
        
        try:
            from .cv_processor import load_embedding_model
            load_embedding_model()
            print("  ✓ Embedding model loaded successfully!")
        except Exception as e:
            print(f"  ⚠ Could not pre-load model: {e}")
            print("  Model will be loaded on first request.")
        
        print("="*50 + "\n")