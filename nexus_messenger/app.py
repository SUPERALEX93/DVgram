from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'nexus-messenger-secret-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///nexus.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Server(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    icon_color = db.Column(db.String(7), default='#6366f1')
    
    channels = db.relationship('Channel', backref='server', lazy=True, cascade='all, delete-orphan')
    members = db.relationship('ServerMember', backref='server', lazy=True, cascade='all, delete-orphan')

class Channel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    channel_type = db.Column(db.String(20), default='text')  # text, voice
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=False)
    position = db.Column(db.Integer, default=0)
    
    messages = db.relationship('Message', backref='channel', lazy=True, cascade='all, delete-orphan')

class ServerMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='server_memberships')

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    channel_id = db.Column(db.Integer, db.ForeignKey('channel.id'))
    dm_recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    dm_recipient = db.relationship('User', foreign_keys=[dm_recipient_id], backref='received_messages')

class DMConversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user1_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user2_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('user1_id', 'user2_id', name='unique_dm_pair'),)
    
    user1 = db.relationship('User', foreign_keys=[user1_id], backref='dm_conversations_as_user1')
    user2 = db.relationship('User', foreign_keys=[user2_id], backref='dm_conversations_as_user2')

# Initialize database
with app.app_context():
    db.create_all()
    
    # Create some demo servers if none exist
    if Server.query.count() == 0:
        demo_user = User(username='NexusAdmin', password_hash=generate_password_hash('admin123'))
        db.session.add(demo_user)
        db.session.commit()
        
        servers = [
            Server(name='🌟 Welcome Hub', description='Добро пожаловать в Nexus!', owner_id=demo_user.id, icon_color='#6366f1'),
            Server(name='🎮 Gaming Zone', description='Игровое сообщество', owner_id=demo_user.id, icon_color='#ec4899'),
            Server(name='💻 Tech Talk', description='Технологии и программирование', owner_id=demo_user.id, icon_color='#10b981'),
            Server(name='🎵 Music Lounge', description='Музыка и отдых', owner_id=demo_user.id, icon_color='#f59e0b'),
            Server(name='🚀 Startup Ideas', description='Обмен идеями и стартапы', owner_id=demo_user.id, icon_color='#ef4444'),
        ]
        
        for server in servers:
            db.session.add(server)
            db.session.commit()
            
            # Add default channels
            text_channel = Channel(name='general', channel_type='text', server_id=server.id, position=0)
            voice_channel = Channel(name='Voice Lounge', channel_type='voice', server_id=server.id, position=1)
            db.session.add(text_channel)
            db.session.add(voice_channel)
            
            # Add admin as member
            member = ServerMember(user_id=demo_user.id, server_id=server.id)
            db.session.add(member)
        
        db.session.commit()

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('app_main'))
    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({'error': 'Введите имя пользователя и пароль'}), 400
    
    if len(username) < 3:
        return jsonify({'error': 'Имя должно быть не менее 3 символов'}), 400
    
    if len(password) < 6:
        return jsonify({'error': 'Пароль должен быть не менее 6 символов'}), 400
    
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Пользователь с таким именем уже существует'}), 400
    
    user = User(username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    
    session['user_id'] = user.id
    session['username'] = username
    
    return jsonify({'success': True, 'username': username})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    user = User.query.filter_by(username=username).first()
    
    if user and user.check_password(password):
        session['user_id'] = user.id
        session['username'] = username
        return jsonify({'success': True, 'username': username})
    
    return jsonify({'error': 'Неверное имя пользователя или пароль'}), 401

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/app')
def app_main():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return render_template('app.html', username=session['username'], user_id=session['user_id'])

# API Routes
@app.route('/api/users')
def get_users():
    users = User.query.all()
    return jsonify([{
        'id': user.id,
        'username': user.username,
        'created_at': user.created_at.isoformat()
    } for user in users])

@app.route('/api/servers')
def get_servers():
    servers = Server.query.all()
    return jsonify([{
        'id': server.id,
        'name': server.name,
        'description': server.description,
        'icon_color': server.icon_color,
        'channels': [{
            'id': channel.id,
            'name': channel.name,
            'type': channel.channel_type
        } for channel in sorted(server.channels, key=lambda c: c.position)],
        'member_count': len(server.members)
    } for server in servers])

@app.route('/api/server/<int:server_id>')
def get_server(server_id):
    server = Server.query.get_or_404(server_id)
    return jsonify({
        'id': server.id,
        'name': server.name,
        'description': server.description,
        'icon_color': server.icon_color,
        'channels': [{
            'id': channel.id,
            'name': channel.name,
            'type': channel.channel_type
        } for channel in sorted(server.channels, key=lambda c: c.position)],
        'members': [{
            'id': member.user.id,
            'username': member.user.username
        } for member in server.members]
    })

@app.route('/api/messages/<int:channel_id>')
def get_messages(channel_id):
    messages = Message.query.filter_by(channel_id=channel_id).order_by(Message.timestamp.asc()).limit(50).all()
    return jsonify([{
        'id': msg.id,
        'content': msg.content,
        'timestamp': msg.timestamp.isoformat(),
        'sender': {
            'id': msg.sender.id,
            'username': msg.sender.username
        }
    } for msg in messages])

@app.route('/api/dm/<int:user_id>')
def get_dm_messages(user_id):
    current_user_id = session['user_id']
    messages = Message.query.filter(
        ((Message.sender_id == current_user_id) & (Message.dm_recipient_id == user_id)) |
        ((Message.sender_id == user_id) & (Message.dm_recipient_id == current_user_id))
    ).order_by(Message.timestamp.asc()).limit(50).all()
    
    return jsonify([{
        'id': msg.id,
        'content': msg.content,
        'timestamp': msg.timestamp.isoformat(),
        'sender': {
            'id': msg.sender.id,
            'username': msg.sender.username
        },
        'is_self': msg.sender_id == current_user_id
    } for msg in messages])

# Socket.IO events
@socketio.on('connect')
def handle_connect():
    if 'user_id' in session:
        emit('connected', {'user_id': session['user_id'], 'username': session['username']})

@socketio.on('join_channel')
def handle_join_channel(data):
    channel_id = data['channel_id']
    room = f'channel_{channel_id}'
    join_room(room)
    emit('joined_channel', {'channel_id': channel_id, 'room': room})

@socketio.on('leave_channel')
def handle_leave_channel(data):
    channel_id = data['channel_id']
    room = f'channel_{channel_id}'
    leave_room(room)

@socketio.on('send_message')
def handle_send_message(data):
    if 'user_id' not in session:
        return
    
    content = data.get('content', '').strip()
    channel_id = data.get('channel_id')
    dm_recipient_id = data.get('dm_recipient_id')
    
    if not content:
        return
    
    message = Message(
        content=content,
        sender_id=session['user_id'],
        channel_id=channel_id,
        dm_recipient_id=dm_recipient_id
    )
    db.session.add(message)
    db.session.commit()
    
    message_data = {
        'id': message.id,
        'content': message.content,
        'timestamp': message.timestamp.isoformat(),
        'sender': {
            'id': session['user_id'],
            'username': session['username']
        }
    }
    
    if channel_id:
        room = f'channel_{channel_id}'
        emit('new_message', message_data, room=room)
    elif dm_recipient_id:
        # Send to both users in DM
        emit('new_dm_message', message_data, room=f'dm_{min(session["user_id"], dm_recipient_id)}_{max(session["user_id"], dm_recipient_id)}')
        emit('new_dm_message', message_data, room=f'user_{dm_recipient_id}')

@socketio.on('join_dm')
def handle_join_dm(data):
    other_user_id = data['user_id']
    current_user_id = session['user_id']
    room = f'dm_{min(current_user_id, other_user_id)}_{max(current_user_id, other_user_id)}'
    join_room(room)
    emit('joined_dm', {'room': room, 'other_user_id': other_user_id})

@socketio.on('typing')
def handle_typing(data):
    channel_id = data.get('channel_id')
    dm_recipient_id = data.get('dm_recipient_id')
    
    typing_data = {
        'user_id': session['user_id'],
        'username': session['username']
    }
    
    if channel_id:
        emit('user_typing', typing_data, room=f'channel_{channel_id}', include_self=False)
    elif dm_recipient_id:
        emit('user_typing', typing_data, room=f'user_{dm_recipient_id}', include_self=False)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
