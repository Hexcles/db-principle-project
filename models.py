from flask import g, request
from datetime import datetime
import binascii
import sqlite3
import settings
import base64
import os

def _get_current_time():
    ''' A small helper function to get current time in Y-m-d H:M:S '''
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def _get_db():
    ''' Get database connection '''
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(settings.database)
        db.row_factory = sqlite3.Row
    return db

def setup():
    ''' Set up database schema (force overwrite old database!) '''
    os.unlink(settings.database)
    conn = _get_db()
    conn.execute('''
        CREATE TABLE "board"
            ("id" INTEGER PRIMARY KEY  AUTOINCREMENT  NOT NULL  UNIQUE  DEFAULT 1,
             "name" VARCHAR NOT NULL  UNIQUE  DEFAULT "",
             "introduction" VARCHAR NOT NULL  DEFAULT "")
    ''')
    conn.execute('''
        CREATE TABLE "post"
            ("id" INTEGER PRIMARY KEY  AUTOINCREMENT  NOT NULL  UNIQUE  DEFAULT 1,
             "thread_id" INTEGER,
             "user_id" INTEGER,
             "title" VARCHAR NOT NULL  DEFAULT "",
             "content" TEXT NOT NULL  DEFAULT "",
             "timestamp" DATETIME NOT NULL  DEFAULT CURRENT_TIMESTAMP)
    ''')
    conn.execute('''
        CREATE TABLE "thread"
            ("id" INTEGER PRIMARY KEY  AUTOINCREMENT  NOT NULL  UNIQUE  DEFAULT 1,
             "board_id" INTEGER,
             "head_post" INTEGER)
    ''')
    conn.execute('''
        CREATE TABLE "user"
            ("id" INTEGER PRIMARY KEY  AUTOINCREMENT  NOT NULL  UNIQUE  DEFAULT 1,
             "show_id" VARCHAR NOT NULL  UNIQUE  DEFAULT "",
             "nickname" VARCHAR NOT NULL  DEFAULT "",
             "session" VARCHAR NOT NULL  UNIQUE  DEFAULT "",
             "last_ip" INTEGER NOT NULL  DEFAULT 0,
             "last_time" DATETIME NOT NULL  DEFAULT "1970-01-01 00:00:00")
    ''')
    conn.commit()

def generate_session():
    ''' Generate new session '''
    conn = _get_db()
    go = True
    last_ip = request.remote_addr
    cur = conn.cursor()
    while go:
        session = base64.b64encode(os.urandom(66)).decode('ascii')
        show_id = binascii.hexlify(os.urandom(4)).decode('ascii')
        go = False
        try:
            with conn:
                cur.execute('''
                    INSERT INTO user(session, show_id, last_ip, last_time) VALUES(?, ?, ?, ?)
                ''', (session, show_id, last_ip, _get_current_time()))
        except sqlite3.IntegrityError:
            go = True
    conn.commit()
    g._user = {
            'id': cur.lastrowid,
            'session': session,
            'show_id': show_id,
            'nickname': ''
    }

def check_session(session):
    ''' Check session '''
    conn = _get_db()
    res = conn.execute('''
        SELECT id, session, show_id, nickname FROM user
        WHERE session = ?
    ''', (session,))
    row = res.fetchone()
    if row is None:
        return False
    g._user = {
            'id': row['id'],
            'session': row['session'],
            'show_id': row['show_id'],
            'nickname': row['nickname']
    }
    conn.execute('''
        UPDATE user
        SET last_time = ?,
            last_ip = ?
        WHERE session = ?
    ''', (_get_current_time(), request.remote_addr, session))
    conn.commit()
    return True

def start_session():
    ''' Start a session (check existing or generate new) '''
    session = request.cookies.get('user_session')
    if session is None or not check_session(session):
        generate_session()

def show_thread(thread_id):
    ''' View a thread (list all posts in the thread) '''
    conn = _get_db()
    res = conn.execute('''
        SELECT post.id AS post_id, user.id AS user_id, user.show_id AS user_show_id, user.nickname, post.title, post.content, post.timestamp
            FROM post
            LEFT JOIN user ON post.user_id = user.id
            WHERE thread_id = ?
            ORDER BY post.timestamp ASC
    ''', (thread_id, )).fetchall()
    return res

def get_thread_borad(thread_id):
    ''' Get the board which the thread belongs to '''
    conn = _get_db()
    res = conn.execute('''
        SELECT board.id, board.name
            FROM thread
            LEFT JOIN board ON thread.board_id = board.id
            WHERE thread.id = ?
    ''', (thread_id, )).fetchone()
    return res

def get_user_thread(user_id):
    ''' Get all threads posted by a user '''
    conn = _get_db()
    res = conn.execute('''
        SELECT board.id AS board_id, board.name AS board_name,
               thread.id AS thread_id, post.id AS post_id,
               post.title, post.timestamp
            FROM post
            LEFT JOIN thread ON post.thread_id = thread.id
            LEFT JOIN board ON thread.board_id = board.id
            WHERE post.user_id = ?
    ''', (user_id, ))
    return res.fetchall()

def list_threads(board_id):
    ''' List threads in a board '''
    conn = _get_db()
    res = conn.execute('''
        SELECT thread.id AS thread_id, post.id AS post_id, user.id AS user_id, user.show_id AS user_show_id, user.nickname, post.title, post.timestamp
            FROM thread
            LEFT JOIN post ON thread.head_post = post.id
            LEFT JOIN user ON post.user_id = user.id
            WHERE board_id = ?
            ORDER BY post.timestamp DESC
    ''', (board_id, )).fetchall()
    return res

def list_boards():
    ''' List all boards '''
    conn = _get_db()
    res = conn.execute('''
        SELECT id, name, introduction
            FROM board
    ''').fetchall()
    return res

def board_info(board_id):
    ''' Get board details '''
    conn = _get_db()
    res = conn.execute('''
        SELECT id, name, introduction
            FROM board
            WHERE id=?
    ''',(board_id, ))
    return res.fetchone()

def new_post(user_id, thread_id, post_title=None, post_content=''):
    ''' Create a new post '''
    if thread_id is None and post_title is None:
        return False
    conn = _get_db()
    if post_title is None:
        res = conn.execute('''
            SELECT title FROM thread
                LEFT JOIN post ON thread.head_post = post.id
                WHERE thread.id = ?
        ''', (thread_id, ))
        post_title = "Re: " + res.fetchone()[0]
    conn.execute('''
        INSERT INTO post
            (user_id, thread_id, title, content, timestamp)
            VALUES (?, ?, ?, ?, ?)
    ''', (user_id, thread_id, post_title, post_content, _get_current_time()))
    conn.commit()

def new_thread(user_id, board_id, post_title, post_content=''):
    ''' Create a new thread '''
    conn = _get_db()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO thread
            (head_post, board_id)
            VALUES (?, ?)
    ''', (-1, board_id))
    conn.commit()
    thread_id = cur.lastrowid
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO post
            (thread_id, user_id, title, content, timestamp)
            VALUES (?, ?, ?, ?, ?)
    ''', (thread_id, user_id, post_title, post_content, _get_current_time()))
    conn.commit()
    conn.execute('''
        UPDATE thread
            SET head_post = ?
            WHERE id = ?
    ''', (cur.lastrowid, thread_id))
    conn.commit()

def new_board(name, introduction=''):
    ''' Create a new board '''
    conn = _get_db()
    conn.execute('''
        INSERT INTO board
            (name, introduction)
            VALUES (?, ?)
    ''', (name, introduction))
    conn.commit()

def modify_board(board_id, name=None, introduction=None):
    ''' Modify a board '''
    conn = _get_db()
    if name is not None:
        conn.execute('''
            UPDATE board
                SET name = ?
                WHERE id = ?
        ''', (name, board_id))
    if introduction is not None:
        conn.execute('''
            UPDATE board
                SET introduction = ?
                WHERE id = ?
        ''', (introduction, board_id))
    conn.commit()

def modify_user(user_id, nickname):
    ''' Modify a user (nickname) '''
    conn = _get_db()
    conn.execute('''
        UPDATE user
            SET nickname = ?
            WHERE id = ?
    ''', (nickname, user_id))
    conn.commit()
    g._user['nickname'] = nickname
