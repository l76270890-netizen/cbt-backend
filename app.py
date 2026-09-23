from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import secrets
import time
import json

# Optional Cloudinary - won't break if not installed
try:
    import cloudinary
    import cloudinary.uploader
    HAS_CLOUDINARY = True
    if os.environ.get('CLOUDINARY_CLOUD_NAME'):
        cloudinary.config(
            cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
            api_key=os.environ.get('CLOUDINARY_API_KEY'),
            api_secret=os.environ.get('CLOUDINARY_API_SECRET')
        )
except:
    HAS_CLOUDINARY = False

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.environ.get('DATABASE_URL')
if db_path and db_path.startswith("postgres"):
    app.config['SQLALCHEMY_DATABASE_URI'] = db_path.replace("postgres://", "postgresql://")
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, 'examcore.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
AVATAR_FOLDER = os.path.join(UPLOAD_FOLDER, 'avatars')
QUESTION_FOLDER = os.path.join(UPLOAD_FOLDER, 'questions')
os.makedirs(AVATAR_FOLDER, exist_ok=True)
os.makedirs(QUESTION_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'jfif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_to_cloudinary(file, folder):
    if HAS_CLOUDINARY and os.environ.get('CLOUDINARY_CLOUD_NAME'):
        try:
            result = cloudinary.uploader.upload(file, folder=folder)
            return result['secure_url']
        except:
            return None
    return None

def get_image_url(path):
    if not path: return None
    if path.startswith('http'): return path
    return f"/uploads/{path}"

db = SQLAlchemy(app)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    profile_image = db.Column(db.String(1000), nullable=True)

class Exam(db.Model):
    __tablename__ = 'exams'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    examType = db.Column(db.String(80))
    subject = db.Column(db.String(500))
    year = db.Column(db.Integer)
    duration = db.Column(db.Integer)
    totalQuestions = db.Column(db.Integer, default=20)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Question(db.Model):
    __tablename__ = 'questions'
    id = db.Column(db.Integer, primary_key=True)
    examId = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=True)
    examType = db.Column(db.String(80))
    subject = db.Column(db.String(100))
    question = db.Column(db.Text)
    options = db.Column(db.JSON)
    answer = db.Column(db.String(10))
    explanation = db.Column(db.Text)
    year = db.Column(db.Integer, default=2024)
    image_path = db.Column(db.String(1000), nullable=True)

class CBTResult(db.Model):
    __tablename__ = 'results'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    email = db.Column(db.String(120))
    title = db.Column(db.String(200), default="Practice Test")
    score = db.Column(db.Integer)
    total = db.Column(db.Integer)
    duration = db.Column(db.String(20), default="0m")
    status = db.Column(db.String(20), default="Failed")
    mode = db.Column(db.String(20), default="exam")
    examType = db.Column(db.String(80))
    date = db.Column(db.DateTime, default=datetime.utcnow)

def init_db():
    with app.app_context():
        db.create_all()
        print(f"Database ready - Cloudinary: {HAS_CLOUDINARY}")

init_db()

@app.route('/')
def home():
    return jsonify(message="CBT Backend is LIVE", status="ok", cloudinary=HAS_CLOUDINARY)

@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    if not data.get('email') or not data.get('password'):
        return jsonify(success=False, message="Missing fields"), 400
    if User.query.filter_by(email=data['email']).first():
        return jsonify(success=False, message="Email already exists"), 400
    user = User(username=data.get('name') or data.get('username') or data['email'].split('@')[0], email=data['email'], password=generate_password_hash(data['password']))
    db.session.add(user)
    db.session.commit()
    return jsonify(success=True, user_id=user.id, username=user.username, email=user.email)

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(email=data['email']).first()
    if user and check_password_hash(user.password, data['password']):
        return jsonify(success=True, user_id=user.id, username=user.username, email=user.email, profile_image=user.profile_image)
    return jsonify(success=False, message="Invalid email or password"), 401

@app.route('/api/user/upload-avatar/<user_id>', methods=['POST'])
def upload_avatar(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"success": False, "message":"User not found"}),404
    file = request.files.get('avatar')
    if not file or file.filename == '':
        return jsonify({"success": False, "message":"No file"}),400
    if not allowed_file(file.filename):
        return jsonify({"success": False, "message":"Invalid file type"}),400

    # Try Cloudinary first (permanent on Render)
    cloud_url = upload_to_cloudinary(file, folder="examcore/avatars")
    if cloud_url:
        user.profile_image = cloud_url
        db.session.commit()
        return jsonify({"success": True, "profile_image": cloud_url, "url": cloud_url})

    # Fallback local
    try:
        file.seek(0)
    except: pass
    filename = f"avatar_{user_id}_{int(time.time())}_{secure_filename(file.filename)}"
    path = os.path.join(AVATAR_FOLDER, filename)
    file.save(path)
    user.profile_image = f"avatars/{filename}"
    db.session.commit()
    return jsonify({"success": True, "profile_image": user.profile_image, "url": f"/uploads/avatars/{filename}"})

@app.route('/api/update-user/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    data = request.json
    user = User.query.get(user_id)
    if not user:
        return jsonify(message="Not found"), 404
    if data.get('username'):
        user.username = data['username']
    db.session.commit()
    return jsonify(success=True, username=user.username)

@app.route('/api/exams', methods=['GET'])
def get_exams():
    exams = Exam.query.order_by(Exam.created_at.desc()).all()
    return jsonify([{"id": e.id, "title": e.title, "examType": e.examType, "subject": e.subject, "year": e.year, "duration": e.duration, "totalQuestions": e.totalQuestions} for e in exams])

@app.route('/api/questions', methods=['GET'])
def get_questions():
    examType = request.args.get('examType')
    subject = request.args.get('subject')
    subjects = request.args.get('subjects')
    examId = request.args.get('examId')
    q = Question.query
    if examId:
        try: q = q.filter(Question.examId == int(examId))
        except: pass
    if examType:
        q = q.filter(Question.examType.ilike(f"%{examType}%"))
    if subject:
        q = q.filter(Question.subject.ilike(f"%{subject}%"))
    if subjects:
        subs = [s.strip() for s in subjects.split(',') if s.strip()]
        if subs:
            q = q.filter(Question.subject.in_(subs))
    questions = q.all()
    return jsonify([{"id": x.id, "examId": x.examId, "examType": x.examType, "subject": x.subject, "question": x.question, "options": x.options, "answer": x.answer, "explanation": x.explanation, "year": x.year, "image_path": x.image_path, "image_url": get_image_url(x.image_path)} for x in questions])

@app.route('/api/save-result', methods=['POST'])
@app.route('/api/history', methods=['POST'])
def save_history_alias():
    d = request.json
    r = CBTResult(user_id=d.get('user_id'), email=d.get('email'), title=d.get('title', 'Practice Test'), score=d['score'], total=d['total'], duration=d.get('duration', '0m'), status=d.get('status', 'Failed'), mode=d.get('mode', 'exam'), examType=d.get('examType', 'JAMB'))
    db.session.add(r)
    db.session.commit()
    return jsonify(success=True, id=r.id)

@app.route('/api/history/<int:user_id>', methods=['GET'])
def history(user_id):
    res = CBTResult.query.filter_by(user_id=user_id).order_by(CBTResult.date.desc()).all()
    return jsonify([{"id": r.id, "title": r.title, "score": r.score, "total": r.total, "duration": r.duration, "status": r.status, "mode": r.mode, "examType": r.examType, "date": r.date.isoformat(), "email": r.email} for r in res])

@app.route('/api/history/<int:result_id>', methods=['DELETE'])
def delete_history(result_id):
    r = CBTResult.query.get(result_id)
    if r:
        db.session.delete(r)
        db.session.commit()
    return jsonify(success=True)

@app.route('/api/history/clear/<int:user_id>', methods=['DELETE'])
def clear_history(user_id):
    CBTResult.query.filter_by(user_id=user_id).delete()
    db.session.commit()
    return jsonify(success=True)

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    if data['email'] == "Lawrenceifeanyi0001@gmail.com" and data['password'] == "admin123":
        user = User.query.filter_by(email=data['email']).first()
        if not user:
            user = User(username="Admin", email=data['email'], password=generate_password_hash("admin123"))
            db.session.add(user)
            db.session.commit()
        return jsonify(success=True, user_id=user.id, username=user.username, email=user.email, role="admin")
    user = User.query.filter_by(email=data['email']).first()
    if user and check_password_hash(user.password, data['password']):
        return jsonify(success=True, user_id=user.id, username=user.username, email=user.email, role="admin")
    return jsonify(success=False, message="Invalid admin"), 401

@app.route('/api/admin/create-exam', methods=['POST'])
def create_exam():
    d = request.json
    total_q = len(d.get('questions', [])) or 0
    exam = Exam(title=d['title'], examType=d['examType'], subject=",".join(d['subjects']), year=int(d.get('year', 2024)), duration=int(d.get('duration', 60)), totalQuestions=total_q if total_q > 0 else 20)
    db.session.add(exam)
    db.session.commit()
    for q in d.get('questions', []):
        opts = q['options']
        if isinstance(opts, list):
            opts = {"A": opts[0], "B": opts[1], "C": opts[2], "D": opts[3]}
        ques = Question(examId=exam.id, examType=d['examType'], subject=q['subject'], question=q['question'], options=opts, answer=q['correctAnswer'], explanation=q.get('explanation', ''), year=int(d.get('year', 2024)), image_path=q.get('image_path'))
        db.session.add(ques)
    db.session.commit()
    return jsonify(success=True, exam_id=exam.id, message=f"{d['title']} saved")

@app.route('/api/admin/exam/<int:exam_id>', methods=['PUT', 'DELETE'])
def manage_exam(exam_id):
    exam = Exam.query.get(exam_id)
    if not exam:
        return jsonify(message="Not found"), 404
    if request.method == 'DELETE':
        try:
            Question.query.filter_by(examId=exam_id).delete(synchronize_session=False)
            db.session.delete(exam)
            db.session.commit()
            return jsonify(success=True, message="Deleted permanently"), 200
        except Exception as e:
            db.session.rollback()
            return jsonify(message=str(e)), 500
    data = request.json
    if 'title' in data: exam.title=data['title']
    if 'examType' in data: exam.examType=data['examType']
    if 'year' in data: exam.year=int(data['year'])
    if 'duration' in data: exam.duration=int(data['duration'])
    if 'subjects' in data: exam.subject=",".join(data['subjects'])
    db.session.commit()
    return jsonify(success=True)

@app.route('/api/admin/add-question', methods=['POST'])
def add_question():
    if request.content_type and 'multipart/form-data' in request.content_type:
        d = request.form
        file = request.files.get('image')
        image_path = None
        if file and file.filename!= '' and allowed_file(file.filename):
            cloud_url = upload_to_cloudinary(file, folder="examcore/questions")
            if cloud_url:
                image_path = cloud_url
            else:
                try: file.seek(0)
                except: pass
                filename = f"q_{int(time.time())}_{secure_filename(file.filename)}"
                filepath = os.path.join(QUESTION_FOLDER, filename)
                file.save(filepath)
                image_path = f"questions/{filename}"
        exam_id = int(d.get('examId'))
        exam = Exam.query.get(exam_id)
        exam_type = exam.examType if exam else d.get('examType', 'JAMB')
        options_data = d.get('options')
        try:
            options_data = json.loads(options_data) if isinstance(options_data, str) else options_data
        except:
            options_data = {"A": d.get('option_a'), "B": d.get('option_b'), "C": d.get('option_c'), "D": d.get('option_d')}
        q = Question(examId=exam_id, examType=exam_type, subject=d.get('subject'), question=d.get('question'), options=options_data, answer=d.get('correctAnswer'), explanation=d.get('explanation',''), image_path=image_path)
    else:
        d = request.json
        exam = Exam.query.get(int(d['examId']))
        exam_type = exam.examType if exam else d.get('examType', 'JAMB')
        q = Question(examId=int(d['examId']), examType=exam_type, subject=d['subject'], question=d['question'], options=d['options'], answer=d['correctAnswer'], explanation=d.get('explanation', ''), image_path=d.get('image_path'))
    db.session.add(q)
    db.session.commit()
    exam = Exam.query.get(q.examId)
    if exam:
        exam.totalQuestions = Question.query.filter_by(examId=exam.id).count()
        db.session.commit()
    return jsonify(success=True, id=q.id, image_path=q.image_path, image_url=get_image_url(q.image_path))

@app.route('/api/upload/question-image', methods=['POST'])
def upload_question_image():
    file = request.files.get('image')
    if not file or file.filename == '':
        return jsonify(success=False, message="No file"), 400
    if not allowed_file(file.filename):
        return jsonify(success=False, message="Invalid type"), 400

    cloud_url = upload_to_cloudinary(file, folder="examcore/questions")
    if cloud_url:
        return jsonify(success=True, image_path=cloud_url, image_url=cloud_url)

    try: file.seek(0)
    except: pass
    filename = f"q_{int(time.time())}_{secure_filename(file.filename)}"
    filepath = os.path.join(QUESTION_FOLDER, filename)
    file.save(filepath)
    rel_path = f"questions/{filename}"
    return jsonify(success=True, image_path=rel_path, image_url=f"/uploads/{rel_path}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))