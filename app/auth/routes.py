"""Auth blueprint – register, login, logout."""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from app import db
from app.models import User, AuditLog
from app.auth.forms import RegistrationForm, LoginForm

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("media.dashboard"))

    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data.strip(),
            email=form.email.data.strip().lower(),
            role="user",
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()

        # Audit
        db.session.add(AuditLog(user_id=user.id, action="register", result="success"))
        db.session.commit()

        flash("Registration successful — please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("media.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.strip().lower()).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            db.session.add(AuditLog(user_id=user.id, action="login", result="success"))
            db.session.commit()
            next_page = request.args.get("next")
            return redirect(next_page or url_for("media.dashboard"))

        # Failed login
        if user:
            db.session.add(AuditLog(user_id=user.id, action="login", result="failure"))
            db.session.commit()
        flash("Invalid email or password.", "danger")

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    db.session.add(AuditLog(user_id=current_user.id, action="logout", result="success"))
    db.session.commit()
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
