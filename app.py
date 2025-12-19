"""
Мобильные сотрудники - Web приложение для управления сотрудниками компании
Расширенная версия с аутентификацией и функционалом для сотрудников
Запуск: python app.py
Открыть в браузере: http://localhost:5000
"""

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from functools import wraps
import sqlite3
import hashlib
import os
import datetime

app = Flask(__name__)
app.secret_key = 'mobile-employees-secret-key-2024-advanced'
app.config['SESSION_TYPE'] = 'filesystem'

# ========== БАЗА ДАННЫХ ==========

class Database:
    def __init__(self):
        self.db_name = 'employees.db'
        self.init_db()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        conn = self.get_connection()
        c = conn.cursor()
        
        # Таблица пользователей (админы и сотрудники)
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL DEFAULT 'employee',
                employee_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (employee_id) REFERENCES employees (id) ON DELETE SET NULL
            )
        ''')
        
        # Таблица сотрудников - ОБНОВЛЕНА С hourly_rate
        c.execute('''
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                position TEXT NOT NULL,
                department TEXT,
                phone TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                location TEXT,
                status TEXT DEFAULT 'active',
                latitude REAL,
                longitude REAL,
                work_schedule TEXT,
                current_task TEXT,
                hourly_rate REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица задач
        c.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                employee_id INTEGER NOT NULL,
                manager_id INTEGER,
                status TEXT DEFAULT 'pending',
                priority TEXT DEFAULT 'medium',
                due_date TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                feedback TEXT,
                rating INTEGER,
                FOREIGN KEY (employee_id) REFERENCES employees (id) ON DELETE CASCADE,
                FOREIGN KEY (manager_id) REFERENCES users (id) ON DELETE SET NULL
            )
        ''')
        
        # Таблица отчетов о работе
        c.execute('''
            CREATE TABLE IF NOT EXISTS work_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                date DATE NOT NULL,
                hours_worked REAL DEFAULT 0,
                tasks_completed INTEGER DEFAULT 0,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (employee_id) REFERENCES employees (id) ON DELETE CASCADE
            )
        ''')
        
        # Таблица сообщений
        c.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER NOT NULL,
                receiver_id INTEGER NOT NULL,
                subject TEXT,
                content TEXT NOT NULL,
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sender_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (receiver_id) REFERENCES users (id) ON DELETE CASCADE
            )
        ''')
        
        # Проверяем существующие таблицы и добавляем отсутствующие колонки
        self.update_table_structure()
        
        # Проверяем, есть ли администратор
        c.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        if c.fetchone()[0] == 0:
            # Создаем администратора по умолчанию
            admin_password = self.hash_password('admin123')
            c.execute('''
                INSERT INTO users (username, password, email, role) 
                VALUES (?, ?, ?, ?)
            ''', ('admin', admin_password, 'admin@company.com', 'admin'))
            
            # Создаем тестовых сотрудников (БЕЗ hourly_rate в старых версиях)
            test_employees = [
                ('Иванов Иван Иванович', 'Менеджер по продажам', 'Отдел продаж', 
                 '+7 (999) 111-11-11', 'ivanov@company.com', 'Москва', 'active'),
                ('Петров Петр Петрович', 'Курьер', 'Логистика', 
                 '+7 (999) 222-22-22', 'petrov@company.com', 'Санкт-Петербург', 'on_mission'),
                ('Сидорова Мария Сергеевна', 'Торговый представитель', 'Отдел продаж', 
                 '+7 (999) 333-33-33', 'sidorova@company.com', 'Казань', 'active'),
                ('Козлов Алексей Владимирович', 'Сервисный инженер', 'Технический отдел', 
                 '+7 (999) 444-44-44', 'kozlov@company.com', 'Екатеринбург', 'active')
            ]
            
            for emp in test_employees:
                # Проверяем, есть ли колонка hourly_rate
                c.execute("PRAGMA table_info(employees)")
                columns = [col[1] for col in c.fetchall()]
                
                if 'hourly_rate' in columns:
                    c.execute('''
                        INSERT INTO employees (name, position, department, phone, email, location, status, hourly_rate)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (*emp, 500))  # Добавляем hourly_rate = 500
                else:
                    c.execute('''
                        INSERT INTO employees (name, position, department, phone, email, location, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', emp)
                
                # Создаем пользователя для сотрудника
                username = emp[4].split('@')[0]  # email без домена
                password = self.hash_password('employee123')
                c.execute('''
                    INSERT INTO users (username, password, email, role, employee_id)
                    VALUES (?, ?, ?, ?, ?)
                ''', (username, password, emp[4], 'employee', c.lastrowid))
            
            # Добавляем тестовые задачи
            test_tasks = [
                ('Доставить документы', 'Доставить пакет документов в офис на Пушкина, 10', 1, 'high', '2024-01-20'),
                ('Встреча с клиентом', 'Презентация нового продукта компании ООО "ТехноПром"', 2, 'medium', '2024-01-18'),
                ('Обслуживание оборудования', 'Плановое техническое обслуживание серверного оборудования', 3, 'low', '2024-01-25'),
                ('Закупка материалов', 'Закупка расходных материалов для офиса согласно списку', 4, 'medium', '2024-01-22'),
                ('Составление отчета', 'Ежемесячный отчет по продажам за январь 2024', 1, 'high', '2024-01-31'),
                ('Обучение нового сотрудника', 'Провести вводный инструктаж для нового менеджера', 2, 'medium', '2024-01-19')
            ]
            for task in test_tasks:
                c.execute('''
                    INSERT INTO tasks (title, description, employee_id, priority, due_date)
                    VALUES (?, ?, ?, ?, ?)
                ''', task)
            
            # Добавляем тестовые отчеты
            today = datetime.date.today()
            test_reports = [
                (1, today, 8, 3, 'Работа с клиентами, составление договоров'),
                (2, today, 6, 2, 'Доставка грузов по маршруту'),
                (3, today, 7, 4, 'Встречи с партнерами, переговоры'),
                (4, today, 8, 3, 'Ремонт оборудования, диагностика')
            ]
            for report in test_reports:
                c.execute('''
                    INSERT INTO work_reports (employee_id, date, hours_worked, tasks_completed, description)
                    VALUES (?, ?, ?, ?, ?)
                ''', report)
        
        conn.commit()
        conn.close()
    
    def update_table_structure(self):
        """Обновляет структуру таблиц если они уже существуют"""
        conn = self.get_connection()
        c = conn.cursor()
        
        try:
            # Проверяем и добавляем колонку hourly_rate в таблицу employees
            c.execute("PRAGMA table_info(employees)")
            columns = [col[1] for col in c.fetchall()]
            
            if 'hourly_rate' not in columns:
                c.execute("ALTER TABLE employees ADD COLUMN hourly_rate REAL DEFAULT 0")
                print("✓ Добавлена колонка hourly_rate в таблицу employees")
            
            # Проверяем и добавляем другие отсутствующие колонки
            if 'work_schedule' not in columns:
                c.execute("ALTER TABLE employees ADD COLUMN work_schedule TEXT")
                print("✓ Добавлена колонка work_schedule в таблицу employees")
            
            if 'current_task' not in columns:
                c.execute("ALTER TABLE employees ADD COLUMN current_task TEXT")
                print("✓ Добавлена колонка current_task в таблицу employees")
                
        except Exception as e:
            print(f"Ошибка при обновлении структуры таблиц: {e}")
        
        conn.commit()
        conn.close()
    
    def hash_password(self, password):
        """Хеширование пароля"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    # ========== АУТЕНТИФИКАЦИЯ ==========
    
    def authenticate_user(self, username, password):
        """Проверка логина и пароля"""
        conn = self.get_connection()
        user = conn.execute('''
            SELECT u.*, e.name as employee_name, e.position 
            FROM users u 
            LEFT JOIN employees e ON u.employee_id = e.id 
            WHERE u.username = ?
        ''', (username,)).fetchone()
        conn.close()
        
        if user and user['password'] == self.hash_password(password):
            return dict(user)
        return None
    
    def register_user(self, username, password, email, role='employee', employee_id=None):
        """Регистрация нового пользователя"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO users (username, password, email, role, employee_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (username, self.hash_password(password), email, role, employee_id))
            
            conn.commit()
            user_id = cursor.lastrowid
            conn.close()
            return user_id
        except sqlite3.IntegrityError:
            return None
    
    # ========== СОТРУДНИКИ ==========
    
    def get_all_employees(self):
        conn = self.get_connection()
        employees = conn.execute('SELECT * FROM employees ORDER BY name').fetchall()
        conn.close()
        return employees
    
    def get_employee_by_id(self, id):
        conn = self.get_connection()
        employee = conn.execute('SELECT * FROM employees WHERE id = ?', (id,)).fetchone()
        conn.close()
        return employee
    
    def get_employee_by_user_id(self, user_id):
        conn = self.get_connection()
        employee = conn.execute('''
            SELECT e.* FROM employees e
            JOIN users u ON e.id = u.employee_id
            WHERE u.id = ?
        ''', (user_id,)).fetchone()
        conn.close()
        return employee
    
    def add_employee(self, data):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Проверяем наличие колонки hourly_rate
        c = conn.cursor()
        c.execute("PRAGMA table_info(employees)")
        columns = [col[1] for col in c.fetchall()]
        
        if 'hourly_rate' in columns:
            cursor.execute('''
                INSERT INTO employees (name, position, department, phone, email, location, status, hourly_rate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['name'],
                data['position'],
                data['department'],
                data['phone'],
                data['email'],
                data.get('location', ''),
                data.get('status', 'active'),
                data.get('hourly_rate', 0)
            ))
        else:
            cursor.execute('''
                INSERT INTO employees (name, position, department, phone, email, location, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['name'],
                data['position'],
                data['department'],
                data['phone'],
                data['email'],
                data.get('location', ''),
                data.get('status', 'active')
            ))
        
        conn.commit()
        employee_id = cursor.lastrowid
        conn.close()
        return employee_id
    
    def update_employee(self, id, data):
        conn = self.get_connection()
        
        # Проверяем наличие колонки hourly_rate
        c = conn.cursor()
        c.execute("PRAGMA table_info(employees)")
        columns = [col[1] for col in c.fetchall()]
        
        if 'hourly_rate' in columns:
            conn.execute('''
                UPDATE employees 
                SET name = ?, position = ?, department = ?, phone = ?, email = ?, 
                    location = ?, status = ?, hourly_rate = ?
                WHERE id = ?
            ''', (
                data['name'],
                data['position'],
                data['department'],
                data['phone'],
                data['email'],
                data.get('location', ''),
                data.get('status', 'active'),
                data.get('hourly_rate', 0),
                id
            ))
        else:
            conn.execute('''
                UPDATE employees 
                SET name = ?, position = ?, department = ?, phone = ?, email = ?, 
                    location = ?, status = ?
                WHERE id = ?
            ''', (
                data['name'],
                data['position'],
                data['department'],
                data['phone'],
                data['email'],
                data.get('location', ''),
                data.get('status', 'active'),
                id
            ))
        
        conn.commit()
        conn.close()
    
    def delete_employee(self, id):
        conn = self.get_connection()
        conn.execute('DELETE FROM employees WHERE id = ?', (id,))
        conn.commit()
        conn.close()
    
    # ========== ЗАДАЧИ ==========
    
    def get_all_tasks(self, employee_id=None):
        conn = self.get_connection()
        if employee_id:
            tasks = conn.execute('''
                SELECT t.*, e.name as employee_name
                FROM tasks t 
                LEFT JOIN employees e ON t.employee_id = e.id 
                WHERE t.employee_id = ?
                ORDER BY t.due_date
            ''', (employee_id,)).fetchall()
        else:
            tasks = conn.execute('''
                SELECT t.*, e.name as employee_name
                FROM tasks t 
                LEFT JOIN employees e ON t.employee_id = e.id 
                ORDER BY t.due_date
            ''').fetchall()
        conn.close()
        return tasks
    
    def get_task_by_id(self, task_id):
        conn = self.get_connection()
        task = conn.execute('''
            SELECT t.*, e.name as employee_name
            FROM tasks t 
            LEFT JOIN employees e ON t.employee_id = e.id 
            WHERE t.id = ?
        ''', (task_id,)).fetchone()
        conn.close()
        return task
    
    def add_task(self, data, manager_id=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO tasks (title, description, employee_id, priority, due_date, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            data['title'],
            data.get('description', ''),
            data['employee_id'],
            data.get('priority', 'medium'),
            data.get('due_date'),
            'pending'
        ))
        
        conn.commit()
        task_id = cursor.lastrowid
        conn.close()
        return task_id
    
    def update_task_status(self, id, status, feedback=None):
        conn = self.get_connection()
        
        if status == 'completed':
            conn.execute('''
                UPDATE tasks 
                SET status = ?, completed_at = CURRENT_TIMESTAMP, feedback = ?
                WHERE id = ?
            ''', (status, feedback, id))
        else:
            conn.execute('''
                UPDATE tasks 
                SET status = ?, completed_at = NULL, feedback = ?
                WHERE id = ?
            ''', (status, feedback, id))
        
        conn.commit()
        conn.close()
    
    def delete_task(self, id):
        conn = self.get_connection()
        conn.execute('DELETE FROM tasks WHERE id = ?', (id,))
        conn.commit()
        conn.close()
    
    # ========== ОТЧЕТЫ ==========
    
    def add_work_report(self, employee_id, date, hours_worked, tasks_completed, description):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO work_reports (employee_id, date, hours_worked, tasks_completed, description)
            VALUES (?, ?, ?, ?, ?)
        ''', (employee_id, date, hours_worked, tasks_completed, description))
        
        conn.commit()
        report_id = cursor.lastrowid
        conn.close()
        return report_id
    
    def get_work_reports(self, employee_id=None):
        conn = self.get_connection()
        if employee_id:
            reports = conn.execute('''
                SELECT wr.*, e.name as employee_name 
                FROM work_reports wr
                JOIN employees e ON wr.employee_id = e.id
                WHERE wr.employee_id = ?
                ORDER BY wr.date DESC
            ''', (employee_id,)).fetchall()
        else:
            reports = conn.execute('''
                SELECT wr.*, e.name as employee_name 
                FROM work_reports wr
                JOIN employees e ON wr.employee_id = e.id
                ORDER BY wr.date DESC
            ''').fetchall()
        conn.close()
        return reports
    
    def register_user_with_employee(self, username, password, email, role='employee', employee_id=None):
        """Регистрация пользователя с проверкой"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO users (username, password, email, role, employee_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (username, self.hash_password(password), email, role, employee_id))
            
            conn.commit()
            user_id = cursor.lastrowid
            conn.close()
            return user_id
        except sqlite3.IntegrityError:
            return None
    
    def update_employee_password(self, employee_id, new_password):
        """Обновление пароля сотрудника"""
        conn = self.get_connection()
        
        # Находим user_id по employee_id
        user = conn.execute('SELECT id FROM users WHERE employee_id = ?', (employee_id,)).fetchone()
        
        if user:
            hashed_password = self.hash_password(new_password)
            conn.execute('UPDATE users SET password = ? WHERE id = ?', (hashed_password, user['id']))
            conn.commit()
        
        conn.close()
    
    def get_user_by_employee_id(self, employee_id):
        """Получение пользователя по ID сотрудника"""
        conn = self.get_connection()
        user = conn.execute('SELECT * FROM users WHERE employee_id = ?', (employee_id,)).fetchone()
        conn.close()
        return user 

    # ========== СООБЩЕНИЯ ==========
    
    def send_message(self, sender_id, receiver_id, subject, content):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO messages (sender_id, receiver_id, subject, content)
            VALUES (?, ?, ?, ?)
        ''', (sender_id, receiver_id, subject, content))
        
        conn.commit()
        message_id = cursor.lastrowid
        conn.close()
        return message_id
    
    def get_messages(self, user_id, inbox=True):
        conn = self.get_connection()
        if inbox:
            messages = conn.execute('''
                SELECT m.*, u1.username as sender_name
                FROM messages m
                JOIN users u1 ON m.sender_id = u1.id
                WHERE m.receiver_id = ?
                ORDER BY m.created_at DESC
            ''', (user_id,)).fetchall()
        else:
            messages = conn.execute('''
                SELECT m.*, u2.username as receiver_name
                FROM messages m
                JOIN users u2 ON m.receiver_id = u2.id
                WHERE m.sender_id = ?
                ORDER BY m.created_at DESC
            ''', (user_id,)).fetchall()
        conn.close()
        return messages
    
    def mark_message_as_read(self, message_id):
        conn = self.get_connection()
        conn.execute('UPDATE messages SET is_read = 1 WHERE id = ?', (message_id,))
        conn.commit()
        conn.close()
    
    # ========== СТАТИСТИКА ==========
    
    def get_stats(self):
        conn = self.get_connection()
        
        stats = {
            'total_employees': conn.execute('SELECT COUNT(*) FROM employees').fetchone()[0],
            'active_employees': conn.execute("SELECT COUNT(*) FROM employees WHERE status = 'active'").fetchone()[0],
            'on_mission': conn.execute("SELECT COUNT(*) FROM employees WHERE status = 'on_mission'").fetchone()[0],
            'total_tasks': conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
            'tasks_pending': conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'pending'").fetchone()[0],
            'tasks_completed': conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'completed'").fetchone()[0],
            'total_reports': conn.execute("SELECT COUNT(*) FROM work_reports").fetchone()[0]
        }
        
        # Расчет эффективности
        total_hours = conn.execute("SELECT SUM(hours_worked) FROM work_reports").fetchone()[0] or 0
        total_tasks_completed = conn.execute("SELECT SUM(tasks_completed) FROM work_reports").fetchone()[0] or 0
        
        if total_hours > 0:
            stats['efficiency'] = round((total_tasks_completed / total_hours) * 100, 2)
        else:
            stats['efficiency'] = 0
        
        conn.close()
        return stats
    
    def get_employee_stats(self, employee_id):
        conn = self.get_connection()
        
        stats = {
            'total_tasks': conn.execute("SELECT COUNT(*) FROM tasks WHERE employee_id = ?", (employee_id,)).fetchone()[0],
            'tasks_pending': conn.execute("SELECT COUNT(*) FROM tasks WHERE employee_id = ? AND status = 'pending'", (employee_id,)).fetchone()[0],
            'tasks_completed': conn.execute("SELECT COUNT(*) FROM tasks WHERE employee_id = ? AND status = 'completed'", (employee_id,)).fetchone()[0],
            'total_reports': conn.execute("SELECT COUNT(*) FROM work_reports WHERE employee_id = ?", (employee_id,)).fetchone()[0],
            'total_hours': conn.execute("SELECT SUM(hours_worked) FROM work_reports WHERE employee_id = ?", (employee_id,)).fetchone()[0] or 0,
            'avg_tasks_per_day': conn.execute("SELECT AVG(tasks_completed) FROM work_reports WHERE employee_id = ?", (employee_id,)).fetchone()[0] or 0
        }
        
        conn.close()
        return stats

# ========== ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ==========

db = Database()

# ========== ДЕКОРАТОРЫ ДОСТУПА ==========

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('Доступ запрещен. Требуются права администратора', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def employee_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login'))
        if session.get('role') != 'employee':
            flash('Доступ разрешен только сотрудникам', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# ========== МАРШРУТЫ АУТЕНТИФИКАЦИИ ==========

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = db.authenticate_user(username, password)
        
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['employee_name'] = user.get('employee_name', 'Администратор')
            
            flash(f'Добро пожаловать, {session["employee_name"]}!', 'success')
            
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('employee_dashboard'))
        else:
            flash('Неверное имя пользователя или пароль', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы успешно вышли из системы', 'success')
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Пароли не совпадают', 'danger')
            return render_template('register.html')
        
        user_id = db.register_user(username, password, email, 'employee')
        
        if user_id:
            flash('Регистрация успешна! Теперь вы можете войти в систему', 'success')
            return redirect(url_for('login'))
        else:
            flash('Имя пользователя или email уже заняты', 'danger')
    
    return render_template('register.html')

# ========== ГЛАВНАЯ СТРАНИЦА ==========

@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('employee_dashboard'))
    else:
        return redirect(url_for('login'))

# ========== АДМИНИСТРАТОР ==========

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    stats = db.get_stats()
    recent_tasks = db.get_all_tasks()[:5]
    employees = db.get_all_employees()
    
    return render_template('admin/dashboard.html', 
                         stats=stats, 
                         recent_tasks=recent_tasks, 
                         employees=employees)

@app.route('/admin/employees')
@admin_required
def admin_employees():
    employees = db.get_all_employees()
    return render_template('admin/employees.html', employees=employees)

@app.route('/admin/add_employee', methods=['GET', 'POST'])
@admin_required
def admin_add_employee():
    if request.method == 'POST':
        try:
            # Данные сотрудника
            employee_data = {
                'name': request.form['name'],
                'position': request.form['position'],
                'department': request.form['department'],
                'phone': request.form['phone'],
                'email': request.form['email'],
                'location': request.form.get('location', ''),
                'status': request.form.get('status', 'active'),
                'hourly_rate': float(request.form.get('hourly_rate', 0))
            }
            
            # Пароль из формы
            password = request.form['password']
            
            # Добавляем сотрудника в БД
            employee_id = db.add_employee(employee_data)
            
            # Создаем учетную запись для сотрудника
            username = employee_data['email']  # Используем email как логин
            success = db.register_user_with_employee(
                username, 
                password, 
                employee_data['email'], 
                'employee', 
                employee_id
            )
            
            if success:
                flash(f'Сотрудник {employee_data["name"]} успешно добавлен! Логин: {username}, Пароль: {password}', 'success')
                return redirect(url_for('admin_employees'))
            else:
                # Если не удалось создать пользователя, удаляем сотрудника
                db.delete_employee(employee_id)
                flash('Ошибка создания учетной записи. Возможно, email уже используется', 'danger')
                
        except Exception as e:
            flash(f'Ошибка при добавлении сотрудника: {str(e)}', 'danger')
    
    return render_template('admin/add_employee.html')

@app.route('/admin/edit_employee/<int:id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_employee(id):
    if request.method == 'POST':
        try:
            data = {
                'name': request.form['name'],
                'position': request.form['position'],
                'department': request.form['department'],
                'phone': request.form['phone'],
                'email': request.form['email'],
                'location': request.form.get('location', ''),
                'status': request.form.get('status', 'active'),
                'hourly_rate': float(request.form.get('hourly_rate', 0))
            }
            
            db.update_employee(id, data)
            flash('Данные сотрудника обновлены!', 'success')
            return redirect(url_for('admin_employees'))
        except Exception as e:
            flash(f'Ошибка при обновлении данных: {str(e)}', 'danger')
    
    employee = db.get_employee_by_id(id)
    if not employee:
        flash('Сотрудник не найден', 'danger')
        return redirect(url_for('admin_employees'))
    
    return render_template('admin/edit_employee.html', employee=employee)

@app.route('/admin/delete_employee/<int:id>')
@admin_required
def admin_delete_employee(id):
    db.delete_employee(id)
    flash('Сотрудник удален!', 'success')
    return redirect(url_for('admin_employees'))

@app.route('/admin/tasks')
@admin_required
def admin_tasks():
    tasks = db.get_all_tasks()
    employees = db.get_all_employees()
    return render_template('admin/tasks.html', tasks=tasks, employees=employees)

@app.route('/admin/add_task', methods=['POST'])
@admin_required
def admin_add_task():
    try:
        data = {
            'title': request.form['title'],
            'description': request.form.get('description', ''),
            'employee_id': request.form['employee_id'],
            'priority': request.form.get('priority', 'medium'),
            'due_date': request.form.get('due_date')
        }
        
        db.add_task(data)
        flash('Задача добавлена!', 'success')
    except Exception as e:
        flash(f'Ошибка: {str(e)}', 'danger')
    
    return redirect(url_for('admin_tasks'))

@app.route('/admin/reports')
@admin_required
def admin_reports():
    reports = db.get_work_reports()
    return render_template('admin/reports.html', reports=reports)

@app.route('/admin/analytics')
@admin_required
def admin_analytics():
    stats = db.get_stats()
    employees = db.get_all_employees()
    
    employee_stats = []
    for emp in employees:
        emp_stats = db.get_employee_stats(emp['id'])
        employee_stats.append({
            'id': emp['id'],
            'name': emp['name'],
            'position': emp['position'],
            **emp_stats
        })
    
    return render_template('admin/analytics.html', 
                         stats=stats, 
                         employee_stats=employee_stats)

# ========== СОТРУДНИК ==========

@app.route('/employee/dashboard')
@employee_required
def employee_dashboard():
    employee = db.get_employee_by_user_id(session['user_id'])
    if not employee:
        flash('Профиль сотрудника не найден', 'danger')
        return redirect(url_for('logout'))
    
    stats = db.get_employee_stats(employee['id'])
    tasks = db.get_all_tasks(employee['id'])
    recent_reports = db.get_work_reports(employee['id'])[:3]
    
    return render_template('employee/dashboard.html',
                         employee=employee,
                         stats=stats,
                         tasks=tasks[:5],
                         recent_reports=recent_reports)

@app.route('/employee/tasks')
@employee_required
def employee_tasks():
    employee = db.get_employee_by_user_id(session['user_id'])
    tasks = db.get_all_tasks(employee['id'])
    return render_template('employee/tasks.html', tasks=tasks)

@app.route('/employee/task/<int:task_id>', methods=['GET', 'POST'])
@employee_required
def employee_task_detail(task_id):
    task = db.get_task_by_id(task_id)
    employee = db.get_employee_by_user_id(session['user_id'])
    
    if not task or task['employee_id'] != employee['id']:
        flash('Задача не найдена', 'danger')
        return redirect(url_for('employee_tasks'))
    
    if request.method == 'POST':
        status = request.form['status']
        feedback = request.form.get('feedback', '')
        
        db.update_task_status(task_id, status, feedback)
        flash('Статус задачи обновлен!', 'success')
        return redirect(url_for('employee_task_detail', task_id=task_id))
    
    return render_template('employee/task_detail.html', task=task)

@app.route('/employee/reports', methods=['GET', 'POST'])
@employee_required
def employee_reports():
    employee = db.get_employee_by_user_id(session['user_id'])
    
    if request.method == 'POST':
        date = request.form['date']
        hours_worked = float(request.form['hours_worked'])
        tasks_completed = int(request.form['tasks_completed'])
        description = request.form['description']
        
        db.add_work_report(employee['id'], date, hours_worked, tasks_completed, description)
        flash('Отчет успешно добавлен!', 'success')
        return redirect(url_for('employee_reports'))
    
    reports = db.get_work_reports(employee['id'])
    
    # Добавляем today для формы
    today = datetime.date.today().isoformat()
    
    return render_template('employee/reports.html', 
                         reports=reports,
                         today=today)


@app.route('/employee/profile')
@employee_required
def employee_profile():
    employee = db.get_employee_by_user_id(session['user_id'])
    if not employee:
        flash('Профиль сотрудника не найден', 'danger')
        return redirect(url_for('logout'))
    
    stats = db.get_employee_stats(employee['id'])
    
    return render_template('employee/profile.html',
                         employee=employee,
                         stats=stats)

@app.route('/employee/change_password', methods=['POST'])
@employee_required
def employee_change_password():
    try:
        data = request.get_json()
        old_password = data.get('old_password')
        new_password = data.get('new_password')
        
        if not old_password or not new_password:
            return jsonify({'success': False, 'error': 'Все поля обязательны'}), 400
        
        # Получаем текущего пользователя
        conn = db.get_connection()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        conn.close()
        
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'}), 404
        
        # Проверяем старый пароль
        if user['password'] != db.hash_password(old_password):
            return jsonify({'success': False, 'error': 'Неверный старый пароль'}), 400
        
        # Обновляем пароль
        conn = db.get_connection()
        hashed_password = db.hash_password(new_password)
        conn.execute('UPDATE users SET password = ? WHERE id = ?', (hashed_password, session['user_id']))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Пароль успешно изменен'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/employee/messages')
@employee_required
def employee_messages():
    messages = db.get_messages(session['user_id'], inbox=True)
    sent_messages = db.get_messages(session['user_id'], inbox=False)
    return render_template('employee/messages.html', 
                         messages=messages, 
                         sent_messages=sent_messages)

@app.route('/employee/send_message', methods=['POST'])
@employee_required
def employee_send_message():
    receiver_id = request.form['receiver_id']
    subject = request.form['subject']
    content = request.form['content']
    
    db.send_message(session['user_id'], receiver_id, subject, content)
    flash('Сообщение отправлено!', 'success')
    return redirect(url_for('employee_messages'))

# ========== СТАРЫЕ МАРШРУТЫ ДЛЯ СОВМЕСТИМОСТИ ==========

@app.route('/employees')
@admin_required
def employees():
    return redirect(url_for('admin_employees'))

@app.route('/add_employee', methods=['GET', 'POST'])
@admin_required
def add_employee():
    return redirect(url_for('admin_add_employee'))

@app.route('/edit_employee/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_employee(id):
    return redirect(url_for('admin_edit_employee', id=id))

@app.route('/delete_employee/<int:id>')
@admin_required
def delete_employee(id):
    return redirect(url_for('admin_delete_employee', id=id))

@app.route('/tasks')
@admin_required
def tasks():
    return redirect(url_for('admin_tasks'))

@app.route('/add_task', methods=['POST'])
@admin_required
def add_task():
    return redirect(url_for('admin_add_task'))

@app.route('/update_task_status/<int:id>', methods=['POST'])
@admin_required
def update_task_status(id):
    db.update_task_status(id, request.form['status'])
    flash('Статус задачи обновлен!', 'success')
    return redirect(url_for('admin_tasks'))

@app.route('/delete_task/<int:id>')
@admin_required
def delete_task(id):
    db.delete_task(id)
    flash('Задача удалена!', 'success')
    return redirect(url_for('admin_tasks'))

# ========== API МАРШРУТЫ ==========

@app.route('/api/update_location/<int:id>', methods=['POST'])
@login_required
def update_location(id):
    try:
        data = request.get_json()
        
        # Проверяем права доступа
        if session.get('role') == 'employee':
            employee = db.get_employee_by_user_id(session['user_id'])
            if employee['id'] != id:
                return jsonify({'error': 'Доступ запрещен'}), 403
        
        conn = db.get_connection()
        conn.execute('''
            UPDATE employees 
            SET latitude = ?, longitude = ?, location = ?
            WHERE id = ?
        ''', (data.get('latitude'), data.get('longitude'), data.get('location', ''), id))
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Location updated'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/employee_locations')
@login_required
def employee_locations():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Доступ запрещен'}), 403
    
    conn = db.get_connection()
    locations = conn.execute('''
        SELECT id, name, position, latitude, longitude, status 
        FROM employees 
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    ''').fetchall()
    conn.close()
    
    result = []
    for loc in locations:
        result.append({
            'id': loc['id'],
            'name': loc['name'],
            'position': loc['position'],
            'latitude': loc['latitude'],
            'longitude': loc['longitude'],
            'status': loc['status']
        })
    return jsonify(result)

@app.route('/employee/update_profile', methods=['POST'])
@employee_required
def employee_update_profile():
    try:
        employee = db.get_employee_by_user_id(session['user_id'])
        if not employee:
            return jsonify({'success': False, 'error': 'Сотрудник не найден'}), 404
        
        data = request.get_json()
        
        # Обновляем данные сотрудника
        conn = db.get_connection()
        conn.execute('''
            UPDATE employees 
            SET name = ?, position = ?, department = ?, phone = ?, email = ?, location = ?
            WHERE id = ?
        ''', (
            data.get('name'),
            data.get('position'),
            data.get('department'),
            data.get('phone'),
            data.get('email'),
            data.get('location'),
            employee['id']
        ))
        
        # Если указан новый пароль, обновляем его
        new_password = data.get('new_password')
        if new_password and new_password.strip():
            # Получаем user_id
            user = conn.execute('SELECT id FROM users WHERE employee_id = ?', (employee['id'],)).fetchone()
            if user:
                hashed_password = db.hash_password(new_password)
                conn.execute('UPDATE users SET password = ? WHERE id = ?', (hashed_password, user['id']))
        
        conn.commit()
        conn.close()
        
        # Обновляем имя в сессии
        session['employee_name'] = data.get('name')
        
        return jsonify({'success': True, 'message': 'Профиль обновлен'})
    except sqlite3.IntegrityError as e:
        return jsonify({'success': False, 'error': 'Email или телефон уже используются'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/stats')
@login_required
def get_stats_api():
    if session.get('role') == 'admin':
        stats = db.get_stats()
    else:
        employee = db.get_employee_by_user_id(session['user_id'])
        stats = db.get_employee_stats(employee['id'])
    
    return jsonify(stats)

# ========== ЗАПУСК СЕРВЕРА ==========

if __name__ == '__main__':
    print("\n" + "="*60)
    print("СИСТЕМА УПРАВЛЕНИЯ МОБИЛЬНЫМИ СОТРУДНИКАМИ")
    print("="*60)
    print("Сервер запущен: http://localhost:5000")
    print("\nДоступы для тестирования:")
    print("  • Администратор:")
    print("    Логин: admin")
    print("    Пароль: admin123")
    print("  • Сотрудники:")
    print("    Логин: ivanov (или petrov, sidorova, kozlov)")
    print("    Пароль: employee123")
    print("\nДоступные страницы:")
    print("  • Вход: http://localhost:5000/login")
    print("  • Админ-панель: http://localhost:5000/admin/dashboard")
    print("  • Панель сотрудника: http://localhost:5000/employee/dashboard")
    print("="*60 + "\n")
    
    # Создаем необходимые папки для шаблонов
    os.makedirs('templates/admin', exist_ok=True)
    os.makedirs('templates/employee', exist_ok=True)
    
    app.run(debug=True, host='0.0.0.0', port=5000)