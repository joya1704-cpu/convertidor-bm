from flask import Flask, render_template, request, send_file, session, redirect, url_for, flash
import os
from PIL import Image

# =========================================================
# CONFIGURACIÓN PRINCIPAL
# =========================================================
app = Flask(__name__)
app.secret_key = "convertidor_vym_2025"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
PDF_FOLDER = os.path.join(BASE_DIR, "pdfs")
GALLERY_FOLDER = os.path.join(BASE_DIR, "static", "gallery")
USERS_FILE = os.path.join(BASE_DIR, "usuarios.txt")

for folder in [UPLOAD_FOLDER, PDF_FOLDER, GALLERY_FOLDER]:
    os.makedirs(folder, exist_ok=True)

# =========================================================
# CLASE USER (igual que el proyecto grande pero sin BD)
# =========================================================
class User:
    def __init__(self, usuario, correo, contrasena, plan="Básico"):
        self.usuario = usuario
        self.correo = correo
        self.contrasena = contrasena
        self.plan = plan

    def check_password(self, password):
        return self.contrasena == password

# Crear admin si no existe
if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        f.write("admin,admin@vym.com,1234\n")

# =========================================================
# FUNCIONES AUXILIARES
# =========================================================
def leer_usuarios():
    usuarios = []
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            for linea in f:
                partes = linea.strip().split(",")
                if len(partes) == 3:
                    usuarios.append({
                        "usuario": partes[0],
                        "correo": partes[1],
                        "contrasena": partes[2]
                    })
    return usuarios


def guardar_usuario(usuario, correo, contrasena):
    with open(USERS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{usuario},{correo},{contrasena}\n")


@app.context_processor
def inject_user():
    return {"session": session}

# =========================================================
# RUTAS PRINCIPALES
# =========================================================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/convertidor")
def convertidor():
    images = [f for f in os.listdir(GALLERY_FOLDER) if not f.startswith(".")]
    return render_template("convertidor.html", images=images)


@app.route("/suscripcion")
def suscripcion():
    return render_template("suscripcion.html")


# ======= NUEVAS RUTAS PAYPAL =======
@app.route("/suscripcion/gratis")
def suscripcion_gratis():
    return "<h2>Ahora estás usando el plan GRATIS 😊</h2>"


@app.route("/suscripcion/basico")
def suscripcion_basico():
    sub_id = request.args.get("sub_id", "")
    return f"<h2>Gracias por tu suscripción Básica 💚<br> ID: {sub_id}</h2>"


@app.route("/suscripcion/premium")
def suscripcion_premium():
    sub_id = request.args.get("sub_id", "")
    return f"<h2>Gracias por tu suscripción Premium 🌟<br> ID: {sub_id}</h2>"


# =========================================================
# LOGIN / REGISTRO
# =========================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        contrasena = request.form["contrasena"]

        usuarios = leer_usuarios()

        for u in usuarios:
            user = User(u["usuario"], u["correo"], u["contrasena"])
            if user.usuario == usuario and user.check_password(contrasena):
                session["usuario"] = user.usuario
                flash("Inicio de sesión exitoso 💚", "success")
                return redirect(url_for("index"))

        flash("Usuario o contraseña incorrectos ❌", "error")
        return render_template("login.html")

    return render_template("login.html")


@app.route("/registrar_usuario", methods=["POST"])
def registrar_usuario():
    usuario = request.form.get("usuario")
    correo = request.form.get("correo")
    contrasena = request.form.get("contrasena")

    usuarios = leer_usuarios()

    for u in usuarios:
        if u["usuario"] == usuario or u["correo"] == correo:
            flash("El usuario o correo ya existe ❌", "error")
            return redirect(url_for("login"))

    guardar_usuario(usuario, correo, contrasena)
    flash("Usuario creado con éxito ✅", "success")
    return redirect(url_for("login"))


@app.route("/logout")
def logout():
    session.pop("usuario", None)
    flash("Sesión cerrada 👋", "info")
    return redirect(url_for("login"))

# =========================================================
# CONVERTIDORES
# =========================================================
@app.route("/convert", methods=["POST"])
def convert_docx():
    if "file" not in request.files:
        return "No se envió archivo", 400

    file = request.files["file"]
    if not file.filename.lower().endswith(".docx"):
        return "Debe subir un archivo .docx", 400

    upload_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(upload_path)

    output = os.path.join(PDF_FOLDER, file.filename.replace(".docx", ".pdf"))
    os.system(f"libreoffice --headless --convert-to pdf '{upload_path}' --outdir '{PDF_FOLDER}'")

    return send_file(output, as_attachment=True)


@app.route("/convert_image", methods=["POST"])
def convert_image():
    if "image" not in request.files:
        return "No se envió imagen", 400

    image_file = request.files["image"]
    output_format = request.form["format"]

    img = Image.open(image_file)
    nombre_salida = image_file.filename.rsplit(".", 1)[0] + f".{output_format}"
    output_path = os.path.join(GALLERY_FOLDER, nombre_salida)
    img.save(output_path, output_format.upper())

    return send_file(output_path, as_attachment=True)

# =========================================================
# EJECUCIÓN LOCAL
# =========================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
