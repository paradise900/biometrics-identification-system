from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import os
from datetime import datetime
from deepface import DeepFace

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
    # Удаляем все таблицы
    db.drop_all()
    
    # Создаем новые таблицы с актуальной схемой
    db.create_all()
    
    # Добавляем тестовые данные
    test_users = [
        User(id=10000001, full_name='Иванов Иван Иванович', role='Администратор'),
        User(id=10000002, full_name='Петров Петр Петрович', role='Менеджер'),
        User(id=10000003, full_name='Сидорова Анна Михайловна', role='Аналитик')
    ]
    db.session.bulk_save_objects(test_users)
    db.session.commit()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/identify', methods=['POST'])
def identify_user():
    if 'photo' not in request.files:
        return jsonify({'status': 'error', 'error': 'Файл не загружен'}), 400
    
    file = request.files['photo']
    
    if file and allowed_file(file.filename):
        # Сохраняем временный файл
        filename = f"temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        # Идентификация по фото
        result = get_user(filepath)
        
        # Удаляем временный файл
        try:
            os.remove(filepath)
        except:
            pass
        
        if result is None:
            return jsonify({'status': 'error', 'error': 'Пользователь не найден'}), 404
        
        # Извлекаем ID из имени файла (например: "10000001.jpg" → 10000001)
        try:
            photo_name = os.path.basename(result['user']['photo'])
            user_id = int(os.path.splitext(photo_name)[0])
        except:
            return jsonify({'status': 'error', 'error': 'Неверный формат ID'}), 400
            
        # Ищем пользователя в БД по ID
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'status': 'error', 'error': 'Данные пользователя не найдены'}), 404
            
        return jsonify({
            'status': 'success',
            'user': user.to_dict()
        })
    
    return jsonify({'status': 'error', 'error': 'Неподдерживаемый формат файла'}), 400

def get_user(src_image_path):
    try:
        finding_res = DeepFace.find(
            img_path=src_image_path,
            db_path=DB_FOLDER,
            silent=True,
            # threshold=0.7
        )
        
        if len(finding_res) > 0 and len(finding_res[0]) > 0:
            person = finding_res[0]['identity'][0]
            return {
                'status': 'success',
                'user': {
                    'photo': os.path.basename(person).split('_')[0]
                }
            }
        return None
    except Exception as e:
        app.logger.error(f"Face recognition error: {str(e)}")
        return None

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)