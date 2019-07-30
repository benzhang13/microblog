from app import db, translate
from flask import render_template, flash, redirect, url_for, request, g, jsonify, current_app
from app.main.forms import EditProfileForm, PostForm, SearchForm, MessageForm
from flask_login import current_user, login_required
from app.models import User, Post, Message, Notification
from datetime import datetime
from flask_babel import _, get_locale
from guess_language import guess_language
from app.main import bp


@bp.route("/", methods=['GET', 'POST'])
@bp.route("/index", methods=['GET', 'POST'])
@login_required
def index():
    form = PostForm()
    if form.validate_on_submit():
        language = guess_language(form.body.data)
        if language == 'UNKNOWN' or len(language) > 5:
            language = ''
        post = Post(body=form.body.data, author=current_user, language=language)
        db.session.add(post)
        db.session.commit()
        flash(_('Your post is now live!'))
        return redirect(url_for('main.index'))

    page = request.args.get('page', 1, type=int)
    posts = current_user.followed_posts().paginate(page, current_app.config['POSTS_PER_PAGE'], False)
    next_url = url_for('main.index', page=posts.next_num) if posts.has_next else None
    prev_url = url_for('main.index', page=posts.prev_num) if posts.has_prev else None
    return render_template('index.html', title='Home', posts=posts.items, next_url=next_url, prev_url=prev_url,
                           form=form)


@bp.route('/explore')
@login_required
def explore():
    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(Post.timestamp.desc()).paginate(page, current_app.config['POSTS_PER_PAGE'], False)
    next_url = url_for('main.explore', page=posts.next_num) if posts.has_next else None
    prev_url = url_for('main.explore', page=posts.prev_num) if posts.has_prev else None
    return render_template('index.html', title='Explore', next_url=next_url, prev_url=prev_url, posts=posts.items)


@bp.route('/user/<username>', methods=['GET', 'POST'])
@login_required
def user_profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    page = request.args.get('page', 1, type=int)
    posts = user.posts.order_by(Post.timestamp.desc()).paginate(page, current_app.config['POSTS_PER_PAGE'], False)
    next_url = url_for('main.user_profile', username=user.username, page=posts.next_num) if posts.has_next else None
    prev_url = url_for('main.user_profile', username=user.username, page=posts.prev_num) if posts.has_prev else None

    form = MessageForm()
    if form.validate_on_submit():
        msg = Message(recipient=user, author=current_user, body=form.message.data, type='message')
        db.session.add(msg)
        db.session.commit()
        user.add_notification('unread_message_count', user.new_messages())
        db.session.commit()
        flash(_('Your message has been sent!'))
        return redirect(url_for('main.user_profile', username=username))

    return render_template('user_profile.html', user=user, posts=posts.items, next_url=next_url, prev_url=prev_url,
                           form=form)


@bp.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm(current_user.username)
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.about_me = form.about_me.data
        db.session.commit()
        flash(_('Your changes have been saved.'))
        return redirect(url_for('main.edit_profile'))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.about_me.data = current_user.about_me
    return render_template('edit_profile.html', title='Edit Profile', form=form)


@bp.route('/follow/<username>')
def follow(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash(_('User %(username)s was not found', username=username))
        return redirect(url_for('main.index'))
    if user == current_user:
        flash(_('You cannot follow yourself'))
        return redirect(url_for('main.index'))
    current_user.follow(user)
    db.session.commit()

    msg = Message(recipient=user, author=current_user, body=current_user.username + ' followed you!',
                  type='follow_notification')
    db.session.add(msg)
    db.session.commit()
    user.add_notification('unread_message_count', user.new_messages())
    db.session.commit()

    flash(_('You are now following %(username)s!', username=username))
    return redirect(url_for('main.user_profile', username=username))


@bp.route('/unfollow/<username>')
def unfollow(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash(_('User %(username)s was not found', username=username))
        return redirect(url_for('main.index'))
    if user == current_user:
        flash(_('You cannot unfollow yourself'))
        return redirect(url_for('main.index'))
    current_user.unfollow(user)
    db.session.commit()
    flash(_('You have unfollowed %(username)s', username=username))
    return redirect(url_for('main.user_profile', username=username))


@bp.route('/translate', methods=['POST'])
@login_required
def translate_text():
    return jsonify({'text': translate.translate(request.form['text'], request.form['source_language'],
                                                request.form['dest_language'])})


@bp.route('/search')
@login_required
def search():
    if not g.search_form.validate():
        return redirect(url_for('main.explore'))
    page = request.args.get('page', 1, type=int)
    posts, total = Post.search(g.search_form.q.data, page, current_app.config['POSTS_PER_PAGE'])
    next_url = url_for('main.search', q=g.search_form.q.data, page=page+1)\
        if total > page * current_app.config['POSTS_PER_PAGE'] else None
    prev_url = url_for('main.search', q=g.search_form.q.data, page=page-1) if page > 1 else None
    return render_template('search.html', title=_('Search'), posts=posts, next_url=next_url, prev_url=prev_url)


@bp.route('/messages')
@login_required
def messages():
    current_user.last_message_read_time = datetime.utcnow()
    current_user.add_notification('unread_message_count', 0)
    db.session.commit()
    page = request.args.get('page', 1, type=int)
    messages = current_user.messages_received.order_by(Message.timestamp.desc()).paginate(
        page, current_app.config['POSTS_PER_PAGE'], False)
    next_url = url_for('main.messages', page=messages.next_num) if messages.has_next else None
    prev_url = url_for('main.messages', page=messages.prev_num) if messages.has_prev else None
    return render_template('messages.html', messages=messages.items, next_url=next_url,
                           prev_url=prev_url)


@bp.route('/user/<username>/popup')
@login_required
def user_popup(username):
    user = User.query.filter_by(username=username).first_or_404()
    return render_template('user_popup.html', user=user)


@bp.route('/notifications')
@login_required
def notifications():
    since = request.args.get('since', 0.0, type=float)
    notifications = current_user.notifications.filter(Notification.timestamp > since)\
        .order_by(Notification.timestamp.asc())
    return jsonify([{
        'name': n.name,
        'data': n.get_data(),
        'timestamp': n.timestamp
    } for n in notifications])


@bp.route('/user/<username>/followers')
@login_required
def followers(username):
    user = User.query.filter_by(username=username).first_or_404()
    page = request.args.get('page', 1, type=int)
    followers = user.followers.paginate(page, current_app.config['POSTS_PER_PAGE'], False)
    next_url = url_for('main.followers', page=followers.next_num) if followers.has_next else None
    prev_url = url_for('main.followers', page=followers.prev_num) if followers.has_prev else None
    return render_template('followers.html', user=user, followers=followers.items,
                           title=user.username + '\'s Followers', next_url=next_url, prev_url=prev_url,
                           mode='followers')


@bp.route('/user/<username>/following')
@login_required
def following(username):
    user = User.query.filter_by(username=username).first_or_404()
    page = request.args.get('page', 1, type=int)
    following = user.followed.paginate(page, current_app.config['POSTS_PER_PAGE'], False)
    next_url = url_for('main.following', page=following.next_num) if following.has_next else None
    prev_url = url_for('main.following', page=following.prev_num) if following.has_prev else None
    return render_template('followers.html', user=user, followers=following.items, title=user.username + ' Following',
                           next_url=next_url, prev_url=prev_url, mode='following')


@bp.before_app_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        db.session.commit()
        g.search_form = SearchForm()
    g.locale = str(get_locale())
