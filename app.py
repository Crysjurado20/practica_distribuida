import os
from flask import Flask, jsonify, request
from flask_cors import CORS
import smtplib
import ssl
from email.message import EmailMessage
from mssql_python import connect

app = Flask(__name__)

# Habilitar CORS para permitir peticiones desde el front-end
CORS(app)


def get_connection():
    server = os.getenv("DB_SERVER")
    database = os.getenv("DB_DATABASE")
    username = os.getenv("DB_USERNAME")
    password = os.getenv("DB_PASSWORD")
    port = os.getenv("DB_PORT", "1433")

    if not server:
        raise ValueError("Falta DB_SERVER")
    if not database:
        raise ValueError("Falta DB_DATABASE")
    if not username:
        raise ValueError("Falta DB_USERNAME")
    if not password:
        raise ValueError("Falta DB_PASSWORD")

    connection_string = (
        f"Server=tcp:{server},{port};"
        f"Database={database};"
        f"Uid={username};"
        f"Pwd={password};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=no;"
        f"Authentication=SqlPassword;"
    )

    return connect(connection_string)


def enviar_correo_alerta(asunto, mensaje, destino):
    """Envía un correo usando SMTP configurado por variables de entorno.

    Variables esperadas:
    - SMTP_HOST
    - SMTP_PORT (opcional, por defecto 587)
    - SMTP_USER
    - SMTP_PASS
    - FROM_EMAIL (opcional, por defecto SMTP_USER)
    """
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    from_email = os.getenv("FROM_EMAIL") or user

    if not host or not user or not password or not from_email:
        raise ValueError("Faltan variables de entorno para SMTP (SMTP_HOST/SMTP_USER/SMTP_PASS/FROM_EMAIL)")

    msg = EmailMessage()
    msg["From"] = from_email
    msg["To"] = destino
    msg["Subject"] = asunto
    msg.set_content(mensaje)

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls(context=context)
            server.login(user, password)
            server.send_message(msg)
    except Exception:
        raise


@app.route("/")
def home():
    return jsonify({
        "success": True,
        "message": "API Flask funcionando correctamente en Render"
    })


@app.route("/debug-env")
def debug_env():
    return jsonify({
        "DB_SERVER": os.getenv("DB_SERVER"),
        "DB_DATABASE": os.getenv("DB_DATABASE"),
        "DB_USERNAME": os.getenv("DB_USERNAME"),
        "DB_PASSWORD_EXISTS": bool(os.getenv("DB_PASSWORD")),
        "DB_PORT": os.getenv("DB_PORT"),
    })


@app.route("/test-db")
def test_db():
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT GETDATE() AS fecha_servidor")
        row = cursor.fetchone()

        return jsonify({
            "success": True,
            "message": "Conexión a SQL Server exitosa",
            "server_date": str(row[0])
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": "Error al conectar con SQL Server",
            "error": str(e)
        }), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/enviar-alerta", methods=["POST"])
def enviar_alerta():
    try:
        data = request.get_json()
        destino = data.get("to")
        asunto = data.get("subject")
        mensaje = data.get("message")

        if not destino or not asunto or not mensaje:
            return jsonify({
                "success": False,
                "message": "Faltan datos"
            }), 400

        enviar_correo_alerta(asunto, mensaje, destino)

        return jsonify({
            "success": True,
            "message": "Correo enviado"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/productos")
def listar_productos():
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Agregamos url_imagen a la consulta
        cursor.execute("""
            SELECT TOP 20 Id, Nombre, Precio, Stock, url_imagen, Versions
            FROM productos
            ORDER BY Id DESC
        """)
        rows = cursor.fetchall()

        data = []
        for row in rows:
            # Versions (binary) a Hex para JSON
            version_hex = row[5].hex() if row[5] else None

            data.append({
                "id": row[0],
                "nombre": row[1],
                "precio": float(row[2]) if row[2] is not None else 0.0,
                "stock": row[3],
                "imagen_url": row[4],
                "row_version": f"0x{version_hex}" if version_hex else None
            })

        return jsonify({
            "success": True,
            "data": data
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": "Error al consultar productos",
            "error": str(e)
        }), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()



if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)