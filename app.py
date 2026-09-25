import socket

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate


from flask import (
    Flask, request, jsonify, render_template,
    session, redirect, url_for
)
try:
    from importlib import import_module
    _socketio = import_module("flask_socketio")
    SocketIO = _socketio.SocketIO
    join_room = _socketio.join_room
except ImportError:
    # Flask-SocketIO がないとき用の代替クラス
    class SocketIO:
        def __init__(self, app):
            self.app = app

        def on(self, *_args, **_kwargs):
            return lambda func: func

        def emit(self, *_args, **_kwargs):
            return None

        def run(self, *args, **kwargs):
            # host/port は Flask に任せる。debug だけ拾う
            debug = kwargs.get("debug", True)
            return self.app.run(debug=debug)

    def join_room(_room):
        return None

import os
import json
import random
import re
import threading
from werkzeug.utils import secure_filename
import stripe
import time
import uuid
import threading
from datetime import date

from werkzeug.security import generate_password_hash, check_password_hash
FREE_SWIPE_LIMIT = 5
SWIPE_UNLOCK_COST = 50

COIN_PRODUCTS = {
    100: 980,
    500: 3980,
    1000: 6980,
    10000: 59800
}

SWIPE_DAILY_FILE = "swipe_daily.json"


def get_swipe_daily_data(user_id):
    today = date.today().isoformat()

    data = swipe_unlocks.get(user_id)

    if not data or data.get("date") != today:
        data = {
            "date": today,
            "extra_cards": 0
        }

        swipe_unlocks[user_id] = data
        save_json(SWIPE_UNLOCKS_FILE, swipe_unlocks)

    return data

def get_daily_swipe_count(user_id):
    today = date.today().isoformat()

    data = swipe_daily.get(user_id)

    if not data or data.get("date") != today:
        data = {
            "date": today,
            "count": 0
        }

        swipe_daily[user_id] = data
        save_json(SWIPE_DAILY_FILE, swipe_daily)

    return data

CPU_WAIT_SECONDS = 300
daifugo_rooms = {}

app = Flask(__name__)

# =========================
# Flask Secret Key
# =========================

app.secret_key = os.environ.get("FLASK_SECRET_KEY")

if not app.secret_key:
    raise RuntimeError(
        "FLASK_SECRET_KEY が設定されていません"
    )


# =========================
# PostgreSQL
# =========================

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL が設定されていません"
    )

# 古い形式のURLにも対応
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql+psycopg://",
        1
    )
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1
    )

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


# DB初期化
db = SQLAlchemy(app)

migrate = Migrate(app, db)

# =========================
# Database Models
# =========================

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(
        db.String(100),
        primary_key=True
    )

    password = db.Column(
        db.String(255),
        nullable=False
    )

    name = db.Column(
        db.String(100)
    )

    gender = db.Column(
        db.String(50)
    )

    age = db.Column(
        db.Integer
    )

    intro = db.Column(
        db.Text
    )

    photo_url = db.Column(
        db.Text
    )

    coins = db.Column(
        db.Integer,
        nullable=False,
        default=0
    )

    stars = db.Column(
        db.Integer,
        nullable=False,
        default=0
    )

    birthday = db.Column(
        db.String(20)
    )

    address = db.Column(
        db.String(255)
    )

    id_photo = db.Column(
        db.Text
    )

    verified = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    verified = db.Column(
            db.Boolean,
            nullable=False,
            default=False
        )
    
    can_send_photo = db.Column(
            db.Boolean,
            nullable=False,
            default=False
        )

class StripePayment(db.Model):
    __tablename__ = "stripe_payments"

    session_id = db.Column(
        db.String(255),
        primary_key=True
    )

    user_id = db.Column(
        db.String(100),
        nullable=False
    )

    coin = db.Column(
        db.Integer,
        nullable=False
    )

    processed = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

class Like(db.Model):
    __tablename__ = "likes"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    sender_id = db.Column(
        db.String(100),
        db.ForeignKey("users.id"),
        nullable=False
    )

    receiver_id = db.Column(
        db.String(100),
        db.ForeignKey("users.id"),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint(
            "sender_id",
            "receiver_id",
            name="uq_like_sender_receiver"
        ),
    )


    
# =========================
# Socket.IO
# =========================

socketio = SocketIO(
    app,
    async_mode="threading"
)



rooms = {}  # スピード＆ジオゲッサー用オンライン対戦ルーム
daifugo_rooms = {}  # 大富豪用オンライン対戦ルーム

# -------------------------
# Stripe設定

# -------------------------
# -------------------------
# Stripe設定
# -------------------------

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")

STRIPE_WEBHOOK_SECRET = os.environ.get(
    "STRIPE_WEBHOOK_SECRET"
)
BASE_URL = os.environ.get(
    "BASE_URL",
    "http://127.0.0.1:5000"
)


if not STRIPE_SECRET_KEY:
    raise RuntimeError(
        "STRIPE_SECRET_KEY が設定されていません"
    )

stripe.api_key = STRIPE_SECRET_KEY

# -------------------------
# 永続保存ファイル
# -------------------------
USERS_FILE = "users.json"
CHATS_FILE = "chats.json"
BOARDS_FILE = "boards.json"
MAILBOXES_FILE = "mailboxes.json"
SWIPE_HISTORY_FILE = "swipe_history.json"
SWIPE_UNLOCKS_FILE = "swipe_unlocks.json"

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

STRIPE_PAYMENTS_FILE = "stripe_payments.json"

users = load_json(USERS_FILE, {})
chats = load_json(CHATS_FILE, {})
boards = load_json(BOARDS_FILE, [])
mailboxes = load_json(MAILBOXES_FILE, {})
swipe_history = load_json(SWIPE_HISTORY_FILE, {})
swipe_unlocks = load_json(SWIPE_UNLOCKS_FILE, {})
swipe_daily = load_json(SWIPE_DAILY_FILE, {})
stripe_payments = load_json(STRIPE_PAYMENTS_FILE, {})
# -------------------------
# 画像アップロード設定
# -------------------------
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# -------------------------
# トランプ画像読み込み
# -------------------------
def load_card_images():
    card_dir = "static/cards"
    if not os.path.exists(card_dir):
        return []

    files = os.listdir(card_dir)
    cards = []

    pattern = re.compile(
        r"card_(spades|hearts|diamonds|clubs)_(A|J|Q|K|10|[0-9]{2})",
        re.IGNORECASE
    )

    for f in files:
        m = pattern.search(f)
        if not m:
            continue

        suit_raw = m.group(1).lower()
        num_raw = m.group(2).upper()

        suit_map = {
            "spades": "spade",
            "hearts": "heart",
            "diamonds": "diamond",
            "clubs": "club"
        }
        suit = suit_map.get(suit_raw, suit_raw)

        if num_raw in ["A", "J", "Q", "K", "10"]:
            num = num_raw
        else:
            num = str(int(num_raw))

        value_table = {
            "3": 3, "4": 4, "5": 5, "6": 6,
            "7": 7, "8": 8, "9": 9, "10": 10,
            "J": 11, "Q": 12, "K": 13, "A": 14,
            "2": 15
        }
        if num not in value_table:
            continue

        cards.append({
            "suit": suit,
            "num": num,
            "img": f"/static/cards/{f}",
            "value": value_table[num]
        })

    return cards


def check_bind(field):
    """場の最後のカードが縛りを発生させるカードなら、そのマークを返す。"""
    if not field:
        return None

    last = field[-1]
    if last.get("num") == "5":
        return last.get("suit")

    return None


# -------------------------
# トップ
# -------------------------
@app.route("/")
def top():
    return render_template("top.html")


# -------------------------
# 新規登録
# -------------------------
@app.route("/register_page")
def register_page():
    return render_template("register_page.html")

@app.route("/register", methods=["POST"])
def register():

    user_id = request.form.get("user_id", "").strip()
    password = request.form.get("password", "")
    name = request.form.get("name", "").strip()

    gender = request.form.get("gender", "")
    birthday = request.form.get("birthday", "")
    address = request.form.get("address", "")
    intro = request.form.get("intro", "")

    # -------------------------
    # 入力チェック
    # -------------------------

    if not user_id:
        return "ユーザーIDを入力してください", 400

    if not password:
        return "パスワードを入力してください", 400

    if not name:
        return "名前を入力してください", 400


    # -------------------------
    # ID重複チェック
    # -------------------------

    existing_user = db.session.get(
        User,
        user_id
    )

    if existing_user:
        return "そのユーザーIDは既に使用されています", 409


    # -------------------------
    # パスワードをハッシュ化
    # -------------------------

    password_hash = generate_password_hash(
        password
    )


    # -------------------------
    # DB用ユーザー作成
    # -------------------------

    new_user = User(
        id=user_id,
        password=password_hash,
        name=name,
        gender=gender,
        birthday=birthday,
        address=address,
        intro=intro,
        coins=0,
        stars=0,
        verified=False
    )


    try:

        db.session.add(new_user)

        db.session.commit()


    except Exception as e:

        db.session.rollback()

        print(
            "ユーザー登録DBエラー:",
            str(e)
        )

        return "ユーザー登録に失敗しました", 500


    # -------------------------
    # ログイン状態にする
    # -------------------------

    session["user_id"] = user_id


    return redirect(
        url_for("home")
    )


# -------------------------
# ログイン
# -------------------------
@app.route("/login_page")
def login_page():
    return render_template("login_page.html")

@app.route("/login", methods=["POST"])
def login():

    user_id = request.form.get(
        "user_id",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )

    # -------------------------
    # 入力チェック
    # -------------------------

    if not user_id or not password:
        return "ユーザーIDとパスワードを入力してください", 400


    # -------------------------
    # PostgreSQLからユーザー取得
    # -------------------------

    user = db.session.get(
        User,
        user_id
    )


    # -------------------------
    # ユーザー存在チェック
    # -------------------------

    if not user:
        return "ユーザーIDまたはパスワードが違います", 401


    # -------------------------
    # パスワード確認
    # -------------------------

    if not check_password_hash(
        user.password,
        password
    ):
        return "ユーザーIDまたはパスワードが違います", 401


    # -------------------------
    # ログイン成功
    # -------------------------

    session["user_id"] = user.id

    return redirect(
        url_for("home")
    )


# -------------------------
# ホーム
# -------------------------
@app.route("/home")
def home():

    user_id = session.get("user_id")

    if not user_id:
        return redirect(url_for("top"))

    current_user = db.session.get(
        User,
        user_id
    )

    if not current_user:
        session.pop("user_id", None)
        return redirect(url_for("top"))

    filtered_users = db.session.execute(
        db.select(User)
        .where(User.id != user_id)
    ).scalars().all()

    return render_template(
        "home.html",
        user=current_user,
        filtered_users=filtered_users
    )

# -------------------------
# スワイプ用 次のユーザー
# -------------------------
@app.route("/swipe/record", methods=["POST"])
def swipe_record():

    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "message": "ログインしてください"
        }), 401

    user = db.session.get(
        User,
        user_id
    )

    if not user:
        return jsonify({
            "success": False,
            "message": "ユーザーが見つかりません"
        }), 404

    data = get_daily_swipe_count(
        user_id
    )

    unlock_data = get_swipe_daily_data(
        user_id
    )

    extra_cards = unlock_data.get(
        "extra_cards",
        0
    )

    limit = (
        FREE_SWIPE_LIMIT
        + extra_cards
    )

    if data["count"] >= limit:

        return jsonify({
            "success": False,
            "locked": True,
            "count": data["count"],
            "limit": limit,
            "coins": user.coins
        })

    data["count"] += 1

    swipe_daily[user_id] = data

    save_json(
        SWIPE_DAILY_FILE,
        swipe_daily
    )

    locked = (
        data["count"] >= limit
    )

    return jsonify({
        "success": True,
        "locked": locked,
        "count": data["count"],
        "limit": limit,
        "coins": user.coins
    })

@app.route("/swipe/next")
def swipe_next():

    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "message": "ログインしてください"
        }), 401

    current_user = db.session.get(
        User,
        user_id
    )

    if not current_user:
        return jsonify({
            "success": False,
            "message": "ユーザーが見つかりません"
        }), 404

    now = time.time()
    one_day = 60 * 60 * 24

    user_history = swipe_history.get(
        user_id,
        {}
    )

    user_history = {
        uid: timestamp
        for uid, timestamp
        in user_history.items()
        if now - timestamp < one_day
    }

    swipe_history[user_id] = user_history

    daily_data = get_swipe_daily_data(
        user_id
    )

    extra_cards = daily_data.get(
        "extra_cards",
        0
    )

    allowed_count = (
        FREE_SWIPE_LIMIT
        + extra_cards
    )

    viewed_count = len(
        user_history
    )

    if viewed_count >= allowed_count:

        return jsonify({
            "success": False,
            "locked": True,
            "message":
                "本日の無料カードをすべて見ました",
            "cost":
                SWIPE_UNLOCK_COST,
            "coins":
                current_user.coins
        })

    all_users = db.session.execute(
        db.select(User)
        .where(User.id != user_id)
    ).scalars().all()

    candidates = []

    for candidate in all_users:

        if candidate.id in user_history:
            continue

        candidates.append(
            candidate
        )

    if not candidates:

        return jsonify({
            "success": False,
            "locked": False,
            "message":
                "現在表示できるユーザーはいません"
        })

    selected_user = random.choice(
        candidates
    )

    selected_id = selected_user.id

    swipe_history.setdefault(
        user_id,
        {}
    )[selected_id] = now

    save_json(
        SWIPE_HISTORY_FILE,
        swipe_history
    )

    return jsonify({
        "success": True,

        "user": {
            "id": selected_user.id,
            "name": selected_user.name,
            "age": selected_user.age,
            "gender": selected_user.gender,
            "address": selected_user.address,
            "intro": selected_user.intro,
            "photo_url":
                selected_user.photo_url
        },

        "viewed":
            viewed_count + 1,

        "limit":
            allowed_count
    })

@app.route(
    "/swipe/unlock",
    methods=["POST"]
)
def swipe_unlock():

    user_id = session.get(
        "user_id"
    )

    if not user_id:

        return jsonify({
            "success": False,
            "message":
                "ログインしてください"
        }), 401

    user = db.session.get(
        User,
        user_id
    )

    if not user:

        return jsonify({
            "success": False,
            "message":
                "ユーザーが見つかりません"
        }), 404

    coins = user.coins or 0

    if coins < SWIPE_UNLOCK_COST:

        return jsonify({
            "success": False,
            "message":
                "コインが足りません",
            "coins": coins
        })

    try:

        user.coins = (
            coins
            - SWIPE_UNLOCK_COST
        )

        daily_data = (
            get_swipe_daily_data(
                user_id
            )
        )

        daily_data[
            "extra_cards"
        ] = (
            daily_data.get(
                "extra_cards",
                0
            )
            + 1
        )

        swipe_unlocks[
            user_id
        ] = daily_data

        db.session.commit()

        save_json(
            SWIPE_UNLOCKS_FILE,
            swipe_unlocks
        )

    except Exception as e:

        db.session.rollback()

        print(
            "スワイプ解放エラー:",
            str(e)
        )

        return jsonify({
            "success": False,
            "message":
                "処理に失敗しました"
        }), 500

    return jsonify({
        "success": True,
        "message":
            "カードを1枚解放しました",
        "coins":
            user.coins
    })
# =========================
# メールボックス
# =========================

@app.route("/mailbox")
def mailbox():

    user_id = session.get("user_id")

    if not user_id:
        return redirect(url_for("top"))

    user_mails = mailboxes.get(
        user_id,
        []
    )

    unread_count = sum(
        1
        for mail in user_mails
        if not mail.get("read", False)
    )

    return render_template(
        "mailbox.html",
        mails=user_mails,
        unread_count=unread_count
    )

# -------------------------
# LIKE
# -------------------------
@app.route("/like/<partner>")
def like(partner):
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("top"))

    if partner not in users[user_id]["likes"]:
        users[user_id]["likes"].append(partner)

    save_json(USERS_FILE, users)

    matched = False
    if user_id in users.get(partner, {}).get("likes", []):
        users[user_id]["can_send_photo"] = True
        users[partner]["can_send_photo"] = True
        save_json(USERS_FILE, users)
        matched = True

    return jsonify({"matched": matched})


# -------------------------
# プロフィール
# -------------------------
@app.route("/profile")
def profile():

    user_id = session.get(
        "user_id"
    )

    if not user_id:
        return redirect(
            url_for("top")
        )

    user = db.session.get(
        User,
        user_id
    )

    if not user:
        session.pop(
            "user_id",
            None
        )

        return redirect(
            url_for("top")
        )

    return render_template(
        "profile.html",
        user=user
    )

@app.route("/profile_edit_page")
def profile_edit_page():

    user_id = session.get(
        "user_id"
    )

    if not user_id:
        return redirect(
            url_for("top")
        )

    user = db.session.get(
        User,
        user_id
    )

    if not user:
        return redirect(
            url_for("top")
        )

    return render_template(
        "profile_edit_page.html",
        user=user
    )

    


@app.route(
    "/profile_edit",
    methods=["POST"]
)
def profile_edit():

    user_id = session.get(
        "user_id"
    )

    if not user_id:
        return redirect(
            url_for("top")
        )

    user = db.session.get(
        User,
        user_id
    )

    if not user:
        return redirect(
            url_for("top")
        )

    user.name = request.form.get(
        "name"
    )

    user.address = request.form.get(
        "address"
    )

    user.intro = request.form.get(
        "intro"
    )

    try:

        db.session.commit()

    except Exception as e:

        db.session.rollback()

        print(
            "プロフィール更新エラー:",
            str(e)
        )

        return (
            "プロフィール更新に失敗しました",
            500
        )

    return render_template(
        "profile_edit_result.html",
        user=user
    )


# -------------------------
# チャット一覧
# -------------------------
# -------------------------
# チャット一覧
# -------------------------
@app.route("/chat_page")
def chat_page():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("top"))

    partners = {}
    for msg in chats.get(user_id, []):
        partners[msg["partner"]] = msg

    return render_template("chat_page.html", partners=partners, users=users)


# -------------------------
# SocketIO: チャットルーム入室
# -------------------------
@socketio.on("join_room")
def handle_join_room(data):
    room = data["room"]
    join_room(room)


# -------------------------
# チャットルーム
# -------------------------
@app.route("/chat_room/<partner>", methods=["GET", "POST"])
def chat_room(partner):

    user_id = session.get("user_id")

    if not user_id:
        return redirect(url_for("top"))

    # PostgreSQLから取得
    current_user = db.session.get(User, user_id)
    partner_user = db.session.get(User, partner)

    if not current_user:
        session.pop("user_id", None)
        return redirect(url_for("top"))

    if not partner_user:
        return "相手ユーザーが存在しません", 404

    # 既読処理
    for msg in chats.get(user_id, []):
        if (
            msg.get("partner") == partner
            and msg.get("sender") != user_id
        ):
            msg["read"] = True

    save_json(CHATS_FILE, chats)

    # -------------------------
    # メッセージ送信
    # -------------------------
    if request.method == "POST":

        message = request.form.get("message")
        photo = request.files.get("photo")

        if (current_user.coins or 0) < 30:
            return jsonify({
                "error": "コイン不足（30必要）"
            }), 403

        photo_url = None

        if photo and allowed_file(photo.filename):

            filename = secure_filename(
                photo.filename
            )

            save_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                filename
            )

            photo.save(save_path)

            photo_url = "/" + save_path.replace(
                "\\",
                "/"
            )

        try:

            # PostgreSQLで30コイン消費
            current_user.coins -= 30

            db.session.commit()

        except Exception as e:

            db.session.rollback()

            print(
                "チャットコイン消費エラー:",
                str(e)
            )

            return jsonify({
                "error": "コイン処理に失敗しました"
            }), 500

        now = time.time()

        # 自分側
        chats.setdefault(
            user_id,
            []
        ).append({
            "partner": partner,
            "sender": user_id,
            "message": message,
            "photo": photo_url,
            "read": False,
            "gift": False,
            "timestamp": now
        })

        # 相手側
        chats.setdefault(
            partner,
            []
        ).append({
            "partner": user_id,
            "sender": user_id,
            "message": message,
            "photo": photo_url,
            "read": False,
            "gift": False,
            "timestamp": now
        })

        save_json(
            CHATS_FILE,
            chats
        )

    # -------------------------
    # 履歴
    # -------------------------
    history = [
        item
        for item in chats.get(user_id, [])
        if item.get("partner") == partner
    ]

    history.sort(
        key=lambda x: x.get(
            "timestamp",
            0
        )
    )

    return render_template(
        "chat_room.html",
        partner=partner,
        partner_user=partner_user,
        history=history,
        user_id=user_id
    )


# -------------------------
# ギフト送信（SocketIO）
# -------------------------
@socketio.on("send_rank_gift")
def handle_send_rank_gift(data):

    print("===== ギフト送信 =====")

    user_id = session.get("user_id")

    if not user_id:
        return

    partner = data.get("partner")
    rank = data.get("rank")

    star_map = {
        "銅": 5,
        "銀": 15,
        "金": 30,
        "サファイア": 70,
        "エメラルド": 120,
        "ダイヤモンド": 300,
        "プラチナ": 700,
        "氷の柱": 2000,
        "ハートの雨": 5000,
        "宝石の爆発": 10000,
        "恋の龍": 50000
    }

    cost_map = {
        "銅": 10,
        "銀": 30,
        "金": 60,
        "サファイア": 120,
        "エメラルド": 200,
        "ダイヤモンド": 500,
        "プラチナ": 1000,
        "氷の柱": 10000,
        "ハートの雨": 30000,
        "宝石の爆発": 50000,
        "恋の龍": 100000
    }

    if rank not in cost_map:
        return

    sender_user = db.session.get(
        User,
        user_id
    )

    receiver_user = db.session.get(
        User,
        partner
    )

    if not sender_user or not receiver_user:
        return

    stars = star_map[rank]
    cost = cost_map[rank]

    if (sender_user.coins or 0) < cost:

        socketio.emit(
            "gift_error",
            {
                "message": "コイン不足です"
            },
            room=user_id
        )

        return

    try:

        # 送信者のコインを減らす
        sender_user.coins -= cost

        # 受信者のスターを増やす
        receiver_user.stars = (
            (receiver_user.stars or 0)
            + stars
        )

        # 2つまとめてDBへ保存
        db.session.commit()

    except Exception as e:

        db.session.rollback()

        print(
            "ギフトDB処理エラー:",
            str(e)
        )

        socketio.emit(
            "gift_error",
            {
                "message": "ギフト処理に失敗しました"
            },
            room=user_id
        )

        return

    timestamp = time.time()

    chats.setdefault(
        user_id,
        []
    ).append({
        "partner": partner,
        "sender": user_id,
        "message":
            f"{rank}ギフトを送りました！（+{stars}）",
        "gift": True,
        "timestamp": timestamp
    })

    chats.setdefault(
        partner,
        []
    ).append({
        "partner": user_id,
        "sender": user_id,
        "message":
            f"{rank}ギフトを受け取りました！（+{stars}）",
        "gift": True,
        "timestamp": timestamp
    })

    save_json(
        CHATS_FILE,
        chats
    )

    socketio.emit(
        "gift_received",
        {
            "from": user_id,
            "rank": rank,
            "stars": stars
        },
        room=partner
    )



# -------------------------
# チャットAPI（Flutter用）
# -------------------------
@app.route("/chat/send", methods=["POST"])
def chat_send():

    data = request.get_json(
        silent=True
    ) or {}

    user_id = data.get("id")
    partner = data.get("partner")
    message = data.get("message")

    user = db.session.get(
        User,
        user_id
    )

    partner_user = db.session.get(
        User,
        partner
    )

    if not user:
        return jsonify({
            "error": "ユーザーが存在しません"
        }), 404

    if not partner_user:
        return jsonify({
            "error": "相手が存在しません"
        }), 404

    if (user.coins or 0) < 30:
        return jsonify({
            "error": "コイン不足（30必要）"
        }), 403

    try:

        user.coins -= 30

        db.session.commit()

    except Exception as e:

        db.session.rollback()

        print(
            "チャットAPI DBエラー:",
            str(e)
        )

        return jsonify({
            "error": "コイン処理に失敗しました"
        }), 500

    now = time.time()

    chats.setdefault(
        user_id,
        []
    ).append({
        "partner": partner,
        "sender": user_id,
        "message": message,
        "photo": None,
        "read": False,
        "gift": False,
        "timestamp": now
    })

    chats.setdefault(
        partner,
        []
    ).append({
        "partner": user_id,
        "sender": user_id,
        "message": message,
        "photo": None,
        "read": False,
        "gift": False,
        "timestamp": now
    })

    save_json(
        CHATS_FILE,
        chats
    )

    return jsonify({
        "message": "送信完了",
        "coins": user.coins
    })

GIFTS = {
    "bronze": {"name": "銅", "coins": 10, "star": 5},
    "silver": {"name": "銀", "coins": 30, "star": 15},
    "gold": {"name": "金", "coins": 60, "star": 30},
    "sapphire": {"name": "サファイア", "coins": 120, "star": 70},
    "emerald": {"name": "エメラルド", "coins": 200, "star": 120},
    "diamond": {"name": "ダイヤ", "coins": 500, "star": 300},
    "platinum": {"name": "プラチナ", "coins": 1000, "star": 700},
    "ice_pillar": {"name": "氷の柱", "coins": 10000, "star": 2000},
    "heart_rain": {"name": "ハートの雨", "coins": 30000, "star": 5000},
    "gem_explosion": {"name": "宝石の爆発", "coins": 50000, "star": 10000},
    "love_dragon": {"name": "恋の龍", "coins": 100000, "star": 50000}
}

    
@app.route("/send_gift", methods=["POST"])
def send_gift():

    data = request.get_json(
        silent=True
    ) or {}

    sender = session.get(
        "user_id"
    )

    if not sender:
        return jsonify({
            "error": "ログインしてください"
        }), 401

    receiver = data.get(
        "receiver"
    )

    gift_id = data.get(
        "gift_id"
    )

    if gift_id not in GIFTS:

        return jsonify({
            "error": "ギフトが存在しません"
        }), 400

    sender_user = db.session.get(
        User,
        sender
    )

    receiver_user = db.session.get(
        User,
        receiver
    )

    if not sender_user:

        return jsonify({
            "error": "送信者が存在しません"
        }), 404

    if not receiver_user:

        return jsonify({
            "error": "相手が存在しません"
        }), 404

    gift = GIFTS[gift_id]

    if (
        sender_user.coins or 0
    ) < gift["coins"]:

        return jsonify({
            "error": "コインが足りません"
        }), 403

    try:

        sender_user.coins -= (
            gift["coins"]
        )

        receiver_user.stars = (
            (receiver_user.stars or 0)
            + gift["star"]
        )

        db.session.commit()

    except Exception as e:

        db.session.rollback()

        print(
            "ギフトAPI DBエラー:",
            str(e)
        )

        return jsonify({
            "error":
                "ギフト処理に失敗しました"
        }), 500

    print(
        f"{sender} → {receiver} に "
        f"{gift['name']} ギフト送信"
    )

    return jsonify({
        "ok": True,
        "gift": gift["name"],
        "star_added": gift["star"],
        "coins_left":
            sender_user.coins
    })
# -------------------------
# チャットAPI（自動更新）
# -------------------------
@app.route("/chat_room_api/<partner>")
def chat_room_api(partner):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "ログインしてください"})

    my_history = chats.get(user_id, [])
    partner_history = chats.get(partner, [])

    history = []

    for item in my_history:
        if item.get("partner") == partner:
            history.append(item)

    for item in partner_history:
        if item.get("partner") == user_id:
            history.append(item)

    history.sort(key=lambda x: x.get("timestamp", 0))

    return jsonify({"history": history})


# -------------------------
# 掲示板
# -------------------------
@app.route("/board")
def board():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("top"))
    return render_template("board.html", boards=boards)


@app.route("/board_post", methods=["GET", "POST"])
def board_post():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("top"))

    if request.method == "POST":
        title = request.form.get("title")
        body = request.form.get("body")
        boards.append({
            "user_id": user_id,
            "title": title,
            "body": body
        })
        save_json(BOARDS_FILE, boards)
        return redirect(url_for("board"))

    return render_template("board_post.html")

@app.route("/profile/<uid>")
def profile_uid(uid):
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("top"))

    target = users.get(uid)
    if not target:
        return "ユーザーが存在しません"

    return render_template("profile.html", user=target)

# -------------------------
# コインページ
# -------------------------
@app.route("/coin_page")
def coin_page():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("top"))
    user = users.get(user_id)
    return render_template("coin_page.html", user=user)


# -------------------------
# Stripe決済
# -------------------------
@app.route("/pay/stripe", methods=["POST"])
def pay_stripe():

    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "error": "ログインしてください"
        }), 401

    if user_id not in users:
        return jsonify({
            "error": "ユーザーが存在しません"
        }), 404

    data = request.get_json(
        silent=True
    ) or {}

    try:
        coin = int(
            data.get("amount", 0)
        )
    except (TypeError, ValueError):

        return jsonify({
            "error": "不正なコイン数です"
        }), 400


    if coin not in COIN_PRODUCTS:

        return jsonify({
            "error": "購入できないコイン数です"
        }), 400


    yen = COIN_PRODUCTS[coin]


    try:

        checkout_session = (
            stripe.checkout.Session.create(

                mode="payment",

                managed_payments={
                    "enabled": False
                },

                line_items=[
                    {
                        "price_data": {

                            "currency": "jpy",

                            "product_data": {
                                "name":
                                    f"{coin}コイン"
                            },

                            "unit_amount": yen
                        },

                        "quantity": 1
                    }
                ],

                client_reference_id=user_id,

                metadata={
                    "user_id": user_id,
                    "coin": str(coin)
                },

                success_url=(
                    BASE_URL
                    + "/pay/success"
                    + "?session_id="
                    + "{CHECKOUT_SESSION_ID}"
                ),

                cancel_url=(
                    BASE_URL
                    + "/pay/cancel"
                )
            )
        )


        return jsonify({
            "url": checkout_session.url
        })


    except stripe.error.StripeError as e:

        print(
            "Stripeエラー:",
            str(e)
        )

        return jsonify({
            "error":
                "決済ページを作成できませんでした"
        }), 500


    except Exception as e:

        print(
            "決済処理エラー:",
            str(e)
        )

        return jsonify({
            "error":
                "決済処理でエラーが発生しました"
        }), 500

def fulfill_coin_payment(checkout_session):

    # Stripe Sessionを通常のdictへ変換
    if hasattr(checkout_session, "to_dict"):
        checkout_session = checkout_session.to_dict()

    # -------------------------
    # Stripe Session ID
    # -------------------------

    session_id = checkout_session.get("id")

    if not session_id:
        raise ValueError(
            "Stripe Session ID がありません"
        )

    # -------------------------
    # 支払い状態
    # -------------------------

    payment_status = checkout_session.get(
        "payment_status"
    )

    if payment_status != "paid":
        print(
            "未決済のためコイン付与しません:",
            session_id,
            payment_status
        )
        return

    # -------------------------
    # metadata取得
    # -------------------------

    metadata = checkout_session.get(
        "metadata"
    ) or {}

    user_id = metadata.get(
        "user_id"
    )

    coin_value = metadata.get(
        "coins"
    )

    if not user_id:
        raise ValueError(
            "metadata.user_id がありません"
        )

    if not coin_value:
        raise ValueError(
            "metadata.coins がありません"
        )

    try:
        coins = int(coin_value)
    except (TypeError, ValueError):
        raise ValueError(
            "metadata.coins が不正です"
        )

    # -------------------------
    # User取得
    # -------------------------

    user = db.session.get(
        User,
        user_id
    )

    if not user:
        raise ValueError(
            f"ユーザーが存在しません: {user_id}"
        )

    # -------------------------
    # 二重付与防止
    # -------------------------

    existing_payment = db.session.get(
        StripePayment,
        session_id
    )

    if existing_payment:
        print(
            "処理済みStripe Session:",
            session_id
        )
        return

    try:

        # コイン付与
        user.coins = (
            (user.coins or 0)
            + coins
        )

        # 決済履歴
        payment = StripePayment(
            session_id=session_id,
            user_id=user_id,
            coin=coins,
            processed=True
        )

        db.session.add(payment)

        # PostgreSQLへ確定
        db.session.commit()

        print(
            f"Stripe決済完了: "
            f"user={user_id}, "
            f"coins=+{coins}, "
            f"session={session_id}"
        )

    except Exception:
        db.session.rollback()
        raise
    
@app.route(
    "/stripe/webhook",
    methods=["POST"]
)
def stripe_webhook():

    payload = request.get_data()

    signature = request.headers.get(
        "Stripe-Signature"
    )

    if not STRIPE_WEBHOOK_SECRET:
        print(
            "STRIPE_WEBHOOK_SECRET が設定されていません"
        )
        return "", 500

    if not signature:
        print(
            "Stripe-Signature がありません"
        )
        return "", 400

    try:

        event = stripe.Webhook.construct_event(
            payload,
            signature,
            STRIPE_WEBHOOK_SECRET
        )

    except ValueError:

        print(
            "Webhook payloadエラー"
        )

        return "", 400

    except stripe.error.SignatureVerificationError:

        print(
            "Webhook署名エラー"
        )

        return "", 400

    try:

        if (
            event["type"]
            == "checkout.session.completed"
        ):

            checkout_session = (
                event["data"]["object"]
            )

            fulfill_coin_payment(
                checkout_session
            )

    except Exception as e:

        print(
            "Webhook処理エラー:",
            str(e)
        )

        return "", 500

    return "", 200


@app.route("/pay/cancel")
def pay_cancel():

    return redirect(
        url_for("coin_page")
    )


@app.route("/pay/success")
def pay_success():

    user_id = session.get(
        "user_id"
    )

    if not user_id:

        return redirect(
            url_for("login_page")
        )


    session_id = request.args.get(
        "session_id"
    )


    return render_template(
        "payment_success.html",
        session_id=session_id
    )


# -------------------------
# ゲーム選択ページ
# -------------------------
@app.route("/matching_page")
def matching_page():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("top"))
    return render_template("matching_page.html")


# -------------------------
# ゲーム1：質問で相性診断
# -------------------------
@app.route("/matching_question")
def matching_question():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("top"))
    return render_template("matching_question.html")


@app.route("/answer_question", methods=["POST"])
def answer_question():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("top"))

    if users[user_id]["coins"] < 30:
        return "コイン不足（30必要）"

    users[user_id]["coins"] -= 30
    save_json(USERS_FILE, users)

    data = request.form
    answers = [
        data.get("q1"),
        data.get("q2"),
        data.get("q3"),
        data.get("q4"),
        data.get("q5")
    ]
    target_answers = ["A", "B", "C", "A", "C"]

    match_count = sum(1 for a, b in zip(answers, target_answers) if a == b)
    match_rate = int((match_count / 5) * 100)
    matched = match_rate >= 80

    partner = None
    for uid, u in users.items():
        if uid != user_id:
            partner = u
            break

    if matched:
        users[user_id]["can_send_photo"] = True
        save_json(USERS_FILE, users)

    return render_template("result_question.html",
                           match_rate=match_rate,
                           matched=matched,
                           partner=partner)





GOMOKU_ENTRY_COST = 50

GOMOKU_WIN_REWARD = 100

gomoku_rooms = {}

waiting_gomoku_players = []

@app.route("/gomoku_home")

@app.route("/gomoku_home")
def gomoku_home():

    user_id = session.get("user_id")

    if not user_id:
        return redirect(url_for("top"))

    return render_template(
        "gomoku_home.html"
    )

@socketio.on("gomoku_match_request")
def gomoku_match_request():

    user_id = session.get("user_id")

    if not user_id:
        return

    if users[user_id]["coins"] < GOMOKU_ENTRY_COST:

        socketio.emit(
            "match_error",
            {
                "message":
                f"{GOMOKU_ENTRY_COST}コイン必要です"
            },
            room=user_id
        )

        return

    if user_id not in waiting_gomoku_players:

        waiting_gomoku_players.append(
            user_id
        )

    socketio.emit(
        "gomoku_match_update",
        {
            "count":
            len(waiting_gomoku_players)
        }
    )

    check_gomoku_matching()

def check_gomoku_matching():

    global waiting_gomoku_players

    if len(waiting_gomoku_players) < 2:
        return

    players = waiting_gomoku_players[:2]

    waiting_gomoku_players = (
        waiting_gomoku_players[2:]
    )

    room_id = str(uuid.uuid4())

    random.shuffle(players)

    black_player = players[0]

    white_player = players[1]

    board = [
        [0 for _ in range(15)]
        for _ in range(15)
    ]

    gomoku_rooms[room_id] = {

        "players": players,

        "black": black_player,

        "white": white_player,

        "turn": "black",

        "board": board,

        "winner": None,

        "room_id": room_id,

        "last_move_time": time.time()
    }

    # 開始時徴収
    for uid in players:

        users[uid]["coins"] -= (
            GOMOKU_ENTRY_COST
        )

    save_json(
        USERS_FILE,
        users
    )

    for uid in players:

        socketio.emit(
            "gomoku_match_start",
            {
                "room_id": room_id
            },
            room=uid
        )

@app.route("/gomoku_play")
def gomoku_play():

    user_id = session.get("user_id")

    if not user_id:
        return redirect(url_for("top"))

    room_id = request.args.get("room_id")

    if room_id not in gomoku_rooms:
        return "部屋が存在しません"

    room = gomoku_rooms[room_id]

    my_color = None

    if user_id == room["black"]:

        my_color = "black"

    elif user_id == room["white"]:

        my_color = "white"

    else:

        return "参加権限がありません"

    return render_template(
        "gomoku_play.html",
        room_id=room_id,
        my_color=my_color
    )

def check_gomoku_winner(
    board,
    x,
    y,
    stone
):

    directions = [
        (1, 0),
        (0, 1),
        (1, 1),
        (1, -1)
    ]

    for dx, dy in directions:

        count = 1

        tx = x + dx
        ty = y + dy

        while (
            0 <= tx < 15
            and
            0 <= ty < 15
            and
            board[ty][tx] == stone
        ):

            count += 1

            tx += dx
            ty += dy

        tx = x - dx
        ty = y - dy

        while (
            0 <= tx < 15
            and
            0 <= ty < 15
            and
            board[ty][tx] == stone
        ):

            count += 1

            tx -= dx
            ty -= dy

        if count >= 5:
            return True

    return False


@socketio.on("join_gomoku_room")
def join_gomoku_room(data):

    room_id = data["room_id"]

    if room_id not in gomoku_rooms:
        return

    room = gomoku_rooms[room_id]

    join_room(room_id)

    socketio.emit(
        "gomoku_update",
        {
            "board": room["board"],
            "turn": room["turn"]
        },
        room=room_id
    )
    

@socketio.on("gomoku_place")
def gomoku_place(data):

    room_id = data["room_id"]

    x = data["x"]

    y = data["y"]

    user_id = session.get("user_id")

    if room_id not in gomoku_rooms:
        return

    room = gomoku_rooms[room_id]

    if room["winner"] is not None:
        return

    stone = None

    if (
        user_id == room["black"]
        and
        room["turn"] == "black"
    ):
        stone = 1

    elif (
        user_id == room["white"]
        and
        room["turn"] == "white"
    ):
        stone = 2

    else:
        return

    board = room["board"]

    if board[y][x] != 0:
        return

    board[y][x] = stone

    if check_gomoku_winner(
        board,
        x,
        y,
        stone
    ):

        winner = user_id

        room["winner"] = winner

        users[winner]["coins"] += (
            GOMOKU_WIN_REWARD
        )

        save_json(
            USERS_FILE,
            users
        )

        print("勝利判定")
        print("winner =", winner)

        socketio.emit(
            "gomoku_finish",
            {
                "winner": winner
            },
            room=room_id
        )

        print("gomoku_finish送信")

        return

    room["turn"] = (
        "white"
        if room["turn"] == "black"
        else "black"
    )

    socketio.emit(
        "gomoku_update",
        {
            "board": board,
            "turn": room["turn"]
        },
        room=room_id
    )

@app.route("/gomoku_result")
def gomoku_result():

    user_id = session["user_id"]

    result = request.args.get(
        "result"
    )

    return render_template(
        "gomoku_result.html",
        result=result,
        coins=users[user_id]["coins"]
    )

def check_gomoku_timeout():

    while True:

        time.sleep(1)

        for room in gomoku_rooms.values():

            if room["winner"]:
                continue

            if (
                time.time()
                - room["last_move_time"]
                > 20
            ):

                room["turn"] = (
                    "white"
                    if room["turn"]=="black"
                    else "black"
                )

                room["last_move_time"] = (
                    time.time()
                )

                socketio.emit(
                    "gomoku_update",
                    {
                      "board":
                      room["board"],

                      "turn":
                      room["turn"]
                    },
                    room=room["room_id"]
                )

# -------------------------
# ゲーム2：大富豪（自動マッチング＋5分でCPU補充）
# -------------------------
ENTRY_COST = 50

REWARD_TABLE = {
    1: 100,
    2: 70,
    3: 25,
    4: 0
}

POINT_TABLE = {
    "大富豪": 3,
    "富豪": 2,
    "貧民": 1,
    "大貧民": 0
}

import uuid

daifugo_rooms = {}

waiting_players = []


@socketio.on("connect")
def connect():

    user_id = session.get("user_id")

    if user_id:
        join_room(user_id)

        print(f"{user_id} 接続")


@app.route("/matching_daifugo_home")
def matching_daifugo_home():

    user_id = session.get("user_id")

    if not user_id:
        return redirect(url_for("top"))

    return render_template(
        "matching_daifugo_home.html"
    )


@socketio.on("daifugo_match_request")
def daifugo_match_request():

    user_id = session.get("user_id")

    if not user_id:
        return

    if users[user_id]["coins"] < ENTRY_COST:

        socketio.emit(
            "match_error",
            {
                "message":
                f"{ENTRY_COST}コイン必要です"
            },
            room=user_id
        )

        return

    if user_id not in waiting_players:

        waiting_players.append(user_id)

    socketio.emit(
        "daifugo_match_update",
        {
            "count": len(waiting_players)
        }
    )

    check_daifugo_matching()


def check_daifugo_matching():

    global waiting_players

    if len(waiting_players) < 4:
        return

    players = waiting_players[:4]

    waiting_players = waiting_players[4:]

    room_id = str(uuid.uuid4())

    daifugo_rooms[room_id] = {
        "players": players,
        "joined_users": []
    }

    start_online_daifugo(room_id)

    # 4人だけへ通知
    for uid in players:

        socketio.emit(
            "daifugo_match_start",
            {
                "room_id": room_id
            },
            room=uid
        )


def start_online_daifugo(room_id):
    """Initialize the game state for a newly matched Daifugo room."""
    room = daifugo_rooms.get(room_id)
    if not room or len(room.get("players", [])) != 4:
        return

    deck = load_card_images()
    if len(deck) < 52:
        return

    random.shuffle(deck)
    now = time.time()
    room["game"] = {
        "hands": {
            f"p{i + 1}": deck[i * 13:(i + 1) * 13]
            for i in range(4)
        },
        "field": [],
        "round": 1,
        "turn": random.choice(["p1", "p2", "p3", "p4"]),
        "revolution": False,
        "bind_suit": None,
        "last_suit": None,
        "jback_active": False,
        "pass_count": 0,
        "last_player": None,
        "last_action": {f"p{i + 1}": now for i in range(4)},
        "finished": {f"p{i + 1}": False for i in range(4)},
        "finish_order": [],
        "state_mode": "normal",
        "state_message": "ゲーム開始"
    }

def check_cpu_match():

    time.sleep(CPU_WAIT_SECONDS)

    global waiting_players

    if len(waiting_players) == 0:
        return

    if len(waiting_players) >= 4:
        return

    players = waiting_players[:]

    while len(players) < 4:

        players.append(
            f"CPU{len(players)+1}"
        )

    waiting_players.clear()

    room_id = str(uuid.uuid4())

    daifugo_rooms[room_id] = {

        "players": players,

        "joined_users": [],

        "game": None,

        "created_at": time.time()
    }

    for uid in players:

        if uid.startswith("CPU"):
            continue

        socketio.emit(
            "daifugo_match_start",
            {
                "room_id": room_id
            },
            room=uid
        )

@socketio.on("disconnect")
def disconnect():

    user_id = session.get("user_id")

    if not user_id:
        return

    print(
        user_id,
        "切断"
    )

    for room_id, room in daifugo_rooms.items():

        if user_id in room["players"]:

            room.setdefault(
                "disconnected",
                []
            )

@socketio.on("connect")
def connect():

    user_id = session.get("user_id")

    if not user_id:
        return

    join_room(user_id)

    print(
        f"{user_id} 接続"
    )

    for room_id, room in daifugo_rooms.items():

        if user_id in room["players"]:

            join_room(room_id)

            if (
                "disconnected" in room
                and
                user_id in room["disconnected"]
            ):

                room["disconnected"].remove(
                    user_id
                )

                socketio.emit(
                    "reconnected",
                    {
                        "message":
                        "再接続しました"
                    },
                    room=user_id
                )

@app.route("/matching_daifugo_online_play")
def matching_daifugo_online_play():

    user_id = session.get("user_id")

    if not user_id:
        return redirect(url_for("top"))

    room_id = request.args.get("room_id")

    if room_id not in daifugo_rooms:
        return "部屋が存在しません"

    room = daifugo_rooms[room_id]

    my_pid = None

    for i, uid in enumerate(room["players"]):

        if uid == user_id:

            my_pid = f"p{i+1}"
            break

    if my_pid is None:
        return "参加権限がありません"

    game = room["game"]

    return render_template(
        "matching_daifugo_online_play.html",
        room_id=room_id,
        my_pid=my_pid,
        hands=game["hands"],
        field=game["field"],
        round=game["round"],
        state_message=game["state_message"]
    )


# -------------------------
# ゲーム開始（手札配布）
# -------------------------
# -------------------------
# ゲーム開始
# -------------------------

game = {
    "last_suit": None,
    "jback_active": False,
    "round": 1,
    "pass_count": 0,
    "last_player": None,
    "last_action": {},
}


def get_strength(card):

    order = {
        "3": 3,
        "4": 4,
        "5": 5,
        "6": 6,
        "7": 7,
        "8": 8,
        "9": 9,
        "10": 10,
        "J": 11,
        "Q": 12,
        "K": 13,
        "A": 14,
        "2": 15
    }

    return order[card["num"]]

def is_straight(cards):

    if len(cards) < 3:
        return False

    suits = {
        c["suit"]
        for c in cards
    }

    if len(suits) != 1:
        return False

    values = sorted(
        get_strength(c)
        for c in cards
    )

    for i in range(len(values) - 1):

        if values[i + 1] != values[i] + 1:
            return False

    return True

def can_play(game, pid, played):

    field = game["field"]

    revolution = game["revolution"]

    bind_suit = game["bind_suit"]

    if len(played) == 0:
        return False

    nums = {
        c["num"]
        for c in played
    }

    played_straight = is_straight(
        played
    )

    # 同じ数字か階段のみ
    if not played_straight:

        if len(nums) != 1:
            return False

    # 縛り
    if bind_suit:

        for c in played:

            if c["suit"] != bind_suit:
                return False

    # 場が空
    if not field:
        return True

    field_straight = is_straight(
        field
    )

    # 場が階段
    if field_straight:

        if not played_straight:
            return False

        if len(played) != len(field):
            return False

        played_power = min(
            get_strength(c)
            for c in played
        )

        field_power = min(
            get_strength(c)
            for c in field
        )

        if revolution:
            return played_power < field_power

        return played_power > field_power

    # 通常札

def next_turn_online(game, pid):

    order = [
        "p1",
        "p2",
        "p3",
        "p4"
    ]

    idx = order.index(pid)

    for _ in range(4):

        idx = (idx + 1) % 4

        next_pid = order[idx]

        if not game["finished"][next_pid]:
            return next_pid

    return pid

def skip_turn(game, pid):

    current = pid

    for _ in range(2):

        current = next_turn_online(
            game,
            current
        )

    return current

def apply_special_rules_online(
    game,
    played,
    pid
):

    num = played[0]["num"]

    # 8切り
    if num == "8":

        game["field"] = []

        game["bind_suit"] = None

        game["last_suit"] = None

        game["pass_count"] = 0

        game["state_mode"] = "eightcut"

        game["state_message"] = (
            f"{pid} が8切り"
        )

        return "eightcut"

    # Jバック
    if num == "J":

        game["revolution"] = (
            not game["revolution"]
        )

        game["jback_active"] = True

        game["state_mode"] = "jback"

        game["state_message"] = (
            f"{pid} がJバック"
        )

        return "jback"

    # 革命
    nums = {
        c["num"]
        for c in played
    }

    if len(played) == 4 and len(nums) == 1:

        game["revolution"] = (
            not game["revolution"]
        )

        game["state_mode"] = "revolution"

        game["state_message"] = (
            f"{pid} が革命"
        )

        return "revolution"

    # 5スキップ
    if num == "5":

        game["state_mode"] = "skip"

        game["state_message"] = (
            f"{pid} が5スキップ"
        )

        return "skip"

    game["state_mode"] = "normal"

    return "normal"

@socketio.on("play_card")
def play_card(data):

    room_id = data["room_id"]
    pid = data["pid"]
    selected = data["selected"]

    if room_id not in daifugo_rooms:
        return

    game = daifugo_rooms[room_id]["game"]

    if pid != game["turn"]:
        return

    if game["finished"][pid]:
        return

    hand = game["hands"][pid]

    played = []

    for i in selected:

        if i < 0:
            return

        if i >= len(hand):
            return

        played.append(hand[i])

    if not can_play(
        game,
        pid,
        played
    ):

        game["state_message"] = (
            "そのカードは出せません"
        )

        socketio.emit(
            "update_game",
            {
                "room_id": room_id,
                "game": game
            },
            room=room_id
        )

        return

    # 手札削除
    for i in sorted(
        selected,
        reverse=True
    ):
        hand.pop(i)

    game["hands"][pid] = hand

    game["field"] = played

    game["last_player"] = pid

    game["pass_count"] = 0

    # 縛り判定
    suits = {
        c["suit"]
        for c in played
    }

    if len(suits) == 1:

        current_suit = played[0]["suit"]

        if game["last_suit"] == current_suit:

            game["bind_suit"] = current_suit

        game["last_suit"] = current_suit

    else:

        game["last_suit"] = None

    game["last_action"][pid] = time.time()

    mode = apply_special_rules_online(
        game,
        played,
        pid
    )

    # 上がり
    if len(hand) == 0:

        if not game["finished"][pid]:
            game["finished"][pid] = True

            game["finish_order"].append(
                pid
            )

    # 最後の1人を自動追加
    alive = [
        p
        for p in game["finished"]
        if not game["finished"][p]
    ]

    if len(alive) == 1:

        last_pid = alive[0]

        game["finished"][last_pid] = True

        game["finish_order"].append(
            last_pid
        )

        finish_daifugo_game(
            room_id
        )

        return

    # ターン処理
    if mode == "eightcut":

        game["turn"] = pid

    elif mode == "skip":

        game["turn"] = skip_turn(
            game,
            pid
        )

    else:

        game["turn"] = next_turn_online(
            game,
            pid
        )

    socketio.emit(
        "update_game",
        {
            "room_id": room_id,
            "game": game
        },
        room=room_id
    )

@socketio.on("pass")
def pass_turn(data):

    room_id = data["room_id"]
    pid = data["pid"]

    if room_id not in daifugo_rooms:
        return

    game = daifugo_rooms[room_id]["game"]

    if pid != game["turn"]:
        return

    if game["finished"][pid]:
        return

    game["pass_count"] += 1

    alive_count = sum(
        1
        for p in game["finished"]
        if not game["finished"][p]
    )

    # 最後に出した人以外の全員がパス
    if game["pass_count"] >= alive_count - 1:

        game["field"] = []

        game["bind_suit"] = None

        game["last_suit"] = None

        game["pass_count"] = 0

        # Jバック解除
        if game["jback_active"]:

            game["revolution"] = (
                not game["revolution"]
            )

            game["jback_active"] = False

        game["turn"] = game["last_player"]

        game["state_mode"] = "normal"

        game["state_message"] = (
            "場流し"
        )

    else:

        game["turn"] = next_turn_online(
            game,
            pid
        )

        game["state_message"] = (
            f"{pid} がパス"
        )

    socketio.emit(
        "update_game",
        {
            "room_id": room_id,
            "game": game
        },
        room=room_id
    )

def finish_daifugo_game(room_id):

    if room_id not in daifugo_rooms:
        return

    room = daifugo_rooms[room_id]

    game = room["game"]

    finish_order = game["finish_order"][:]

    labels = [
        "大富豪",
        "富豪",
        "貧民",
        "大貧民"
    ]

    final_ranks = {}

    for i, pid in enumerate(finish_order):

        if i < len(labels):

            final_ranks[pid] = labels[i]

    # 報酬配布
    for i, pid in enumerate(finish_order):

        reward = REWARD_TABLE.get(
            i + 1,
            0
        )

        player_index = (
            int(pid.replace("p", "")) - 1
        )

        user_id = room["players"][
            player_index
        ]

        if user_id.startswith("CPU"):
            continue

        users[user_id]["coins"] += reward

    save_json(
        USERS_FILE,
        users
    )

    socketio.emit(
        "final_result",
        {
            "finish_order":
            finish_order,

            "final_ranks":
            final_ranks,

            "rewards":
            REWARD_TABLE
        },
        room=room_id
    )

    if room_id in daifugo_rooms:

        del daifugo_rooms[room_id]
# -------------------------
# ラウンド終了（全員上がった）
# -------------------------
# -------------------------
# 次ラウンド
# -------------------------
@socketio.on("next_round")
def next_round(data):

    room_id = data["room_id"]

    if room_id not in daifugo_rooms:
        return

    game = daifugo_rooms[room_id]["game"]

    # 3ラウンド終了
    if game["round"] >= 3:

        finish_daifugo_game(room_id)

        return

    labels = [
        "大富豪",
        "富豪",
        "貧民",
        "大貧民"
    ]

    ranks = {}

    for i, pid in enumerate(game["finish_order"]):

        ranks[pid] = labels[i]

    # -------------------------
    # カード交換
    # -------------------------

    def give_cards(from_pid, to_pid, count):

        hand_from = game["hands"][from_pid]

        hand_to = game["hands"][to_pid]

        sorted_from = sorted(
            hand_from,
            key=lambda c: c["value"]
        )

        give = sorted_from[:count]

        for c in give:

            hand_from.remove(c)

            hand_to.append(c)

    daifugo_pid = None
    daihinmin_pid = None

    fugo_pid = None
    hinmin_pid = None

    for pid, rank in ranks.items():

        if rank == "大富豪":
            daifugo_pid = pid

        elif rank == "大貧民":
            daihinmin_pid = pid

        elif rank == "富豪":
            fugo_pid = pid

        elif rank == "貧民":
            hinmin_pid = pid

    if daifugo_pid and daihinmin_pid:

        give_cards(
            daihinmin_pid,
            daifugo_pid,
            2
        )

    if fugo_pid and hinmin_pid:

        give_cards(
            hinmin_pid,
            fugo_pid,
            1
        )

    # -------------------------
    # ラウンド初期化
    # -------------------------

    game["field"] = []

    game["bind_suit"] = None

    game["revolution"] = False

    game["state_mode"] = "normal"

    game["state_message"] = (
        "ラウンド開始"
    )

    game["finished"] = {
        "p1": False,
        "p2": False,
        "p3": False,
        "p4": False
    }

    game["finish_order"] = []

    game["round"] += 1

    game["turn"] = random.choice(
    ["p1", "p2", "p3", "p4"]
)

    socketio.emit(
        "update_game",
        {
            "room_id": room_id,
            "game": game
        },
        room=room_id
    )

def check_afk(room_id):

    if room_id not in daifugo_rooms:
        return

    game = daifugo_rooms[room_id]["game"]

    now = time.time()

    for pid, last in game["last_action"].items():

        if now - last > 60:

            game["turn"] = next_turn_online(
                pid
            )

            socketio.emit(
                "update_game",
                {
                    "room_id": room_id,
                    "game": game
                },
                room=room_id
            )
# -------------------------
# 最終結果
# -------------------------
def finish_daifugo_game(room_id):

    if room_id not in daifugo_rooms:
        return

    room = daifugo_rooms[room_id]

    game = room["game"]

    finish_order = game["finish_order"]

    labels = [
        "大富豪",
        "富豪",
        "貧民",
        "大貧民"
    ]

    final_ranks = {}



    # -------------------------
    # 順位決定
    # -------------------------

    for i, pid in enumerate(finish_order):

        final_ranks[pid] = labels[i]

    # -------------------------
    # コイン配布
    # -------------------------

    for i, pid in enumerate(finish_order):

        reward = REWARD_TABLE.get(
            i + 1,
            0
        )

        player_index = (
            int(pid.replace("p", "")) - 1
        )

        user_id = room["players"][
            player_index
        ]

        # CPUは除外
        if user_id.startswith("CPU"):
            continue

        users[user_id]["coins"] += reward

    save_json(
        USERS_FILE,
        users
    )

    # -------------------------
    # 結果送信
    # -------------------------

    socketio.emit(
        "final_result",
        {
            "finish_order":
            finish_order,

            "final_ranks":
            final_ranks,

            "rewards":
            REWARD_TABLE
        },
        room=room_id
    )

    # -------------------------
    # 部屋削除
    # -------------------------

    if room_id in daifugo_rooms:

        del daifugo_rooms[room_id]
# -------------------------
# ゲーム3：スピードゲーム（オンライン対戦）
# -------------------------
@app.route("/speed_online")
def speed_online():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("top"))

    if users[user_id]["coins"] < 30:
        return "コイン不足（参加費30コインが必要です）"

    users[user_id]["coins"] -= 30
    save_json(USERS_FILE, users)

    return render_template("speed_online.html", user_id=user_id)


@socketio.on("join_speed")
def on_join_speed(data):
    room = data["room"]
    user_id = data["user_id"]

    join_room(room)

    if room not in rooms:
        rooms[room] = {"p1": user_id, "p2": None, "go_time": 0}
    else:
        rooms[room]["p2"] = user_id

        delay = random.uniform(2, 5)
        rooms[room]["go_time"] = time.time() + delay

        socketio.emit("speed_ready", {"delay": delay}, room=room)


@socketio.on("speed_reaction")
def on_speed_reaction(data):
    room = data["room"]
    user_id = data["user_id"]
    reaction_time = data["reaction"]

    room_data = rooms.get(room)
    if not room_data:
        return

    if "speed_results" not in room_data:
        room_data["speed_results"] = []

    room_data["speed_results"].append((user_id, reaction_time))

    if len(room_data["speed_results"]) == 2:
        p1, r1 = room_data["speed_results"][0]
        p2, r2 = room_data["speed_results"][1]

        if r1 < r2:
            winner = p1
            loser = p2
        else:
            winner = p2
            loser = p1

        users[winner]["coins"] += 40
        users[loser]["coins"] += 20
        save_json(USERS_FILE, users)

        socketio.emit("speed_result", {
            "winner": winner,
            "loser": loser,
            "r1": r1,
            "r2": r2
        }, room=room)

@app.route("/speed_online_result")
def speed_online_result():
    return render_template("speed_online_result.html")

# -------------------------
# ゲーム4：ジオゲッサー（オンライン対戦・参加費200）
# -------------------------
@app.route("/geoguess_online")
def geoguess_online():

    user_id = session.get("user_id")

    if not user_id:
        return redirect(url_for("top"))

    return render_template(
        "geoguess_online.html",
        user_id=user_id
    )


geo_rooms = {}


@socketio.on("geoguess_join")
def geoguess_join(data):

    room = data["room"]
    user_id = data["user_id"]

    # マッチングボタンを押した時点で所持コイン確認
    if users[user_id]["coins"] < 200:

        socketio.emit(
            "match_error",
            {
                "message": "参加費200コインが必要です"
            }
        )

        return

    join_room(room)

    # ---------------------
    # 1人目
    # ---------------------
    if room not in geo_rooms:

        place = random.choice(LOCATIONS)

        geo_rooms[room] = {
            "p1": user_id,
            "p2": None,
            "place": place,
            "answers": []
        }

        return

    # ---------------------
    # 2人目
    # ---------------------
    if geo_rooms[room]["p2"] is None:

        geo_rooms[room]["p2"] = user_id

        p1 = geo_rooms[room]["p1"]
        p2 = user_id

        # 開始直前に再確認
        if users[p1]["coins"] < 200:

            socketio.emit(
                "match_error",
                {
                    "message":
                    "対戦相手のコインが不足しています"
                },
                room=room
            )

            del geo_rooms[room]
            return

        if users[p2]["coins"] < 200:

            socketio.emit(
                "match_error",
                {
                    "message":
                    "コインが不足しています"
                },
                room=room
            )

            del geo_rooms[room]
            return

        # ---------------------
        # 試合開始時に徴収
        # ---------------------
        users[p1]["coins"] -= 200
        users[p2]["coins"] -= 200

        save_json(USERS_FILE, users)

        place = geo_rooms[room]["place"]

        socketio.emit(
            "geoguess_start",
            {
                "images": place["images"],
                "lat": place["lat"],
                "lng": place["lng"]
            },
            room=room
        )


LOCATIONS = [
    {
        "name": "鉄人28号",

        "lat": 34.656028,
        "lng": 135.144361,

        "images": [
            "/static/where/001_a.jpg.png",
            "/static/where/001_b.jpg.png",
            "/static/where/001_c.jpg.png",
            "/static/where/001_d.jpg.png"
        ]
    }
]

@socketio.on("geoguess_answer")
def geoguess_answer(data):
    room = data["room"]
    user_id = data["user_id"]
    guess_lat = float(data["lat"])
    guess_lng = float(data["lng"])

    room_data = geo_rooms.get(room)
    if not room_data:
        return

    if "answers" not in room_data:
        room_data["answers"] = []

    room_data["answers"].append({
        "user_id": user_id,
        "lat": guess_lat,
        "lng": guess_lng
    })

    if len(room_data["answers"]) == 2:
        true_lat = room_data["place"]["lat"]
        true_lng = room_data["place"]["lng"]

        def distance(a_lat, a_lng, b_lat, b_lng):
            return ((a_lat - b_lat) ** 2 + (a_lng - b_lng) ** 2) ** 0.5

        a = room_data["answers"][0]
        b = room_data["answers"][1]

        dist_a = distance(a["lat"], a["lng"], true_lat, true_lng)
        dist_b = distance(b["lat"], b["lng"], true_lat, true_lng)

        if dist_a < dist_b:
            winner = a["user_id"]
            loser = b["user_id"]
        else:
            winner = b["user_id"]
            loser = a["user_id"]

        users[winner]["coins"] += 400
        save_json(USERS_FILE, users)

        socketio.emit("geoguess_result", {
            "winner": winner,
            "loser": loser,
            "true_lat": true_lat,
            "true_lng": true_lng,
            "a_user": a["user_id"],
            "a_lat": a["lat"],
            "a_lng": a["lng"],
            "b_user": b["user_id"],
            "b_lat": b["lat"],
            "b_lng": b["lng"],
        }, room=room)


if __name__ == "__main__":
    socketio.run(app, debug=True)