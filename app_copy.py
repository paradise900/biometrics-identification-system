from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
import os
from datetime import datetime
from deepface import DeepFace
import cv2 


app = Flask(__name__)

db = SQLAlchemy()
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
db.init_app(app)

class User(db.Model):
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    
    def to_dict(self):
        return {
            'id': f"{self.id:08d}",
            'name': self.full_name,
            'position': self.role,
            'department': 'Не указан',
            'last_seen': datetime.now().strftime('%Y-%m-%d %H:%M')
        }

UPLOAD_FOLDER = 'images'
DB_FOLDER = 'photos_db'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DB_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

with app.app_context():
    db.drop_all()
    
    db.create_all()
    
    test_users = [
        User(id=10000000, full_name='Гырдымов Антон Вячеславович', role='CEO'),
        User(id=10000001, full_name='Кочанова Юлия Вадимовна', role='Менеджер'),
        User(id=10000002, full_name='Сидорова Анна Михайловна', role='Аналитик')
    ]
    db.session.bulk_save_objects(test_users)
    db.session.commit()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/photos_db/<path:filename>')
def serve_photo(filename):
    return send_from_directory(
        os.path.join(app.root_path, 'photos_db'),
        filename,
        mimetype='image/jpeg'
    )

@app.route('/identify', methods=['POST'])
def identify_user():
    if 'photo' not in request.files:
        return jsonify({'status': 'error', 'error': 'Файл не загружен'}), 400
    
    file = request.files['photo']
    
    if file and allowed_file(file.filename):
        filename = f"temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        # Проверка с anti-spoofing
        result = get_user_with_anti_spoofing(filepath)
        
        # Удаляем временный файл
        try:
            os.remove(filepath)
        except:
            pass
        
        if result is None:
            return jsonify({'status': 'error', 'error': 'Пользователь не найден'}), 404
        
        if result.get('status') == 'error':  # Если обнаружен спуфинг
            return jsonify(result), 403
            
        # Получаем ID из имени файла
        try:
            photo_name = os.path.basename(result['user']['photo'])
            user_id = int(os.path.splitext(photo_name)[0])
        except:
            return jsonify({'status': 'error', 'error': 'Неверный формат ID'}), 400
            
        # Ищем пользователя в БД
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'status': 'error', 'error': 'Данные пользователя не найдены'}), 404
            
        return jsonify({
            'status': 'success',
            'user': user.to_dict()
        })
    
    return jsonify({'status': 'error', 'error': 'Неподдерживаемый формат файла'}), 400

def get_user_with_anti_spoofing(src_image_path):
    try:
        # Загружаем изображение
        img = cv2.imread(src_image_path)
        
        # Проверка на спуфинг
        spoof_check = DeepFace.analyze(
            img_path=img,
            actions=['spoof'],
            detector_backend='opencv',
            silent=True
        )
        
        # Если обнаружен спуфинг (фото вместо реального лица)
        if spoof_check[0]['is_spoof']:
            return {
                'status': 'error',
                'error': 'Обнаружена попытка обмана системы (использование фото вместо реального лица)'
            }
        
        # Если проверка на спуфинг пройдена, ищем лицо в базе
        finding_res = DeepFace.find(
            img_path=img,
            db_path=DB_FOLDER,
            model_name='Facenet512',
            detector_backend='yolov8',
            distance_metric='cosine',
            enforce_detection=True,
            silent=True
        )
        
        if len(finding_res) > 0 and not finding_res[0].empty:
            best_match = finding_res[0].iloc[0]
            return {
                'status': 'success',
                'user': {
                    'photo': os.path.basename(best_match['identity'])
                }
            }
        return None
        
    except Exception as e:
        app.logger.error(f"Face recognition error: {str(e)}")
        return None

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)