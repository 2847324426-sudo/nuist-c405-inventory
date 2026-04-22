from __future__ import annotations

import os
from datetime import datetime
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)


def make_database_url() -> str:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        return "sqlite:///" + os.path.join(INSTANCE_DIR, "inventory.db")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif database_url.startswith("postgresql://") and "+psycopg" not in database_url:
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = make_database_url()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("COOKIE_SECURE", "0") == "1"


db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "请先登录"
login_manager.login_message_category = "warning"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(80), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="member")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def set_password(self, raw_password: str):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class Item(db.Model):
    __tablename__ = "items"

    id = db.Column(db.Integer, primary_key=True)
    category_path = db.Column(db.String(255), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    model = db.Column(db.String(120), nullable=False, default="")
    spec = db.Column(db.String(255), nullable=False, default="")
    unit = db.Column(db.String(20), nullable=False, default="个")
    quantity = db.Column(db.Integer, nullable=False, default=0)
    min_quantity = db.Column(db.Integer, nullable=False, default=0)
    location = db.Column(db.String(255), nullable=False, default="")
    note = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    creator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    creator = db.relationship("User", backref="created_items")


class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("items.id"), nullable=False, index=True)
    tx_type = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    before_quantity = db.Column(db.Integer, nullable=False)
    after_quantity = db.Column(db.Integer, nullable=False)
    purpose = db.Column(db.String(255), nullable=False, default="")
    remark = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    operator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    item = db.relationship("Item", backref="transactions")
    operator = db.relationship("User", backref="transactions")


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, int(user_id))


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if not current_user.is_admin:
            flash("只有管理员可以访问这个页面", "danger")
            return redirect(url_for("items"))
        return view_func(*args, **kwargs)

    return wrapper


def parse_non_negative_int(value: str, field_name: str) -> int:
    try:
        number = int(value)
    except Exception as exc:
        raise ValueError(f"{field_name}必须是整数") from exc
    if number < 0:
        raise ValueError(f"{field_name}不能小于0")
    return number


def seed_default_admin():
    username = os.getenv("DEFAULT_ADMIN_USERNAME", "admin").strip() or "admin"
    password = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123456").strip() or "admin123456"
    display_name = os.getenv("DEFAULT_ADMIN_DISPLAY_NAME", "系统管理员").strip() or "系统管理员"
    admin = User.query.filter_by(username=username).first()
    if admin:
        return
    admin = User(username=username, display_name=display_name, role="admin")
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()


@app.context_processor
def inject_globals():
    low_stock_count = 0
    if current_user.is_authenticated:
        low_stock_count = db.session.query(func.count(Item.id)).filter(Item.quantity <= Item.min_quantity).scalar() or 0
    return {"current_year": datetime.utcnow().year, "low_stock_count": low_stock_count}


@app.before_request
def bootstrap_database():
    db.create_all()
    seed_default_admin()


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("items"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"
        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            flash("用户名或密码错误", "danger")
            return render_template("login.html")
        login_user(user, remember=remember)
        flash(f"欢迎回来，{user.display_name}", "success")
        return redirect(url_for("items"))
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("已退出登录", "info")
    return redirect(url_for("login"))


@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("items"))
    return redirect(url_for("login"))


@app.route("/items")
@login_required
def items():
    keyword = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    query = Item.query
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            (Item.name.ilike(like))
            | (Item.model.ilike(like))
            | (Item.spec.ilike(like))
            | (Item.location.ilike(like))
            | (Item.note.ilike(like))
        )
    if category:
        query = query.filter(Item.category_path == category)
    items_data = query.order_by(Item.category_path.asc(), Item.name.asc(), Item.model.asc()).all()
    categories = [x[0] for x in db.session.query(Item.category_path).distinct().order_by(Item.category_path.asc()).all()]
    total_items = len(items_data)
    total_quantity = sum(item.quantity for item in items_data)
    return render_template(
        "items.html",
        items=items_data,
        keyword=keyword,
        category=category,
        categories=categories,
        total_items=total_items,
        total_quantity=total_quantity,
    )


@app.route("/items/new", methods=["GET", "POST"])
@login_required
def create_item():
    if request.method == "POST":
        try:
            item = Item(
                category_path=request.form.get("category_path", "").strip(),
                name=request.form.get("name", "").strip(),
                model=request.form.get("model", "").strip(),
                spec=request.form.get("spec", "").strip(),
                unit=request.form.get("unit", "个").strip() or "个",
                quantity=parse_non_negative_int(request.form.get("quantity", "0"), "当前库存"),
                min_quantity=parse_non_negative_int(request.form.get("min_quantity", "0"), "预警库存"),
                location=request.form.get("location", "").strip(),
                note=request.form.get("note", "").strip(),
                creator_id=current_user.id,
            )
            if not item.category_path or not item.name:
                raise ValueError("分类路径和名称不能为空")
            db.session.add(item)
            db.session.flush()
            tx = Transaction(
                item_id=item.id,
                tx_type="ADJUST",
                quantity=item.quantity,
                before_quantity=0,
                after_quantity=item.quantity,
                purpose="创建物料",
                remark="新建物料时初始化库存",
                operator_id=current_user.id,
            )
            db.session.add(tx)
            db.session.commit()
            flash("物料已新增", "success")
            return redirect(url_for("items"))
        except Exception as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return render_template("item_form.html", item=None)


@app.route("/items/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def edit_item(item_id: int):
    item = db.session.get(Item, item_id)
    if not item:
        flash("物料不存在", "danger")
        return redirect(url_for("items"))

    if request.method == "POST":
        try:
            old_quantity = item.quantity
            item.category_path = request.form.get("category_path", "").strip()
            item.name = request.form.get("name", "").strip()
            item.model = request.form.get("model", "").strip()
            item.spec = request.form.get("spec", "").strip()
            item.unit = request.form.get("unit", "个").strip() or "个"
            item.quantity = parse_non_negative_int(request.form.get("quantity", "0"), "当前库存")
            item.min_quantity = parse_non_negative_int(request.form.get("min_quantity", "0"), "预警库存")
            item.location = request.form.get("location", "").strip()
            item.note = request.form.get("note", "").strip()
            item.updated_at = datetime.utcnow()
            if not item.category_path or not item.name:
                raise ValueError("分类路径和名称不能为空")
            if old_quantity != item.quantity:
                tx = Transaction(
                    item_id=item.id,
                    tx_type="ADJUST",
                    quantity=item.quantity,
                    before_quantity=old_quantity,
                    after_quantity=item.quantity,
                    purpose="编辑物料",
                    remark="编辑物料时修改库存",
                    operator_id=current_user.id,
                )
                db.session.add(tx)
            db.session.commit()
            flash("物料已更新", "success")
            return redirect(url_for("items"))
        except Exception as exc:
            db.session.rollback()
            flash(str(exc), "danger")

    return render_template("item_form.html", item=item)


@app.route("/items/<int:item_id>/move", methods=["GET", "POST"])
@login_required
def move_item(item_id: int):
    item = db.session.get(Item, item_id)
    if not item:
        flash("物料不存在", "danger")
        return redirect(url_for("items"))

    if request.method == "POST":
        try:
            tx_type = request.form.get("tx_type", "OUT").strip().upper()
            quantity = parse_non_negative_int(request.form.get("quantity", "0"), "数量")
            purpose = request.form.get("purpose", "").strip()
            remark = request.form.get("remark", "").strip()
            if quantity <= 0:
                raise ValueError("数量必须大于0")
            before_quantity = item.quantity
            if tx_type == "IN":
                after_quantity = before_quantity + quantity
            elif tx_type == "OUT":
                if before_quantity < quantity:
                    raise ValueError("库存不足，无法领用")
                after_quantity = before_quantity - quantity
            elif tx_type == "ADJUST":
                after_quantity = quantity
            else:
                raise ValueError("无效的操作类型")
            item.quantity = after_quantity
            item.updated_at = datetime.utcnow()
            tx = Transaction(
                item_id=item.id,
                tx_type=tx_type,
                quantity=quantity,
                before_quantity=before_quantity,
                after_quantity=after_quantity,
                purpose=purpose,
                remark=remark,
                operator_id=current_user.id,
            )
            db.session.add(tx)
            db.session.commit()
            flash("库存已更新", "success")
            return redirect(url_for("items"))
        except Exception as exc:
            db.session.rollback()
            flash(str(exc), "danger")

    return render_template("movement_form.html", item=item)


@app.route("/transactions")
@login_required
def transactions():
    rows = Transaction.query.order_by(Transaction.created_at.desc()).limit(500).all()
    return render_template("transactions.html", rows=rows)


@app.route("/users", methods=["GET", "POST"])
@login_required
@admin_required
def users():
    if request.method == "POST":
        try:
            username = request.form.get("username", "").strip()
            display_name = request.form.get("display_name", "").strip()
            password = request.form.get("password", "")
            role = request.form.get("role", "member").strip()
            if not username or not display_name or not password:
                raise ValueError("用户名、显示名、密码都不能为空")
            if User.query.filter_by(username=username).first():
                raise ValueError("用户名已存在")
            if role not in {"admin", "member"}:
                raise ValueError("角色不正确")
            user = User(username=username, display_name=display_name, role=role)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash("账号已创建", "success")
            return redirect(url_for("users"))
        except Exception as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    all_users = User.query.order_by(User.created_at.asc()).all()
    return render_template("users.html", users=all_users)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
