from flask import Flask, render_template, request, send_file, session, redirect, url_for, flash
from datetime import datetime
from PIL import Image
import os

# =========================
# CONFIGURACIÓN PRINCIPAL
# =========================
app = Flask(__name__)
app.secret_key = "convertidor_vym_2025"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
PDF_FOLDER = os.path.join(BASE_DIR, "pdfs")
GALLERY_FOLDER = os.path.join(BASE_DIR, "static", "gallery")
USERS_FILE = os.path.join(BASE_DIR, "usuarios.txt")

for folder in [UPLOAD_FOLDER, PDF_FOLDER, GALLERY_FOLDER]:
    os.makedirs(folder, exist_ok=True)

# Crear usuario admin por defecto
if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        f.write("admin,admin@vym.com,1234,Básico\n")

# =========================
# CLASE USER
# =========================
class User:
    def __init__(self, username, email, contrasena, plan="Básico"):
        self.username = username
        self.email = email
        self.contrasena = contrasena
        self.plan = plan

    def check_password(self, password):
        return self.contrasena == password

# =========================
# FUNCIONES AUXILIARES
# =========================
def leer_usuarios():
    usuarios = []
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            for linea in f:
                partes = linea.strip().split(",")
                if len(partes) >= 4:
                    usuarios.append(User(partes[0], partes[1], partes[2], partes[3]))
    return usuarios

def guardar_usuario(username, email, contrasena, plan="Básico"):
    with open(USERS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{username},{email},{contrasena},{plan}\n")

def get_current_user():
    username = session.get("usuario")
    if username:
        usuarios = leer_usuarios()
        for u in usuarios:
            if u.username == username:
                return u
    return None

@app.context_processor
def inject_user():
    return {"current_user": get_current_user()}

# =========================
# RUTAS PRINCIPALES
# =========================
@app.route("/")
def index():
    return render_template("index.html")

# ======== RUTA CONVERTIDOR CORREGIDA ========
@app.route("/convertidor")
def convertidor():
    user = get_current_user()
    if not user:
        flash("Debes iniciar sesión para usar el convertidor 🔒", "warning")
        return redirect(url_for("login"))

    # Últimos 10 PDFs convertidos
    pdfs = sorted(
        [f for f in os.listdir(PDF_FOLDER) if f.lower().endswith(".pdf")],
        key=lambda x: os.path.getmtime(os.path.join(PDF_FOLDER, x)),
        reverse=True
    )[:10]

    # Últimas 10 imágenes convertidas
    images = sorted(
        [f for f in os.listdir(GALLERY_FOLDER) if not f.startswith(".")],
        key=lambda x: os.path.getmtime(os.path.join(GALLERY_FOLDER, x)),
        reverse=True
    )[:10]

    return render_template("convertidor.html", pdfs=pdfs, images=images)

@app.route("/suscripcion")
def suscripcion():
    return render_template("suscripcion.html")

@app.route("/quienes-somos")
def quienes():
    return render_template("quienes.html")

@app.route("/perfil")
def perfil():
    user = get_current_user()
    if not user:
        flash("Primero inicia sesión para ver tu perfil 🔒", "warning")
        return redirect(url_for("login"))

    docs = sorted(
        [f for f in os.listdir(PDF_FOLDER) if f.lower().endswith(".pdf")],
        key=lambda x: os.path.getmtime(os.path.join(PDF_FOLDER, x)),
        reverse=True
    )[:10]

    imgs = sorted(
        [f for f in os.listdir(GALLERY_FOLDER) if not f.startswith(".")],
        key=lambda x: os.path.getmtime(os.path.join(GALLERY_FOLDER, x)),
        reverse=True
    )[:10]

    return render_template(
        "perfil.html",
        usuario=user,
        plan=user.plan,
        docs=docs,
        imgs=imgs
    )

# =========================
# LOGIN / REGISTRO / LOGOUT
# =========================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        contrasena = request.form["contrasena"]

        usuarios = leer_usuarios()
        for u in usuarios:
            if u.username == usuario and u.check_password(contrasena):
                session["usuario"] = usuario
                flash("Inicio de sesión exitoso 💚", "success")
                return redirect(url_for("index"))

        flash("Usuario o contraseña incorrectos ❌", "error")
        return render_template("login.html")

    return render_template("login.html")

@app.route("/registrar_usuario", methods=["POST"])
def registrar_usuario():
    username = request.form.get("usuario")
    email = request.form.get("correo")
    contrasena = request.form.get("contrasena")

    usuarios = leer_usuarios()
    for u in usuarios:
        if u.username == username or u.email == email:
            flash("El usuario o correo ya existe ❌", "error")
            return redirect(url_for("login"))

    guardar_usuario(username, email, contrasena)
    flash("Usuario creado con éxito ✅", "success")
    return redirect(url_for("login"))

@app.route("/logout")
def logout():
    session.pop("usuario", None)
    flash("Sesión cerrada 👋", "info")
    return redirect(url_for("login"))

# =========================
# CONVERTIDORES
# =========================
@app.route("/convert", methods=["POST"])
def convert_docx():
    if "file" not in request.files:
        return "No se envió archivo", 400

    file = request.files["file"]
    if not file.filename.lower().endswith(".docx"):
        return "Debe subir un archivo .docx", 400

    upload_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(upload_path)

    output_path = os.path.join(PDF_FOLDER, file.filename.replace(".docx", ".pdf"))
    os.system(f"libreoffice --headless --convert-to pdf '{upload_path}' --outdir '{PDF_FOLDER}'")

    if not os.path.exists(output_path):
        return "Error al convertir DOCX a PDF ❌", 500

    return send_file(output_path, as_attachment=True)

@app.route("/convert_image", methods=["POST"])
def convert_image():
    if "image" not in request.files:
        return "No se envió imagen", 400

    image_file = request.files["image"]
    output_format = request.form.get("format", "PNG").lower()

    try:
        img = Image.open(image_file)
        nombre_salida = image_file.filename.rsplit(".", 1)[0] + f".{output_format}"
        output_path = os.path.join(GALLERY_FOLDER, nombre_salida)
        img.save(output_path, output_format.upper())
    except Exception as e:
        return f"Error al convertir imagen: {str(e)}", 500

    return send_file(output_path, as_attachment=True)

@app.route("/dashboard")
def dashboard():
    if "usuario" not in session:
        flash("Debes iniciar sesión para ver el dashboard ❗", "error")
        return redirect(url_for("login"))

    # Datos de ejemplo (luego los puedes generar dinámicos)
    stats = {
        "total_convertidos": 128,
        "imagenes_convertidas": 89,
        "documentos_convertidos": 39,
        "usuarios_registrados": 14
    }

    # Datos para gráficas
    grafica_mes = {
        "labels": ["Ene", "Feb", "Mar", "Abr", "May", "Jun"],
        "valores": [10, 15, 20, 25, 18, 30]
    }

    grafica_planes = {
        "labels": ["Gratis", "Básico", "Premium"],
        "valores": [10, 3, 1]
    }

    return render_template("dashboard.html",
                           stats=stats,
                           grafica_mes=grafica_mes,
                           grafica_planes=grafica_planes)


# =========================
# EJECUCIÓN LOCAL
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
