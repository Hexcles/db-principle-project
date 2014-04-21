# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, make_response, g, Response, url_for, flash, redirect, abort
from flask.ext.basicauth import BasicAuth
from jinja2 import evalcontextfilter, Markup, escape

from datetime import datetime, timedelta
from functools import wraps
import models
import settings
import re

app = Flask(__name__)
app.config['BASIC_AUTH_USERNAME'] = settings.username
app.config['BASIC_AUTH_PASSWORD'] = settings.password
app.config['BASIC_AUTH_REALM'] = 'Welcome to the admin page'
app.secret_key = settings.secret_key

basic_auth = BasicAuth(app)

# Disconnet to the database
@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# Session decorater
def session_wrapper(func):
    @wraps(func)
    def decorated(*args, **kwargs):
        models.start_session()
        resp = func(*args, **kwargs)
        if resp is not Response:
            resp = make_response(resp)
        expiration = datetime.now() + timedelta(weeks=50)
        resp.set_cookie('user_session', g._user['session'], httponly=True, expires=expiration)
        return resp
    return decorated

# Generate a dict for breadcrumb
def _bc(name, url):
    return {'name': name, 'url': url}

# nl2br filter
_paragraph_re = re.compile(r'(?:\r\n|\r|\n){2,}')

@app.template_filter()
@evalcontextfilter
def nl2br(eval_ctx, value):
    result = u'\n\n'.join(u'<p>%s</p>' % p.replace('\n', '<br>\n') \
        for p in _paragraph_re.split(escape(value)))
    if eval_ctx.autoescape:
        result = Markup(result)
    return result

# Views / Routes
################

@app.route('/')
@session_wrapper
def home():
    ''' Homepage '''
    g.current_page = 'home'
    g.breadcrumb = None
    boards = models.list_boards()
    return render_template('home.html', boards=boards)

@app.route('/profile', methods=['POST', 'GET'])
@session_wrapper
def profile():
    ''' Get or update personal profile '''
    g.current_page = 'profile'
    g.breadcrumb = None
    if request.method == 'POST':
        models.modify_user(g._user['id'], request.form['nickname'])
        flash('更新昵称成功', 'success')
    threads = models.get_user_thread(g._user['id'])
    return render_template('profile.html', threads=threads)

@app.route('/board/<int:board_id>/new', methods=['POST', 'GET'])
@session_wrapper
def new_thread(board_id):
    ''' Edit or post new thread '''
    board = models.board_info(board_id)
    if board is None:
        abort(404)
    if request.method == 'POST':
        models.new_thread(g._user['id'], board_id, request.form['title'], request.form['content'])
        flash('发布新串成功！', 'success')
        return redirect(url_for('view_board', board_id=board_id))
    else:
        g.current_page = 'view'
        g.breadcrumb = [
                _bc('首页', url_for('home')),
                _bc(board['name'], url_for('view_board', board_id=board_id)),
                _bc('发布新串', '')
        ]
        return render_template('new_thread.html')

@app.route('/board/<int:board_id>')
@session_wrapper
def view_board(board_id):
    ''' View a board (list all threads in the board) '''
    board = models.board_info(board_id)
    if board is None:
        abort(404)
    threads = models.list_threads(board_id)
    g.current_page = 'view'
    g.breadcrumb = [
            _bc('首页', url_for('home')),
            _bc(board['name'], url_for('view_board', board_id=board_id))
    ]
    return render_template('board.html', board=board, threads=threads)

@app.route('/thread/<int:thread_id>', methods=['GET', 'POST'])
@session_wrapper
def thread(thread_id):
    ''' View a thread or post reply '''
    threads = models.show_thread(thread_id)
    board = models.get_thread_borad(thread_id)
    if threads == [] or board is None:
        abort(404)
    if request.method == 'POST':
        models.new_post(g._user['id'], thread_id, request.form['title'], request.form['content'])
        flash('回复成功', 'success')
    g.current_page = 'view'
    g.breadcrumb = [
            _bc('首页', url_for('home')),
            _bc(board['name'], url_for('view_board', board_id=board['id'])),
            _bc(threads[0]['title'], url_for('thread', thread_id=thread_id))
    ]
    return render_template('thread.html', threads=threads)

@app.route('/admin')
@basic_auth.required
@session_wrapper
def admin():
    ''' Admin page (edit boards) '''
    boards = models.list_boards()
    return render_template('admin.html', boards=boards)

@app.route('/about')
@session_wrapper
def about():
    ''' About us '''
    g.current_page = 'about'
    g.breadcrumb = None
    return render_template('about.html')

@app.route('/new-session')
@session_wrapper
def new_session():
    ''' Force generate new session '''
    models.generate_session()
    return redirect(url_for('home'))

# Main runner
if __name__ == '__main__':
    app.run(debug=settings.debug, host=settings.listen_host, port=settings.listen_port)
