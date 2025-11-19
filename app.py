from flask import Flask, render_template, request, send_file, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from PIL import Image
import os

# =========================================================
# CONFIGURACIÓN PRINCIPAL
# =========================================================
app = Flask(__name__)
app.secret_key = "convertidor_vym_2025"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
PDF_FOLDER = os.path.join(BASE_DIR, "pdfs")
GALLERY_FOLDER = os.path.join(BASE_DIR, "static", "gallery")

for folder in [UPLOAD_FOLDER, PDF_FOLDER, GALLERY_FOLDER]:
    os.makedirs(folder, exist_ok=True)

# =========================================================
# BASE DE DATOS (SQLite)
# =========================================================
db_path = os.path.join(BASE_DIR, "convertidor_vym.sqlite")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# =========================================================
# MODELOS
# =========================================================
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    plan = db.Column(db.String(20), nullable=False, default="Básico")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Conversion(db.Model):
    __tablename__ = "conversions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"))
    tipo = db.Column(db.String(20), nullable=False)  # docx_pdf | image
    input_filename = db.Column(db.String(255), nullable=False)
    output_filename = db.Column(db.String(255), nullable=False)
    output_format = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    input_data = db.Column(db.LargeBinary, nullable=False)
    output_data = db.Column(db.LargeBinary, nullable=False)
    output_mime = db.Column(db.String(100), nullable=False)

# =========================================================
# HELPERS
# =========================================================
def get_current_user():
    uid = session.get("user_id")
    return User.query.get(uid) if uid else None

@app.context_processor
def inject_user():
    return {"current_user": get_current_user()}

# =========================================================
# RUTAS PRINCIPALES
# =========================================================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/convertidor")
def convertidor():
    user = get_current_user()
    if not user:
        flash("Debes iniciar sesión para usar el convertidor 🔒", "warning")
        return redirect(url_for("login"))

    images = Conversion.query.filter_by(user_id=user.id, tipo="image") \
                             .order_by(Conversion.created_at.desc()) \
                             .limit(10).all()

    return render_template("convertidor.html", images=images)


@app.route("/quienes-somos")
def quienes():
    return render_template("quienes.html")


@app.route("/suscripcion")
def suscripcion():
    return render_template("suscripcion.html")


# =========================================================
# LOGIN / REGISTRO / LOGOUT
# =========================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"].strip()
        clave = request.form["contrasena"]

        u = User.query.filter_by(username=usuario).first()
        if u and check_password_hash(u.password_hash, clave):
            session["user_id"] = u.id
            flash("Inicio de sesión exitoso 💚", "success")
            return redirect(url_for("index"))

        flash("Usuario o contraseña incorrectos ❌", "error")

    return render_template("login.html")


@app.route("/registrar_usuario", methods=["POST"])
def registrar_usuario():
    username = request.form["usuario"]
    email = request.form["correo"]
    contra = request.form["contrasena"]

    existe = User.query.filter((User.username == username) | (User.email == email)).first()
    if existe:
        flash("Usuario o correo ya existe ❌", "error")
        return redirect(url_for("login"))

    u = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(contra),
        plan="Básico"
    )
    db.session.add(u)
    db.session.commit()

    flash("Usuario creado con éxito 💚", "success")
    return redirect(url_for("login"))


@app.route("/logout")
def logout():
    session.clear()
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

    # Guardar registro de conversión en BD
    user = get_current_user()
    if user:
        with open(upload_path, "rb") as f_in, open(output, "rb") as f_out:
            conv = Conversion(
                user_id=user.id,
                tipo="docx_pdf",
                input_filename=file.filename,
                output_filename=os.path.basename(output),
                output_format="pdf",
                input_data=f_in.read(),
                output_data=f_out.read(),
                output_mime="application/pdf"
            )
            db.session.add(conv)
            db.session.commit()

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

    # Guardar registro de conversión en BD
    user = get_current_user()
    if user:
        with open(image_file.filename, "rb") as f_in, open(output_path, "rb") as f_out:
            conv = Conversion(
                user_id=user.id,
                tipo="image",
                input_filename=image_file.filename,
                output_filename=nombre_salida,
                output_format=output_format,
                input_data=f_in.read(),
                output_data=f_out.read(),
                output_mime=f"image/{output_format.lower()}"
            )
            db.session.add(conv)
            db.session.commit()

    return send_file(output_path, as_attachment=True)

# =========================================================
# INICIALIZAR BD Y ADMIN
# =========================================================
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username="admin").first():
        admin = User(
            username="admin",
            email="admin@vym.com",
            password_hash=generate_password_hash("1234"),
            plan="Premium"
        )
        db.session.add(admin)
        db.session.commit()

# =========================================================
# RUN
# =========================================================
if __name__ == "__main__":
    app.run(debug=True)
