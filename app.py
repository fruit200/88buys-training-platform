"""
阿里系供应链直签服务商精英培训会
Flask + SQLite 全栈应用
v2.0 - 公司视觉规范 + 管理员创建账号 + 天数结构 + 新板块
"""

import os
import uuid
import datetime
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, send_from_directory, abort
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# ============================================================
# 应用配置
# ============================================================

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'training-platform-dev-secret-key-2024')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'training.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

for d in ['videos', 'pdfs', 'covers', 'photos', 'homeworks', 'showcases']:
    os.makedirs(os.path.join(UPLOAD_FOLDER, d), exist_ok=True)

ALLOWED_VIDEO_EXT = {'mp4', 'webm', 'mov', 'avi'}
ALLOWED_PDF_EXT = {'pdf'}
ALLOWED_IMAGE_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

db = SQLAlchemy(app)


# ============================================================
# 数据模型
# ============================================================

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(50), default='')
    company = db.Column(db.String(100), default='')
    position = db.Column(db.String(50), default='')
    role = db.Column(db.String(10), default='user')          # user / admin
    password_hash = db.Column(db.String(200), default='')
    is_disabled = db.Column(db.Boolean, default=False)
    group_name = db.Column(db.String(50), default='')        # 所属小组
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    video_progress = db.relationship('UserVideoProgress', backref='user', lazy='dynamic',
                                     cascade='all, delete-orphan')
    views = db.relationship('UserView', backref='user', lazy='dynamic', cascade='all, delete-orphan')


class TrainingPeriod(db.Model):
    __tablename__ = 'training_periods'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    cover_image = db.Column(db.String(255), default='')
    description = db.Column(db.Text, default='')
    total_days = db.Column(db.Integer, default=1)            # 培训天数
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    materials = db.relationship('Material', backref='period', lazy='dynamic',
                                cascade='all, delete-orphan', order_by='Material.sort_order')


class Material(db.Model):
    __tablename__ = 'materials'
    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey('training_periods.id'), nullable=False)
    day_number = db.Column(db.Integer, default=1)            # 第几天 (1, 2, 3...)
    section = db.Column(db.String(20), default='courseware') # courseware/photo/homework/team_showcase
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, default='')
    material_type = db.Column(db.String(10), nullable=False) # video / pdf / image
    file_path = db.Column(db.String(500), default='')
    file_url = db.Column(db.String(500), default='')         # 外部 URL
    group_name = db.Column(db.String(50), default='')        # 小组名称（用于小组风采）
    sort_order = db.Column(db.Integer, default=0)
    view_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    video_progress = db.relationship('UserVideoProgress', backref='material', lazy='dynamic',
                                     cascade='all, delete-orphan')
    views = db.relationship('UserView', backref='material', lazy='dynamic',
                            cascade='all, delete-orphan')


class UserVideoProgress(db.Model):
    __tablename__ = 'user_video_progress'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('materials.id'), nullable=False)
    progress_seconds = db.Column(db.Float, default=0.0)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'material_id', name='uq_user_material_progress'),)


class UserView(db.Model):
    __tablename__ = 'user_views'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('materials.id'), nullable=False)
    first_view_time = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'material_id', name='uq_user_material_view'),)


class LoginLog(db.Model):
    __tablename__ = 'login_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    login_time = db.Column(db.DateTime, default=datetime.datetime.utcnow)


# ============================================================
# 工具函数
# ============================================================

def random_filename(original):
    """生成随机文件名，保留扩展名"""
    ext = original.rsplit('.', 1)[-1].lower() if '.' in original else ''
    return f"{uuid.uuid4().hex}.{ext}"


def allowed_file(filename, allowed_ext):
    return '.' in filename and filename.rsplit('.', 1)[-1].lower() in allowed_ext


# ============================================================
# 认证装饰器
# ============================================================

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
        user = db.session.get(User, session['user_id'])
        if not user or user.is_disabled:
            session.clear()
            flash('账号已被禁用，请联系管理员', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('admin_login'))
        user = db.session.get(User, session['user_id'])
        if not user or user.role != 'admin':
            flash('无管理员权限', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


# ============================================================
# 上下文处理器
# ============================================================

@app.context_processor
def inject_current_user():
    if 'user_id' in session:
        user = db.session.get(User, session['user_id'])
        return dict(current_user=user)
    return dict(current_user=None)


# ============================================================
# 用户端路由
# ============================================================

@app.route('/')
def index():
    """首页 - 展示所有培训期数"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = db.session.get(User, session['user_id'])
    if not user or user.is_disabled:
        session.clear()
        return redirect(url_for('login'))

    search = request.args.get('search', '').strip()
    type_filter = request.args.get('type', '').strip()

    query = TrainingPeriod.query.order_by(TrainingPeriod.sort_order.asc(),
                                          TrainingPeriod.created_at.desc())

    if search:
        query = query.outerjoin(Material).filter(
            db.or_(
                TrainingPeriod.title.contains(search),
                Material.title.contains(search)
            )
        ).distinct()

    periods = query.all()

    period_data = []
    for p in periods:
        mat_query = p.materials.filter_by(section='courseware')
        if type_filter in ('video', 'pdf'):
            mat_query = mat_query.filter_by(material_type=type_filter)
        mat_count = mat_query.count()
        total_count = p.materials.filter_by(section='courseware').count()
        photo_count = p.materials.filter_by(section='photo').count()
        homework_count = p.materials.filter_by(section='homework').count()
        showcase_count = p.materials.filter_by(section='team_showcase').count()
        period_data.append({
            'period': p,
            'material_count': total_count,
            'filtered_count': mat_count,
            'photo_count': photo_count,
            'homework_count': homework_count,
            'showcase_count': showcase_count,
        })

    return render_template('index.html',
                           period_data=period_data,
                           search=search,
                           type_filter=type_filter)


@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录页 - 管理员创建的账号登录"""
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '').strip()

        if not phone:
            flash('请输入手机号', 'error')
            return render_template('login.html')

        if not password:
            flash('请输入密码', 'error')
            return render_template('login.html')

        user = User.query.filter_by(phone=phone).first()

        if not user or not user.password_hash or not check_password_hash(user.password_hash, password):
            flash('手机号或密码错误，请联系管理员开通账号', 'error')
            return render_template('login.html')

        if user.is_disabled:
            flash('您的账号已被禁用，请联系管理员', 'error')
            return render_template('login.html')

        session['user_id'] = user.id
        session['user_role'] = user.role

        log = LoginLog(user_id=user.id, login_time=datetime.datetime.utcnow())
        db.session.add(log)
        db.session.commit()

        flash(f'欢迎回来，{user.name or user.phone}！', 'success')
        if user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('index'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('已安全退出', 'success')
    return redirect(url_for('login'))


@app.route('/period/<int:period_id>')
@login_required
def period_detail(period_id):
    """期数详情页 - 天数导航 + 板块切换 + 资料列表 + 播放/预览"""
    period = db.session.get(TrainingPeriod, period_id)
    if not period:
        abort(404)

    # 当前天数
    current_day = request.args.get('day', 1, type=int)
    if current_day < 1:
        current_day = 1
    if current_day > (period.total_days or 1):
        current_day = period.total_days or 1

    # 当前板块
    current_section = request.args.get('section', 'courseware').strip()
    valid_sections = ('courseware', 'photo', 'homework', 'team_showcase')
    if current_section not in valid_sections:
        current_section = 'courseware'

    # 获取当前天数+板块的资料
    materials = Material.query.filter_by(
        period_id=period_id,
        day_number=current_day,
        section=current_section
    ).order_by(Material.sort_order.asc()).all()

    mid = request.args.get('mid', type=int)
    active_material = None
    if mid:
        active_material = db.session.get(Material, mid)
    elif materials:
        active_material = materials[0]

    # 获取当前用户对当前视频的播放进度
    progress = 0
    if active_material and active_material.material_type == 'video':
        vp = UserVideoProgress.query.filter_by(
            user_id=session['user_id'],
            material_id=active_material.id
        ).first()
        if vp:
            progress = vp.progress_seconds

    # 各板块资料数统计（当天）
    section_counts = {}
    for sec in valid_sections:
        section_counts[sec] = Material.query.filter_by(
            period_id=period_id, day_number=current_day, section=sec
        ).count()

    return render_template('period_detail.html',
                           period=period,
                           materials=materials,
                           active=active_material,
                           progress=progress,
                           current_day=current_day,
                           current_section=current_section,
                           section_counts=section_counts)


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """个人中心"""
    user = db.session.get(User, session['user_id'])

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        company = request.form.get('company', '').strip()
        position = request.form.get('position', '').strip()

        if not name:
            flash('姓名不能为空', 'error')
        else:
            user.name = name
            user.company = company
            user.position = position
            db.session.commit()
            flash('个人信息已更新', 'success')

    views = (UserView.query
             .filter_by(user_id=user.id)
             .join(Material)
             .order_by(UserView.first_view_time.desc())
             .all())

    return render_template('profile.html', user=user, views=views)


# ============================================================
# API 路由
# ============================================================

@app.route('/api/progress/save', methods=['POST'])
@login_required
def save_progress():
    data = request.get_json()
    material_id = data.get('material_id')
    progress = data.get('progress', 0)

    if not material_id:
        return jsonify({'ok': False, 'error': 'missing material_id'}), 400

    vp = UserVideoProgress.query.filter_by(
        user_id=session['user_id'],
        material_id=material_id
    ).first()

    if vp:
        vp.progress_seconds = progress
    else:
        vp = UserVideoProgress(
            user_id=session['user_id'],
            material_id=material_id,
            progress_seconds=progress
        )
        db.session.add(vp)

    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/progress/load/<int:material_id>')
@login_required
def load_progress(material_id):
    vp = UserVideoProgress.query.filter_by(
        user_id=session['user_id'],
        material_id=material_id
    ).first()
    return jsonify({'progress': vp.progress_seconds if vp else 0})


@app.route('/api/material/<int:material_id>/view', methods=['POST'])
@login_required
def record_view(material_id):
    material = db.session.get(Material, material_id)
    if not material:
        return jsonify({'ok': False}), 404

    existing = UserView.query.filter_by(
        user_id=session['user_id'],
        material_id=material_id
    ).first()

    if not existing:
        view = UserView(
            user_id=session['user_id'],
            material_id=material_id,
            first_view_time=datetime.datetime.utcnow()
        )
        db.session.add(view)
        material.view_count = (material.view_count or 0) + 1
        db.session.commit()

    return jsonify({'ok': True, 'view_count': material.view_count})


@app.route('/api/material/<int:material_id>/view_count')
def get_view_count(material_id):
    material = db.session.get(Material, material_id)
    if not material:
        return jsonify({'view_count': 0})
    return jsonify({'view_count': material.view_count or 0})


# ============================================================
# 文件服务
# ============================================================

@app.route('/serve/video/<filename>')
def serve_video(filename):
    return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'videos'), filename)


@app.route('/serve/pdf/<filename>')
def serve_pdf(filename):
    return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'pdfs'), filename)


@app.route('/serve/cover/<filename>')
def serve_cover(filename):
    return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'covers'), filename)


@app.route('/serve/photo/<filename>')
def serve_photo(filename):
    return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'photos'), filename)


@app.route('/serve/homework/<filename>')
def serve_homework(filename):
    return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'homeworks'), filename)


@app.route('/serve/showcase/<filename>')
def serve_showcase(filename):
    return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'showcases'), filename)


# ============================================================
# 管理员路由
# ============================================================

@app.route('/admin')
def admin_index():
    if 'user_id' in session:
        user = db.session.get(User, session['user_id'])
        if user and user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
    return redirect(url_for('admin_login'))


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        user = User.query.filter_by(phone=username, role='admin').first()
        if not user:
            user = User.query.filter_by(name=username, role='admin').first()

        if user and user.password_hash and check_password_hash(user.password_hash, password):
            if user.is_disabled:
                flash('账号已被禁用', 'error')
            else:
                session['user_id'] = user.id
                session['user_role'] = user.role
                log = LoginLog(user_id=user.id, login_time=datetime.datetime.utcnow())
                db.session.add(log)
                db.session.commit()
                return redirect(url_for('admin_dashboard'))
        else:
            flash('用户名或密码错误', 'error')

    return render_template('admin/login.html')


@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    total_users = User.query.filter(User.role != 'admin').count()
    total_periods = TrainingPeriod.query.count()
    total_materials = Material.query.count()
    total_views = db.session.query(db.func.sum(Material.view_count)).scalar() or 0

    return render_template('admin/dashboard.html',
                           total_users=total_users,
                           total_periods=total_periods,
                           total_materials=total_materials,
                           total_views=total_views)


@app.route('/admin/api/dashboard_data')
@admin_required
def admin_dashboard_data():
    top_materials = (Material.query
                     .order_by(Material.view_count.desc())
                     .limit(10).all())
    chart_materials = [{'name': m.title, 'count': m.view_count or 0} for m in top_materials]

    today = datetime.date.today()
    daily_logins = []
    for i in range(6, -1, -1):
        day = today - datetime.timedelta(days=i)
        next_day = day + datetime.timedelta(days=1)
        count = (db.session.query(db.func.count(db.func.distinct(LoginLog.user_id)))
                 .filter(LoginLog.login_time >= datetime.datetime.combine(day, datetime.time.min),
                         LoginLog.login_time < datetime.datetime.combine(next_day, datetime.time.min))
                 .scalar() or 0)
        daily_logins.append({'date': day.strftime('%m-%d'), 'count': count})

    return jsonify({
        'materials': chart_materials,
        'daily_logins': daily_logins,
    })


# ---------- 期数管理 ----------

@app.route('/admin/periods')
@admin_required
def admin_periods():
    periods = TrainingPeriod.query.order_by(TrainingPeriod.sort_order.asc()).all()
    return render_template('admin/periods.html', periods=periods)


@app.route('/admin/periods/new', methods=['GET', 'POST'])
@admin_required
def admin_period_new():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        total_days = request.form.get('total_days', 1, type=int)
        sort_order = request.form.get('sort_order', 0, type=int)

        if not title:
            flash('标题不能为空', 'error')
            return render_template('admin/period_edit.html', period=None)

        period = TrainingPeriod(
            title=title,
            description=description,
            total_days=max(1, total_days),
            sort_order=sort_order
        )

        cover = request.files.get('cover_image')
        if cover and cover.filename and allowed_file(cover.filename, ALLOWED_IMAGE_EXT):
            fname = random_filename(cover.filename)
            cover.save(os.path.join(UPLOAD_FOLDER, 'covers', fname))
            period.cover_image = fname

        db.session.add(period)
        db.session.commit()
        flash('期数创建成功', 'success')
        return redirect(url_for('admin_periods'))

    return render_template('admin/period_edit.html', period=None)


@app.route('/admin/periods/<int:period_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_period_edit(period_id):
    period = db.session.get(TrainingPeriod, period_id)
    if not period:
        abort(404)

    if request.method == 'POST':
        period.title = request.form.get('title', '').strip() or period.title
        period.description = request.form.get('description', '').strip()
        period.total_days = max(1, request.form.get('total_days', 1, type=int))
        period.sort_order = request.form.get('sort_order', 0, type=int)

        cover = request.files.get('cover_image')
        if cover and cover.filename and allowed_file(cover.filename, ALLOWED_IMAGE_EXT):
            fname = random_filename(cover.filename)
            cover.save(os.path.join(UPLOAD_FOLDER, 'covers', fname))
            period.cover_image = fname

        db.session.commit()
        flash('期数已更新', 'success')
        return redirect(url_for('admin_periods'))

    return render_template('admin/period_edit.html', period=period)


@app.route('/admin/periods/<int:period_id>/delete', methods=['POST'])
@admin_required
def admin_period_delete(period_id):
    period = db.session.get(TrainingPeriod, period_id)
    if period:
        db.session.delete(period)
        db.session.commit()
        flash('期数已删除', 'success')
    return redirect(url_for('admin_periods'))


# ---------- 资料管理 ----------

@app.route('/admin/periods/<int:period_id>/materials')
@admin_required
def admin_materials(period_id):
    period = db.session.get(TrainingPeriod, period_id)
    if not period:
        abort(404)
    materials = period.materials.order_by(Material.day_number.asc(),
                                          Material.section.asc(),
                                          Material.sort_order.asc()).all()
    return render_template('admin/materials.html', period=period, materials=materials)


@app.route('/admin/periods/<int:period_id>/materials/upload', methods=['POST'])
@admin_required
def admin_material_upload(period_id):
    period = db.session.get(TrainingPeriod, period_id)
    if not period:
        abort(404)

    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    material_type = request.form.get('material_type', '').strip()
    day_number = request.form.get('day_number', 1, type=int)
    section = request.form.get('section', 'courseware').strip()
    group_name = request.form.get('group_name', '').strip()
    sort_order = request.form.get('sort_order', 0, type=int)
    file_url = request.form.get('file_url', '').strip()

    if not title:
        flash('标题不能为空', 'error')
        return redirect(url_for('admin_materials', period_id=period_id))

    # image 类型用于照片墙和小组风采
    if section in ('photo', 'team_showcase'):
        material_type = 'image'

    material = Material(
        period_id=period_id,
        day_number=max(1, day_number),
        section=section,
        title=title,
        description=description,
        material_type=material_type,
        group_name=group_name,
        sort_order=sort_order,
        file_url=file_url,
    )

    file = request.files.get('file')
    if file and file.filename:
        if material_type == 'video' and allowed_file(file.filename, ALLOWED_VIDEO_EXT):
            fname = random_filename(file.filename)
            file.save(os.path.join(UPLOAD_FOLDER, 'videos', fname))
            material.file_path = fname
        elif material_type == 'pdf' and allowed_file(file.filename, ALLOWED_PDF_EXT):
            fname = random_filename(file.filename)
            file.save(os.path.join(UPLOAD_FOLDER, 'pdfs', fname))
            material.file_path = fname
        elif material_type == 'image' and allowed_file(file.filename, ALLOWED_IMAGE_EXT):
            sub = 'photos' if section == 'photo' else 'showcases'
            fname = random_filename(file.filename)
            file.save(os.path.join(UPLOAD_FOLDER, sub, fname))
            material.file_path = fname
        else:
            flash('文件类型不支持', 'error')
            return redirect(url_for('admin_materials', period_id=period_id))

    db.session.add(material)
    db.session.commit()
    flash('资料上传成功', 'success')
    return redirect(url_for('admin_materials', period_id=period_id))


@app.route('/admin/periods/<int:period_id>/materials/batch_upload', methods=['POST'])
@admin_required
def admin_material_batch_upload(period_id):
    """批量上传资料 - 照片墙/小组风采免描述，课件/作业需标题描述"""
    period = db.session.get(TrainingPeriod, period_id)
    if not period:
        abort(404)

    section = request.form.get('section', 'photo').strip()
    day_number = request.form.get('day_number', 1, type=int)
    group_name = request.form.get('group_name', '').strip()
    base_sort = request.form.get('sort_order', 0, type=int)
    shared_title = request.form.get('shared_title', '').strip()
    shared_desc = request.form.get('shared_description', '').strip()

    files = request.files.getlist('files')
    if not files or all(not f.filename for f in files):
        flash('请选择至少一个文件', 'error')
        return redirect(url_for('admin_materials', period_id=period_id))

    # 照片墙/小组风采 → image; 课件/作业 → 根据文件扩展名自动判断
    if section in ('photo', 'team_showcase'):
        material_type = 'image'
    else:
        material_type = None  # auto-detect per file

    count = 0
    for i, file in enumerate(files):
        if not file or not file.filename:
            continue

        fname = secure_filename(file.filename)
        if not fname:
            continue

        # 自动判断类型
        if material_type is None:
            ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
            if ext in ALLOWED_VIDEO_EXT:
                mt = 'video'
            elif ext in ALLOWED_PDF_EXT:
                mt = 'pdf'
            elif ext in ALLOWED_IMAGE_EXT:
                mt = 'image'
            else:
                continue
        else:
            mt = material_type
            ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
            # 验证文件类型
            if mt == 'image' and ext not in ALLOWED_IMAGE_EXT:
                continue
            if mt == 'video' and ext not in ALLOWED_VIDEO_EXT:
                continue
            if mt == 'pdf' and ext not in ALLOWED_PDF_EXT:
                continue

        # 照片/小组风采：文件名去扩展名作为标题，无需描述
        if section in ('photo', 'team_showcase'):
            title = os.path.splitext(fname)[0].replace('_', ' ').replace('-', ' ')
            if len(title) > 50:
                title = title[:50]
            description = ''
        else:
            # 课件/作业：如果有共享标题则用共享标题+序号，否则用文件名
            if shared_title:
                title = f"{shared_title} ({i+1})" if len(files) > 1 else shared_title
            else:
                title = os.path.splitext(fname)[0].replace('_', ' ').replace('-', ' ')
            description = shared_desc

        new_filename = random_filename(fname)
        sub_dir_map = {'video': 'videos', 'pdf': 'pdfs', 'image': 'photos' if section == 'photo' else 'showcases'}
        sub_dir = sub_dir_map.get(mt, 'videos')

        # image 类型根据 section 选择子目录
        if mt == 'image':
            sub_dir = 'photos' if section == 'photo' else 'showcases'

        file.save(os.path.join(UPLOAD_FOLDER, sub_dir, new_filename))

        material = Material(
            period_id=period_id,
            day_number=max(1, day_number),
            section=section,
            title=title,
            description=description,
            material_type=mt,
            group_name=group_name,
            sort_order=base_sort + i,
            file_path=new_filename,
        )
        db.session.add(material)
        count += 1

    db.session.commit()
    flash(f'批量上传成功，共添加 {count} 份资料', 'success')
    return redirect(url_for('admin_materials', period_id=period_id))


@app.route('/admin/materials/<int:material_id>/edit', methods=['POST'])
@admin_required
def admin_material_edit(material_id):
    material = db.session.get(Material, material_id)
    if not material:
        abort(404)

    material.title = request.form.get('title', '').strip() or material.title
    material.description = request.form.get('description', '').strip()
    material.day_number = max(1, request.form.get('day_number', 1, type=int))
    material.section = request.form.get('section', 'courseware').strip()
    material.group_name = request.form.get('group_name', '').strip()
    material.sort_order = request.form.get('sort_order', 0, type=int)
    material.file_url = request.form.get('file_url', '').strip()
    db.session.commit()
    flash('资料已更新', 'success')
    return redirect(url_for('admin_materials', period_id=material.period_id))


@app.route('/admin/materials/<int:material_id>/delete', methods=['POST'])
@admin_required
def admin_material_delete(material_id):
    material = db.session.get(Material, material_id)
    if material:
        period_id = material.period_id
        if material.file_path:
            sub_map = {'video': 'videos', 'pdf': 'pdfs', 'image': 'photos'}
            sub = sub_map.get(material.material_type, 'videos')
            fpath = os.path.join(UPLOAD_FOLDER, sub, material.file_path)
            if os.path.exists(fpath):
                os.remove(fpath)
        db.session.delete(material)
        db.session.commit()
        flash('资料已删除', 'success')
        return redirect(url_for('admin_materials', period_id=period_id))
    abort(404)


# ---------- 用户管理（管理员创建账号） ----------

@app.route('/admin/users')
@admin_required
def admin_users():
    users = User.query.filter(User.role != 'admin').order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)


@app.route('/admin/users/create', methods=['POST'])
@admin_required
def admin_user_create():
    phone = request.form.get('phone', '').strip()
    name = request.form.get('name', '').strip()
    password = request.form.get('password', '').strip()
    company = request.form.get('company', '').strip()
    position = request.form.get('position', '').strip()
    group_name = request.form.get('group_name', '').strip()

    if not phone:
        flash('手机号不能为空', 'error')
        return redirect(url_for('admin_users'))

    if not password or len(password) < 4:
        flash('密码至少4位', 'error')
        return redirect(url_for('admin_users'))

    existing = User.query.filter_by(phone=phone).first()
    if existing:
        flash(f'手机号 {phone} 已被注册', 'error')
        return redirect(url_for('admin_users'))

    user = User(
        phone=phone,
        name=name,
        password_hash=generate_password_hash(password),
        company=company,
        position=position,
        group_name=group_name,
        role='user',
    )
    db.session.add(user)
    db.session.commit()
    flash(f'用户 {name or phone} 创建成功，密码: {password}', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/<int:user_id>/toggle', methods=['POST'])
@admin_required
def admin_user_toggle(user_id):
    user = db.session.get(User, user_id)
    if user and user.role != 'admin':
        user.is_disabled = not user.is_disabled
        db.session.commit()
        status = '已禁用' if user.is_disabled else '已启用'
        flash(f'用户 {user.name} {status}', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/<int:user_id>/reset_password', methods=['POST'])
@admin_required
def admin_user_reset_password(user_id):
    user = db.session.get(User, user_id)
    if user and user.role != 'admin':
        new_password = request.form.get('new_password', '').strip()
        if not new_password or len(new_password) < 4:
            flash('密码至少4位', 'error')
        else:
            user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            flash(f'用户 {user.name} 密码已重置为: {new_password}', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def admin_user_delete(user_id):
    user = db.session.get(User, user_id)
    if user and user.role != 'admin':
        db.session.delete(user)
        db.session.commit()
        flash(f'用户 {user.name} 已删除', 'success')
    return redirect(url_for('admin_users'))


# ============================================================
# 数据库初始化 & 示例数据
# ============================================================

def init_db():
    """创建数据表并插入示例数据"""
    with app.app_context():
        db.create_all()

        # 创建管理员账号
        admin = User.query.filter_by(role='admin').first()
        if not admin:
            admin = User(
                phone='admin',
                name='admin',
                role='admin',
                password_hash=generate_password_hash('admin123'),
                company='平台运营中心',
                position='系统管理员',
            )
            db.session.add(admin)

        # 创建示例用户
        demo_user = User.query.filter_by(phone='13800001111').first()
        if not demo_user:
            demo_user = User(
                phone='13800001111',
                name='张三',
                password_hash=generate_password_hash('123456'),
                company='杭州供应链有限公司',
                position='运营经理',
                group_name='第一组',
            )
            db.session.add(demo_user)

        demo_user2 = User.query.filter_by(phone='13800002222').first()
        if not demo_user2:
            demo_user2 = User(
                phone='13800002222',
                name='李四',
                password_hash=generate_password_hash('123456'),
                company='深圳物流科技公司',
                position='采购主管',
                group_name='第二组',
            )
            db.session.add(demo_user2)

        # 创建示例数据
        if TrainingPeriod.query.count() == 0:
            period = TrainingPeriod(
                title='第1期 - 供应链数字化转型实战',
                description=(
                    '本期培训聚焦供应链数字化转型的核心方法论，涵盖从传统供应链到智慧供应链的升级路径、'
                    '数字化采购与物流协同、以及 AI 驱动的库存优化策略。为期2天的集中培训。'
                ),
                cover_image='',
                total_days=2,
                sort_order=1,
            )
            db.session.add(period)
            db.session.flush()

            # === 第1天 培训课件 ===
            video1 = Material(
                period_id=period.id,
                day_number=1,
                section='courseware',
                title='供应链数字化概述与趋势分析',
                description='本课程从宏观视角解读供应链数字化转型的时代背景，深入分析全球供应链格局变化。',
                material_type='video',
                file_url='https://www.w3schools.com/html/mov_bbb.mp4',
                sort_order=1,
            )
            db.session.add(video1)

            video2 = Material(
                period_id=period.id,
                day_number=1,
                section='courseware',
                title='AI 驱动的智慧库存管理实操',
                description='聚焦库存管理的数字化升级实战，讲解如何利用 AI 算法实现需求预测和智能补货。',
                material_type='video',
                file_url='https://www.w3schools.com/html/movie.mp4',
                sort_order=2,
            )
            db.session.add(video2)

            # === 第1天 照片 ===
            photo1 = Material(
                period_id=period.id,
                day_number=1,
                section='photo',
                title='开班合影',
                description='第1天开班仪式全体合影',
                material_type='image',
                file_url='',
                sort_order=1,
            )
            db.session.add(photo1)

            # === 第1天 作业存档 ===
            hw1 = Material(
                period_id=period.id,
                day_number=1,
                section='homework',
                title='第一天课后作业 - 供应链诊断报告',
                description='请根据今天所学内容，完成一份企业供应链现状诊断报告。',
                material_type='pdf',
                file_url='https://mozilla.github.io/pdf.js/web/compressed.tracemonkey-pldi-09.pdf',
                sort_order=1,
            )
            db.session.add(hw1)

            # === 第2天 培训课件 ===
            pdf2 = Material(
                period_id=period.id,
                day_number=2,
                section='courseware',
                title='数字化供应链管理白皮书（2024版）',
                description='行业专家编写的供应链管理数字化白皮书，涵盖转型路径规划和技术选型建议。',
                material_type='pdf',
                file_url='https://mozilla.github.io/pdf.js/web/compressed.tracemonkey-pldi-09.pdf',
                sort_order=1,
            )
            db.session.add(pdf2)

            # === 第2天 小组风采 ===
            showcase1 = Material(
                period_id=period.id,
                day_number=2,
                section='team_showcase',
                title='第一组 - 数字化方案展示',
                description='第一组在结业汇报中展示的企业数字化供应链转型方案。',
                material_type='image',
                group_name='第一组',
                file_url='',
                sort_order=1,
            )
            db.session.add(showcase1)

            showcase2 = Material(
                period_id=period.id,
                day_number=2,
                section='team_showcase',
                title='第二组 - 智慧仓储项目路演',
                description='第二组展示的智慧仓储数字化升级项目方案与落地计划。',
                material_type='image',
                group_name='第二组',
                file_url='',
                sort_order=2,
            )
            db.session.add(showcase2)

        db.session.commit()
        print('[OK] 数据库初始化完成，已创建示例数据')


# ============================================================
# 启动入口
# ============================================================

if __name__ == '__main__':
    import sys
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    init_db()
    print('=' * 60)
    print('  阿里系供应链直签服务商精英培训会 v2.0')
    print('  用户端: http://127.0.0.1:5000')
    print('  管理端: http://127.0.0.1:5000/admin')
    print('  管理员: admin / admin123')
    print('  用户1: 13800001111 / 123456 (张三)')
    print('  用户2: 13800002222 / 123456 (李四)')
    print('=' * 60)
    app.run(host='0.0.0.0', port=5000, debug=True)
