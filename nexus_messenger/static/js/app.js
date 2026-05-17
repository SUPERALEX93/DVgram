let socket, currentServerId = null, currentChannelId = null, currentChannelType = 'text', currentDMUserId = null, allUsers = [], allServers = [], typingTimeout = null;

document.addEventListener('DOMContentLoaded', () => {
    socket = io();
    socket.on('connect', () => console.log('Connected'));
    socket.on('new_message', (d) => { if (d.channel_id === currentChannelId && currentChannelType === 'text') { appendMessage(d); scrollToBottom(); }});
    socket.on('new_private_message', (d) => { if (currentDMUserId && (d.sender_id === currentDMUserId || d.recipient_id === currentDMUserId)) { appendMessage(d); scrollToBottom(); }});
    socket.on('user_online', (d) => updateUserStatus(d.user_id, true));
    socket.on('user_offline', (d) => updateUserStatus(d.user_id, false));
    socket.on('user_typing', (d) => { if (d.channel_id === currentChannelId) showTypingIndicator(d.username); });
    socket.on('server_created', () => loadServers());
    socket.on('channel_created', (d) => { if (d.server_id === currentServerId) loadServer(currentServerId).then(s => renderChannelsList(s.text_channels, s.voice_channels)); });
    loadUsers(); loadServers(); setupEventListeners();
});

async function loadUsers() { try { const r = await fetch('/api/users'); allUsers = await r.json(); renderUsersList(allUsers); } catch(e){console.error(e);} }
async function loadServers() { try { const r = await fetch('/api/servers'); allServers = await r.json(); renderServersList(); } catch(e){console.error(e);} }
async function loadServer(id) { try { const r = await fetch(`/api/server/${id}`); return await r.json(); } catch(e){return null;} }
async function loadMessages(cid) { try { const r = await fetch(`/api/messages/channel/${cid}`); return await r.json(); } catch(e){return [];} }
async function loadPrivateMessages(uid) { try { const r = await fetch(`/api/messages/private/${uid}`); return await r.json(); } catch(e){return [];} }

function renderServersList() {
    const c = document.getElementById('servers-container'); c.innerHTML = '';
    allServers.forEach(s => {
        const b = document.createElement('button'); b.className = 'server-btn'; b.dataset.serverId = s.id;
        b.innerHTML = `<div class="server-icon" style="background:${s.icon_color};width:100%;height:100%;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:20px;">${s.name.charAt(0)}</div>`;
        b.onclick = () => selectServer(s.id); c.appendChild(b);
    });
}

function renderUsersList(users) {
    const c = document.getElementById('users-list'); c.innerHTML = '';
    users.filter(u => u.id !== window.currentUser.id).forEach(u => {
        const i = document.createElement('div'); i.className = 'user-item'; i.dataset.userId = u.id;
        i.innerHTML = `<div class="user-avatar-small">${u.username.charAt(0).toUpperCase()}<div class="${u.is_online?'online-indicator':'offline-indicator'}"></div></div><span>${u.username}</span>`;
        i.onclick = () => openDM(u.id, u.username); c.appendChild(i);
    });
}

function renderChannelsList(tc, vc) {
    const tc_c = document.getElementById('text-channels-list'), vc_c = document.getElementById('voice-channels-list');
    tc_c.innerHTML = ''; vc_c.innerHTML = '';
    tc.forEach(c => { const i = document.createElement('div'); i.className = 'channel-item'; i.dataset.channelId = c.id; i.dataset.type = 'text';
        i.innerHTML = '<span class="channel-icon">#</span><span>'+c.name+'</span>'; i.onclick = () => selectTextChannel(c.id, c.name); tc_c.appendChild(i); });
    vc.forEach(c => { const i = document.createElement('div'); i.className = 'channel-item'; i.dataset.channelId = c.id; i.dataset.type = 'voice';
        i.innerHTML = '<span class="channel-icon">🔊</span><span>'+c.name+'</span>'; i.onclick = () => joinVoiceChannel(c.id, c.name); vc_c.appendChild(i); });
}

function appendMessage(m) {
    const c = document.getElementById('messages-list'), t = new Date(m.created_at).toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'}), u = m.sender_username||'Unknown';
    const el = document.createElement('div'); el.className = 'message';
    el.innerHTML = `<div class="message-avatar">${u.charAt(0).toUpperCase()}</div><div class="message-content"><div class="message-header"><span class="message-author">${u}</span><span class="message-time">${t}</span></div><div class="message-text">${escapeHtml(m.content)}</div></div>`;
    c.appendChild(el);
}
function clearMessages() { document.getElementById('messages-list').innerHTML = ''; }
function scrollToBottom() { document.getElementById('messages-container').scrollTop = document.getElementById('messages-container').scrollHeight; }

function updateUserStatus(uid, online) {
    const i = document.querySelector(`.user-item[data-user-id="${uid}"]`);
    if(i) { const ind = i.querySelector('.online-indicator,.offline-indicator'); if(ind) ind.className = online ? 'online-indicator' : 'offline-indicator'; }
    const u = allUsers.find(x => x.id === uid); if(u) u.is_online = online;
}

async function selectServer(sid) {
    document.querySelectorAll('.server-btn').forEach(b => { b.classList.remove('active'); if(b.dataset.serverId == sid) b.classList.add('active'); });
    currentServerId = sid; currentDMUserId = null; socket.emit('join_server', {server_id: sid});
    const s = await loadServer(sid);
    if(s) {
        document.getElementById('current-server-name').textContent = s.name;
        document.getElementById('channels-section').style.display = 'block';
        document.getElementById('users-section').style.display = 'none';
        renderChannelsList(s.text_channels, s.voice_channels);
        if(s.text_channels.length > 0) selectTextChannel(s.text_channels[0].id, s.text_channels[0].name);
    }
}

async function selectTextChannel(cid, name) {
    if(currentChannelId && currentChannelType === 'text') socket.emit('leave_text_channel', {channel_id: currentChannelId});
    currentChannelId = cid; currentChannelType = 'text';
    socket.emit('join_text_channel', {channel_id: cid});
    document.querySelectorAll('.channel-item').forEach(i => { i.classList.remove('active'); if(i.dataset.channelId == cid && i.dataset.type === 'text') i.classList.add('active'); });
    document.getElementById('chat-name').textContent = '# ' + name;
    clearMessages(); const msgs = await loadMessages(cid); msgs.forEach(m => appendMessage(m)); scrollToBottom();
}

async function openDM(uid, name) {
    currentDMUserId = uid; currentChannelType = 'dm';
    document.querySelectorAll('.user-item').forEach(i => { i.classList.remove('active'); if(i.dataset.userId == uid) i.classList.add('active'); });
    document.getElementById('current-server-name').textContent = '@' + name;
    document.getElementById('channels-section').style.display = 'none';
    document.getElementById('users-section').style.display = 'block';
    document.getElementById('chat-name').textContent = '@' + name;
    clearMessages(); const msgs = await loadPrivateMessages(uid); msgs.forEach(m => appendMessage(m)); scrollToBottom();
}

async function joinVoiceChannel(cid, name) {
    if(currentChannelId && currentChannelType === 'voice') socket.emit('leave_voice_channel', {});
    currentChannelId = cid; currentChannelType = 'voice';
    socket.emit('join_voice_channel', {channel_id: cid});
    document.getElementById('voice-panel').style.display = 'flex';
    document.getElementById('voice-channel-name').textContent = name;
}

function leaveVoiceChannel() { socket.emit('leave_voice_channel', {}); currentChannelId = null; document.getElementById('voice-panel').style.display = 'none'; }

function sendMessage() {
    const inp = document.getElementById('message-input'), content = inp.value.trim();
    if(!content) return;
    if(currentDMUserId) socket.emit('send_private_message', {content, recipient_id: currentDMUserId});
    else if(currentChannelId && currentChannelType === 'text') socket.emit('send_message', {content, channel_id: currentChannelId});
    inp.value = '';
}

function showTypingIndicator(u) { document.getElementById('typing-indicator').textContent = u + ' печатает...'; }
function hideTypingIndicator() { document.getElementById('typing-indicator').textContent = ''; }

async function createServer(name, color) {
    try {
        const r = await fetch('/api/server', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name, icon_color: color})});
        const d = await r.json(); if(r.ok) { await loadServers(); selectServer(d.server.id); closeModal('create-server-modal'); } else alert(d.error);
    } catch(e) { alert('Ошибка'); }
}

async function createChannel(name, type) {
    if(!currentServerId) return;
    try {
        const ep = type === 'text' ? '/api/text-channel' : '/api/voice-channel';
        const r = await fetch(ep, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({server_id: currentServerId, name})});
        const d = await r.json(); if(r.ok) { const s = await loadServer(currentServerId); renderChannelsList(s.text_channels, s.voice_channels); closeModal('create-channel-modal'); } else alert(d.error);
    } catch(e) { alert('Ошибка'); }
}

function openModal(id) { document.getElementById(id).style.display = 'flex'; }
function closeModal(id) { document.getElementById(id).style.display = 'none'; }

function setupEventListeners() {
    const inp = document.getElementById('message-input');
    inp.addEventListener('keypress', e => { if(e.key === 'Enter') sendMessage(); else { if(currentChannelId) { socket.emit('typing_start',{channel_id:currentChannelId}); clearTimeout(typingTimeout); typingTimeout = setTimeout(()=>socket.emit('typing_stop',{channel_id:currentChannelId}),2000); }}});
    document.getElementById('send-btn').onclick = sendMessage;
    document.querySelector('.home-btn').onclick = () => {
        document.querySelectorAll('.server-btn').forEach(b=>b.classList.remove('active')); document.querySelector('.home-btn').classList.add('active');
        currentServerId = null; currentDMUserId = null;
        document.getElementById('current-server-name').textContent = 'Личные сообщения';
        document.getElementById('channels-section').style.display = 'none'; document.getElementById('users-section').style.display = 'block';
        document.getElementById('chat-name').textContent = '# выберите-пользователя'; clearMessages();
    };
    document.getElementById('add-server-btn').onclick = () => openModal('create-server-modal');
    document.getElementById('create-server-form').onsubmit = e => { e.preventDefault(); createServer(document.getElementById('server-name').value.trim(), document.getElementById('server-color').value); };
    document.querySelectorAll('.add-channel-btn').forEach(b => b.onclick = () => {
        if(!currentServerId) { alert('Выберите сервер'); return; }
        document.getElementById('channel-modal-title').textContent = b.dataset.type === 'text' ? 'Создать текстовый канал' : 'Создать голосовой канал';
        document.getElementById('create-channel-form').dataset.type = b.dataset.type; openModal('create-channel-modal');
    });
    document.getElementById('create-channel-form').onsubmit = e => { e.preventDefault(); createChannel(document.getElementById('channel-name').value.trim(), e.target.dataset.type); };
    document.querySelectorAll('.modal-overlay,.cancel-btn').forEach(el => el.onclick = e => { e.target.closest('.modal').style.display = 'none'; });
    document.getElementById('close-voice-btn').onclick = leaveVoiceChannel;
    document.getElementById('disconnect-voice-btn').onclick = leaveVoiceChannel;
    document.getElementById('mute-btn').onclick = function() { this.classList.toggle('active'); };
    document.getElementById('deafen-btn').onclick = function() { this.classList.toggle('active'); };
    document.getElementById('user-search').oninput = e => { const q = e.target.value.toLowerCase(); renderUsersList(allUsers.filter(u => u.id !== window.currentUser.id && u.username.toLowerCase().includes(q))); };
    document.getElementById('logout-btn').onclick = async () => { await fetch('/logout',{method:'POST'}); window.location.href = '/'; };
}

function escapeHtml(t) { const d = document.createElement('div'); d.textContent = t; return d.innerHTML; }
