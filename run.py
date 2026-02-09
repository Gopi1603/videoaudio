"""Entry-point — run with `python run.py`."""

from app import create_app, db
from app.models import User

app = create_app()


@app.cli.command("seed-admin")
def seed_admin():
    """Create a default admin account (dev convenience)."""
    if User.query.filter_by(role="admin").first():
        print("Admin already exists.")
        return
    admin = User(username="admin", email="admin", role="admin")
    admin.set_password("admin")
    db.session.add(admin)
    db.session.commit()
    print("Admin created  ➜  admin / admin")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
