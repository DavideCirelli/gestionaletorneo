from flask import Flask, render_template, request, redirect, session
import psycopg2

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Connessione DB
def get_db():
    return psycopg2.connect(
        dbname="torneo",
        user="postgres",
        password="a",
        host="localhost"
    )

# ---------------- HOME ----------------
@app.route("/")
def home():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT m.id, t1.name, t2.name, m.score1, m.score2, m.minute, m.status, m.giornata
        FROM matches m
        JOIN teams t1 ON m.team1_id = t1.id
        JOIN teams t2 ON m.team2_id = t2.id
        ORDER BY m.giornata, m.match_date
    """)

    matches = cur.fetchall()
    conn.close()

    # raggruppa per giornata
    giornate = {}
    for m in matches:
        g = m[7]
        if g not in giornate:
            giornate[g] = []
        giornate[g].append(m)

    return render_template("home.html", giornate=giornate)

# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            "SELECT * FROM users WHERE username=%s AND password=%s",
            (request.form["username"], request.form["password"])
        )

        user = cur.fetchone()
        conn.close()

        if user:
            session["user_id"] = user[0]
            session["role"] = user[3]
            return redirect("/dashboard")

    return render_template("login.html")

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    role = session.get("role")

    if role == "squadra":
        return redirect("/distinta")
    elif role == "commissario":
        return redirect("/commissario")
    elif role == "campo":
        return redirect("/telecomando")
    elif role == "admin":
        return redirect("/admin")

    return redirect("/")

# ---------------- SQUADRA ----------------
@app.route("/distinta", methods=["GET", "POST"])
def squadra():

    if "user_id" not in session:
        return redirect("/login")

    if session.get("role") != "squadra":
        return "Accesso negato", 403

    conn = get_db()
    cur = conn.cursor()

    # squadra utente
    cur.execute(
        "SELECT team_id FROM users WHERE id=%s",
        (session["user_id"],)
    )

    team_id = cur.fetchone()[0]

    # partite squadra
    cur.execute("""
        SELECT m.id, t1.name, t2.name, m.match_date
        FROM matches m
        JOIN teams t1 ON m.team1_id = t1.id
        JOIN teams t2 ON m.team2_id = t2.id
        WHERE m.team1_id = %s OR m.team2_id = %s
        ORDER BY m.match_date
    """, (team_id, team_id))

    matches = cur.fetchall()

    success = False

    players = []
    dirigente = ""
    accompagnatore = ""
    guardialinee = ""

    selected_match = None

    # ---------------- POST ----------------
    if request.method == "POST":

        selected_match = request.form["match_id"]

        players = request.form.getlist("players")

        dirigente = request.form.get("dirigente")
        accompagnatore = request.form.get("accompagnatore")
        guardialinee = request.form.get("guardialinee")

        # controlla se lineup esiste già
        cur.execute("""
            SELECT id
            FROM lineups
            WHERE match_id=%s AND team_id=%s
        """, (selected_match, team_id))

        existing = cur.fetchone()

        # se esiste -> elimina vecchi giocatori
        if existing:

            lineup_id = existing[0]

            cur.execute("""
                DELETE FROM players
                WHERE lineup_id=%s
            """, (lineup_id,))

        else:

            # crea nuova lineup
            cur.execute("""
                INSERT INTO lineups (match_id, team_id)
                VALUES (%s, %s)
                RETURNING id
            """, (selected_match, team_id))

            lineup_id = cur.fetchone()[0]

        # salva giocatori
        for p in players:

            if p.strip():

                cur.execute("""
                    INSERT INTO players (name, lineup_id, role)
                    VALUES (%s, %s, 'player')
                """, (p, lineup_id))

        # dirigente
        if dirigente:

            cur.execute("""
                INSERT INTO players (name, lineup_id, role)
                VALUES (%s, %s, 'dirigente')
            """, (dirigente, lineup_id))

        # accompagnatore
        if accompagnatore:

            cur.execute("""
                INSERT INTO players (name, lineup_id, role)
                VALUES (%s, %s, 'accompagnatore')
            """, (accompagnatore, lineup_id))

        # guardialinee
        if guardialinee:

            cur.execute("""
                INSERT INTO players (name, lineup_id, role)
                VALUES (%s, %s, 'guardialinee')
            """, (guardialinee, lineup_id))

        conn.commit()

        success = True

    # ---------- CARICA DISTINTA ESISTENTE ----------

    if selected_match:

        cur.execute("""
            SELECT id
            FROM lineups
            WHERE match_id=%s AND team_id=%s
        """, (selected_match, team_id))

        lineup = cur.fetchone()

        if lineup:

            lineup_id = lineup[0]

            cur.execute("""
                SELECT name, role
                FROM players
                WHERE lineup_id=%s
            """, (lineup_id,))

            rows = cur.fetchall()

            players = []

            for r in rows:

                name = r[0]
                role = r[1]

                if role == "player":
                    players.append(name)

                elif role == "dirigente":
                    dirigente = name

                elif role == "accompagnatore":
                    accompagnatore = name

                elif role == "guardialinee":
                    guardialinee = name

    conn.close()

    return render_template(
        "squadra.html",
        matches=matches,
        success=success,
        players=players,
        dirigente=dirigente,
        accompagnatore=accompagnatore,
        guardialinee=guardialinee,
        selected_match=selected_match
    )
# ---------------- COMMISSARIO ----------------
@app.route("/commissario", methods=["GET", "POST"])
def commissario():

    conn = get_db()
    cur = conn.cursor()

    # =========================
    # LISTA PARTITE
    # =========================
    cur.execute("""
        SELECT m.id, t1.name, t2.name
        FROM matches m
        JOIN teams t1 ON m.team1_id = t1.id
        JOIN teams t2 ON m.team2_id = t2.id
        ORDER BY m.match_date
    """)
    matches = cur.fetchall()

    selected_match = None

    team1_players = []
    team2_players = []
    team1_staff = []
    team2_staff = []

    # =========================
    # POST
    # =========================
    if request.method == "POST":

        action = request.form.get("action")
        selected_match = request.form.get("match_id")

        # ---------------- SELECT MATCH ----------------
        if action == "select_match" and selected_match:

            # GIOCATORI CASA
            cur.execute("""
                SELECT p.id, p.name, p.number
                FROM players p
                JOIN lineups l ON p.lineup_id = l.id
                WHERE l.match_id = %s
                  AND l.team_id = (SELECT team1_id FROM matches WHERE id=%s)
                  AND p.role='player'
                ORDER BY p.number
            """, (selected_match, selected_match))
            team1_players = cur.fetchall()

            # GIOCATORI OSPITI
            cur.execute("""
                SELECT p.id, p.name, p.number
                FROM players p
                JOIN lineups l ON p.lineup_id = l.id
                WHERE l.match_id = %s
                  AND l.team_id = (SELECT team2_id FROM matches WHERE id=%s)
                  AND p.role='player'
                ORDER BY p.number
            """, (selected_match, selected_match))
            team2_players = cur.fetchall()

            # STAFF CASA
            cur.execute("""
                SELECT name, role
                FROM players p
                JOIN lineups l ON p.lineup_id = l.id
                WHERE l.match_id = %s
                  AND l.team_id = (SELECT team1_id FROM matches WHERE id=%s)
                  AND p.role != 'player'
            """, (selected_match, selected_match))
            team1_staff = cur.fetchall()

            # STAFF OSPITE
            cur.execute("""
                SELECT name, role
                FROM players p
                JOIN lineups l ON p.lineup_id = l.id
                WHERE l.match_id = %s
                  AND l.team_id = (SELECT team2_id FROM matches WHERE id=%s)
                  AND p.role != 'player'
            """, (selected_match, selected_match))
            team2_staff = cur.fetchall()

        # ---------------- SAVE PLAYERS ----------------
        elif action == "save_players":

            player_ids = request.form.getlist("player_id")
            names = request.form.getlist("name")
            numbers = request.form.getlist("number")

            selected_match = request.form.get("match_id")

            for i in range(len(player_ids)):
                cur.execute("""
                    UPDATE players
                    SET name=%s, number=%s
                    WHERE id=%s
                """, (names[i], numbers[i], player_ids[i]))

            conn.commit()

            # ricarica giocatori CASA
            cur.execute("""
                SELECT p.id, p.name, p.number
                FROM players p
                JOIN lineups l ON p.lineup_id = l.id
                WHERE l.match_id = %s
                  AND l.team_id = (SELECT team1_id FROM matches WHERE id=%s)
                  AND p.role='player'
            """, (selected_match, selected_match))
            team1_players = cur.fetchall()

            # ricarica giocatori OSPITI
            cur.execute("""
                SELECT p.id, p.name, p.number
                FROM players p
                JOIN lineups l ON p.lineup_id = l.id
                WHERE l.match_id = %s
                  AND l.team_id = (SELECT team2_id FROM matches WHERE id=%s)
                  AND p.role='player'
            """, (selected_match, selected_match))
            team2_players = cur.fetchall()

    conn.close()

    return render_template(
        "commissario.html",
        matches=matches,
        team1_players=team1_players,
        team2_players=team2_players,
        team1_staff=team1_staff,
        team2_staff=team2_staff,
        selected_match=selected_match
    )
# ---------------- TV ----------------
@app.route("/tv")
def tv():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT m.id,
               t1.name,
               t2.name,
               m.score1,
               m.score2,
               m.elapsed_seconds,
               m.start_time,
               m.status
        FROM matches m
        JOIN teams t1 ON m.team1_id = t1.id
        JOIN teams t2 ON m.team2_id = t2.id
        WHERE m.status IN ('live','paused', 'upcoming')
        ORDER BY m.match_date
        LIMIT 1
    """)

    match = cur.fetchone()

    current_time = 0
    team1_players = []
    team2_players = []
    team1_staff = []
    team2_staff = []

    if match:
        match_id = match[0]

        base = match[5] or 0
        start = match[6]
        status = match[7]

        if start is not None and status == "live":
            cur.execute("""
                SELECT EXTRACT(EPOCH FROM (NOW() - %s))::INT
            """, (start,))
            live = cur.fetchone()[0] or 0
            current_time = base + live
        else:
            current_time = base

        # 🔵 CASA
        cur.execute("""
            SELECT p.name, p.number
            FROM players p
            JOIN lineups l ON p.lineup_id = l.id
            WHERE l.match_id=%s
            AND l.team_id=(SELECT team1_id FROM matches WHERE id=%s)
            AND p.role='player'
            ORDER BY p.number
        """, (match_id, match_id))
        team1_players = cur.fetchall()

        # 🔴 OSPITE
        cur.execute("""
            SELECT p.name, p.number
            FROM players p
            JOIN lineups l ON p.lineup_id = l.id
            WHERE l.match_id=%s
            AND l.team_id=(SELECT team2_id FROM matches WHERE id=%s)
            AND p.role='player'
            ORDER BY p.number
        """, (match_id, match_id))
        team2_players = cur.fetchall()

    # STAFF CASA
    cur.execute("""
        SELECT name, role
        FROM players p
        JOIN lineups l ON p.lineup_id = l.id
        WHERE l.match_id=%s
        AND l.team_id=(SELECT team1_id FROM matches WHERE id=%s)
        AND p.role IN ('dirigente','accompagnatore','guardialinee')
    """, (match_id, match_id))

    team1_staff = cur.fetchall()

    # STAFF OSPITE
    cur.execute("""
        SELECT name, role
        FROM players p
        JOIN lineups l ON p.lineup_id = l.id
        WHERE l.match_id=%s
        AND l.team_id=(SELECT team2_id FROM matches WHERE id=%s)
        AND p.role IN ('dirigente','accompagnatore','guardialinee')
    """, (match_id, match_id))
    team2_staff = cur.fetchall()
    
    conn.close()

    return render_template(
        "tv.html",
        match=match,
        time=current_time,
        team1_players=team1_players,
        team2_players=team2_players,
        team1_staff=team1_staff,
        team2_staff=team2_staff
    )

   
# ---------------- TELECOMANDO ----------------
from datetime import datetime

@app.route("/telecomando/<int:match_id>", methods=["GET", "POST"])
def telecomando_match(match_id):

    conn = get_db()
    cur = conn.cursor()

    # ---------------- AZIONI ----------------
    if request.method == "POST":
        action = request.form.get("action")

        # ▶ START
        if action == "start":
            cur.execute("""
                UPDATE matches
                SET status='live',
                    start_time=NOW()
                WHERE id=%s
            """, (match_id,))

        # ⏸ STOP
        elif action == "stop":
            cur.execute("""
                UPDATE matches
                SET elapsed_seconds =
                    elapsed_seconds +
                    EXTRACT(EPOCH FROM (NOW() - start_time))::INT,
                    start_time=NULL,
                    status='paused'
                WHERE id=%s
            """, (match_id,))

        # 🔄 RESET
        elif action == "reset":
            cur.execute("""
                UPDATE matches
                SET elapsed_seconds=0,
                    start_time=NULL,
                    status='upcoming'
                WHERE id=%s
            """, (match_id,))

        # ⚽ GOAL CASA
        elif action == "goal1":
            cur.execute("""
                UPDATE matches
                SET score1 = score1 + 1
                WHERE id=%s
            """, (match_id,))

        # ⚽ GOAL OSPITE
        elif action == "goal2":
            cur.execute("""
                UPDATE matches
                SET score2 = score2 + 1
                WHERE id=%s
            """, (match_id,))

        # ❌ - CASA
        elif action == "goal1_minus":
            cur.execute("""
                UPDATE matches
                SET score1 = GREATEST(score1 - 1, 0)
                WHERE id=%s
            """, (match_id,))

        # ❌ - OSPITE
        elif action == "goal2_minus":
            cur.execute("""
                UPDATE matches
                SET score2 = GREATEST(score2 - 1, 0)
                WHERE id=%s
            """, (match_id,))

        conn.commit()

    # ---------------- LETTURA MATCH ----------------
    cur.execute("""
        SELECT m.id,
               t1.name,
               t2.name,
               m.score1,
               m.score2,
               m.elapsed_seconds,
               m.start_time,
               m.status
        FROM matches m
        JOIN teams t1 ON m.team1_id = t1.id
        JOIN teams t2 ON m.team2_id = t2.id
        WHERE m.id=%s
    """, (match_id,))

    match = cur.fetchone()

    current_time = 0

    if match:
        base = match[5] or 0
        start = match[6]
        status = match[7]

        if start is not None and status == "live":
            cur.execute("""
                SELECT EXTRACT(EPOCH FROM (NOW() - %s))::INT
            """, (start,))
            live = cur.fetchone()[0] or 0
            current_time = base + live
        else:
            current_time = base

    conn.close()

    return render_template(
        "telecomando_match.html",
        match=match,
        time=current_time
    )

    conn = get_db()
    cur = conn.cursor()

    # ---------------- POST (azioni) ----------------
    if request.method == "POST":

        action = request.form.get("action")

        if action == "start":
            cur.execute("""
                UPDATE matches
                SET status='live',
                    start_time = NOW()
                WHERE id=%s
            """, (match_id,))

        elif action == "stop":
            cur.execute("""
                UPDATE matches
                SET elapsed_seconds =
                    elapsed_seconds +
                    EXTRACT(EPOCH FROM (NOW() - start_time))::INT,
                    start_time = NULL,
                    status='paused'
                WHERE id=%s
            """, (match_id,))

        elif action == "reset":
            cur.execute("""
                UPDATE matches
                SET elapsed_seconds = 0,
                    start_time = NULL,
                    status = 'upcoming'
                WHERE id=%s
            """, (match_id,))

        elif action == "finish":
            cur.execute("""
                UPDATE matches
                SET status='finished',
                    start_time=NULL
                WHERE id=%s
            """, (match_id,))

        conn.commit()

    # ---------------- SEMPRE GET DATI PARTITA ----------------
    cur.execute("""
        SELECT m.id,
               t1.name,
               t2.name,
               m.score1,
               m.score2,
               m.elapsed_seconds,
               m.start_time,
               m.status
        FROM matches m
        JOIN teams t1 ON m.team1_id = t1.id
        JOIN teams t2 ON m.team2_id = t2.id
        WHERE m.id=%s
    """, (match_id,))

    match = cur.fetchone()

    current_time = 0

    if match:
        base = match[5] or 0
        start = match[6]
        status = match[7]

        if start is not None and status == "live":
            cur.execute("""
                SELECT EXTRACT(EPOCH FROM (NOW() - %s))::INT
            """, (start,))
            live = cur.fetchone()[0] or 0
            current_time = base + live
        else:
            current_time = base

    conn.close()

    return render_template(
        "telecomando_match.html",
        match=match,
        time=current_time
    )

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        action = request.form.get("action")

        # ▶ START
        if action == "start":
            cur.execute("""
                UPDATE matches
                SET status='live',
                    start_time = NOW()
                WHERE id=%s
            """, (match_id,))

        # ⏸ STOP
        elif action == "stop":
            cur.execute("""
                UPDATE matches
                SET elapsed_seconds =
                    elapsed_seconds +
                    EXTRACT(EPOCH FROM (NOW() - start_time))::INT,
                    start_time = NULL,
                    status='paused'
                WHERE id=%s
            """, (match_id,))

        # 🔄 RESET
        elif action == "reset":
            cur.execute("""
                UPDATE matches
                SET elapsed_seconds = 0,
                    start_time = NULL,
                    status = 'upcoming'
                WHERE id=%s
            """, (match_id,))

        conn.commit()

    conn.close()
    return render_template("telecomando_match.html", match=match)

# ---------------- ADMIN ----------------
@app.route("/admin", methods=["GET", "POST"])
def admin():
    conn = get_db()
    cur = conn.cursor()

    # ---------------- CREA SQUADRA ----------------
    if request.form.get("action") == "add_team":
        name = request.form["team_name"]
        cur.execute("INSERT INTO teams (name) VALUES (%s)", (name,))
        conn.commit()

    # ---------------- CREA UTENTE ----------------
    if request.form.get("action") == "add_user":
        username = request.form["username"]
        password = request.form["password"]
        role = request.form["role"]
        team_id = request.form.get("team_id") or None

        cur.execute("""
            INSERT INTO users (username, password, role, team_id)
            VALUES (%s, %s, %s, %s)
        """, (username, password, role, team_id))
        conn.commit()

    # ---------------- CREA PARTITA ----------------
    if request.form.get("action") == "add_match":
        team1 = request.form["team1"]
        team2 = request.form["team2"]
        date = request.form["match_date"]
        giornata = request.form["giornata"]

        cur.execute("""
            INSERT INTO matches (team1_id, team2_id, status, match_date, giornata)
            VALUES (%s, %s, 'upcoming', %s, %s)
        """, (team1, team2, date, giornata))

        conn.commit()

    # ---------------- DATI ----------------
    cur.execute("SELECT * FROM teams")
    teams = cur.fetchall()

    cur.execute("""
        SELECT m.id, t1.name, t2.name, m.status
        FROM matches m
        JOIN teams t1 ON m.team1_id = t1.id
        JOIN teams t2 ON m.team2_id = t2.id
    """)
    matches = cur.fetchall()

    cur.execute("SELECT id, username, role FROM users")
    users = cur.fetchall()

    conn.close()

    return render_template(
        "admin.html",
        teams=teams,
        matches=matches,
        users=users
    )

# 🚀 AVVIO APP
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)