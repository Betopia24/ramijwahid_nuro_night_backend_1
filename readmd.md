Legal Advocacy API
A FastAPI-based service for generating audio from PDFs and evaluating speech submissions using OpenAI's speech-to-text and text-to-speech technologies.
Features

Audio Generation: Convert PDF documents to speech with multiple voice support
Speech Evaluation: Transcribe audio submissions and grade them against PDF instructions
Database Integration: PostgreSQL with automatic grading report storage
Cloud Storage: Cloudinary integration for audio file management

Prerequisites

Docker and Docker Compose
OpenAI API key
Cloudinary account (for audio storage)
Database connection (PostgreSQL)

Quick Start

Extract the project

bash   unzip legal_advocacy_api.zip
   cd legal_advocacy_api

Create environment file
Create a .env file in the root directory:

Make sure env exist with all: 
   OPENAI_API_KEY=sk-your-openai-api-key
   CLOUDINARY_CLOUD_NAME=your-cloud-name
   CLOUDINARY_API_KEY=your-api-key
   CLOUDINARY_API_SECRET=your-api-secret
   DATABASE_URL=your-postgresql-connection-string

Run with Docker

bash   docker-compose up --build

Access the API

API Documentation: http://localhost:8000/docs
Health Check: http://localhost:8000/health



API Endpoints
Generate Audio from Scenario
httpPOST /speech/generate-from-scenario
Parameters:

scenario_id (string): UUID of the scenario

Response:
json{
  "message": "Audio generated from scenario successfully",
  "scenario_id": "uuid",
  "cloudinary_url": "https://...",
  "status": "Database updated"
}
Evaluate Submission
httpPOST /grade/evaluate-submission
Parameters:

scenario_id (string): UUID of the scenario
user_id (string): UUID of the user
audio_file (file): Audio file to evaluate

Response:
json{
  "message": "database updated",
  "user_id": "uuid",
  "submission_id": "uuid"
}
Environment Variables
VariableDescriptionRequiredOPENAI_API_KEYYour OpenAI API keyYesDATABASE_URLPostgreSQL connection stringYesCLOUDINARY_CLOUD_NAMECloudinary cloud nameYesCLOUDINARY_API_KEYCloudinary API keyYesCLOUDINARY_API_SECRETCloudinary API secretYes
Database Schema
The API expects these PostgreSQL tables:

Scenario: Stores scenario data with speech and marking pointer information
Submission: Stores evaluation results
reference_audio: Stores generated audio file references

Development
Without Docker

Install dependencies: pip install -r requirements.txt
Set environment variables
Run: python main.py

With Docker

Build: docker-compose build
Run: docker-compose up

Troubleshooting
psycopg2 build error: The requirements.txt uses psycopg2-binary to avoid compilation issues.
Missing nginx.conf: The nginx service is commented out in docker-compose.yml for simplicity.
Database connection: Ensure your DATABASE_URL is correct and accessible.
Tech Stack

Framework: FastAPI
Database: PostgreSQL with psycopg2
AI Services: OpenAI (TTS, Whisper, GPT)
Cloud Storage: Cloudinary
Deployment: Docker & Docker Compose
