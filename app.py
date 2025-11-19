from flask import Flask, render_template, request, send_file, session, redirect, url_for, flash, Response, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from PIL import Image
from io import BytesIO
import tempfile
import mimetypes
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
# BASE DE DATOS (POSTGRESQL)
# =========================================================
app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://vym_user:12345678@localhost/convertidor_vym"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# =========================================================
# MODELOS ACTUALIZADOS (BINARIOS EN BD)
# =========================================================
class User(db.Model):
    __tablename__ = "users"
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(50), unique=True, nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    plan          = db.Column(db.String(20), nullable=False, default="Básico")
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    conversions = db.relationship("Conversion", backref="user", lazy=True, cascade="all,delete")

    # 🔥 AÑADIR ESTO:
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)



class Conversion(db.Model):
    __tablename__ = "conversions"

    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"))
    tipo          = db.Column(db.String(20), nullable=False)  # docx_pdf | image

    input_filename  = db.Column(db.String(255), nullable=False)
    output_filename = db.Column(db.String(255), nullable=False)
    output_format   = db.Column(db.String(10), nullable=False)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    # === NUEVO: archivos guardados en BD ===
    input_data    = db.Column(db.LargeBinary, nullable=False)
    output_data   = db.Column(db.LargeBinary, nullable=False)
    output_mime   = db.Column(db.String(100), nullable=False)


class Subscription(db.Model):
    __tablename__ = "subscriptions"

    id        = db.Column(db.Integer, primary_key=True)
    user_id   = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"))
    plan      = db.Column(db.String(20), nullable=False)
    started_at= db.Column(db.DateTime, default=datetime.utcnow)
    ended_at  = db.Column(db.DateTime)


# =========================================================
# HELPERS
# =========================================================
def get_current_user():
    uid = session.get("user_id")
    return User.query.get(uid) if uid else None


def guess_mime(name):
    return mimetypes.guess_type(name)[0] or "application/octet-stream"

def count_today_conversions(user_id, tipo):
    hoy = datetime.utcnow().date()
    return Conversion.query.filter(
        Conversion.user_id == user_id,
        Conversion.tipo == tipo,
        db.func.date(Conversion.created_at) == hoy
    ).count()



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
        clave   = request.form["contrasena"]

        u = User.query.filter_by(username=usuario).first()
        if u and u.check_password(clave):
            session["user_id"] = u.id
            flash("Inicio de sesión exitoso 💚", "success")
            return redirect(url_for("index"))

        flash("Usuario o contraseña incorrectos ❌", "error")

    return render_template("login.html")

# =========================================================
# PERFIL DE USUARIO (RESTAURADA)
# =========================================================
# =========================================================
# PERFIL DE USUARIO
# =========================================================
@app.route("/perfil")
def perfil():
    user = get_current_user()
    if not user:
        flash("Primero inicia sesión para ver tu perfil 🔒", "warning")
        return redirect(url_for("login"))

    docs = Conversion.query.filter_by(user_id=user.id, tipo="docx_pdf") \
                           .order_by(Conversion.created_at.desc()).all()

    imgs = Conversion.query.filter_by(user_id=user.id, tipo="image") \
                           .order_by(Conversion.created_at.desc()).all()

    return render_template(
        "perfil.html",
        usuario=user,
        plan=user.plan,
        docs=docs,
        imgs=imgs
    )



@app.route("/registrar_usuario", methods=["POST"])
def registrar_usuario():
    username = request.form["usuario"]
    email    = request.form["correo"]
    contra   = request.form["contrasena"]

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
# CONVERTIR DOCX → PDF (GUARDAR EN BD)
# =========================================================
@app.route("/convert_docx", methods=["POST"])
def convert_docx():
    user = get_current_user()
    if not user:
        flash("Debes iniciar sesión 🔒", "warning")
        return redirect(url_for("login"))

    # 🔥 LIMITE PARA PLAN BÁSICO: 5 PDF POR DÍA
    if user.plan == "Básico":
        hoy_pdf = count_today_conversions(user.id, "docx_pdf")
        if hoy_pdf >= 5:
            flash("Límite diario alcanzado (5 PDFs por día en plan Básico) ⚠️", "error")
            return redirect(url_for("convertidor"))

    f = request.files.get("file")
    if not f or not f.filename.endswith(".docx"):
        flash("Archivo inválido ❌", "error")
        return redirect(url_for("convertidor"))

    input_bytes = f.read()
    input_name  = f.filename

    # Convertir usando LibreOffice
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, input_name)
        with open(src, "wb") as x: 
            x.write(input_bytes)

        os.system(f"libreoffice --headless --convert-to pdf '{src}' --outdir '{tmp}'")

        out_name = input_name.replace(".docx", ".pdf")
        out_path = os.path.join(tmp, out_name)

        with open(out_path, "rb") as x:
            output_bytes = x.read()

    conv = Conversion(
        user_id=user.id,
        tipo="docx_pdf",
        input_filename=input_name,
        output_filename=out_name,
        output_format="pdf",
        input_data=input_bytes,
        output_data=output_bytes,
        output_mime="application/pdf"
    )

    db.session.add(conv)
    db.session.commit()

    return send_file(BytesIO(output_bytes),
                     download_name=out_name,
                     mimetype="application/pdf",
                     as_attachment=True)



# =========================================================
# CONVERTIR IMAGEN (GUARDAR EN BD)
# =========================================================
@app.route("/convert_image", methods=["POST"])
def convert_image():
    user = get_current_user()
    if not user:
        flash("Debes iniciar sesión 🔒", "warning")
        return redirect(url_for("login"))

    # 🔥 LIMITE PARA PLAN BÁSICO: 5 IMÁGENES POR DÍA
    if user.plan == "Básico":
        hoy_img = count_today_conversions(user.id, "image")
        if hoy_img >= 5:
            flash("Límite diario alcanzado (5 imágenes por día en plan Básico) ⚠️", "error")
            return redirect(url_for("convertidor"))

    image_file = request.files.get("image")
    formato = request.form.get("format")

    if not image_file:
        flash("Selecciona una imagen ❌", "error")
        return redirect(url_for("convertidor"))

    input_bytes = image_file.read()
    input_name  = image_file.filename

    with Image.open(BytesIO(input_bytes)) as img:
        if formato == "jpg":
            img = img.convert("RGB")

        buffer = BytesIO()
        save_fmt = "JPEG" if formato == "jpg" else formato.upper()
        img.save(buffer, save_fmt, quality=90)
        output_bytes = buffer.getvalue()

    out_name = input_name.rsplit(".", 1)[0] + f".{formato}"
    out_mime = guess_mime(out_name)

    conv = Conversion(
        user_id=user.id,
        tipo="image",
        input_filename=input_name,
        output_filename=out_name,
        output_format=formato,
        input_data=input_bytes,
        output_data=output_bytes,
        output_mime=out_mime
    )

    db.session.add(conv)
    db.session.commit()

    return send_file(BytesIO(output_bytes),
                     download_name=out_name,
                     mimetype=out_mime,
                     as_attachment=True)



# =========================================================
# ENDPOINT PARA MOSTRAR IMÁGENES DESDE BD
# =========================================================
@app.route("/image_raw/<int:id>")
def image_raw(id):
    conv = Conversion.query.get_or_404(id)
    if conv.tipo != "image":
        abort(404)
    return Response(conv.output_data, mimetype=conv.output_mime)


# =========================================================
# ENDPOINT PARA DESCARGAS DESDE BD
# =========================================================
@app.route("/download/<int:id>")
def download(id):
    conv = Conversion.query.get_or_404(id)
    return send_file(BytesIO(conv.output_data),
                     download_name=conv.output_filename,
                     mimetype=conv.output_mime,
                     as_attachment=True)


# =========================================================
# RUN
# =========================================================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)

    
