"""
FaceID System Backend Documentation

This module provides the backend API for FaceID - a facial recognition system.
It uses FastAPI for web framework, SQLAlchemy for database operations,
and DeepFace for facial recognition.
"""

import os
import logging
from datetime import datetime
from fastapi import FastAPI, File, UploadFile, HTTPException, status, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from deepface import DeepFace
from pathlib import Path

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = "sqlite:///instance/users.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    """
    Database model representing a system user.
    
    Attributes:
        id (int): Unique user identifier (primary key)
        full_name (str): User's full name
        role (str): User's position/role in the system
    """
    __tablename__ = 'user'
    
    id = Column(Integer, primary_key=True)
    full_name = Column(String(100), nullable=False)
    role = Column(String(50), nullable=False)
    
    def to_dict(self):
        """
        Convert User object to dictionary representation.
        
        Returns:
            dict: Dictionary containing user data with keys:
                  - id (str): 8-digit formatted ID
                  - name (str): Full name
                  - position (str): Role
                  - department (str): Hardcoded as 'Не указан'
                  - last_seen (str): Current timestamp
        """
        return {
            'id': f"{self.id:08d}",
            'name': self.full_name,
            'position': self.role,
            'department': 'Не указан',
            'last_seen': datetime.now().strftime('%Y-%m-%d %H:%M')
        }

def initialize_database():
    """
    Initialize the database with test data.
    
    Drops existing tables, creates new ones, and populates with test users.
    Handles database exceptions and logs errors.
    """
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        test_users = [
            User(id=10000000, full_name='Гырдымов Антон Вячеславович', role='CEO'),
            User(id=10000001, full_name='Кочанова Юлия Вадимовна', role='Менеджер'),
            User(id=10000002, full_name='Сидорова Анна Михайловна', role='Аналитик')
        ]
        db.add_all(test_users)
        db.commit()
    except SQLAlchemyError as e:
        logging.error(f"Database initialization error: {str(e)}")
        db.rollback()
    finally:
        db.close()

UPLOAD_FOLDER = 'images'
DB_FOLDER = 'photos_db'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DB_FOLDER, exist_ok=True)

initialize_database()

def allowed_file(filename: str) -> bool:
    """
    Check if file has allowed extension.
    
    Args:
        filename (str): Name of the file to check
        
    Returns:
        bool: True if extension is allowed (jpg, jpeg, png), False otherwise
    """
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """
    Serve the main application page.
    
    Args:
        request (Request): FastAPI request object
        
    Returns:
        TemplateResponse: Rendered HTML template
    """
    return templates.TemplateResponse("index.html", {"request": request})

app.mount("/photos_db", StaticFiles(directory="photos_db"), name="photos_db")

@app.post("/identify")
async def identify_user(photo: UploadFile = File(...)):
    """
    Handle facial identification request.
    
    Args:
        photo (UploadFile): Image file uploaded for identification
        
    Returns:
        JSONResponse: Identification result containing:
                     - status (str): 'success' or 'error'
                     - user (dict): User data if successful
                     - error (str): Error message if failed
        
    Raises:
        HTTPException: 400 if no file/invalid format
        HTTPException: 403 if spoof detected
        HTTPException: 404 if user not found
        HTTPException: 500 if file processing fails
    """
    if not photo.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Файл не загружен"
        )
    
    if not allowed_file(photo.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неподдерживаемый формат файла"
        )
    
    filename = f"temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    
    try:
        with open(filepath, "wb") as buffer:
            buffer.write(await photo.read())
    except Exception as e:
        logging.error(f"File saving error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка сохранения файла"
        )
    
    result = get_user(filepath)
    
    try:
        os.remove(filepath)
    except Exception as e:
        logging.warning(f"Temp file deletion warning: {str(e)}")
    
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )
    
    if result.get('status') == 'error':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=result['error']
        )
    
    try:
        photo_name = os.path.basename(result['user']['photo'])
        user_id = int(os.path.splitext(photo_name)[0])
    except Exception as e:
        logging.error(f"ID extraction error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный формат ID"
        )
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Данные пользователя не найдены"
            )
        
        return JSONResponse({
            'status': 'success',
            'user': user.to_dict()
        })
    finally:
        db.close()

def get_user(src_image_path: str):
    """
    Perform facial recognition using DeepFace.
    
    Args:
        src_image_path (str): Path to image for recognition
        
    Returns:
        dict: Recognition result with:
              - status (str): 'success' or 'error'
              - user (dict): Contains 'photo' filename if successful
              - error (str): Error message if failed
        
    Note:
        Uses Facenet512 model with retinaface detector and anti-spoofing.
        Matching threshold set to 0.7 cosine distance.
    """
    try:
        finding_res = DeepFace.find(
            img_path=src_image_path,
            db_path=DB_FOLDER,
            model_name='Facenet512',
            detector_backend='retinaface',
            distance_metric='cosine',
            threshold=0.7,
            anti_spoofing=True,
            silent=True
        )
        
        if finding_res and not finding_res[0].empty:
            person = finding_res[0]['identity'][0]
            return {
                'status': 'success',
                'user': {
                    'photo': os.path.basename(person).split('_')[0]
                }
            }
        return None
    except Exception as e:
        if str(e) == 'Spoof detected in the given image.':
            return {
                "status": "error",
                "error": "Система обнаружила возможную подделку (фото/видео вместо реального лица)"
            }
        logging.error(f"Face recognition error: {str(e)}")
        return None

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, port=5001)