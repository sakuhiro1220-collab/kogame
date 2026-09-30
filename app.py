import socket

from flask_socketio import SocketIO, join_room


from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate


from flask import (
    Flask, request, jsonify, render_template,
    session, redirect, url_for
)


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

from flask_socketio import SocketIO, join_room, emit

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
socketio = SocketIO(app)

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

class SpeedRoom(db.Model):
    __tablename__ = "speed_rooms"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    room_code = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="waiting"
    )

    player1_id = db.Column(
        db.String(100),
        db.ForeignKey("users.id"),
        nullable=False
    )

    player2_id = db.Column(
        db.String(100),
        db.ForeignKey("users.id"),
        nullable=True
    )

    go_time = db.Column(
        db.Float,
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        nullable=False
    )

    finished_at = db.Column(
        db.DateTime,
        nullable=True
    )

class SpeedResult(db.Model):
    __tablename__ = "speed_results"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    room_id = db.Column(
        db.Integer,
        db.ForeignKey("speed_rooms.id"),
        nullable=False
    )

    user_id = db.Column(
        db.String(100),
        db.ForeignKey("users.id"),
        nullable=False
    )

    reaction_time = db.Column(
        db.Float,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint(
            "room_id",
            "user_id",
            name="uq_speed_result_room_user"
        ),
    )   

class GeoRoom(db.Model):
    __tablename__ = "geo_rooms"

    id = db.Column(db.Integer, primary_key=True)

    room_code = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="waiting"
    )

    player1_id = db.Column(
        db.String(100),
        db.ForeignKey("users.id"),
        nullable=False
    )

    player2_id = db.Column(
        db.String(100),
        db.ForeignKey("users.id"),
        nullable=True
    )

    location_index = db.Column(
        db.Integer,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        nullable=False
    )

    finished_at = db.Column(
        db.DateTime,
        nullable=True
    )


class GeoAnswer(db.Model):
    __tablename__ = "geo_answers"

    id = db.Column(db.Integer, primary_key=True)

    room_id = db.Column(
        db.Integer,
        db.ForeignKey("geo_rooms.id"),
        nullable=False
    )

    user_id = db.Column(
        db.String(100),
        db.ForeignKey("users.id"),
        nullable=False
    )

    guess_lat = db.Column(
        db.Float,
        nullable=False
    )

    guess_lng = db.Column(
        db.Float,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint(
            "room_id",
            "user_id",
            name="uq_geo_answer_room_user"
        ),
    )

class GomokuRoom(db.Model):
    __tablename__ = "gomoku_rooms"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    room_code = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="waiting"
    )

    player1_id = db.Column(
        db.String(100),
        db.ForeignKey("users.id"),
        nullable=False
    )

    player2_id = db.Column(
        db.String(100),
        db.ForeignKey("users.id"),
        nullable=True
    )

    black_player_id = db.Column(
        db.String(100),
        db.ForeignKey("users.id"),
        nullable=True
    )

    white_player_id = db.Column(
        db.String(100),
        db.ForeignKey("users.id"),
        nullable=True
    )

    turn = db.Column(
        db.String(10),
        nullable=False,
        default="black"
    )

    board = db.Column(
        db.JSON,
        nullable=False
    )

    winner_id = db.Column(
        db.String(100),
        db.ForeignKey("users.id"),
        nullable=True
    )

    last_move_time = db.Column(
        db.Float,
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        nullable=False
    )

    finished_at = db.Column(
        db.DateTime,
        nullable=True
    )

class Mailbox(db.Model):
    __tablename__ = "mailboxes"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    receiver_id = db.Column(
        db.String(100),
        db.ForeignKey("users.id"),
        nullable=False
    )

    sender_id = db.Column(
        db.String(100),
        db.ForeignKey("users.id"),
        nullable=True
    )

    mail_type = db.Column(
        db.String(30),
        nullable=False,
        default="notification"
    )

    message = db.Column(
        db.Text,
        nullable=False
    )

    is_read = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        nullable=False
    )
# =========================
# Socket.IO
# =========================

socketio = SocketIO(
    app,
    async_mode="threading",
    logger=True,
    engineio_logger=True
)

# ============================================================
# PAIR LINK
# ============================================================

PAIR_LINK_ENTRY_COST = 100

PAIR_LINK_WIN_REWARD = 200

PAIR_LINK_PLAYER_COUNT = 6

PAIR_LINK_QUESTION_COUNT = 5

PAIR_REACTION_ROUNDS = 10

PAIR_REACTION_PENALTY_SECONDS = 2.0


# ============================================================
# PAIR LINK 待機ユーザー
# ============================================================

pair_link_waiting = {
    "male": [],
    "female": []
}


# ============================================================
# PAIR LINK ゲームルーム
# ============================================================

pair_link_rooms = {}


# ============================================================
# ユーザー → ゲームルーム
# ============================================================

pair_link_user_room = {}




rooms = {}  # スピード＆ジオゲッサー用オンライン対戦ルーム
daifugo_rooms = {}  # 大富豪用オンライン対戦ルーム

PAIR_LINK_QUESTIONS = [

    {
        "text": "休日の理想は？",
        "options": [
            {"value": "A", "text": "家でのんびり"},
            {"value": "B", "text": "外へ遊びに行く"},
            {"value": "C", "text": "趣味に没頭"},
            {"value": "D", "text": "その日の気分"}
        ]
    },

    {
        "text": "恋人との連絡頻度は？",
        "options": [
            {"value": "A", "text": "毎日たくさん"},
            {"value": "B", "text": "1日数回"},
            {"value": "C", "text": "必要なとき"},
            {"value": "D", "text": "あまり気にしない"}
        ]
    },

    {
        "text": "理想のデートは？",
        "options": [
            {"value": "A", "text": "テーマパーク"},
            {"value": "B", "text": "カフェやレストラン"},
            {"value": "C", "text": "旅行や自然"},
            {"value": "D", "text": "家で映画やゲーム"}
        ]
    },

    {
        "text": "相手に一番求めるものは？",
        "options": [
            {"value": "A", "text": "優しさ"},
            {"value": "B", "text": "面白さ"},
            {"value": "C", "text": "誠実さ"},
            {"value": "D", "text": "一緒にいて落ち着く"}
        ]
    },

    {
        "text": "旅行するなら？",
        "options": [
            {"value": "A", "text": "温泉"},
            {"value": "B", "text": "海外"},
            {"value": "C", "text": "都会"},
            {"value": "D", "text": "自然豊かな場所"}
        ]
    },

    {
        "text": "休日に起きる時間は？",
        "options": [
            {"value": "A", "text": "朝早く"},
            {"value": "B", "text": "9時くらい"},
            {"value": "C", "text": "昼前"},
            {"value": "D", "text": "昼過ぎ"}
        ]
    },

    {
        "text": "ゲームするなら？",
        "options": [
            {"value": "A", "text": "協力ゲーム"},
            {"value": "B", "text": "対戦ゲーム"},
            {"value": "C", "text": "RPG"},
            {"value": "D", "text": "あまりゲームしない"}
        ]
    },

    {
        "text": "予定はどう決める？",
        "options": [
            {"value": "A", "text": "かなり前から"},
            {"value": "B", "text": "数日前"},
            {"value": "C", "text": "前日"},
            {"value": "D", "text": "当日のノリ"}
        ]
    },

    {
        "text": "プレゼントでもらって嬉しいものは？",
        "options": [
            {"value": "A", "text": "実用的な物"},
            {"value": "B", "text": "ファッション"},
            {"value": "C", "text": "食べ物"},
            {"value": "D", "text": "一緒にできる体験"}
        ]
    },

    {
        "text": "好きな季節は？",
        "options": [
            {"value": "A", "text": "春"},
            {"value": "B", "text": "夏"},
            {"value": "C", "text": "秋"},
            {"value": "D", "text": "冬"}
        ]
    },

    {
        "text": "デートの食事なら？",
        "options": [
            {"value": "A", "text": "おしゃれなお店"},
            {"value": "B", "text": "焼肉"},
            {"value": "C", "text": "居酒屋系"},
            {"value": "D", "text": "家で一緒に料理"}
        ]
    },

    {
        "text": "友達付き合いは？",
        "options": [
            {"value": "A", "text": "少人数で深く"},
            {"value": "B", "text": "大人数でワイワイ"},
            {"value": "C", "text": "どちらも好き"},
            {"value": "D", "text": "一人時間が多い"}
        ]
    },

    {
        "text": "会話ではどのタイプ？",
        "options": [
            {"value": "A", "text": "自分から話す"},
            {"value": "B", "text": "相手の話を聞く"},
            {"value": "C", "text": "半々"},
            {"value": "D", "text": "慣れると話す"}
        ]
    },

    {
        "text": "映画を見るなら？",
        "options": [
            {"value": "A", "text": "恋愛"},
            {"value": "B", "text": "ホラー"},
            {"value": "C", "text": "アクション"},
            {"value": "D", "text": "コメディ"}
        ]
    },

    {
        "text": "突然1万円もらったら？",
        "options": [
            {"value": "A", "text": "貯金"},
            {"value": "B", "text": "欲しい物を買う"},
            {"value": "C", "text": "美味しい物を食べる"},
            {"value": "D", "text": "遊びや旅行"}
        ]
    },

    {
        "text": "意見がぶつかったときは？",
        "options": [
            {"value": "A", "text": "すぐ話し合う"},
            {"value": "B", "text": "少し時間を置く"},
            {"value": "C", "text": "相手から話すのを待つ"},
            {"value": "D", "text": "冷静に考える"}
        ]
    },

    {
        "text": "好きなデート時間は？",
        "options": [
            {"value": "A", "text": "朝"},
            {"value": "B", "text": "昼"},
            {"value": "C", "text": "夕方"},
            {"value": "D", "text": "夜"}
        ]
    },

    {
        "text": "一番大切にしたい時間は？",
        "options": [
            {"value": "A", "text": "恋人との時間"},
            {"value": "B", "text": "友達との時間"},
            {"value": "C", "text": "趣味の時間"},
            {"value": "D", "text": "全部バランス良く"}
        ]
    },

    {
        "text": "恋人との趣味は？",
        "options": [
            {"value": "A", "text": "同じ方がいい"},
            {"value": "B", "text": "違っていてもいい"},
            {"value": "C", "text": "一部同じがいい"},
            {"value": "D", "text": "気にしない"}
        ]
    },

    {
        "text": "理想の関係は？",
        "options": [
            {"value": "A", "text": "いつも一緒"},
            {"value": "B", "text": "親友みたい"},
            {"value": "C", "text": "お互い自由"},
            {"value": "D", "text": "支え合える"}
        ]
    }

]

# ============================================================
# PAIR LINK
# 参加・6人マッチング
# ============================================================

@app.route(
    "/pair_link/join",
    methods=["POST"]
)
def pair_link_join():

    user_id = session.get(
        "user_id"
    )

    if not user_id:

        return jsonify({
            "success": False,
            "message": "ログインしてください"
        }), 401


    # ========================================================
    # ユーザー取得
    # ========================================================

    user = db.session.get(
        User,
        user_id
    )

    if not user:

        return jsonify({
            "success": False,
            "message": "ユーザーが存在しません"
        }), 404


    # ========================================================
    # コイン確認
    # この時点ではまだ引かない
    # ========================================================

    if (
        user.coins or 0
    ) < PAIR_LINK_ENTRY_COST:

        return jsonify({
            "success": False,
            "message": "参加には100 COIN必要です"
        }), 403


    # ========================================================
    # すでにゲーム参加済み
    # ========================================================

    if (
        user_id
        in pair_link_user_room
    ):

        room_id = (
            pair_link_user_room[
                user_id
            ]
        )

        return jsonify({
            "success": True,
            "matched": True,
            "room_id": room_id,
            "next_url": url_for(
                "pair_link_questions"
            )
        })


    # ========================================================
    # 性別取得
    #
    # DBに male / female が入っている想定
    # ========================================================

    gender = (
        user.gender or ""
    ).strip().lower()


    # 日本語で保存している場合にも対応
    if gender in (
        "男",
        "男性"
    ):

        gender = "male"


    elif gender in (
        "女",
        "女性"
    ):

        gender = "female"


    # ========================================================
    # 今回の3 + 3マッチング対象外
    # ========================================================

    if gender not in (
        "male",
        "female"
    ):

        return jsonify({
            "success": False,
            "message":
                "現在このゲームに参加できる設定ではありません"
        }), 400


    # ========================================================
    # 二重参加防止
    # ========================================================

    if (
        user_id
        in pair_link_waiting["male"]
        or
        user_id
        in pair_link_waiting["female"]
    ):

        return jsonify({
            "success": True,
            "waiting": True,
            "male_count": len(
                pair_link_waiting[
                    "male"
                ]
            ),
            "female_count": len(
                pair_link_waiting[
                    "female"
                ]
            )
        })


    # ========================================================
    # 待機列へ追加
    # ========================================================

    pair_link_waiting[
        gender
    ].append(
        user_id
    )


    male_count = len(
        pair_link_waiting[
            "male"
        ]
    )

    female_count = len(
        pair_link_waiting[
            "female"
        ]
    )


    print(
        "PAIR LINK WAITING:",
        male_count,
        female_count
    )


    # ========================================================
    # まだ3 + 3揃っていない
    # ========================================================

    if (
        male_count < 3
        or
        female_count < 3
    ):

        return jsonify({
            "success": True,
            "waiting": True,
            "male_count":
                male_count,
            "female_count":
                female_count,
            "total_count":
                male_count
                +
                female_count
        })


    # ========================================================
    # 3 + 3成立
    # ========================================================

    players = (

        pair_link_waiting[
            "male"
        ][:3]

        +

        pair_link_waiting[
            "female"
        ][:3]

    )


    # ========================================================
    # PostgreSQLから6人を再取得
    # ========================================================

    player_users = []


    for player_id in players:

        player = db.session.get(
            User,
            player_id
        )


        if not player:

            return jsonify({
                "success": False,
                "message":
                    "参加者情報を取得できませんでした"
            }), 409


        # ----------------------------------------------------
        # 100 COIN再確認
        # ----------------------------------------------------

        if (
            player.coins or 0
        ) < PAIR_LINK_ENTRY_COST:

            # 残高不足ユーザーを待機列から除外
            for waiting_gender in (
                "male",
                "female"
            ):

                if (
                    player_id
                    in pair_link_waiting[
                        waiting_gender
                    ]
                ):

                    pair_link_waiting[
                        waiting_gender
                    ].remove(
                        player_id
                    )


            return jsonify({
                "success": False,
                "message":
                    "参加者の残高不足によりゲームを開始できませんでした"
            }), 409


        player_users.append(
            player
        )


    # ========================================================
    # ゲームルーム作成
    # ========================================================

    room_id = str(
        uuid.uuid4()
    )


    # ========================================================
    # 20問から5問を選択
    # この6人は全員同じ5問になる
    # ========================================================

    question_indexes = (
        random.sample(
            range(
                len(
                    PAIR_LINK_QUESTIONS
                )
            ),
            PAIR_LINK_QUESTION_COUNT
        )
    )


    # ========================================================
    # 参加費
    # 6人揃ったこのタイミングで初めて徴収
    # ========================================================

    try:

        for player in player_users:

            player.coins -= (
                PAIR_LINK_ENTRY_COST
            )


        db.session.commit()


    except Exception as e:

        db.session.rollback()


        print(
            "PAIR LINK参加費エラー:",
            str(e)
        )


        return jsonify({
            "success": False,
            "message":
                "参加費の処理に失敗しました"
        }), 500


    # ========================================================
    # 待機列から6人削除
    # ========================================================

    del pair_link_waiting[
        "male"
    ][:3]


    del pair_link_waiting[
        "female"
    ][:3]


    # ========================================================
    # ゲーム情報作成
    # ========================================================

    pair_link_rooms[
        room_id
    ] = {

        "id":
            room_id,

        "players":
            players,

        "questions":
            question_indexes,

        "answers":
            {},

        "pairs":
            [],

        "reaction":
            {},

        "phase":
            "questions",

        "winner_pair":
            None,

        "results":
            [],

        "reward_paid":
            False
    }


    # ========================================================
    # ユーザーとルームを紐付け
    # ========================================================

    for player_id in players:

        pair_link_user_room[
            player_id
        ] = room_id


    # ========================================================
    # 6人へゲーム開始を通知
    # ========================================================

    for player_id in players:

        socketio.emit(

            "pair_link_game_ready",

            {

                "room_id":
                    room_id,

                "next_url":
                    url_for(
                        "pair_link_questions"
                    )

            },

            room=str(
                player_id
            )

        )


    # ========================================================
    # 最後に参加したユーザーにも結果を返す
    # ========================================================

    return jsonify({

        "success":
            True,

        "waiting":
            False,

        "matched":
            True,

        "room_id":
            room_id,

        "next_url":
            url_for(
                "pair_link_questions"
            )

    })


# ============================================================
# PAIR LINK
# 質問ページ
# ============================================================

@app.route(
    "/pair_link/questions"
)
def pair_link_questions():

    user_id = session.get(
        "user_id"
    )


    if not user_id:

        return redirect(
            url_for(
                "top"
            )
        )


    # ========================================================
    # ユーザー確認
    # ========================================================

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
            url_for(
                "top"
            )
        )


    # ========================================================
    # 所属ルーム取得
    # ========================================================

    room_id = (
        pair_link_user_room.get(
            user_id
        )
    )


    if not room_id:

        return redirect(
            url_for(
                "matching_question"
            )
        )


    room = pair_link_rooms.get(
        room_id
    )


    if not room:

        return redirect(
            url_for(
                "matching_question"
            )
        )


    # ========================================================
    # 参加者チェック
    # ========================================================

    if (
        user_id
        not in room[
            "players"
        ]
    ):

        return (
            "このゲームには参加していません",
            403
        )


    # ========================================================
    # このゲームで使う5問
    # ========================================================

    questions = [

        PAIR_LINK_QUESTIONS[
            question_index
        ]

        for question_index
        in room[
            "questions"
        ]

    ]


    # ========================================================
    # HTMLへ
    # ========================================================

    return render_template(

        "answer_page.html",

        questions=
            questions,

        room_id=
            room_id

    )


# ============================================================
# PAIR LINK
# Socket.IO参加
# ============================================================

@socketio.on(
    "pair_link_join"
)
def handle_pair_link_join(
    data=None
):

    user_id = session.get(
        "user_id"
    )


    if not user_id:

        return


    # ========================================================
    # 個人ルーム
    # ========================================================

    join_room(
        str(
            user_id
        )
    )


    # ========================================================
    # ゲームルーム
    # ========================================================

    room_id = (
        pair_link_user_room.get(
            user_id
        )
    )


    if room_id:

        join_room(
            room_id
        )


        print(
            "PAIR LINK room参加:",
            user_id,
            room_id
        )
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
# ==========================================
# メールボックス
# PostgreSQL版
# ==========================================

@app.route("/mailbox")
def mailbox():

    user_id = session.get(
        "user_id"
    )

    if not user_id:

        return redirect(
            url_for("top")
        )


    # ======================================
    # ユーザー確認
    # ======================================

    current_user = db.session.get(
        User,
        user_id
    )


    if not current_user:

        session.pop(
            "user_id",
            None
        )

        return redirect(
            url_for("top")
        )


    # ======================================
    # 自分宛てのメールを取得
    # 新しい順
    # ======================================

    user_mails = (
        db.session.execute(

            db.select(
                Mailbox
            )

            .where(
                Mailbox.receiver_id
                == user_id
            )

            .order_by(
                Mailbox.created_at.desc()
            )

        )

        .scalars()
        .all()
    )


    # ======================================
    # 未読件数
    # ======================================

    unread_count = (
        db.session.execute(

            db.select(
                db.func.count(
                    Mailbox.id
                )
            )

            .where(
                Mailbox.receiver_id
                == user_id
            )

            .where(
                Mailbox.is_read
                .is_(False)
            )

        )

        .scalar()
        or 0
    )


    return render_template(
        "mailbox.html",

        mails=
            user_mails,

        unread_count=
            unread_count,

        user=
            current_user
    )

# -------------------------
# LIKE
# -------------------------
# ==========================================
# LIKE
# PostgreSQL版
# ==========================================
@app.route("/like/<partner>")
def like(partner):

    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "message": "ログインしてください"
        }), 401


    # 自分自身にはいいねできない
    if user_id == partner:
        return jsonify({
            "success": False,
            "message": "自分自身にはいいねできません"
        }), 400


    # ユーザー取得
    current_user = db.session.get(
        User,
        user_id
    )

    partner_user = db.session.get(
        User,
        partner
    )


    if not current_user:
        return jsonify({
            "success": False,
            "message": "ユーザーが見つかりません"
        }), 404


    if not partner_user:
        return jsonify({
            "success": False,
            "message": "相手ユーザーが見つかりません"
        }), 404


    try:

        # ==================================
        # 自分 → 相手 のLIKE確認
        # ==================================

        existing_like = (
            db.session.execute(
                db.select(Like)
                .where(
                    Like.sender_id == user_id,
                    Like.receiver_id == partner
                )
            )
            .scalars()
            .first()
        )


        # ==================================
        # 新規LIKE
        # ==================================

        if not existing_like:

            new_like = Like(
                sender_id=user_id,
                receiver_id=partner
            )

            db.session.add(
                new_like
            )


            # ==============================
            # 相手へLIKE通知
            # ==============================

            like_mail = Mailbox(
                receiver_id=partner,
                sender_id=user_id,
                mail_type="like",
                message=(
                    f"{current_user.name}さんから"
                    "いいねが届きました"
                ),
                is_read=False
            )

            db.session.add(
                like_mail
            )


        # ==================================
        # 相手 → 自分 のLIKE確認
        # ==================================

        reverse_like = (
            db.session.execute(
                db.select(Like)
                .where(
                    Like.sender_id == partner,
                    Like.receiver_id == user_id
                )
            )
            .scalars()
            .first()
        )


        matched = (
            reverse_like is not None
        )


        # ==================================
        # 相互いいね成立
        # ==================================

        if matched:

            # 自分側に同じマッチ通知があるか確認
            my_match_exists = (
                db.session.execute(
                    db.select(Mailbox)
                    .where(
                        Mailbox.receiver_id == user_id,
                        Mailbox.sender_id == partner,
                        Mailbox.mail_type == "match"
                    )
                )
                .scalars()
                .first()
            )


            # 相手側に同じマッチ通知があるか確認
            partner_match_exists = (
                db.session.execute(
                    db.select(Mailbox)
                    .where(
                        Mailbox.receiver_id == partner,
                        Mailbox.sender_id == user_id,
                        Mailbox.mail_type == "match"
                    )
                )
                .scalars()
                .first()
            )


            # 自分へのマッチ通知
            if not my_match_exists:

                my_match_mail = Mailbox(
                    receiver_id=user_id,
                    sender_id=partner,
                    mail_type="match",
                    message=(
                        f"{partner_user.name}さんと"
                        "マッチしました！"
                        "チャットが解禁されました"
                    ),
                    is_read=False
                )

                db.session.add(
                    my_match_mail
                )


            # 相手へのマッチ通知
            if not partner_match_exists:

                partner_match_mail = Mailbox(
                    receiver_id=partner,
                    sender_id=user_id,
                    mail_type="match",
                    message=(
                        f"{current_user.name}さんと"
                        "マッチしました！"
                        "チャットが解禁されました"
                    ),
                    is_read=False
                )

                db.session.add(
                    partner_match_mail
                )


        # ==================================
        # PostgreSQLへ保存
        # ==================================

        db.session.commit()


        # ==================================
        # 相互いいね成立ならチャットURL返却
        # ==================================

        if matched:

            chat_url = url_for(
                "chat_room",
                partner=partner
            )

            return jsonify({
                "success": True,
                "matched": True,
                "message": "マッチング成立！",
                "chat_url": chat_url
            })


        # ==================================
        # まだ相互いいねではない
        # ==================================

        return jsonify({
            "success": True,
            "matched": False,
            "message": "いいねを送りました"
        })


    except Exception as e:

        db.session.rollback()

        print(
            "LIKE DB ERROR:",
            str(e)
        )

        return jsonify({
            "success": False,
            "message": "いいね処理に失敗しました"
        }), 500


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
# チャット一覧
# -------------------------
@app.route("/chat_page")
def chat_page():

    user_id = session.get(
        "user_id"
    )

    if not user_id:

        return redirect(
            url_for("top")
        )


    # -------------------------
    # ログインユーザー確認
    # -------------------------

    current_user = db.session.get(
        User,
        user_id
    )

    if not current_user:

        session.pop(
            "user_id",
            None
        )

        return redirect(
            url_for("top")
        )


    # -------------------------
    # チャット相手一覧
    # -------------------------

    partners = {}

    for msg in chats.get(
        user_id,
        []
    ):

        partner_id = msg.get(
            "partner"
        )

        if not partner_id:
            continue

        partners[
            partner_id
        ] = msg


    # -------------------------
    # 相手ユーザーをDBから取得
    # -------------------------

    partner_users = {}

    for partner_id in partners.keys():

        partner_user = db.session.get(
            User,
            partner_id
        )

        if partner_user:

            partner_users[
                partner_id
            ] = partner_user


    # -------------------------
    # DBに存在しない相手を除外
    # -------------------------

    partners = {

        partner_id: last_message

        for partner_id, last_message
        in partners.items()

        if partner_id in partner_users
    }


    return render_template(
        "chat_page.html",
        partners=partners,
        users=partner_users
    )


# -------------------------
# SocketIO: チャットルーム入室
# -------------------------
# -------------------------
# SocketIO: チャットルーム入室
# -------------------------
@socketio.on("join_room")
def handle_join_room(data):

    user_id = session.get("user_id")

    if not user_id:
        return

    room = str(user_id)

    join_room(room)

    print(
        "SocketIO room参加:",
        room
    )


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

    # -------------------------
# 送信者へ成功通知
# -------------------------

    socketio.emit(
    "gift_sent",
    {
        "to": partner,
        "rank": rank,
        "stars": stars,
        "cost": cost,
        "coins_left": sender_user.coins
    },
    room=str(user_id)
)


# -------------------------
# 受信者へギフト通知
# -------------------------

    socketio.emit(
    "gift_received",
    {
        "from": user_id,
        "rank": rank,
        "stars": stars
    },
    room=str(partner)
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


@app.route("/board")
def board():
    user_id = session.get("user_id")

    if not user_id:
        return redirect(url_for("top"))

    return render_template(
        "board.html",
        boards=boards
    )


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

        save_json(
            BOARDS_FILE,
            boards
        )

        return redirect(
            url_for("board")
        )

    return render_template(
        "board_post.html"
    )

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

    user = db.session.get(User, user_id)

    if not user:
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
                    "coins": str(coin)
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
# ============================================================
# ゲーム1：PAIR LINK 相性診断
# ============================================================

@app.route("/matching_question")
def matching_question():

    user_id = session.get(
        "user_id"
    )

    if not user_id:
        return redirect(
            url_for("top")
        )

    current_user = db.session.get(
        User,
        user_id
    )

    if not current_user:

        session.pop(
            "user_id",
            None
        )

        return redirect(
            url_for("top")
        )

    return render_template(
        "matching_question.html",
        user=current_user
    )


# ============================================================
# 相性スコア計算
# 同じ回答1問につき20点
# ============================================================

def pair_link_compatibility_score(
    answers_a,
    answers_b
):

    score = 0

    for answer_a, answer_b in zip(
        answers_a,
        answers_b
    ):

        if answer_a == answer_b:
            score += 20

    return score


# ============================================================
# 6人から3ペアを作る
#
# 3ペアの相性スコア合計が
# 一番高くなる組み合わせを採用
# ============================================================

def create_pair_link_pairs(room):

    players = room.get(
        "players",
        []
    )

    answers = room.get(
        "answers",
        {}
    )

    if len(players) != 6:
        return []

    for player_id in players:

        if player_id not in answers:
            return []

    best_pairs = None

    best_total_score = -1


    def search_pairs(
        remaining_players,
        current_pairs,
        current_score
    ):

        nonlocal best_pairs
        nonlocal best_total_score

        # ====================================
        # 6人全員のペアが完成
        # ====================================

        if not remaining_players:

            if current_score > best_total_score:

                best_total_score = (
                    current_score
                )

                best_pairs = [

                    {
                        "players": list(
                            pair_data[
                                "players"
                            ]
                        ),

                        "score": pair_data[
                            "score"
                        ]
                    }

                    for pair_data
                    in current_pairs
                ]

            return


        # ====================================
        # 最初の1人
        # ====================================

        first_player = (
            remaining_players[0]
        )


        # ====================================
        # 残りの誰と組ませるか全部試す
        # ====================================

        for index in range(
            1,
            len(remaining_players)
        ):

            second_player = (
                remaining_players[
                    index
                ]
            )


            pair_score = (
                pair_link_compatibility_score(

                    answers[
                        first_player
                    ],

                    answers[
                        second_player
                    ]

                )
            )


            next_remaining = (
                remaining_players[
                    1:index
                ]
                +
                remaining_players[
                    index + 1:
                ]
            )


            next_pairs = (
                current_pairs
                +
                [
                    {
                        "players": (
                            first_player,
                            second_player
                        ),

                        "score":
                            pair_score
                    }
                ]
            )


            search_pairs(
                next_remaining,
                next_pairs,
                current_score + pair_score
            )


    # ========================================
    # ペア計算開始
    # ========================================

    search_pairs(
        list(players),
        [],
        0
    )


    if not best_pairs:
        return []


    # ========================================
    # pair_1 ～ pair_3 を付与
    # ========================================

    result = []


    for index, pair_data in enumerate(
        best_pairs,
        start=1
    ):

        result.append({

            "pair_id":
                f"pair_{index}",

            "players":
                pair_data[
                    "players"
                ],

            "compatibility_score":
                pair_data[
                    "score"
                ]

        })


    return result


# ============================================================
# 相性診断回答
# ============================================================

@app.route(
    "/answer_question",
    methods=["POST"]
)
def answer_question():

    # ========================================
    # ログイン確認
    # ========================================

    user_id = session.get(
        "user_id"
    )

    if not user_id:

        return redirect(
            url_for("top")
        )


    # ========================================
    # PostgreSQLユーザー確認
    # ========================================

    current_user = db.session.get(
        User,
        user_id
    )

    if not current_user:

        session.pop(
            "user_id",
            None
        )

        return redirect(
            url_for("top")
        )


    # ========================================
    # PAIR LINKルーム取得
    # ========================================

    room_id = (
        pair_link_user_room.get(
            user_id
        )
    )


    if not room_id:

        return redirect(
            url_for(
                "matching_question"
            )
        )


    room = pair_link_rooms.get(
        room_id
    )


    if not room:

        return redirect(
            url_for(
                "matching_question"
            )
        )


    # ========================================
    # 参加者チェック
    # ========================================

    players = room.get(
        "players",
        []
    )


    if user_id not in players:

        return (
            "このゲームには参加していません",
            403
        )


    # ========================================
    # 現在のゲーム状態確認
    # ========================================

    phase = room.get(
        "phase"
    )


    if phase not in (
        "questions",
        "answering"
    ):

        return (
            "現在は回答できません",
            409
        )


    # ========================================
    # Q1 ～ Q5取得
    # ========================================

    answers = []


    for question_number in range(
        1,
        PAIR_LINK_QUESTION_COUNT + 1
    ):

        answer = request.form.get(
            f"q{question_number}"
        )


        # ====================================
        # 不正な値を拒否
        # ====================================

        if answer not in (
            "A",
            "B",
            "C",
            "D"
        ):

            return (
                f"Q{question_number}の回答が正しくありません",
                400
            )


        answers.append(
            answer
        )


    # ========================================
    # 二重回答防止
    # ========================================

    if user_id in room["answers"]:

        return render_template(
            "pair_link_waiting.html"
        )


    # ========================================
    # 回答保存
    # ========================================

    room[
        "answers"
    ][
        user_id
    ] = answers


    room[
        "phase"
    ] = "answering"


    print(
        "PAIR LINK 回答:",
        user_id,
        answers
    )


    # ========================================
    # 現在の回答人数
    # ========================================

    answer_count = len(
        room["answers"]
    )


    print(
        "PAIR LINK 回答人数:",
        answer_count,
        "/",
        PAIR_LINK_PLAYER_COUNT
    )


    # ========================================
    # 6人へ回答人数通知
    # ========================================

    socketio.emit(

        "pair_link_answer_count",

        {
            "count":
                answer_count,

            "total":
                PAIR_LINK_PLAYER_COUNT
        },

        room=room_id

    )


    # ========================================
    # まだ全員回答していない
    # ========================================

    if (
        answer_count
        < PAIR_LINK_PLAYER_COUNT
    ):

        return render_template(
            "pair_link_waiting.html"
        )


    # ========================================
    # 6人全員回答完了
    # ========================================

    print(
        "PAIR LINK 全員回答完了:",
        room_id
    )


    # ========================================
    # 相性から3ペア作成
    # ========================================

    pairs = create_pair_link_pairs(
        room
    )


    if len(pairs) != 3:

        print(
            "PAIR LINK ペア作成失敗:",
            pairs
        )

        return (
            "ペア作成に失敗しました",
            500
        )


    # ========================================
    # ペア保存
    # ========================================

    room[
        "pairs"
    ] = pairs


    # ========================================
    # PAIR REACTIONデータ作成
    # ========================================

    reaction_data = {}


    for pair_data in pairs:

        pair_id = pair_data[
            "pair_id"
        ]


        reaction_data[
            pair_id
        ] = {

            "players":
                pair_data[
                    "players"
                ],

            "times":
                {},

            "total_time":
                None,

            "finished":
                False

        }


    room[
        "reaction"
    ] = reaction_data


    # ========================================
    # PAIR REACTIONフェーズへ
    # ========================================

    room[
        "phase"
    ] = "reaction"


    # ========================================
    # デバッグ表示
    # ========================================

    for pair_data in pairs:

        print(
            "PAIR LINK PAIR:",
            pair_data[
                "pair_id"
            ],
            pair_data[
                "players"
            ],
            "相性:",
            pair_data[
                "compatibility_score"
            ]
        )


    # ========================================
    # 6人全員にPAIR REACTION開始通知
    # ========================================

    socketio.emit(

        "pair_link_all_answered",

        {
            "count":
                PAIR_LINK_PLAYER_COUNT,

            "next_url":
                url_for(
                    "pair_reaction"
                )
        },

        room=room_id

    )


    # ========================================
    # 最後に回答した人も待機画面へ
    # Socket.IO通知で自動遷移
    # ========================================

    return render_template(
        "pair_link_waiting.html"
    )


# ============================================================
# 回答待機画面
# Socket.IOルーム参加
# ============================================================

@socketio.on(
    "pair_link_join_waiting"
)
def handle_pair_link_join_waiting(
    data=None
):

    user_id = session.get(
        "user_id"
    )


    if not user_id:
        return


    room_id = (
        pair_link_user_room.get(
            user_id
        )
    )


    if not room_id:
        return


    room = pair_link_rooms.get(
        room_id
    )


    if not room:
        return


    # ========================================
    # 6人共通ルームへ参加
    # ========================================

    join_room(
        room_id
    )


    # ========================================
    # 現在の回答人数
    # ========================================

    answer_count = len(
        room.get(
            "answers",
            {}
        )
    )


    # ========================================
    # 接続した本人へ人数通知
    # ========================================

    emit(

        "pair_link_answer_count",

        {
            "count":
                answer_count,

            "total":
                PAIR_LINK_PLAYER_COUNT
        }

    )


    print(
        "PAIR LINK 待機room参加:",
        user_id,
        room_id,
        answer_count
    )


    # ========================================
    # すでに6人回答済みだった場合
    #
    # 通知より後にページを開いた人も
    # PAIR REACTIONへ進める
    # ========================================

    if (
        room.get("phase")
        == "reaction"
    ):

        emit(

            "pair_link_all_answered",

            {
                "count":
                    PAIR_LINK_PLAYER_COUNT,

                "next_url":
                    url_for(
                        "pair_reaction"
                    )
            }

        )





# ==========================================
# 五目並べ
# PostgreSQL + Socket.IO版
# ==========================================

GOMOKU_ENTRY_COST = 50
GOMOKU_WIN_REWARD = 100

GOMOKU_BOARD_SIZE = 15
GOMOKU_TURN_SECONDS = 20


# ==========================================
# 空盤面
# ==========================================

def create_gomoku_board():

    return [
        [
            0
            for _ in range(GOMOKU_BOARD_SIZE)
        ]
        for _ in range(GOMOKU_BOARD_SIZE)
    ]


# ==========================================
# 五目並べホーム
# ==========================================

@app.route("/gomoku_home")
def gomoku_home():

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
        "gomoku_home.html",
        user_id=user_id,
        coins=user.coins or 0
    )


# ==========================================
# マッチング要求
# ==========================================

@socketio.on("gomoku_match_request")
def gomoku_match_request():

    user_id = session.get(
        "user_id"
    )


    if not user_id:

        socketio.emit(
            "match_error",
            {
                "message":
                    "ログインしてください"
            }
        )

        return


    user = db.session.get(
        User,
        user_id
    )


    if not user:

        socketio.emit(
            "match_error",
            {
                "message":
                    "ユーザーが存在しません"
            }
        )

        return


    # ======================================
    # すでに対局中 / 待機中か
    # ======================================

    existing_room = db.session.execute(

        db.select(
            GomokuRoom
        )

        .where(
            GomokuRoom.status.in_(
                [
                    "waiting",
                    "playing"
                ]
            )
        )

        .where(
            db.or_(
                GomokuRoom.player1_id
                    == user_id,

                GomokuRoom.player2_id
                    == user_id
            )
        )

        .order_by(
            GomokuRoom.created_at.desc()
        )

    ).scalars().first()


    if existing_room:

        room_code = (
            existing_room.room_code
        )


        join_room(
            room_code
        )


        if (
            existing_room.status
            == "waiting"
        ):

            socketio.emit(
                "gomoku_match_update",
                {
                    "count": 1,

                    "room_id":
                        room_code,

                    "message":
                        "対戦相手を待っています"
                }
            )

        else:

            socketio.emit(
                "gomoku_match_start",
                {
                    "room_id":
                        room_code,

                    "black":
                        existing_room.black_player_id,

                    "white":
                        existing_room.white_player_id
                }
            )

        return


    # ======================================
    # コイン確認
    # ======================================

    if (
        user.coins or 0
    ) < GOMOKU_ENTRY_COST:

        socketio.emit(
            "match_error",
            {
                "message":
                    f"{GOMOKU_ENTRY_COST}コイン必要です",

                "coins":
                    user.coins or 0
            }
        )

        return


    # ======================================
    # 待機中の卓を取得
    # ======================================

    waiting_room = db.session.execute(

        db.select(
            GomokuRoom
        )

        .where(
            GomokuRoom.status
                == "waiting"
        )

        .where(
            GomokuRoom.player2_id
                .is_(None)
        )

        .where(
            GomokuRoom.player1_id
                != user_id
        )

        .order_by(
            GomokuRoom.created_at.asc()
        )

    ).scalars().first()


    try:

        # ==================================
        # 待機卓なし
        # 1人目として作成
        # ==================================

        if not waiting_room:

            room_code = (
                "gomoku_"
                + uuid.uuid4().hex[:12]
            )


            room = GomokuRoom(

                room_code=
                    room_code,

                status=
                    "waiting",

                player1_id=
                    user_id,

                player2_id=
                    None,

                black_player_id=
                    None,

                white_player_id=
                    None,

                turn=
                    "black",

                board=
                    create_gomoku_board(),

                winner_id=
                    None,

                last_move_time=
                    time.time()
            )


            db.session.add(
                room
            )


            db.session.commit()


            join_room(
                room_code
            )


            print(
                "GOMOKU WAITING:",
                user_id,
                room_code
            )


            socketio.emit(
                "gomoku_match_update",
                {
                    "count":
                        1,

                    "room_id":
                        room_code,

                    "message":
                        "対戦相手を待っています"
                }
            )


            return


        # ==================================
        # 2人目
        # ==================================

        player1 = db.session.get(
            User,
            waiting_room.player1_id
        )


        if not player1:

            waiting_room.status = (
                "finished"
            )

            waiting_room.finished_at = (
                db.func.now()
            )

            db.session.commit()


            socketio.emit(
                "match_error",
                {
                    "message":
                        "待機卓を使用できません。もう一度お試しください"
                }
            )

            return


        # ==================================
        # 1人目の残高再確認
        # ==================================

        if (
            player1.coins or 0
        ) < GOMOKU_ENTRY_COST:

            waiting_room.status = (
                "finished"
            )

            waiting_room.finished_at = (
                db.func.now()
            )

            db.session.commit()


            socketio.emit(
                "match_error",
                {
                    "message":
                        "待機卓を終了しました。もう一度マッチングしてください"
                }
            )

            return


        # ==================================
        # 黒・白決定
        # ==================================

        players = [
            player1.id,
            user.id
        ]


        random.shuffle(
            players
        )


        black_player = (
            players[0]
        )


        white_player = (
            players[1]
        )


        # ==================================
        # 参加費
        # ==================================

        player1.coins = (
            (player1.coins or 0)
            - GOMOKU_ENTRY_COST
        )


        user.coins = (
            (user.coins or 0)
            - GOMOKU_ENTRY_COST
        )


        # ==================================
        # 対局開始
        # ==================================

        waiting_room.player2_id = (
            user.id
        )


        waiting_room.black_player_id = (
            black_player
        )


        waiting_room.white_player_id = (
            white_player
        )


        waiting_room.turn = (
            "black"
        )


        waiting_room.status = (
            "playing"
        )


        waiting_room.board = (
            create_gomoku_board()
        )


        waiting_room.last_move_time = (
            time.time()
        )


        db.session.commit()


        room_code = (
            waiting_room.room_code
        )


        join_room(
            room_code
        )


        print(
            "GOMOKU MATCH:",
            player1.id,
            "VS",
            user.id
        )


        socketio.emit(
            "gomoku_match_start",
            {
                "room_id":
                    room_code,

                "black":
                    black_player,

                "white":
                    white_player
            },
            room=room_code
        )


    except Exception as e:

        db.session.rollback()


        print(
            "GOMOKU MATCH ERROR:",
            str(e)
        )


        socketio.emit(
            "match_error",
            {
                "message":
                    "マッチング処理に失敗しました"
            }
        )


# ==========================================
# 五目並べプレイ画面
# ==========================================

@app.route("/gomoku_play")
def gomoku_play():

    user_id = session.get(
        "user_id"
    )


    if not user_id:

        return redirect(
            url_for("top")
        )


    room_code = request.args.get(
        "room_id"
    )


    if not room_code:

        return "部屋が指定されていません"


    room = db.session.execute(

        db.select(
            GomokuRoom
        )

        .where(
            GomokuRoom.room_code
                == room_code
        )

    ).scalars().first()


    if not room:

        return "部屋が存在しません"


    if user_id == room.black_player_id:

        my_color = (
            "black"
        )

    elif user_id == room.white_player_id:

        my_color = (
            "white"
        )

    else:

        return "参加権限がありません"


    return render_template(
        "gomoku_play.html",

        room_id=
            room.room_code,

        my_color=
            my_color,

        user_id=
            user_id
    )


# ==========================================
# 勝利判定
# ==========================================

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
            0 <= tx < GOMOKU_BOARD_SIZE
            and
            0 <= ty < GOMOKU_BOARD_SIZE
            and
            board[ty][tx] == stone
        ):

            count += 1

            tx += dx
            ty += dy


        tx = x - dx
        ty = y - dy


        while (
            0 <= tx < GOMOKU_BOARD_SIZE
            and
            0 <= ty < GOMOKU_BOARD_SIZE
            and
            board[ty][tx] == stone
        ):

            count += 1

            tx -= dx
            ty -= dy


        if count >= 5:

            return True


    return False


# ==========================================
# Socket.IO room参加
# ==========================================

# ==========================================
# 五目並べ
# 対局ルーム参加
# ==========================================

@socketio.on("join_gomoku_room")
def join_gomoku_room_handler(data):

    user_id = session.get(
        "user_id"
    )

    if not user_id:

        socketio.emit(
            "gomoku_error",
            {
                "message":
                    "ログインしてください"
            }
        )

        return


    room_code = data.get(
        "room_id"
    )


    if not room_code:

        socketio.emit(
            "gomoku_error",
            {
                "message":
                    "ルームIDがありません"
            }
        )

        return


    # ======================================
    # DBから対局ルーム取得
    # ======================================

    room = db.session.execute(

        db.select(
            GomokuRoom
        )

        .where(
            GomokuRoom.room_code
            == room_code
        )

    ).scalars().first()


    if not room:

        socketio.emit(
            "gomoku_error",
            {
                "message":
                    "対局ルームが見つかりません"
            }
        )

        return


    # ======================================
    # この対局の参加者か確認
    # ======================================

    if user_id not in (
        room.player1_id,
        room.player2_id
    ):

        socketio.emit(
            "gomoku_error",
            {
                "message":
                    "この対局には参加できません"
            }
        )

        return


    # ======================================
    # Socket.IO roomへ参加
    # ======================================

    join_room(
        room_code
    )


    # ======================================
    # 自分の色を判定
    # ======================================

    if (
        user_id
        == room.black_player_id
    ):

        my_color = (
            "black"
        )

    elif (
        user_id
        == room.white_player_id
    ):

        my_color = (
            "white"
        )

    else:

        my_color = (
            None
        )


    print(
        "GOMOKU ROOM JOIN:",
        user_id,
        room_code,
        my_color
    )


    # ======================================
    # 参加した本人へ現在状態を返す
    # ======================================

    socketio.emit(
        "gomoku_update",

        {
            "board":
                room.board,

            "turn":
                room.turn,

            "my_color":
                my_color,

            "black":
                room.black_player_id,

            "white":
                room.white_player_id,

            "winner":
                room.winner_id,

            "status":
                room.status
        },

        room=request.sid
    )


# ==========================================
# 石を置く
# ==========================================

@socketio.on("gomoku_place")
def gomoku_place(data):

    user_id = session.get(
        "user_id"
    )


    if not user_id:

        return


    room_code = data.get(
        "room_id"
    )


    if not room_code:

        return


    try:

        x = int(
            data.get("x")
        )

        y = int(
            data.get("y")
        )

    except (
        TypeError,
        ValueError
    ):

        return


    # ======================================
    # 座標確認
    # ======================================

    if not (
        0 <= x < GOMOKU_BOARD_SIZE
        and
        0 <= y < GOMOKU_BOARD_SIZE
    ):

        return


    room = db.session.execute(

        db.select(
            GomokuRoom
        )

        .where(
            GomokuRoom.room_code
                == room_code
        )

    ).scalars().first()


    if not room:

        return


    if room.status != "playing":

        return


    if room.winner_id is not None:

        return


    # ======================================
    # 参加者確認
    # ======================================

    if user_id not in (
        room.black_player_id,
        room.white_player_id
    ):

        return


    # ======================================
    # 手番確認
    # ======================================

    if (
        user_id
        == room.black_player_id
        and
        room.turn == "black"
    ):

        stone = 1


    elif (
        user_id
        == room.white_player_id
        and
        room.turn == "white"
    ):

        stone = 2


    else:

        return


    # ======================================
    # 盤面コピー
    # ======================================

    board = [
        list(row)
        for row in room.board
    ]


    # ======================================
    # すでに石がある
    # ======================================

    if board[y][x] != 0:

        return


    # ======================================
    # 石を置く
    # ======================================

    board[y][x] = stone


    room.board = (
        board
    )


    room.last_move_time = (
        time.time()
    )


    # ======================================
    # 勝利判定
    # ======================================

    if check_gomoku_winner(
        board,
        x,
        y,
        stone
    ):

        winner = db.session.get(
            User,
            user_id
        )


        if not winner:

            db.session.rollback()
            return


        room.winner_id = (
            user_id
        )


        room.status = (
            "finished"
        )


        room.finished_at = (
            db.func.now()
        )


        winner.coins = (
            (winner.coins or 0)
            + GOMOKU_WIN_REWARD
        )


        try:

            db.session.commit()


        except Exception as e:

            db.session.rollback()


            print(
                "GOMOKU WIN ERROR:",
                str(e)
            )


            return


        print(
            "GOMOKU WINNER:",
            user_id
        )


        socketio.emit(
            "gomoku_update",
            {
                "board":
                    board,

                "turn":
                    room.turn
            },
            room=room_code
        )


        socketio.emit(
            "gomoku_finish",
            {
                "winner":
                    user_id,

                "reward":
                    GOMOKU_WIN_REWARD
            },
            room=room_code
        )


        return


    # ======================================
    # 次のターン
    # ======================================

    room.turn = (
        "white"
        if room.turn == "black"
        else "black"
    )


    try:

        db.session.commit()


    except Exception as e:

        db.session.rollback()


        print(
            "GOMOKU MOVE ERROR:",
            str(e)
        )


        return


    # ======================================
    # 両プレイヤーへ盤面送信
    # ======================================

    socketio.emit(
        "gomoku_update",
        {
            "board":
                board,

            "turn":
                room.turn
        },
        room=room_code
    )


# ==========================================
# 結果画面
# ==========================================

@app.route("/gomoku_result")
def gomoku_result():

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


    result = request.args.get(
        "result"
    )


    return render_template(
        "gomoku_result.html",

        result=
            result,

        coins=
            user.coins or 0
    )


# ==========================================
# 20秒ターン制限
# ==========================================
# ==========================================
# 五目並べ
# 20秒時間切れ監視
# ==========================================

def check_gomoku_timeout():

    while True:

        socketio.sleep(1)

        try:

            with app.app_context():

                now = time.time()

                playing_rooms = (
                    db.session.execute(

                        db.select(
                            GomokuRoom
                        )

                        .where(
                            GomokuRoom.status
                            == "playing"
                        )

                    )
                    .scalars()
                    .all()
                )


                for room in playing_rooms:

                    # すでに終了している場合
                    if room.winner_id:

                        continue


                    # 時刻がまだ設定されていない場合
                    if not room.last_move_time:

                        room.last_move_time = now

                        db.session.commit()

                        continue


                    elapsed = (
                        now
                        - room.last_move_time
                    )


                    # まだ20秒経っていない
                    if (
                        elapsed
                        <= GOMOKU_TURN_SECONDS
                    ):

                        continue


                    # ==================================
                    # 時間切れになったプレイヤー
                    # ==================================

                    if room.turn == "black":

                        loser_id = (
                            room.black_player_id
                        )

                        winner_id = (
                            room.white_player_id
                        )

                    else:

                        loser_id = (
                            room.white_player_id
                        )

                        winner_id = (
                            room.black_player_id
                        )


                    # 念のため確認
                    if (
                        not winner_id
                        or
                        not loser_id
                    ):

                        continue


                    winner = db.session.get(
                        User,
                        winner_id
                    )


                    if not winner:

                        continue


                    # ==================================
                    # 勝者へ100コイン
                    # ==================================

                    winner.coins = (
                        (winner.coins or 0)
                        + GOMOKU_WIN_REWARD
                    )


                    # ==================================
                    # 対局終了
                    # ==================================

                    room.winner_id = (
                        winner_id
                    )


                    room.status = (
                        "finished"
                    )


                    room.finished_at = (
                        db.func.now()
                    )


                    db.session.commit()


                    print(
                        "GOMOKU TIMEOUT:"
                    )

                    print(
                        "LOSER:",
                        loser_id
                    )

                    print(
                        "WINNER:",
                        winner_id
                    )


                    # ==================================
                    # 2人へ時間切れ通知
                    # ==================================

                    socketio.emit(
                        "gomoku_timeout_finish",

                        {
                            "winner":
                                winner_id,

                            "loser":
                                loser_id,

                            "reward":
                                GOMOKU_WIN_REWARD
                        },

                        room=room.room_code
                    )


                    # 通常の終了イベントも送る
                    socketio.emit(
                        "gomoku_finish",

                        {
                            "winner":
                                winner_id,

                            "reward":
                                GOMOKU_WIN_REWARD,

                            "reason":
                                "timeout"
                        },

                        room=room.room_code
                    )


        except Exception as e:

            db.session.rollback()

            print(
                "GOMOKU TIMEOUT ERROR:",
                str(e)
            )

# ==========================================
# タイムアウト監視開始
# ==========================================

gomoku_timeout_thread = threading.Thread(
    target=check_gomoku_timeout,
    daemon=True
)

gomoku_timeout_thread.start()

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
# =========================
# スピードゲーム
# PostgreSQL + 複数卓対応
# =========================

SPEED_ENTRY_COST = 30
SPEED_WIN_REWARD = 40
SPEED_LOSE_REWARD = 20


@app.route("/speed_online")
def speed_online():

    user_id = session.get("user_id")

    if not user_id:
        return redirect(
            url_for("top")
        )

    user = db.session.get(
        User,
        user_id
    )

    if not user:
        session.pop("user_id", None)

        return redirect(
            url_for("top")
        )

    # ここではまだ参加費を引かない
    return render_template(
        "speed_online.html",
        user_id=user_id,
        coins=user.coins or 0
    )


# =========================
# マッチング開始
# =========================

@socketio.on("join_speed")
def on_join_speed(data):

    print("================ SPEED JOIN ================")

    user_id = session.get("user_id")

    print("SPEED user_id:", user_id)

    if not user_id:
        socketio.emit(
            "speed_error",
            {
                "message":
                    "ログインしてください"
            }
        )
        return

    user = db.session.get(
        User,
        user_id
    )

    if not user:
        socketio.emit(
            "speed_error",
            {
                "message":
                    "ユーザーが存在しません"
            }
        )
        return

    # -------------------------
    # すでに参加中か確認
    # -------------------------

    existing_room = db.session.execute(
        db.select(SpeedRoom)
        .where(
            SpeedRoom.status.in_([
                "waiting",
                "playing"
            ])
        )
        .where(
            db.or_(
                SpeedRoom.player1_id == user_id,
                SpeedRoom.player2_id == user_id
            )
        )
    ).scalars().first()

    print(
        "SPEED existing_room:",
        existing_room.room_code
        if existing_room
        else None,
        "status:",
        existing_room.status
        if existing_room
        else None
    )
    if existing_room:

        

        room_code = (
            existing_room.room_code
        )

        join_room(room_code)

        socketio.emit(
            "speed_joined",
            {
                "room": room_code,
                "status":
                    existing_room.status
            }
        )

        return


    # -------------------------
    # コイン確認
    # -------------------------

    if (
        user.coins or 0
    ) < SPEED_ENTRY_COST:

        socketio.emit(
            "speed_error",
            {
                "message":
                    "参加には30コイン必要です",
                "coins":
                    user.coins or 0
            }
        )

        return


    # -------------------------
    # 待機中の卓を探す
    # -------------------------

    waiting_room = db.session.execute(
        db.select(SpeedRoom)
        .where(
            SpeedRoom.status
            == "waiting"
        )
        .where(
            SpeedRoom.player2_id
            .is_(None)
        )
        .order_by(
            SpeedRoom.created_at.asc()
        )
    ).scalars().first()


    try:

        # =========================
        # 待機卓がない
        # → 新しい卓を作成
        # =========================

        if not waiting_room:

            user.coins -= SPEED_ENTRY_COST

            room_code = (
                "speed_"
                + uuid.uuid4().hex[:12]
            )

            new_room = SpeedRoom(
                room_code=room_code,
                status="waiting",
                player1_id=user_id,
                player2_id=None
            )

            db.session.add(
                new_room
            )

            db.session.commit()

            join_room(
                room_code
            )

            socketio.emit(
                "speed_waiting",
                {
                    "room":
                        room_code,

                    "message":
                        "対戦相手を待っています",

                    "coins":
                        user.coins
                }
            )

            return


        # =========================
        # 待機卓がある
        # → 2人目として参加
        # =========================

        user.coins -= SPEED_ENTRY_COST

        waiting_room.player2_id = (
            user_id
        )

        waiting_room.status = (
            "playing"
        )

        delay = random.uniform(
            2,
            5
        )

        waiting_room.go_time = (
            time.time()
            + delay
        )

        db.session.commit()

        room_code = (
            waiting_room.room_code
        )

        join_room(
            room_code
        )

        # 2人とも同じ卓へ通知
        socketio.emit(
            "speed_ready",
            {
                "room":
                    room_code,

                "delay":
                    delay,

                "player1":
                    waiting_room.player1_id,

                "player2":
                    waiting_room.player2_id
            },
            room=room_code
        )


    except Exception as e:

        db.session.rollback()

        print(
            "Speedマッチングエラー:",
            str(e)
        )

        socketio.emit(
            "speed_error",
            {
                "message":
                    "マッチング処理に失敗しました"
            }
        )
  

@socketio.on("speed_reaction")
def on_speed_reaction(data):

    user_id = session.get(
        "user_id"
    )

    if not user_id:
        return

    room_code = data.get(
        "room"
    )

    try:
        reaction_time = float(
            data.get("reaction")
        )
    except (TypeError, ValueError):

        socketio.emit(
            "speed_error",
            {
                "message":
                    "リアクションタイムが不正です"
            }
        )

        return


    # -------------------------
    # 卓取得
    # -------------------------

    speed_room = db.session.execute(
        db.select(SpeedRoom)
        .where(
            SpeedRoom.room_code
            == room_code
        )
    ).scalars().first()


    if not speed_room:

        socketio.emit(
            "speed_error",
            {
                "message":
                    "対戦卓が見つかりません"
            }
        )

        return


    if speed_room.status != "playing":
        return


    # -------------------------
    # この卓の参加者か
    # -------------------------

    if user_id not in (
        speed_room.player1_id,
        speed_room.player2_id
    ):

        return


    # -------------------------
    # 二重送信確認
    # -------------------------

    old_result = db.session.execute(
        db.select(SpeedResult)
        .where(
            SpeedResult.room_id
            == speed_room.id
        )
        .where(
            SpeedResult.user_id
            == user_id
        )
    ).scalars().first()


    if old_result:
        return


    try:

        result = SpeedResult(
            room_id=speed_room.id,
            user_id=user_id,
            reaction_time=reaction_time
        )

        db.session.add(
            result
        )

        db.session.commit()


        # -------------------------
        # 両者の結果取得
        # -------------------------

        results = db.session.execute(
            db.select(SpeedResult)
            .where(
                SpeedResult.room_id
                == speed_room.id
            )
            .order_by(
                SpeedResult.reaction_time.asc()
            )
        ).scalars().all()


        # まだ1人
        if len(results) < 2:

            socketio.emit(
                "speed_opponent_wait",
                {
                    "message":
                        "相手の入力を待っています"
                }
            )

            return


        # -------------------------
        # 勝敗決定
        # -------------------------

        winner_result = results[0]
        loser_result = results[1]

        winner = db.session.get(
            User,
            winner_result.user_id
        )

        loser = db.session.get(
            User,
            loser_result.user_id
        )


        if not winner or not loser:
            raise ValueError(
                "対戦ユーザーが見つかりません"
            )


        # -------------------------
        # 賞金付与
        # -------------------------

        winner.coins = (
            (winner.coins or 0)
            + SPEED_WIN_REWARD
        )

        loser.coins = (
            (loser.coins or 0)
            + SPEED_LOSE_REWARD
        )

        speed_room.status = (
            "finished"
        )

        speed_room.finished_at = (
            db.func.now()
        )

        db.session.commit()


        # -------------------------
        # 両者へ結果送信
        # -------------------------

        socketio.emit(
            "speed_result",
            {
                "winner":
                    winner.id,

                "loser":
                    loser.id,

                "winner_reaction":
                    winner_result.reaction_time,

                "loser_reaction":
                    loser_result.reaction_time,

                "winner_reward":
                    SPEED_WIN_REWARD,

                "loser_reward":
                    SPEED_LOSE_REWARD
            },
            room=room_code
        )


    except Exception as e:

        db.session.rollback()

        print(
            "Speedゲーム結果エラー:",
            str(e)
        )

        socketio.emit(
            "speed_error",
            {
                "message":
                    "対戦結果の処理に失敗しました"
            }
        )
        
# -------------------------
# ゲーム4：ジオゲッサー（オンライン対戦・参加費200）
# -------------------------
GEO_ENTRY_COST = 200
GEO_WIN_REWARD = 400


@app.route("/geoguess_online")
def geoguess_online():

    user_id = session.get("user_id")

    if not user_id:
        return redirect(
            url_for("top")
        )

    user = db.session.get(
        User,
        user_id
    )

    if not user:
        session.pop("user_id", None)

        return redirect(
            url_for("top")
        )

    return render_template(
        "geoguess_online.html",
        user_id=user_id,
        coins=user.coins or 0
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

@socketio.on("geoguess_join")
def geoguess_join(data):

    user_id = session.get("user_id")

    if not user_id:
        socketio.emit(
            "match_error",
            {
                "message":
                    "ログインしてください"
            }
        )
        return

    user = db.session.get(
        User,
        user_id
    )

    if not user:
        socketio.emit(
            "match_error",
            {
                "message":
                    "ユーザーが存在しません"
            }
        )
        return


    # =========================
    # すでに参加中の卓
    # =========================

    existing_room = db.session.execute(
        db.select(GeoRoom)
        .where(
            GeoRoom.status.in_([
                "waiting",
                "playing"
            ])
        )
        .where(
            db.or_(
                GeoRoom.player1_id
                == user_id,

                GeoRoom.player2_id
                == user_id
            )
        )
    ).scalars().first()


    if existing_room:

        join_room(
            existing_room.room_code
        )

        socketio.emit(
            "geoguess_joined",
            {
                "room":
                    existing_room.room_code,

                "status":
                    existing_room.status
            }
        )

        return


    # =========================
    # コイン確認
    # =========================

    if (
        user.coins or 0
    ) < GEO_ENTRY_COST:

        socketio.emit(
            "match_error",
            {
                "message":
                    "参加費200コインが必要です",

                "coins":
                    user.coins or 0
            }
        )

        return


    try:

        # =========================
        # 待機卓を探す
        # =========================

        waiting_room = db.session.execute(
            db.select(GeoRoom)
            .where(
                GeoRoom.status
                == "waiting"
            )
            .where(
                GeoRoom.player2_id
                .is_(None)
            )
            .order_by(
                GeoRoom.created_at.asc()
            )
            .with_for_update(
                skip_locked=True
            )
        ).scalars().first()


        # =========================
        # 待機卓なし
        # =========================

        if not waiting_room:

            location_index = (
                random.randrange(
                    len(LOCATIONS)
                )
            )

            room_code = (
                "geo_"
                + uuid.uuid4().hex[:12]
            )

            new_room = GeoRoom(
                room_code=room_code,
                status="waiting",
                player1_id=user_id,
                player2_id=None,
                location_index=
                    location_index
            )

            db.session.add(
                new_room
            )

            db.session.commit()

            join_room(
                room_code
            )

            socketio.emit(
                "geoguess_waiting",
                {
                    "room":
                        room_code,

                    "message":
                        "対戦相手を待っています",

                    "coins":
                        user.coins or 0
                }
            )

            return


        # =========================
        # 2人目として参加
        # =========================

        player1 = db.session.execute(
            db.select(User)
            .where(
                User.id
                == waiting_room.player1_id
            )
            .with_for_update()
        ).scalar_one_or_none()

        player2 = db.session.execute(
            db.select(User)
            .where(
                User.id == user_id
            )
            .with_for_update()
        ).scalar_one_or_none()


        if not player1 or not player2:
            raise ValueError(
                "対戦ユーザーが見つかりません"
            )


        # =========================
        # 両者のコイン確認
        # =========================

        if (
            player1.coins or 0
        ) < GEO_ENTRY_COST:

            waiting_room.status = (
                "cancelled"
            )

            db.session.commit()

            socketio.emit(
                "match_error",
                {
                    "message":
                        "対戦相手のコインが不足しています"
                },
                room=waiting_room.room_code
            )

            return


        if (
            player2.coins or 0
        ) < GEO_ENTRY_COST:

            socketio.emit(
                "match_error",
                {
                    "message":
                        "参加費200コインが必要です"
                }
            )

            db.session.rollback()

            return


        # =========================
        # 参加費
        # =========================

        player1.coins -= (
            GEO_ENTRY_COST
        )

        player2.coins -= (
            GEO_ENTRY_COST
        )


        # =========================
        # 試合開始
        # =========================

        waiting_room.player2_id = (
            user_id
        )

        waiting_room.status = (
            "playing"
        )

        db.session.commit()


        room_code = (
            waiting_room.room_code
        )

        join_room(
            room_code
        )

        place = LOCATIONS[
            waiting_room.location_index
        ]


        socketio.emit(
            "geoguess_start",
            {
                "room":
                    room_code,

                "images":
                    place["images"],

                "player1":
                    waiting_room.player1_id,

                "player2":
                    waiting_room.player2_id
            },
            room=room_code
        )


    except Exception as e:

        db.session.rollback()

        print(
            "GeoGuessマッチングエラー:",
            str(e)
        )

        socketio.emit(
            "match_error",
            {
                "message":
                    "マッチングに失敗しました"
            }
        )



@socketio.on("geoguess_answer")
def geoguess_answer(data):

    user_id = session.get(
        "user_id"
    )

    if not user_id:
        return

    room_code = data.get(
        "room"
    )

    try:

        guess_lat = float(
            data.get("lat")
        )

        guess_lng = float(
            data.get("lng")
        )

    except (TypeError, ValueError):

        socketio.emit(
            "match_error",
            {
                "message":
                    "回答地点が正しくありません"
            }
        )

        return


    # =========================
    # 卓取得
    # =========================

    geo_room = db.session.execute(
        db.select(GeoRoom)
        .where(
            GeoRoom.room_code
            == room_code
        )
    ).scalars().first()


    if not geo_room:

        socketio.emit(
            "match_error",
            {
                "message":
                    "対戦卓が見つかりません"
            }
        )

        return


    if geo_room.status != "playing":
        return


    # =========================
    # この卓の参加者か確認
    # =========================

    if user_id not in (
        geo_room.player1_id,
        geo_room.player2_id
    ):
        return


    # =========================
    # 二重回答防止
    # =========================

    existing_answer = (
        db.session.execute(
            db.select(GeoAnswer)
            .where(
                GeoAnswer.room_id
                == geo_room.id
            )
            .where(
                GeoAnswer.user_id
                == user_id
            )
        )
        .scalars()
        .first()
    )


    if existing_answer:

        socketio.emit(
            "match_error",
            {
                "message":
                    "すでに回答しています"
            }
        )

        return


    try:

        answer = GeoAnswer(
            room_id=geo_room.id,
            user_id=user_id,
            guess_lat=guess_lat,
            guess_lng=guess_lng
        )

        db.session.add(
            answer
        )

        db.session.commit()


        # =========================
        # 2人の回答確認
        # =========================

        answers = db.session.execute(
            db.select(GeoAnswer)
            .where(
                GeoAnswer.room_id
                == geo_room.id
            )
            .order_by(
                GeoAnswer.created_at.asc()
            )
        ).scalars().all()


        if len(answers) < 2:

            socketio.emit(
                "geoguess_wait_answer",
                {
                    "message":
                        "相手の回答を待っています"
                }
            )

            return


        # =========================
        # 正解地点
        # =========================

        place = LOCATIONS[
            geo_room.location_index
        ]

        true_lat = float(
            place["lat"]
        )

        true_lng = float(
            place["lng"]
        )


        # =========================
        # 距離計算
        # Haversine
        # =========================

        def distance_km(
            lat1,
            lon1,
            lat2,
            lon2
        ):

            from math import (
                radians,
                sin,
                cos,
                sqrt,
                atan2
            )

            earth_radius = 6371.0

            dlat = radians(
                lat2 - lat1
            )

            dlon = radians(
                lon2 - lon1
            )

            a = (
                sin(dlat / 2) ** 2
                +
                cos(radians(lat1))
                * cos(radians(lat2))
                * sin(dlon / 2) ** 2
            )

            c = 2 * atan2(
                sqrt(a),
                sqrt(1 - a)
            )

            return (
                earth_radius * c
            )


        answer_a = answers[0]
        answer_b = answers[1]


        dist_a = distance_km(
            answer_a.guess_lat,
            answer_a.guess_lng,
            true_lat,
            true_lng
        )

        dist_b = distance_km(
            answer_b.guess_lat,
            answer_b.guess_lng,
            true_lat,
            true_lng
        )


        # =========================
        # 勝者
        # =========================

        if dist_a <= dist_b:

            winner_id = (
                answer_a.user_id
            )

            loser_id = (
                answer_b.user_id
            )

        else:

            winner_id = (
                answer_b.user_id
            )

            loser_id = (
                answer_a.user_id
            )


        winner = db.session.execute(
            db.select(User)
            .where(
                User.id == winner_id
            )
            .with_for_update()
        ).scalar_one_or_none()


        if not winner:
            raise ValueError(
                "勝者ユーザーが存在しません"
            )


        # =========================
        # 400コイン
        # =========================

        winner.coins = (
            (winner.coins or 0)
            + GEO_WIN_REWARD
        )

        geo_room.status = (
            "finished"
        )

        geo_room.finished_at = (
            db.func.now()
        )

        db.session.commit()


        # =========================
        # 結果送信
        # =========================

        socketio.emit(
            "geoguess_result",
            {
                "winner":
                    winner_id,

                "loser":
                    loser_id,

                "true_lat":
                    true_lat,

                "true_lng":
                    true_lng,

                "location_name":
                    place["name"],

                "a_user":
                    answer_a.user_id,

                "a_lat":
                    answer_a.guess_lat,

                "a_lng":
                    answer_a.guess_lng,

                "a_distance":
                    round(dist_a, 2),

                "b_user":
                    answer_b.user_id,

                "b_lat":
                    answer_b.guess_lat,

                "b_lng":
                    answer_b.guess_lng,

                "b_distance":
                    round(dist_b, 2),

                "reward":
                    GEO_WIN_REWARD
            },
            room=room_code
        )


    except Exception as e:

        db.session.rollback()

        print(
            "GeoGuess回答処理エラー:",
            str(e)
        )

        socketio.emit(
            "match_error",
            {
                "message":
                    "回答処理に失敗しました"
            }
        )


if __name__ == "__main__":
    socketio.run(app, debug=True)