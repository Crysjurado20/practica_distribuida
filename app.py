import os
from flask import Flask, jsonify, request
from flask_cors import CORS
import smtplib
import ssl
from email.mime.text import MIMEText
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
    email_user = os.getenv("EMAIL_USER") or os.getenv("SMTP_USER")
    email_password = os.getenv("EMAIL_PASSWORD") or os.getenv("SMTP_PASS")

    if not email_user:
        raise ValueError("Falta EMAIL_USER")
    if not email_password:
        raise ValueError("Falta EMAIL_PASSWORD")

    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))

    # Construir el mensaje
    msg = MIMEText(mensaje, "plain", "utf-8")
    msg["Subject"] = asunto
    msg["From"] = email_user
    msg["To"] = destino

    try:
        servidor = smtplib.SMTP(host, port, timeout=10)
        servidor.starttls()
        servidor.login(email_user, email_password)
        servidor.sendmail(email_user, [destino], msg.as_string())
        servidor.quit()
    except OSError as e:
        # errores de red, p. ej. [Errno 101] Network is unreachable
        raise RuntimeError(f"Error de red al conectar con SMTP: {e}")
    except smtplib.SMTPException as e:
        raise RuntimeError(f"Error SMTP: {e}")



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