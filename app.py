from flask import Flask, render_template, request, send_file, session, redirect, url_for, flash, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from PIL import Image
from io import BytesIO
from docx2pdf import convert
import mimetypes
import tempfile
import os

# =========================================================
# CONFIGURACIÓN PRINCIPAL
# =========================================================
app = Flask(__name__)
app.secret_key = "convertidor_vym_2025"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# =========================================================
# BASE DE DATOS POSTGRESQL (RENDER)
# =========================================================
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///local.sqlite")
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
    conversions = db.relationship("Conversion", backref="user", lazy=True, cascade="all,delete")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


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


class Subscription(db.Model):
    __tablename__ = "subscriptions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"))
    plan = db.Column(db.String(20), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime)


# =========================================================
# HELPERS
# =========================================================
def get_current_user():
    uid = session.get("user_id")
    return User.query.get(uid) if uid else None


def guess_mime(filename):
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


@app.context_processor
def inject_user():
    return {"current_user": get_current_user()}


def save_conversion(user_id, tipo, input_file, output_file, output_format, output_mime):
    with open(input_file, "rb") as f:
        input_data = f.read()
    with open(output_file, "rb") as f:
        output_data = f.read()

    conversion = Conversion(
        user_id=user_id,
        tipo=tipo,
        input_filename=os.path.basename(input_file),
        output_filename=os.path.basename(output_file),
        output_format=output_format,
        input_data=input_data,
        output_data=output_data,
        output_mime=output_mime
    )
    db.session.add(conversion)
    db.session.commit()
    return conversion


# =========================================================
# RUTAS PRINCIPALES
# =========================================================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/convertidor", methods=["GET", "POST"])
def convertidor():
    user = get_current_user()
    if not user:
        flash("Debes iniciar sesión para usar el convertidor 🔒", "warning")
        return redirect(url_for("login"))

    if request.method == "POST":
        file = request.files.get("archivo")
        if not file:
            flash("Debes seleccionar un archivo", "error")
            return redirect(url_for("convertidor"))

        filename = file.filename
        ext = os.path.splitext(filename)[1].lower()

        # Crear temp file
        temp_in = tempfile.NamedTemporaryFile(delete=False)
        file.save(temp_in.name)

        if ext == ".docx":  # DOCX a PDF
            temp_out = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            convert(temp_in.name, temp_out.name)
            save_conversion(user.id, "docx_pdf", temp_in.name, temp_out.name, "pdf", "application/pdf")
            flash("Documento convertido a PDF ✅", "success")

        elif ext in [".png", ".jpg", ".jpeg"]:  # Imagen a PNG
            img = Image.open(temp_in.name)
            temp_out = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            img.save(temp_out.name, format="PNG")
            save_conversion(user.id, "image", temp_in.name, temp_out.name, "png", "image/png")
            flash("Imagen convertida a PNG ✅", "success")
        else:
            flash("Formato no soportado ❌", "error")
            return redirect(url_for("convertidor"))

    images = Conversion.query.filter_by(user_id=user.id, tipo="image") \
                             .order_by(Conversion.created_at.desc()) \
                             .limit(10).all()
    return render_template("convertidor.html", images=images)


@app.route("/download/<int:conv_id>")
def download(conv_id):
    user = get_current_user()
    conv = Conversion.query.get_or_404(conv_id)
    if conv.user_id != user.id:
        flash("No tienes permisos para descargar este archivo", "error")
        return redirect(url_for("convertidor"))

    return Response(
        conv.output_data,
        mimetype=conv.output_mime,
        headers={"Content-Disposition": f'attachment; filename="{conv.output_filename}"'}
    )


@app.route("/suscripcion")
def suscripcion():
    return render_template("suscripcion.html")


@app.route("/quienes-somos")
def quienes():
    return render_template("quienes.html")


# =========================================================
# LOGIN / REGISTRO / LOGOUT
# =========================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"].strip()
        clave = request.form["contrasena"]

        u = User.query.filter((User.username==usuario) | (User.email==usuario)).first()
        if u and u.check_password(clave):
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

    existe = User.query.filter((User.username==username) | (User.email==email)).first()
    if existe:
        flash("Usuario o correo ya existe ❌", "error")
        return redirect(url_for("login"))

    u = User(username=username, email=email,
             password_hash=generate_password_hash(contra),
             plan="Básico")
    db.session.add(u)
    db.session.commit()
    flash("Usuario creado con éxito 💚", "success")
    return redirect(url_for("login"))


@app.route("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada 👋", "info")
    return redirect(url_for("login"))


@app.route("/perfil")
def perfil():
    user = get_current_user()
    if not user:
        flash("Primero inicia sesión 🔒", "warning")
        return redirect(url_for("login"))

    docs = Conversion.query.filter_by(user_id=user.id, tipo="docx_pdf") \
                           .order_by(Conversion.created_at.desc()).all()
    imgs = Conversion.query.filter_by(user_id=user.id, tipo="image") \
                           .order_by(Conversion.created_at.desc()).all()
    return render_template("perfil.html", usuario=user, plan=user.plan, docs=docs, imgs=imgs)


# =========================================================
# RUN
# =========================================================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # 🔥 Crea las tablas automáticamente en PostgreSQL
    app.run(debug=True)
