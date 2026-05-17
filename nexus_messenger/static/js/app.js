// Main app functionality
let socket;
let currentChannelId = null;
let currentServerId = null;
let currentDMUserId = null;
let typingTimeout;

document.addEventListener('DOMContentLoaded', () => {
    // Initialize Socket.IO
    socket = io();
    
    // Load initial data
    loadServers();
    loadUsers();
    
    // Setup event listeners
    setupEventListeners();
    
    // Socket events
    setupSocketEvents();
    
    // Default to home (DMs)
    selectHome();
});

function setupEventListeners() {
    // Message input
    const messageInput = document.getElementById('message-input');
    const sendBtn = document.getElementById('send-btn');
    
    sendBtn.addEventListener('click', sendMessage);
    
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            sendMessage();
        } else {
            handleTyping();
        }
    });
    
    // User search
    const userSearch = document.getElementById('user-search');
    userSearch.addEventListener('input', (e) => {
        filterUsers(e.target.value);
    });
    
    // Voice controls
    const muteBtn = document.getElementById('mute-btn');
    const deafenBtn = document.getElementById('deafen-btn');
    
    muteBtn.addEventListener('click', () => {
        muteBtn.classList.toggle('active');
        muteBtn.textContent = muteBtn.classList.contains('active') ? '🔇' : '🎤';
    });
    
    deafenBtn.addEventListener('click', () => {
        deafenBtn.classList.toggle('active');
        deafenBtn.textContent = deafenBtn.classList.contains('active') ? '🔇' : '🔊';
    });
}

function setupSocketEvents() {
    socket.on('connected', (data) => {
        console.log('Connected:', data);
    });
    
    socket.on('new_message', (message) => {
        if (currentChannelId && !currentDMUserId) {
            appendMessage(message, false);
            scrollToBottom();
        }
    });
    
    socket.on('new_dm_message', (message) => {
        if (currentDMUserId) {
            appendMessage(message, message.sender.id === parseInt(localStorage.getItem('userId')));
            scrollToBottom();
        }
    });
    
    socket.on('user_typing', (data) => {
        const typingIndicator = document.getElementById('typing-indicator');
        typingIndicator.textContent = `${data.username} печатает...`;
        
        clearTimeout(typingTimeout);
        typingTimeout = setTimeout(() => {
            typingIndicator.textContent = '';
        }, 3000);
    });
}

async function loadServers() {
    try {
        const response = await fetch('/api/servers');
        const servers = await response.json();
        
        const container = document.getElementById('servers-container');
        container.innerHTML = '';
        
        servers.forEach(server => {
            const serverEl = createServerElement(server);
            container.appendChild(serverEl);
        });
    } catch (error) {
        console.error('Error loading servers:', error);
    }
}

async function loadUsers() {
    try {
        const response = await fetch('/api/users');
        const users = await response.json();
        
        const container = document.getElementById('users-list');
        container.innerHTML = '';
        
        const currentUserId = parseInt(localStorage.getItem('userId'));
        
        users.forEach(user => {
            if (user.id !== currentUserId) {
                const userEl = createUserElement(user);
                container.appendChild(userEl);
            }
        });
    } catch (error) {
        console.error('Error loading users:', error);
    }
}

function createServerElement(server) {
    const el = document.createElement('div');
    el.className = 'server-icon';
    el.style.backgroundColor = server.icon_color;
    el.title = server.name;
    el.innerHTML = `<span>${server.name.charAt(0)}</span>`;
    
    el.addEventListener('click', () => selectServer(server));
    
    return el;
}

function createUserElement(user) {
    const el = document.createElement('div');
    el.className = 'user-item';
    el.dataset.userId = user.id;
    el.innerHTML = `
        <div class="user-avatar">${user.username.charAt(0).toUpperCase()}</div>
        <div class="user-info">
            <div class="username">${user.username}</div>
            <div class="user-status online">Онлайн</div>
        </div>
    `;
    
    el.addEventListener('click', () => selectDM(user));
    
    return el;
}

function selectHome() {
    document.querySelectorAll('.server-icon').forEach(el => el.classList.remove('active'));
    document.querySelector('.home-icon').classList.add('active');
    
    currentServerId = null;
    currentChannelId = null;
    currentDMUserId = null;
    
    document.getElementById('sidebar-title').textContent = 'Личные сообщения';
    document.getElementById('current-channel-name').textContent = 'Выберите пользователя';
    document.getElementById('current-channel-desc').textContent = 'Для начала общения выберите пользователя слева';
    document.getElementById('messages-wrapper').innerHTML = '';
}

function selectServer(server) {
    document.querySelectorAll('.server-icon').forEach(el => el.classList.remove('active'));
    event.target.closest('.server-icon').classList.add('active');
    
    currentServerId = server.id;
    currentDMUserId = null;
    
    document.getElementById('sidebar-title').textContent = 'Участники';
    
    // Load server details and select first text channel
    loadServerDetails(server);
}

async function loadServerDetails(server) {
    try {
        const response = await fetch(`/api/server/${server.id}`);
        const serverData = await response.json();
        
        // Update members list
        const container = document.getElementById('users-list');
        container.innerHTML = '';
        
        serverData.members.forEach(member => {
            const userEl = createUserElement(member);
            container.appendChild(userEl);
        });
        
        // Select first text channel
        const textChannel = serverData.channels.find(c => c.type === 'text');
        if (textChannel) {
            selectChannel(textChannel, serverData);
        }
    } catch (error) {
        console.error('Error loading server details:', error);
    }
}

function selectChannel(channel, serverData) {
    currentChannelId = channel.id;
    currentDMUserId = null;
    
    const channelIcon = channel.type === 'voice' ? '🔊' : '#';
    const channelDesc = channel.type === 'voice' ? 'Голосовой канал' : 'Текстовый канал';
    
    document.getElementById('current-channel-name').textContent = channel.name;
    document.getElementById('current-channel-desc').textContent = channelDesc;
    
    if (channel.type === 'voice') {
        showVoicePanel(channel.name);
        document.getElementById('messages-wrapper').innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 40px;">Голосовые каналы не поддерживают текстовые сообщения</div>';
    } else {
        hideVoicePanel();
        loadMessages(channel.id);
    }
    
    // Leave previous channel room
    if (socket.connected) {
        socket.emit('leave_channel', { channel_id: currentChannelId });
    }
    
    // Join new channel room
    socket.emit('join_channel', { channel_id: channel.id });
}

function selectDM(user) {
    currentDMUserId = user.id;
    currentChannelId = null;
    
    document.querySelectorAll('.user-item').forEach(el => el.classList.remove('active'));
    document.querySelector(`.user-item[data-user-id="${user.id}"]`)?.classList.add('active');
    
    document.getElementById('sidebar-title').textContent = 'Личные сообщения';
    document.getElementById('current-channel-name').textContent = user.username;
    document.getElementById('current-channel-desc').textContent = 'Личная переписка';
    
    hideVoicePanel();
    loadDMMessages(user.id);
    
    // Join DM room
    socket.emit('join_dm', { user_id: user.id });
}

async function loadMessages(channelId) {
    try {
        const response = await fetch(`/api/messages/${channelId}`);
        const messages = await response.json();
        
        const wrapper = document.getElementById('messages-wrapper');
        wrapper.innerHTML = '';
        
        messages.forEach(msg => {
            appendMessage(msg, msg.sender.id === parseInt(localStorage.getItem('userId')));
        });
        
        scrollToBottom();
    } catch (error) {
        console.error('Error loading messages:', error);
    }
}

async function loadDMMessages(userId) {
    try {
        const response = await fetch(`/api/dm/${userId}`);
        const messages = await response.json();
        
        const wrapper = document.getElementById('messages-wrapper');
        wrapper.innerHTML = '';
        
        messages.forEach(msg => {
            appendMessage(msg, msg.is_self);
        });
        
        scrollToBottom();
    } catch (error) {
        console.error('Error loading DM messages:', error);
    }
}

function appendMessage(msg, isSelf) {
    const wrapper = document.getElementById('messages-wrapper');
    const messageEl = document.createElement('div');
    messageEl.className = `message ${isSelf ? 'message-self' : ''}`;
    
    const time = new Date(msg.timestamp).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
    
    messageEl.innerHTML = `
        <div class="message-avatar">${msg.sender.username.charAt(0).toUpperCase()}</div>
        <div class="message-content">
            <div class="message-header">
                <span class="message-author">${msg.sender.username}</span>
                <span class="message-time">${time}</span>
            </div>
            <div class="message-text">${escapeHtml(msg.content)}</div>
        </div>
    `;
    
    wrapper.appendChild(messageEl);
}

function sendMessage() {
    const input = document.getElementById('message-input');
    const content = input.value.trim();
    
    if (!content) return;
    
    const messageData = {
        content: content,
        channel_id: currentChannelId,
        dm_recipient_id: currentDMUserId
    };
    
    socket.emit('send_message', messageData);
    input.value = '';
    
    // Clear typing indicator
    document.getElementById('typing-indicator').textContent = '';
}

function handleTyping() {
    socket.emit('typing', {
        channel_id: currentChannelId,
        dm_recipient_id: currentDMUserId
    });
}

function scrollToBottom() {
    const container = document.getElementById('messages-container');
    container.scrollTop = container.scrollHeight;
}

function filterUsers(query) {
    const users = document.querySelectorAll('.user-item');
    const lowerQuery = query.toLowerCase();
    
    users.forEach(user => {
        const username = user.querySelector('.username').textContent.toLowerCase();
        if (username.includes(lowerQuery)) {
            user.style.display = 'flex';
        } else {
            user.style.display = 'none';
        }
    });
}

function showVoicePanel(channelName) {
    const panel = document.getElementById('voice-panel');
    panel.querySelector('.voice-header span').textContent = `🎤 ${channelName}`;
    panel.classList.add('active');
}

function hideVoicePanel() {
    document.getElementById('voice-panel').classList.remove('active');
}

function closeVoicePanel() {
    hideVoicePanel();
}

function disconnectVoice() {
    hideVoicePanel();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Store user ID for message comparison
localStorage.setItem('userId', '{{ user_id }}');
