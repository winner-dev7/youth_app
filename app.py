import sqlite3
import os
from flask import Flask, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev")

# -----------------------------
# DECORATEURS (🔴 DOIT ÊTRE EN HAUT)
# -----------------------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return wrapper


def role_required(role):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if session.get('role') != role:
                return "Accès refusé ❌"
            return f(*args, **kwargs)
        return wrapper
    return decorator


# -----------------------------
# CONNEXION DB
# -----------------------------
def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn


# -----------------------------
# INITIALISATION DB
# -----------------------------
def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS membres (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS collectes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_collecte TEXT NOT NULL,
        montant INTEGER NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS paiements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collecte_id INTEGER NOT NULL,
        membre_id INTEGER NOT NULL,
        a_paye INTEGER DEFAULT 0,
        rembourse INTEGER DEFAULT 0
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


init_db()

# -----------------------------
# ACCUEIL
# -----------------------------
@app.route('/')
@login_required
def home():
    conn = get_db()
    membres = conn.execute("SELECT * FROM membres").fetchall()
    conn.close()
    return render_template('index.html', membres=membres)


# -----------------------------
# AJOUT MEMBRE
# -----------------------------
@app.route('/add_membres', methods=['POST'])
@login_required
def add_membre():
    nom = request.form['nom']
    conn = get_db()
    conn.execute("INSERT INTO membres (nom) VALUES (?)", (nom,))
    conn.commit()
    conn.close()
    return redirect('/')


# -----------------------------
# SUPPRESSION MEMBRE
# -----------------------------
@app.route('/delete_membres/<int:id>')
@login_required
def delete_membre(id):
    conn = get_db()
    conn.execute("DELETE FROM membres WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect('/')


# -----------------------------
# CREER COLLECTE
# -----------------------------
@app.route('/collecte', methods=['GET', 'POST'])
@login_required
def collecte():
    conn = get_db()

    if request.method == 'POST':
        date = request.form['date']
        montant = request.form['montant']
        membres_coches = request.form.getlist('membres')

        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO collectes (date_collecte, montant) VALUES (?, ?)",
            (date, montant)
        )
        collecte_id = cursor.lastrowid

        membres = conn.execute("SELECT * FROM membres").fetchall()

        for m in membres:
            a_paye = 1 if str(m['id']) in membres_coches else 0

            conn.execute(
                "INSERT INTO paiements (collecte_id, membre_id, a_paye) VALUES (?, ?, ?)",
                (collecte_id, m['id'], a_paye)
            )

        conn.commit()
        conn.close()
        return redirect('/collectes')

    membres = conn.execute("SELECT * FROM membres").fetchall()
    conn.close()
    return render_template("collecte.html", membres=membres)


# -----------------------------
# HISTORIQUE
# -----------------------------
@app.route('/collectes')
@login_required
def collectes():
    conn = get_db()

    data = conn.execute("""
    SELECT c.id, c.date_collecte, c.montant,
           SUM(p.a_paye) as total_paye,
           COUNT(p.id) as total_membres
    FROM collectes c
    LEFT JOIN paiements p ON c.id = p.collecte_id
    GROUP BY c.id
    ORDER BY c.date_collecte DESC
    """).fetchall()

    conn.close()
    return render_template('collectes.html', collectes=data)


# -----------------------------
# DETTES
# -----------------------------
@app.route('/dettes')
@login_required
def dettes():
    conn = get_db()
    membres = conn.execute("SELECT * FROM membres").fetchall()

    resultats = []

    for m in membres:
        data = conn.execute("""
            SELECT COUNT(*) as absences,
                   SUM(c.montant) as total_dette
            FROM paiements p
            JOIN collectes c ON p.collecte_id = c.id
            WHERE p.membre_id = ?
              AND p.a_paye = 0
              AND p.rembourse = 0
        """, (m['id'],)).fetchone()

        resultats.append({
            "nom": m["nom"],
            "absences": data["absences"] or 0,
            "dette": data["total_dette"] or 0
        })

    details = conn.execute("""
        SELECT p.id, m.nom, c.date_collecte, c.montant
        FROM paiements p
        JOIN membres m ON p.membre_id = m.id
        JOIN collectes c ON p.collecte_id = c.id
        WHERE p.a_paye = 0 AND p.rembourse = 0
    """).fetchall()

    conn.close()
    return render_template("dettes.html", data=resultats, details=details)


# -----------------------------
# REMBOURSEMENT
# -----------------------------
@app.route('/rembourser/<int:id>', methods=['POST'])
@login_required
def rembourser(id):
    conn = get_db()
    conn.execute("UPDATE paiements SET rembourse = 1 WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect('/dettes')


# -----------------------------
# DASHBOARD
# -----------------------------
@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db()

    membres = conn.execute("SELECT COUNT(*) FROM membres").fetchone()[0]
    collectes = conn.execute("SELECT COUNT(*) FROM collectes").fetchone()[0]

    total_collecte = conn.execute("""
        SELECT SUM(c.montant)
        FROM paiements p
        JOIN collectes c ON p.collecte_id = c.id
        WHERE p.a_paye = 1
    """).fetchone()[0] or 0

    total_dettes = conn.execute("""
        SELECT SUM(c.montant)
        FROM paiements p
        JOIN collectes c ON p.collecte_id = c.id
        WHERE p.a_paye = 0 AND p.rembourse = 0
    """).fetchone()[0] or 0

    rows = conn.execute("""
        SELECT date_collecte, montant
        FROM collectes
        ORDER BY date_collecte ASC
    """).fetchall()

    dates = [r["date_collecte"] for r in rows]
    montants = [r["montant"] for r in rows]

    conn.close()

    return render_template("dashboard.html",
                           membres=membres,
                           collectes=collectes,
                           total_collecte=total_collecte,
                           total_dettes=total_dettes,
                           dates=dates,
                           montants=montants)


# -----------------------------
# AUTH
# -----------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        role = request.form['role']

        conn = get_db()
        conn.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            (username, password, role)
        )
        conn.commit()
        conn.close()

        return redirect('/login')

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session['user_id'] = user["id"]
            session['role'] = user["role"]
            return redirect('/dashboard')

        return "Identifiants incorrects ❌"

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# -----------------------------
# LANCEMENT
# -----------------------------
if __name__ == "__main__":
    app.run(debug=True)