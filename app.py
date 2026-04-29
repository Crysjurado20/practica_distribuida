import os
from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import base64
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
    client_id = os.getenv("GMAIL_CLIENT_ID")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET")
    refresh_token = os.getenv("GMAIL_REFRESH_TOKEN")
    from_email = os.getenv("FROM_EMAIL")

    if not client_id:
        raise ValueError("Falta GMAIL_CLIENT_ID")
    if not client_secret:
        raise ValueError("Falta GMAIL_CLIENT_SECRET")
    if not refresh_token:
        raise ValueError("Falta GMAIL_REFRESH_TOKEN")
    if not from_email:
        raise ValueError("Falta FROM_EMAIL")

    # 1) Obtener access token desde refresh token
    token_resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    if token_resp.status_code != 200:
        raise RuntimeError(f"Error obteniendo access token: {token_resp.status_code} {token_resp.text}")

    access_token = token_resp.json().get("access_token")
    if not access_token:
        raise RuntimeError("Google no devolvió access_token")

    # 2) Construir correo RFC822 y codificarlo en base64 URL-safe
    msg = MIMEText(mensaje, "plain", "utf-8")
    msg["To"] = destino
    msg["From"] = from_email
    msg["Subject"] = asunto
    raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    # 3) Enviar por Gmail API
    send_resp = requests.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={"raw": raw_message},
        timeout=15,
    )
    if send_resp.status_code not in (200, 202):
        raise RuntimeError(f"Error al enviar con Gmail API: {send_resp.status_code} {send_resp.text}")


@app.route("/test-gmail-api")
def test_gmail_api():
    client_id = os.getenv("GMAIL_CLIENT_ID")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET")
    refresh_token = os.getenv("GMAIL_REFRESH_TOKEN")
    from_email = os.getenv("FROM_EMAIL")

    missing = []
    if not client_id:
        missing.append("GMAIL_CLIENT_ID")
    if not client_secret:
        missing.append("GMAIL_CLIENT_SECRET")
    if not refresh_token:
        missing.append("GMAIL_REFRESH_TOKEN")
    if not from_email:
        missing.append("FROM_EMAIL")

    if missing:
        return jsonify({"success": False, "message": "Faltan variables", "missing": missing}), 400

    token_resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=15,
    )

    if token_resp.status_code != 200:
        return jsonify({
            "success": False,
            "message": "No se pudo obtener access token",
            "status": token_resp.status_code,
            "error": token_resp.text,
        }), 500

    return jsonify({
        "success": True,
        "message": "Gmail API configurada correctamente",
        "from": from_email,
    })



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