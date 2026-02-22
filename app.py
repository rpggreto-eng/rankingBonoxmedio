from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file, flash
import sqlite3, hashlib, os, json
from datetime import datetime
from functools import wraps
import io

app = Flask(__name__)
app.secret_key = 'arena_ranking_secret_2024_xK9mP2'

# ─── DB: usa ranking.db si existe, si no copia la prefabricada ────────────────
DB_PATH = 'ranking.db'
PREFAB_PATH = 'ranking_prefab.db'

def ensure_db():
    if not os.path.exists(DB_PATH):
        if os.path.exists(PREFAB_PATH):
            import shutil
            shutil.copy(PREFAB_PATH, DB_PATH)
            print(f'[DB] Copiada desde {PREFAB_PATH}')
        else:
            init_db_fresh()
            print('[DB] Creada desde cero')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db_fresh():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        discord TEXT UNIQUE NOT NULL,
        minecraft_nick TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE,
        total_points INTEGER DEFAULT 0,
        season_points INTEGER DEFAULT 0,
        created_at TEXT,
        bio TEXT DEFAULT ""
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        event_date TEXT NOT NULL,
        description TEXT,
        created_by TEXT,
        created_at TEXT,
        season INTEGER DEFAULT 1
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS point_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        event_id INTEGER,
        points INTEGER NOT NULL,
        position INTEGER,
        reason TEXT,
        added_by TEXT NOT NULL,
        added_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(event_id) REFERENCES events(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS seasons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        start_date TEXT,
        end_date TEXT,
        is_active INTEGER DEFAULT 1
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS admin_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        created_at TEXT
    )''')

    c.execute("INSERT INTO seasons (name, start_date, is_active) VALUES (?,?,1)", ('Temporada 1', now))

    pw = hashlib.sha256('admin123'.encode()).hexdigest()
    for i in range(1, 14):
        c.execute('INSERT OR IGNORE INTO admin_accounts (username, password, created_at) VALUES (?,?,?)',
                  (f'admin{i}', pw, now))

    conn.commit()
    conn.close()

POINTS_SCALE = {
    1: 25, 2: 15, 3: 12, 4: 10,
    **{i: 5 for i in range(5, 9)},
    **{i: 4 for i in range(9, 16)},
    **{i: 3 for i in range(16, 32)},
    **{i: 2 for i in range(32, 65)},
    **{i: 1 for i in range(65, 129)},
}

def get_pts(pos):
    return POINTS_SCALE.get(pos, 0)

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_id' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

# ─── PUBLIC ROUTES ────────────────────────────────────────────────────────────

@app.route('/')
def index():
    conn = get_db()
    users = conn.execute(
        "SELECT username, discord, minecraft_nick, total_points, season_points FROM users ORDER BY total_points DESC LIMIT 50"
    ).fetchall()
    total_users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
    total_events = conn.execute("SELECT COUNT(*) as c FROM events").fetchone()['c']
    season = conn.execute("SELECT * FROM seasons WHERE is_active=1 ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return render_template('index.html', users=users, total_users=total_users,
                           total_events=total_events, season=season)

@app.route('/ranking')
def ranking():
    conn = get_db()
    users = conn.execute(
        "SELECT username, discord, minecraft_nick, total_points, season_points FROM users ORDER BY total_points DESC"
    ).fetchall()
    conn.close()
    return render_template('ranking.html', users=users)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username  = request.form.get('username', '').strip()
        password  = request.form.get('password', '').strip()
        discord   = request.form.get('discord', '').strip()
        minecraft = request.form.get('minecraft_nick', '').strip()
        email     = request.form.get('email', '').strip() or None

        if not all([username, password, discord, minecraft]):
            return render_template('register.html', error='Todos los campos marcados con * son obligatorios.')
        if len(password) < 6:
            return render_template('register.html', error='La contraseña debe tener mínimo 6 caracteres.')

        conn = get_db()
        existing = conn.execute(
            "SELECT id FROM users WHERE username=? OR discord=? OR LOWER(minecraft_nick)=LOWER(?)",
            (username, discord, minecraft)
        ).fetchone()
        if existing:
            conn.close()
            return render_template('register.html', error='El usuario, Discord o Nick de Minecraft ya está registrado.')
        if email:
            if conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
                conn.close()
                return render_template('register.html', error='Ese email ya está en uso.')

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(
            "INSERT INTO users (username, password, discord, minecraft_nick, email, created_at) VALUES (?,?,?,?,?,?)",
            (username, hash_pw(password), discord, minecraft, email, now)
        )
        conn.commit()
        conn.close()
        return redirect(url_for('login', success='¡Cuenta creada! Ya puedes iniciar sesión.'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, hash_pw(password))
        ).fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('profile'))
        return render_template('login.html', error='Usuario o contraseña incorrectos.')
    return render_template('login.html', success=request.args.get('success'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/profile')
@login_required
def profile():
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    logs = conn.execute('''
        SELECT pl.*, e.name as event_name
        FROM point_logs pl
        LEFT JOIN events e ON pl.event_id = e.id
        WHERE pl.user_id=?
        ORDER BY pl.added_at DESC LIMIT 30
    ''', (session['user_id'],)).fetchall()
    rank = conn.execute(
        "SELECT COUNT(*)+1 as rank FROM users WHERE total_points > (SELECT total_points FROM users WHERE id=?)",
        (session['user_id'],)
    ).fetchone()['rank']
    total_users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
    conn.close()
    return render_template('profile.html', user=user, logs=logs, rank=rank, total_users=total_users)

@app.route('/profile/edit', methods=['POST'])
@login_required
def profile_edit():
    minecraft = request.form.get('minecraft_nick', '').strip()
    email     = request.form.get('email', '').strip() or None
    bio       = request.form.get('bio', '').strip()

    conn = get_db()
    # Check minecraft nick not taken by someone else
    if minecraft:
        conflict = conn.execute(
            "SELECT id FROM users WHERE LOWER(minecraft_nick)=LOWER(?) AND id!=?",
            (minecraft, session['user_id'])
        ).fetchone()
        if conflict:
            conn.close()
            return jsonify({'error': 'Ese Nick de Minecraft ya está registrado por otro usuario.'})
    if email:
        conflict = conn.execute(
            "SELECT id FROM users WHERE email=? AND id!=?",
            (email, session['user_id'])
        ).fetchone()
        if conflict:
            conn.close()
            return jsonify({'error': 'Ese email ya está en uso.'})

    conn.execute(
        "UPDATE users SET minecraft_nick=?, email=?, bio=? WHERE id=?",
        (minecraft, email, bio, session['user_id'])
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/profile/change_password', methods=['POST'])
@login_required
def change_password():
    old_pw  = request.form.get('old_password', '').strip()
    new_pw  = request.form.get('new_password', '').strip()

    if len(new_pw) < 6:
        return jsonify({'error': 'La nueva contraseña debe tener mínimo 6 caracteres.'})

    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE id=? AND password=?",
        (session['user_id'], hash_pw(old_pw))
    ).fetchone()
    if not user:
        conn.close()
        return jsonify({'error': 'Contraseña actual incorrecta.'})

    conn.execute("UPDATE users SET password=? WHERE id=?", (hash_pw(new_pw), session['user_id']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ─── ADMIN ROUTES ─────────────────────────────────────────────────────────────

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        conn = get_db()
        admin = conn.execute(
            "SELECT * FROM admin_accounts WHERE username=? AND password=?",
            (username, hash_pw(password))
        ).fetchone()
        conn.close()
        if admin:
            session['admin_id'] = admin['id']
            session['admin_username'] = admin['username']
            return redirect(url_for('admin_dashboard'))
        return render_template('admin_login.html', error='Credenciales incorrectas.')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_id', None)
    session.pop('admin_username', None)
    return redirect(url_for('admin_login'))

@app.route('/admin')
@admin_required
def admin_dashboard():
    conn = get_db()
    total_users  = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
    total_events = conn.execute("SELECT COUNT(*) as c FROM events").fetchone()['c']
    total_points = conn.execute("SELECT SUM(points) as s FROM point_logs").fetchone()['s'] or 0
    recent_logs  = conn.execute('''
        SELECT pl.*, u.username, u.minecraft_nick, e.name as event_name
        FROM point_logs pl
        JOIN users u ON pl.user_id = u.id
        LEFT JOIN events e ON pl.event_id = e.id
        ORDER BY pl.added_at DESC LIMIT 15
    ''').fetchall()
    events = conn.execute("SELECT * FROM events ORDER BY event_date DESC LIMIT 30").fetchall()
    top3   = conn.execute(
        "SELECT username, minecraft_nick, total_points FROM users ORDER BY total_points DESC LIMIT 3"
    ).fetchall()
    conn.close()
    return render_template('admin_dashboard.html',
        total_users=total_users, total_events=total_events,
        total_points=total_points, recent_logs=recent_logs,
        events=events, top3=top3,
        admin_username=session.get('admin_username'))

@app.route('/admin/search_user')
@admin_required
def admin_search_user():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    conn = get_db()
    users = conn.execute(
        "SELECT id, username, discord, minecraft_nick, total_points, season_points FROM users WHERE username LIKE ? OR minecraft_nick LIKE ? OR discord LIKE ? LIMIT 10",
        (f'%{q}%', f'%{q}%', f'%{q}%')
    ).fetchall()
    conn.close()
    return jsonify([dict(u) for u in users])

@app.route('/admin/user/<int:user_id>')
@admin_required
def admin_user_detail(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    logs = conn.execute('''
        SELECT pl.*, e.name as event_name
        FROM point_logs pl
        LEFT JOIN events e ON pl.event_id = e.id
        WHERE pl.user_id=?
        ORDER BY pl.added_at DESC
    ''', (user_id,)).fetchall()
    rank = conn.execute(
        "SELECT COUNT(*)+1 as r FROM users WHERE total_points > (SELECT total_points FROM users WHERE id=?)",
        (user_id,)
    ).fetchone()['r']
    conn.close()
    if not user:
        return jsonify({'error': 'Usuario no encontrado'}), 404
    return jsonify({'user': dict(user), 'logs': [dict(l) for l in logs], 'rank': rank})

@app.route('/admin/add_points', methods=['POST'])
@admin_required
def admin_add_points():
    data     = request.json
    user_id  = data.get('user_id')
    points   = int(data.get('points', 0))
    event_id = data.get('event_id') or None
    position = data.get('position') or None
    reason   = data.get('reason', '')

    if not user_id or points == 0:
        return jsonify({'error': 'Datos incompletos'}), 400

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        conn.close()
        return jsonify({'error': 'Usuario no encontrado'}), 404

    conn.execute(
        "INSERT INTO point_logs (user_id, event_id, points, position, reason, added_by, added_at) VALUES (?,?,?,?,?,?,?)",
        (user_id, event_id, points, position, reason, session['admin_username'], now)
    )
    conn.execute(
        "UPDATE users SET total_points=total_points+?, season_points=season_points+? WHERE id=?",
        (points, points, user_id)
    )
    conn.commit()
    new_total = conn.execute("SELECT total_points FROM users WHERE id=?", (user_id,)).fetchone()['total_points']
    conn.close()
    return jsonify({'success': True, 'new_total': new_total})

@app.route('/admin/remove_points', methods=['POST'])
@admin_required
def admin_remove_points():
    data    = request.json
    log_id  = data.get('log_id')
    conn = get_db()
    log = conn.execute("SELECT * FROM point_logs WHERE id=?", (log_id,)).fetchone()
    if not log:
        conn.close()
        return jsonify({'error': 'Log no encontrado'}), 404
    conn.execute("DELETE FROM point_logs WHERE id=?", (log_id,))
    conn.execute(
        "UPDATE users SET total_points=MAX(0,total_points-?), season_points=MAX(0,season_points-?) WHERE id=?",
        (log['points'], log['points'], log['user_id'])
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/admin/add_event', methods=['POST'])
@admin_required
def admin_add_event():
    data  = request.json
    name  = data.get('name', '').strip()
    edate = data.get('event_date', '').strip()
    desc  = data.get('description', '').strip()
    if not name or not edate:
        return jsonify({'error': 'Nombre y fecha requeridos'}), 400
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()
    cur  = conn.execute(
        "INSERT INTO events (name, event_date, description, created_by, created_at) VALUES (?,?,?,?,?)",
        (name, edate, desc, session['admin_username'], now)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'event_id': cur.lastrowid, 'name': name, 'date': edate})

@app.route('/admin/bulk_points', methods=['POST'])
@admin_required
def admin_bulk_points():
    data     = request.json
    event_id = data.get('event_id')
    results  = data.get('results', [])
    if not event_id or not results:
        return jsonify({'error': 'Datos incompletos'}), 400

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()
    assigned  = []
    not_found = []
    already   = []

    for r in results:
        nick   = r.get('minecraft_nick', '').strip()
        pos    = int(r.get('position', 999))
        points = get_pts(pos)

        user = conn.execute(
            "SELECT * FROM users WHERE LOWER(minecraft_nick)=LOWER(?)", (nick,)
        ).fetchone()

        if not user:
            not_found.append(nick)
            continue

        # Check if already assigned for this event
        dup = conn.execute(
            "SELECT id FROM point_logs WHERE user_id=? AND event_id=?",
            (user['id'], event_id)
        ).fetchone()
        if dup:
            already.append(nick)
            continue

        if points > 0:
            conn.execute(
                "INSERT INTO point_logs (user_id, event_id, points, position, reason, added_by, added_at) VALUES (?,?,?,?,?,?,?)",
                (user['id'], event_id, points, pos, f'Posición #{pos}', session['admin_username'], now)
            )
            conn.execute(
                "UPDATE users SET total_points=total_points+?, season_points=season_points+? WHERE id=?",
                (points, points, user['id'])
            )
            assigned.append({'nick': nick, 'points': points, 'position': pos})

    conn.commit()
    conn.close()
    return jsonify({'assigned': assigned, 'not_found': not_found, 'already': already})

@app.route('/admin/ocr_image', methods=['POST'])
@admin_required
def admin_ocr_image():
    try:
        import pytesseract
        from PIL import Image
        import re

        file = request.files.get('image')
        if not file:
            return jsonify({'error': 'No se recibió imagen'}), 400

        img  = Image.open(file.stream)
        text = pytesseract.image_to_string(img, lang='spa+eng')
        lines   = text.strip().split('\n')
        results = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            match = re.match(r'^[#\.]?(\d+)[.\s\-:]+(.+)$', line)
            if match:
                pos  = int(match.group(1))
                name = match.group(2).strip()
                if 1 <= pos <= 128 and name:
                    results.append({'position': pos, 'minecraft_nick': name})
        return jsonify({'text': text, 'parsed': results})
    except ImportError:
        return jsonify({'error': 'Instala pytesseract y Tesseract-OCR para usar esta función.'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/export_ranking')
@admin_required
def admin_export_ranking():
    import csv
    conn = get_db()
    users = conn.execute(
        "SELECT username, discord, minecraft_nick, total_points, season_points, created_at FROM users ORDER BY total_points DESC"
    ).fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['#', 'Usuario', 'Discord', 'Nick Minecraft', 'Puntos Totales', 'Puntos Temporada', 'Registro'])
    for i, u in enumerate(users, 1):
        writer.writerow([i, u['username'], u['discord'], u['minecraft_nick'],
                         u['total_points'], u['season_points'], u['created_at']])
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'ranking_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'
    )

@app.route('/admin/get_events')
@admin_required
def admin_get_events():
    conn = get_db()
    events = conn.execute("SELECT * FROM events ORDER BY event_date DESC").fetchall()
    conn.close()
    return jsonify([dict(e) for e in events])

@app.route('/admin/delete_user', methods=['POST'])
@admin_required
def admin_delete_user():
    data    = request.json
    user_id = data.get('user_id')
    conn = get_db()
    conn.execute("DELETE FROM point_logs WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ─── TEMPORADAS ───────────────────────────────────────────────────────────────

@app.route('/admin/seasons')
@admin_required
def admin_seasons():
    conn = get_db()
    seasons = conn.execute("SELECT * FROM seasons ORDER BY id DESC").fetchall()
    active  = conn.execute("SELECT * FROM seasons WHERE is_active=1 ORDER BY id DESC LIMIT 1").fetchone()
    total_users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
    conn.close()
    return render_template('seasons.html',
        seasons=seasons, active=active,
        total_users=total_users,
        admin_username=session.get('admin_username'))

@app.route('/admin/seasons/create', methods=['POST'])
@admin_required
def admin_season_create():
    data = request.json
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'El nombre es requerido'}), 400
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO seasons (name, start_date, is_active) VALUES (?,?,0)",
        (name, now)
    )
    conn.commit()
    season_id = cur.lastrowid
    conn.close()
    return jsonify({'success': True, 'id': season_id, 'name': name})

@app.route('/admin/seasons/activate', methods=['POST'])
@admin_required
def admin_season_activate():
    """Activa una temporada (no resetea puntos todavía)"""
    data = request.json
    season_id = data.get('season_id')
    conn = get_db()
    # Desactivar todas
    conn.execute("UPDATE seasons SET is_active=0")
    # Activar la seleccionada
    conn.execute("UPDATE seasons SET is_active=1 WHERE id=?", (season_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/admin/seasons/end', methods=['POST'])
@admin_required
def admin_season_end():
    """
    Termina la temporada activa:
    1. Guarda snapshot del ranking actual
    2. Resetea season_points de todos a 0
    3. Cierra la temporada con fecha de fin
    4. Activa la nueva temporada indicada
    """
    data          = request.json
    current_id    = data.get('current_id')
    new_season_id = data.get('new_season_id')

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()

    # Guardar snapshot en point_logs como registro histórico
    users = conn.execute(
        "SELECT id, username, season_points FROM users WHERE season_points > 0"
    ).fetchall()

    conn.execute("UPDATE seasons SET is_active=0, end_date=? WHERE id=?", (now, current_id))

    # Resetear puntos de temporada
    conn.execute("UPDATE users SET season_points=0")

    # Activar nueva temporada si se especificó
    if new_season_id:
        conn.execute("UPDATE seasons SET is_active=1, start_date=? WHERE id=?", (now, new_season_id))

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'players_reset': len(users)})

@app.route('/admin/seasons/reset_all', methods=['POST'])
@admin_required
def admin_season_reset_all():
    """Reset TOTAL: puntos de temporada Y puntos totales a 0"""
    data = request.json
    confirm = data.get('confirm', '')
    if confirm != 'RESET':
        return jsonify({'error': 'Confirmación incorrecta'}), 400

    conn = get_db()
    conn.execute("UPDATE users SET season_points=0, total_points=0")
    conn.execute("DELETE FROM point_logs")
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/admin/seasons/stats/<int:season_id>')
@admin_required
def admin_season_stats(season_id):
    conn = get_db()
    season = conn.execute("SELECT * FROM seasons WHERE id=?", (season_id,)).fetchone()
    # Top jugadores por puntos de temporada
    top = conn.execute(
        "SELECT username, discord, minecraft_nick, season_points, total_points FROM users ORDER BY season_points DESC LIMIT 20"
    ).fetchall()
    events = conn.execute(
        "SELECT * FROM events WHERE season=? ORDER BY event_date DESC", (season_id,)
    ).fetchall()
    total_pts = conn.execute("SELECT SUM(season_points) as s FROM users").fetchone()['s'] or 0
    conn.close()
    return jsonify({
        'season': dict(season) if season else {},
        'top': [dict(u) for u in top],
        'events': [dict(e) for e in events],
        'total_pts': total_pts
    })

if __name__ == '__main__':
    ensure_db()
    app.run(debug=True, port=5000)