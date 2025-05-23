from flask import Flask, render_template, request, jsonify, send_from_directory
import os
import uuid
from datetime import datetime
from deepface import DeepFace

app = Flask(__name__)

UPLOAD_FOLDER = 'images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
DB_FOLDER = 'photos_db'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DB_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/identify', methods=['POST'])
def identify_user():
    if 'photo' not in request.files:
        return jsonify({
            'status': 'error',
            'error': 'Файл не загружен',
            'message': 'Пожалуйста, попробуйте еще раз'
        }), 400
    
    file = request.files['photo']
    
    if file and allowed_file(file.filename):
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex}.jpg" # возможно не стоит загружать все попытки входа, надо подумать
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        result = get_user(filepath)
        
        if result is None:
            return jsonify({
                'status': 'error',
                'error': 'Пользователь не найден',
                'message': 'Не удалось идентифицировать пользователя в базе данных'
            }), 404
        
        return jsonify(result)
    
    return jsonify({
        'status': 'error',
        'error': 'Неподдерживаемый формат файла',
        'message': 'Пожалуйста, используйте JPEG или PNG'
    }), 400

def get_user(src_image_path):
    db_path = 'photos_db'
    finding_res = DeepFace.find(img_path=src_image_path, 
                                db_path=db_path, 
                                silent=True, 
                                threshold=0.7)
    try:
        info = finding_res[0].iloc[0]
        return {'status': 'success',
                'user': {
                'id': info['hash'],
                'name': info['identity'],
                'position': 'Старший разработчик',
                'department': 'IT',
                'last_seen': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'photo': os.path.basename(src_image_path)
            }}
    except Exception as e:
        return None

@app.route('/images/<filename>')
def serve_image(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)