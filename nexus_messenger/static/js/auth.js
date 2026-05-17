// ==================== АВТОРИЗАЦИЯ ====================

document.addEventListener('DOMContentLoaded', () => {
    // Переключение между вкладками
    const tabs = document.querySelectorAll('.auth-tab');
    const forms = document.querySelectorAll('.auth-form');
    
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const targetTab = tab.dataset.tab;
            
            tabs.forEach(t => t.classList.remove('active'));
            forms.forEach(f => f.classList.remove('active'));
            
            tab.classList.add('active');
            document.getElementById(`${targetTab}-form`).classList.add('active');
            
            // Очистка ошибок
            document.querySelectorAll('.error-message').forEach(el => {
                el.classList.remove('show');
                el.textContent = '';
            });
        });
    });
    
    // Форма входа
    const loginForm = document.getElementById('login-form');
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const username = document.getElementById('login-username').value.trim();
        const password = document.getElementById('login-password').value;
        const errorEl = document.getElementById('login-error');
        
        try {
            const response = await fetch('/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            
            const data = await response.json();
            
            if (response.ok) {
                window.location.href = '/app';
            } else {
                errorEl.textContent = data.error || 'Ошибка входа';
                errorEl.classList.add('show');
            }
        } catch (error) {
            errorEl.textContent = 'Ошибка соединения с сервером';
            errorEl.classList.add('show');
        }
    });
    
    // Форма регистрации
    const registerForm = document.getElementById('register-form');
    registerForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const username = document.getElementById('register-username').value.trim();
        const password = document.getElementById('register-password').value;
        const errorEl = document.getElementById('register-error');
        
        try {
            const response = await fetch('/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            
            const data = await response.json();
            
            if (response.ok) {
                window.location.href = '/app';
            } else {
                errorEl.textContent = data.error || 'Ошибка регистрации';
                errorEl.classList.add('show');
            }
        } catch (error) {
            errorEl.textContent = 'Ошибка соединения с сервером';
            errorEl.classList.add('show');
        }
    });
});
