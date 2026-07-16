from app.routes import create_app

app = create_app()

if __name__ == "__main__":
    from app.config import get_host, get_port

    app.run(host=get_host(), port=get_port())
