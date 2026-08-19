from app import db
from app.credential_protection import DpapiCredentialProtector
from app.routes import create_app
from app.scheduler import build_scheduler

conn = db.get_connection()
db.init_schema(conn)
conn.commit()
conn.close()

credential_protector = DpapiCredentialProtector()

app = create_app(credential_protector=credential_protector)
scheduler = build_scheduler(credential_protector=credential_protector)
scheduler.start()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
