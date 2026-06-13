import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime

app = Flask(__name__)

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
        montant INTEGER NOT NULL,
        description TEXT DEFAULT ''
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS paiements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collecte_id INTEGER NOT NULL,
        membre_id INTEGER NOT NULL,
        present INTEGER DEFAULT 0,
        a_paye INTEGER DEFAULT 0,
        rembourse INTEGER DEFAULT 0,
        date_remboursement TEXT
    )
    """)

    conn.commit()
    conn.close()


init_db()

# -----------------------------
# ACCUEIL / DASHBOARD
# -----------------------------
@app.route('/')
def home():
    conn = get_db()

    membres_count = conn.execute(
        "SELECT COUNT(*) FROM membres"
    ).fetchone()[0]

    collectes_count = conn.execute(
        "SELECT COUNT(*) FROM collectes"
    ).fetchone()[0]

    total_collecte = conn.execute("""
        SELECT COALESCE(SUM(c.montant), 0)
        FROM paiements p
        JOIN collectes c ON p.collecte_id = c.id
        WHERE p.a_paye = 1
    """).fetchone()[0]

    total_dettes = conn.execute("""
        SELECT COALESCE(SUM(c.montant), 0)
        FROM paiements p
        JOIN collectes c ON p.collecte_id = c.id
        WHERE p.a_paye = 0 AND p.rembourse = 0
    """).fetchone()[0]

    derniere_collecte = conn.execute(
        "SELECT date_collecte, montant FROM collectes ORDER BY date_collecte DESC LIMIT 1"
    ).fetchone()

    rows = conn.execute(
        "SELECT date_collecte, montant FROM collectes ORDER BY date_collecte ASC"
    ).fetchall()

    dates = [r["date_collecte"] for r in rows]
    montants = [r["montant"] for r in rows]

    top_debiteurs = conn.execute("""
        SELECT m.nom, COUNT(p.id) as nb_dettes,
               COALESCE(SUM(c.montant), 0) as total_dette
        FROM paiements p
        JOIN membres m ON p.membre_id = m.id
        JOIN collectes c ON p.collecte_id = c.id
        WHERE p.a_paye = 0 AND p.rembourse = 0
        GROUP BY m.id
        ORDER BY total_dette DESC
        LIMIT 5
    """).fetchall()

    conn.close()

    return render_template('dashboard.html',
        membres_count=membres_count,
        collectes_count=collectes_count,
        total_collecte=total_collecte,
        total_dettes=total_dettes,
        derniere_collecte=derniere_collecte,
        dates=dates,
        montants=montants,
        top_debiteurs=top_debiteurs)

# -----------------------------
# MEMBRES
# -----------------------------
@app.route('/membres')
def membres():
    conn = get_db()

    membres = conn.execute("""
        SELECT m.*,
               COALESCE(SUM(CASE WHEN p.a_paye=0 AND p.rembourse=0
                                 THEN c.montant ELSE 0 END), 0) as dette_totale
        FROM membres m
        LEFT JOIN paiements p ON m.id = p.membre_id
        LEFT JOIN collectes c ON p.collecte_id = c.id
        GROUP BY m.id
        ORDER BY m.nom ASC
    """).fetchall()

    conn.close()
    return render_template('membres.html', membres=membres)


@app.route('/add_membre', methods=['POST'])
def add_membre():
    nom = request.form['nom'].strip()
    if nom:
        conn = get_db()
        conn.execute("INSERT INTO membres (nom) VALUES (?)", (nom,))
        conn.commit()
        conn.close()
    return redirect(url_for('membres'))


@app.route('/delete_membre/<int:id>', methods=['POST'])
def delete_membre(id):
    conn = get_db()
    conn.execute("DELETE FROM paiements WHERE membre_id = ?", (id,))
    conn.execute("DELETE FROM membres WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('membres'))

# -----------------------------
# COLLECTES
# -----------------------------
@app.route('/collecte', methods=['GET', 'POST'])
def collecte():
    conn = get_db()

    if request.method == 'POST':
        date = request.form['date']
        montant = int(request.form['montant'])
        description = request.form.get('description', '').strip()
        payeurs = request.form.getlist('payeurs')

        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO collectes (date_collecte, montant, description) VALUES (?, ?, ?)",
            (date, montant, description)
        )
        collecte_id = cursor.lastrowid

        membres = conn.execute("SELECT * FROM membres").fetchall()

        for m in membres:
            mid = str(m['id'])
            a_paye = 1 if mid in payeurs else 0
            conn.execute(
                "INSERT INTO paiements (collecte_id, membre_id, a_paye) VALUES (?, ?, ?)",
                (collecte_id, m['id'], a_paye)
            )

        conn.commit()
        conn.close()
        return redirect(url_for('collectes'))

    membres = conn.execute("SELECT * FROM membres ORDER BY nom").fetchall()
    conn.close()
    today = datetime.today().strftime('%Y-%m-%d')
    return render_template("collecte.html", membres=membres, today=today)


@app.route('/collectes')
def collectes():
    conn = get_db()

    data = conn.execute("""
    SELECT c.id, c.date_collecte, c.montant, c.description,
           COALESCE(SUM(p.present), 0) as total_presents,
           COALESCE(SUM(p.a_paye), 0) as total_paye,
           COUNT(p.id) as total_membres,
           COALESCE(SUM(CASE WHEN p.a_paye=0 AND p.rembourse=0
                             THEN 1 ELSE 0 END), 0) as total_dettes
    FROM collectes c
    LEFT JOIN paiements p ON c.id = p.collecte_id
    GROUP BY c.id
    ORDER BY c.date_collecte DESC
    """).fetchall()

    conn.close()
    return render_template('collectes.html', collectes=data)


@app.route('/collecte/<int:id>')
def detail_collecte(id):
    conn = get_db()

    c = conn.execute(
        "SELECT * FROM collectes WHERE id = ?", (id,)
    ).fetchone()

    if not c:
        return redirect(url_for('collectes'))

    details = conn.execute("""
        SELECT m.nom, p.present, p.a_paye, p.rembourse
        FROM paiements p
        JOIN membres m ON p.membre_id = m.id
        WHERE p.collecte_id = ?
        ORDER BY m.nom
    """, (id,)).fetchall()

    conn.close()
    return render_template('detail_collecte.html', collecte=c, details=details)


@app.route('/delete_collecte/<int:id>', methods=['POST'])
def delete_collecte(id):
    conn = get_db()
    conn.execute("DELETE FROM paiements WHERE collecte_id = ?", (id,))
    conn.execute("DELETE FROM collectes WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('collectes'))

# -----------------------------
# DETTES
# -----------------------------
@app.route('/dettes')
def dettes():
    conn = get_db()

    resultats = conn.execute("""
        SELECT m.id, m.nom,
               COUNT(p.id) as nb_dettes,
               COALESCE(SUM(c.montant), 0) as total_dette
        FROM membres m
        JOIN paiements p ON m.id = p.membre_id
        JOIN collectes c ON p.collecte_id = c.id
        WHERE p.a_paye = 0 AND p.rembourse = 0
        GROUP BY m.id
        HAVING total_dette > 0
        ORDER BY total_dette DESC
    """).fetchall()

    details = conn.execute("""
        SELECT p.id, m.id as membre_id, m.nom, c.date_collecte, c.montant
        FROM paiements p
        JOIN membres m ON p.membre_id = m.id
        JOIN collectes c ON p.collecte_id = c.id
        WHERE p.a_paye = 0 AND p.rembourse = 0
        ORDER BY m.nom, c.date_collecte
    """).fetchall()

    conn.close()
    return render_template("dettes.html", data=resultats, details=details)


@app.route('/rembourser/<int:id>', methods=['POST'])
def rembourser(id):
    conn = get_db()
    today = datetime.today().strftime('%Y-%m-%d')
    conn.execute(
        "UPDATE paiements SET rembourse = 1, date_remboursement = ? WHERE id = ?",
        (today, id)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('dettes'))


@app.route('/rembourser_tout/<int:membre_id>', methods=['POST'])
def rembourser_tout(membre_id):
    conn = get_db()
    today = datetime.today().strftime('%Y-%m-%d')
    conn.execute("""
        UPDATE paiements
        SET rembourse = 1, date_remboursement = ?
        WHERE membre_id = ?
          AND a_paye = 0
          AND rembourse = 0
    """, (today, membre_id))
    conn.commit()
    conn.close()
    return redirect(url_for('dettes'))

@app.route('/ping')
def ping():
    return "OK", 200

# -----------------------------
# LANCEMENT
# -----------------------------
if __name__ == "__main__":
    app.run(debug=True)