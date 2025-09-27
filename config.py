import os
from pathlib import Path
from dotenv import load_dotenv
import sys

# Load environment variables
load_dotenv()

# OpenAI Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_API_KEY or not OPENAI_API_KEY.startswith('sk-'):
    raise ValueError("Invalid OpenAI API key format")

OPENAI_TTS_MODEL = "tts-1"
# Voice mapping for different speakers
OPENAI_VOICES = {
    "speaker1": "echo",    # Male voice 1
    "speaker2": "onyx",     # Male voice 2  
    "speaker3": "fable",    # Male voice 3
    "female": "nova",       # Female voice
    "default": "onyx"       # Default male voice
}

OPENAI_TRANSCRIBE_MODEL = "whisper-1"

OPENAI_CHAT_MODEL = "gpt-3.5-turbo"

# ADD THESE CLOUDINARY VARIABLES
CLOUDINARY_CLOUD_NAME = os.getenv('CLOUDINARY_CLOUD_NAME')
CLOUDINARY_API_KEY = os.getenv('CLOUDINARY_API_KEY')
CLOUDINARY_API_SECRET = os.getenv('CLOUDINARY_API_SECRET')



# API Configuration
API_HOST = "0.0.0.0"
API_PORT = 8000



# Load environment variables with error handling
try:
    load_dotenv()
except Exception as e:
    print(f"Warning: Could not load .env file: {e}")

# Validate critical environment variables
def validate_environment():
    required_vars = [
        'OPENAI_API_KEY',
        'DATABASE_URL',
        'CLOUDINARY_CLOUD_NAME', 
        'CLOUDINARY_API_KEY',
        'CLOUDINARY_API_SECRET'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"Error: Missing required environment variables: {', '.join(missing_vars)}")
        sys.exit(1)

# Call validation on import
validate_environment()








