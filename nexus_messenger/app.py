from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'nexus-messenger-secret-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///nexus.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# ==================== МОДЕЛИ БАЗЫ ДАННЫХ ====================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_online = db.Column(db.Boolean, default=False)
    current_voice_channel = db.Column(db.Integer, db.ForeignKey('voice_channel.id'), nullable=True)
    
    # Связи
    memberships = db.relationship('ServerMember', backref='user', lazy=True, cascade='all, delete-orphan')
    messages_sent = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy=True)
    private_messages_sent = db.relationship('PrivateMessage', foreign_keys='PrivateMessage.sender_id', backref='sender', lazy=True)
    private_messages_received = db.relationship('PrivateMessage', foreign_keys='PrivateMessage.recipient_id', backref='recipient', lazy=True)

class Server(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    icon_color = db.Column(db.String(20), default='#5865F2')
    
    # Связи
    members = db.relationship('ServerMember', backref='server', lazy=True, cascade='all, delete-orphan')
    text_channels = db.relationship('TextChannel', backref='server', lazy=True, cascade='all, delete-orphan')
    voice_channels = db.relationship('VoiceChannel', backref='server', lazy=True, cascade='all, delete-orphan')

class ServerMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    role = db.Column(db.String(50), default='member')  # admin, moderator, member
    
    __table_args__ = (db.UniqueConstraint('user_id', 'server_id', name='unique_membership'),)

class TextChannel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Связи
    messages = db.relationship('Message', backref='channel', lazy=True, cascade='all, delete-orphan')

class VoiceChannel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    max_users = db.Column(db.Integer, default=10)
    
    # Связи
    users = db.relationship('User', backref='voice_channel', lazy=True)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    channel_id = db.Column(db.Integer, db.ForeignKey('text_channel.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    edited = db.Column(db.Boolean, default=False)

class PrivateMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def init_db():
    with app.app_context():
        db.create_all()
        
        # Создаем демо-сервера если их нет
        if Server.query.count() == 0:
            # Создаем админа если нет
            admin = User.query.filter_by(username='NexusAdmin').first()
            if not admin:
                admin = User(
                    username='NexusAdmin',
                    password_hash=generate_password_hash('admin123'),
                    is_online=True
                )
                db.session.add(admin)
                db.session.commit()
            
            servers_data = [
                ('🌟 Welcome Hub', '#5865F2'),
                ('🎮 Gaming Zone', '#EB459E'),
                ('💻 Tech Talk', '#00A8FC'),
                ('🎵 Music Lounge', '#FEE75C'),
                ('🚀 Startup Ideas', '#00FF88')
            ]
            
            for server_name, color in servers_data:
                server = Server(name=server_name, created_by=admin.id, icon_color=color)
                db.session.add(server)
                db.session.commit()
                
                # Добавляем админа в участники
                membership = ServerMember(user_id=admin.id, server_id=server.id, role='admin')
                db.session.add(membership)
                
                # Создаем каналы
                text_channels = ['general', 'off-topic', 'announcements']
                voice_channels = ['General Voice', 'Gaming', 'Music']
                
                for tc_name in text_channels:
                    channel = TextChannel(name=tc_name, server_id=server.id)
                    db.session.add(channel)
                
                for vc_name in voice_channels:
                    channel = VoiceChannel(name=vc_name, server_id=server.id)
                    db.session.add(channel)
                
                db.session.commit()

# ==================== РОУТЫ АВТОРИЗАЦИИ ====================

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('app_page'))
    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({'error': 'Логин и пароль обязательны'}), 400
    
    if len(username) < 3:
        return jsonify({'error': 'Логин должен быть не менее 3 символов'}), 400
    
    if len(password) < 6:
        return jsonify({'error': 'Пароль должен быть не менее 6 символов'}), 400
    
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Пользователь с таким логином уже существует'}), 400
    
    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        is_online=True
    )
    db.session.add(user)
    db.session.commit()
    
    # Автоматически добавляем пользователя во все сервера
    servers = Server.query.all()
    for server in servers:
        membership = ServerMember(user_id=user.id, server_id=server.id)
        db.session.add(membership)
    db.session.commit()
    
    session['user_id'] = user.id
    socketio.emit('user_online', {'user_id': user.id, 'username': username})
    
    return jsonify({'success': True, 'user_id': user.id, 'username': username})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    user = User.query.filter_by(username=username).first()
    
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Неверный логин или пароль'}), 401
    
    session['user_id'] = user.id
    user.is_online = True
    db.session.commit()
    
    socketio.emit('user_online', {'user_id': user.id, 'username': user.username})
    
    return jsonify({'success': True, 'user_id': user.id, 'username': user.username})

@app.route('/logout', methods=['POST'])
def logout():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            user.is_online = False
            user.current_voice_channel = None
            db.session.commit()
            socketio.emit('user_offline', {'user_id': user.id})
    
    session.pop('user_id', None)
    return jsonify({'success': True})

@app.route('/app')
def app_page():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return render_template('app.html')

# ==================== API РОУТЫ ====================

@app.route('/api/user')
def get_current_user():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user = User.query.get(session['user_id'])
    return jsonify({
        'id': user.id,
        'username': user.username,
        'is_online': user.is_online
    })

@app.route('/api/users')
def get_all_users():
    users = User.query.all()
    return jsonify([{
        'id': u.id,
        'username': u.username,
        'is_online': u.is_online
    } for u in users])

@app.route('/api/servers')
def get_all_servers():
    servers = Server.query.all()
    result = []
    for server in servers:
        result.append({
            'id': server.id,
            'name': server.name,
            'icon_color': server.icon_color,
            'text_channels': [{'id': ch.id, 'name': ch.name} for ch in server.text_channels],
            'voice_channels': [{'id': ch.id, 'name': ch.name} for ch in server.voice_channels]
        })
    return jsonify(result)

@app.route('/api/server/<int:server_id>')
def get_server(server_id):
    server = Server.query.get_or_404(server_id)
    members = ServerMember.query.filter_by(server_id=server_id).all()
    member_ids = [m.user_id for m in members]
    
    return jsonify({
        'id': server.id,
        'name': server.name,
        'icon_color': server.icon_color,
        'text_channels': [{'id': ch.id, 'name': ch.name} for ch in server.text_channels],
        'voice_channels': [{'id': ch.id, 'name': ch.name, 'users': [
            {'id': u.id, 'username': u.username} 
            for u in User.query.filter_by(current_voice_channel=ch.id).all()
        ]} for ch in server.voice_channels],
        'members': [{
            'id': u.id,
            'username': u.username,
            'is_online': u.is_online,
            'role': m.role
        } for m in members for u in [User.query.get(m.user_id)] if u]
    })

@app.route('/api/messages/channel/<int:channel_id>')
def get_channel_messages(channel_id):
    messages = Message.query.filter_by(channel_id=channel_id).order_by(Message.created_at.asc()).limit(50).all()
    return jsonify([{
        'id': m.id,
        'content': m.content,
        'sender_id': m.sender_id,
        'sender_username': User.query.get(m.sender_id).username if m.sender_id else 'Unknown',
        'created_at': m.created_at.isoformat(),
        'edited': m.edited
    } for m in messages])

@app.route('/api/messages/private/<int:other_user_id>')
def get_private_messages(other_user_id):
    current_user_id = session.get('user_id')
    if not current_user_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    messages = PrivateMessage.query.filter(
        ((PrivateMessage.sender_id == current_user_id) & (PrivateMessage.recipient_id == other_user_id)) |
        ((PrivateMessage.sender_id == other_user_id) & (PrivateMessage.recipient_id == current_user_id))
    ).order_by(PrivateMessage.created_at.asc()).limit(50).all()
    
    # Помечаем как прочитанные
    for msg in messages:
        if msg.recipient_id == current_user_id and not msg.read:
            msg.read = True
    db.session.commit()
    
    return jsonify([{
        'id': m.id,
        'content': m.content,
        'sender_id': m.sender_id,
        'recipient_id': m.recipient_id,
        'created_at': m.created_at.isoformat(),
        'read': m.read
    } for m in messages])

@app.route('/api/text-channel', methods=['POST'])
def create_text_channel():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.json
    server_id = data.get('server_id')
    name = data.get('name', '').strip()
    
    if not server_id or not name:
        return jsonify({'error': 'server_id и name обязательны'}), 400
    
    # Проверяем членство
    membership = ServerMember.query.filter_by(user_id=session['user_id'], server_id=server_id).first()
    if not membership or membership.role not in ['admin', 'moderator']:
        return jsonify({'error': 'Недостаточно прав'}), 403
    
    channel = TextChannel(name=name, server_id=server_id)
    db.session.add(channel)
    db.session.commit()
    
    socketio.emit('channel_created', {
        'server_id': server_id,
        'channel': {'id': channel.id, 'name': channel.name, 'type': 'text'}
    }, room=f'server_{server_id}')
    
    return jsonify({'success': True, 'channel': {'id': channel.id, 'name': channel.name}})

@app.route('/api/voice-channel', methods=['POST'])
def create_voice_channel():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.json
    server_id = data.get('server_id')
    name = data.get('name', '').strip()
    max_users = data.get('max_users', 10)
    
    if not server_id or not name:
        return jsonify({'error': 'server_id и name обязательны'}), 400
    
    # Проверяем членство
    membership = ServerMember.query.filter_by(user_id=session['user_id'], server_id=server_id).first()
    if not membership or membership.role not in ['admin', 'moderator']:
        return jsonify({'error': 'Недостаточно прав'}), 403
    
    channel = VoiceChannel(name=name, server_id=server_id, max_users=max_users)
    db.session.add(channel)
    db.session.commit()
    
    socketio.emit('channel_created', {
        'server_id': server_id,
        'channel': {'id': channel.id, 'name': channel.name, 'type': 'voice'}
    }, room=f'server_{server_id}')
    
    return jsonify({'success': True, 'channel': {'id': channel.id, 'name': channel.name}})

@app.route('/api/server', methods=['POST'])
def create_server():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.json
    name = data.get('name', '').strip()
    icon_color = data.get('icon_color', '#5865F2')
    
    if not name:
        return jsonify({'error': 'Название сервера обязательно'}), 400
    
    server = Server(name=name, created_by=session['user_id'], icon_color=icon_color)
    db.session.add(server)
    db.session.commit()
    
    # Создаем дефолтные каналы
    general_text = TextChannel(name='general', server_id=server.id)
    general_voice = VoiceChannel(name='General Voice', server_id=server.id)
    db.session.add_all([general_text, general_voice])
    
    # Добавляем создателя как админа
    membership = ServerMember(user_id=session['user_id'], server_id=server.id, role='admin')
    db.session.add(membership)
    db.session.commit()
    
    # Все пользователи автоматически добавляются на сервер
    all_users = User.query.all()
    for user in all_users:
        if user.id != session['user_id']:
            member = ServerMember(user_id=user.id, server_id=server.id)
            db.session.add(member)
    db.session.commit()
    
    socketio.emit('server_created', {
        'id': server.id,
        'name': server.name,
        'icon_color': icon_color
    })
    
    return jsonify({'success': True, 'server': {'id': server.id, 'name': server.name, 'icon_color': icon_color}})

# ==================== SOCKET.IO СОБЫТИЯ ====================

@socketio.on('connect')
def handle_connect():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            user.is_online = True
            db.session.commit()
            emit('user_online', {'user_id': user.id, 'username': user.username})

@socketio.on('disconnect')
def handle_disconnect():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            user.is_online = False
            if user.current_voice_channel:
                ch_id = user.current_voice_channel
                user.current_voice_channel = None
                db.session.commit()
                emit('user_left_voice', {
                    'user_id': user.id,
                    'username': user.username,
                    'channel_id': ch_id
                }, room=f'voice_{ch_id}')
            db.session.commit()
            emit('user_offline', {'user_id': user.id})

@socketio.on('join_server')
def handle_join_server(data):
    server_id = data.get('server_id')
    if server_id:
        join_room(f'server_{server_id}')

@socketio.on('leave_server')
def handle_leave_server(data):
    server_id = data.get('server_id')
    if server_id:
        leave_room(f'server_{server_id}')

@socketio.on('join_text_channel')
def handle_join_text_channel(data):
    channel_id = data.get('channel_id')
    if channel_id:
        join_room(f'channel_{channel_id}')

@socketio.on('leave_text_channel')
def handle_leave_text_channel(data):
    channel_id = data.get('channel_id')
    if channel_id:
        leave_room(f'channel_{channel_id}')

@socketio.on('send_message')
def handle_send_message(data):
    if 'user_id' not in session:
        return
    
    content = data.get('content', '').strip()
    channel_id = data.get('channel_id')
    
    if not content or not channel_id:
        return
    
    message = Message(
        content=content,
        sender_id=session['user_id'],
        channel_id=channel_id
    )
    db.session.add(message)
    db.session.commit()
    
    channel = TextChannel.query.get(channel_id)
    if channel:
        emit('new_message', {
            'id': message.id,
            'content': message.content,
            'sender_id': message.sender_id,
            'sender_username': session.get('username', User.query.get(session['user_id']).username),
            'channel_id': channel_id,
            'created_at': message.created_at.isoformat(),
            'edited': False
        }, room=f'channel_{channel_id}')

@socketio.on('send_private_message')
def handle_send_private_message(data):
    if 'user_id' not in session:
        return
    
    content = data.get('content', '').strip()
    recipient_id = data.get('recipient_id')
    
    if not content or not recipient_id:
        return
    
    message = PrivateMessage(
        content=content,
        sender_id=session['user_id'],
        recipient_id=recipient_id
    )
    db.session.add(message)
    db.session.commit()
    
    sender = User.query.get(session['user_id'])
    
    # Отправляем получателю
    emit('new_private_message', {
        'id': message.id,
        'content': message.content,
        'sender_id': message.sender_id,
        'sender_username': sender.username,
        'recipient_id': recipient_id,
        'created_at': message.created_at.isoformat(),
        'read': False
    }, room=f'user_{recipient_id}')
    
    # Отправляем отправителю подтверждение
    emit('new_private_message', {
        'id': message.id,
        'content': message.content,
        'sender_id': message.sender_id,
        'sender_username': sender.username,
        'recipient_id': recipient_id,
        'created_at': message.created_at.isoformat(),
        'read': True
    })

@socketio.on('join_voice_channel')
def handle_join_voice_channel(data):
    if 'user_id' not in session:
        return
    
    channel_id = data.get('channel_id')
    if not channel_id:
        return
    
    user = User.query.get(session['user_id'])
    if not user:
        return
    
    # Покидаем предыдущий канал если есть
    if user.current_voice_channel:
        old_channel_id = user.current_voice_channel
        leave_room(f'voice_{old_channel_id}')
        emit('user_left_voice', {
            'user_id': user.id,
            'username': user.username,
            'channel_id': old_channel_id
        }, room=f'voice_{old_channel_id}')
    
    # Присоединяемся к новому
    user.current_voice_channel = channel_id
    db.session.commit()
    join_room(f'voice_{channel_id}')
    
    channel = VoiceChannel.query.get(channel_id)
    emit('user_joined_voice', {
        'user_id': user.id,
        'username': user.username,
        'channel_id': channel_id,
        'channel_name': channel.name if channel else 'Unknown'
    }, room=f'voice_{channel_id}')

@socketio.on('leave_voice_channel')
def handle_leave_voice_channel(data):
    if 'user_id' not in session:
        return
    
    user = User.query.get(session['user_id'])
    if not user or not user.current_voice_channel:
        return
    
    channel_id = user.current_voice_channel
    leave_room(f'voice_{channel_id}')
    
    user.current_voice_channel = None
    db.session.commit()
    
    emit('user_left_voice', {
        'user_id': user.id,
        'username': user.username,
        'channel_id': channel_id
    }, room=f'voice_{channel_id}')

@socketio.on('typing_start')
def handle_typing_start(data):
    if 'user_id' not in session:
        return
    
    channel_id = data.get('channel_id')
    if channel_id:
        user = User.query.get(session['user_id'])
        emit('user_typing', {
            'user_id': user.id,
            'username': user.username,
            'channel_id': channel_id
        }, room=f'channel_{channel_id}')

@socketio.on('typing_stop')
def handle_typing_stop(data):
    if 'user_id' not in session:
        return
    
    channel_id = data.get('channel_id')
    if channel_id:
        user = User.query.get(session['user_id'])
        emit('user_stopped_typing', {
            'user_id': user.id,
            'username': user.username,
            'channel_id': channel_id
        }, room=f'channel_{channel_id}')

if __name__ == '__main__':
    init_db()
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
