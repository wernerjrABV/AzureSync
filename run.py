from app import db
from app.routes import create_app
from app.scheduler import build_scheduler

conn = db.get_connection()
db.init_schema(conn)
conn.commit()
conn.close()

app = create_app()
scheduler = build_scheduler()
scheduler.start()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
