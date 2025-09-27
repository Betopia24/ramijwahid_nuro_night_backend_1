# ===================================
# database.py
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader
import config
from uuid import uuid4

import time
from typing import Optional, List, Dict, Any
import uuid

from psycopg2 import Binary, IntegrityError



load_dotenv()

# Configure Cloudinary
cloudinary.config(
    cloud_name=config.CLOUDINARY_CLOUD_NAME,
    api_key=config.CLOUDINARY_API_KEY,
    api_secret=config.CLOUDINARY_API_SECRET
)

DATABASE_URL = os.getenv('DATABASE_URL')

def get_database_connection(max_retries=3, retry_delay=1):
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(
                DATABASE_URL,
                connect_timeout=10,
                application_name="legal_advocacy_api"
            )
            return conn
        except psycopg2.OperationalError as e:
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
                continue
            print(f"Database connection failed after {max_retries} attempts: {e}")
            return None
        except Exception as e:
            print(f"Unexpected database error: {e}")
            return None
        

def get_data_from_db(query: str, params: Optional[tuple] = None) -> Optional[List[Dict]]:
    if not query.strip():
        raise ValueError("Query cannot be empty")
    
    conn = get_database_connection()
    if not conn:
        return None
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
            data = cursor.fetchall()
            return [dict(row) for row in data]
    except psycopg2.Error as e:
        print(f"Database query error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error in get_data_from_db: {e}")
        return None
    finally:
        conn.close()



def upload_data_to_db(query: str, params: Optional[tuple] = None) -> bool:
    if not query.strip():
        raise ValueError("Query cannot be empty")
    
    conn = get_database_connection()
    if not conn:
        return False
    
    try:
        with conn:  # Auto-commit on success, auto-rollback on exception
            with conn.cursor() as cursor:
                cursor.execute(query, params)
        return True
    except psycopg2.IntegrityError as e:
        error_msg = str(e)
        print(f"Database integrity error: {error_msg}")
        
        # Check for specific foreign key violations
        if "userId_fkey" in error_msg:
            raise ValueError("User not found - invalid user ID provided")
        elif "scenarioId_fkey" in error_msg:
            raise ValueError("Scenario not found - invalid scenario ID provided")
        else:
            raise ValueError("Data integrity constraint violated")
        
    except psycopg2.Error as e:
        print(f"Database upload error: {e}")
        raise ValueError(f"Database operation failed: {str(e)}")
    except Exception as e:
        print(f"Unexpected error in upload_data_to_db: {e}")
        return False
    finally:
        conn.close()


def get_scenario_by_id(scenario_id: str) -> Optional[List[Dict]]:
    if not scenario_id or not scenario_id.strip():
        raise ValueError("Scenario ID cannot be empty")
    
    # Validate UUID format if using UUIDs
    try:
        uuid.UUID(scenario_id)
    except ValueError:
        raise ValueError("Invalid scenario ID format")
    
    query = 'SELECT id, speech FROM "Scenario" WHERE id = %s'
    return get_data_from_db(query, (scenario_id,))



def upload_audio_file_to_cloudinary(file_path: str, public_id: str) -> Optional[str]:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")
    
    if not public_id.strip():
        raise ValueError("Public ID cannot be empty")
    
    try:
        result = cloudinary.uploader.upload(
            file_path,
            resource_type="video",
            public_id=public_id,
            folder="reference_audio",
            overwrite=True,
            timeout=60  # Add timeout
        )
        return result['secure_url']
    except Exception as e:
        print(f"Cloudinary upload failed: {e}")
        return None
    

def upload_audio_url_to_db(scenario_id, audio_url, audio_format, audio_size):
    """Store audio URL, format, and size in database"""
    query = """
    INSERT INTO reference_audio ("id", "audioScenarioId", "audioUrl", "fileFormate", "size", "createdAt") 
    VALUES (%s, %s, %s, %s, %s, NOW())
    ON CONFLICT ("audioScenarioId") DO UPDATE SET 
        "audioUrl" = EXCLUDED."audioUrl", 
        "fileFormate" = EXCLUDED."fileFormate",
        "size" = EXCLUDED."size",
        "createdAt" = NOW()
    """
    return upload_data_to_db(query, (str(uuid4()), scenario_id, audio_url, audio_format, audio_size))

def upload_submission_to_db(user_id, scenario_id, total_score, positives_str, negatives_str, improvements_str):
    """Store submission feedback in database"""
    query = """
    INSERT INTO "Submission" 
    ("id", "userId", "scenarioId", "totalScore", "positive", "negative", "improvement", "status", "createdAt", "updatedAt") 
    VALUES (%s, %s, %s, %s, %s, %s, %s, 'COMPLETED', NOW(), NOW()) 
    """
    
    submission_id = str(uuid4())
    
    params = (
        submission_id,
        user_id,
        scenario_id,
        total_score,
        positives_str,
        negatives_str,
        improvements_str,
    )
    
    try:
        success = upload_data_to_db(query, params)
        if not success:
            raise ValueError("Database operation failed")
        return submission_id
    except ValueError:
        # Re-raise ValueError exceptions from upload_data_to_db
        raise
    except Exception as e:
        raise ValueError(f"Submission upload failed: {str(e)}")


def get_pdfUrl_according_to_scenario(scenario_id):
    query = 'SELECT "markingPointer" FROM "Scenario" WHERE "id" = %s'
    data = get_data_from_db(query, (scenario_id,))
    
    if not data or len(data) == 0:
        return None
        
    try:
        url = data[0]['markingPointer']['fileUrl']
        return url
    except (KeyError, TypeError):
        return None

# print(get_pdfUrl_according_to_scenario("1916acd4-b1fc-46d0-8ee1-389ced21a652"))
# def get_all_reference_audios():
#     query = 'SELECT * FROM reference_audio'
#     return get_data_from_db(query)


# def get_all_Assessments():
#     query = 'SELECT "id" FROM "Scenario"'
#     return get_data_from_db(query)

# print(get_all_Assessments())

# print(get_all_reference_audios())

# def get_all_scenarios():
#     query = 'SELECT id FROM "Scenario"'
#     return get_data_from_db(query)

# print(get_all_scenarios())

# def get_user_id_according_to_scenario_id(scenario_id):
#     query = 'SELECT "userId" FROM "Submission" WHERE "scenarioId" = %s'
#     result = get_data_from_db(query, (scenario_id,))
#     return result

# # Example usage
# print(get_user_id_according_to_scenario_id("1916acd4-b1fc-46d0-8ee1-389ced21a652"))




