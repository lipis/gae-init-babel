# -*- coding: utf-8 -*-

from google.appengine.api import mail
from flask_wtf import Form
import wtforms
import wtforms.validators
from flaskext.babel import Babel
from flaskext.babel import gettext as __
from flaskext.babel import lazy_gettext as _
import flask

import config
import model
import util

app = flask.Flask(__name__)
app.config.from_object(config)
app.jinja_env.line_statement_prefix = '#'
app.jinja_env.line_comment_prefix = '##'
app.jinja_env.globals.update(slugify=util.slugify)

app.config['BABEL_DEFAULT_LOCALE'] = config.LOCALE_DEFAULT
babel = Babel(app)

import auth
import admin


################################################################################
# Main page
################################################################################
@app.route('/')
def welcome():
  return flask.render_template('welcome.html', html_class='welcome')


################################################################################
# Sitemap stuff
################################################################################
@app.route('/sitemap.xml')
def sitemap():
  response = flask.make_response(flask.render_template(
      'sitemap.xml',
      host_url=flask.request.host_url[:-1],
      lastmod=config.CURRENT_VERSION_DATE.strftime('%Y-%m-%d'),
    ))
  response.headers['Content-Type'] = 'application/xml'
  return response


################################################################################
# Profile stuff
################################################################################
class ProfileUpdateForm(Form):
  name = wtforms.TextField(_('Name'),
      [wtforms.validators.required()], filters=[util.strip_filter],
    )
  email = wtforms.TextField(_('Email'),
      [wtforms.validators.optional(), wtforms.validators.email()],
      filters=[util.email_filter],
    )
  locale = wtforms.SelectField(_('Language'),
      choices=config.LOCALE_SORTED, filters=[util.strip_filter],
    )


@app.route('/_s/profile/', endpoint='profile_service')
@app.route('/profile/', methods=['GET', 'POST'])
@auth.login_required
def profile():
  user_db = auth.current_user_db()
  form = ProfileUpdateForm(obj=user_db)

  if form.validate_on_submit():
    form.populate_obj(user_db)
    user_db.put()
    return flask.redirect(flask.url_for(
        'set_locale', locale=user_db.locale, next=flask.url_for('welcome')
      ))

    return flask.redirect(flask.url_for('welcome'))

  if flask.request.path.startswith('/_s/'):
    return util.jsonify_model_db(user_db)

  return flask.render_template(
      'profile.html',
      title=_('Profile'),
      html_class='profile',
      form=form,
      user_db=user_db,
      has_json=True,
    )


################################################################################
# Feedback
################################################################################
class FeedbackForm(Form):
  subject = wtforms.TextField(_('Subject'),
      [wtforms.validators.required()], filters=[util.strip_filter],
    )
  message = wtforms.TextAreaField(_('Message'),
      [wtforms.validators.required()], filters=[util.strip_filter],
    )
  email = wtforms.TextField(_('Email (optional)'),
      [wtforms.validators.optional(), wtforms.validators.email()],
      filters=[util.strip_filter],
    )


@app.route('/feedback/', methods=['GET', 'POST'])
def feedback():
  if not config.CONFIG_DB.feedback_email:
    return flask.abort(418)

  form = FeedbackForm()
  if form.validate_on_submit():
    mail.send_mail(
        sender=config.CONFIG_DB.feedback_email,
        to=config.CONFIG_DB.feedback_email,
        subject='[%s] %s' % (
            config.CONFIG_DB.brand_name,
            form.subject.data,
          ),
        reply_to=form.email.data or config.CONFIG_DB.feedback_email,
        body='%s\n\n%s' % (form.message.data, form.email.data)
      )
    flask.flash(__('Thank you for your feedback!'), category='success')
    return flask.redirect(flask.url_for('welcome'))
  if not form.errors and auth.current_user_id() > 0:
    form.email.data = auth.current_user_db().email

  return flask.render_template(
      'feedback.html',
      title=_('Feedback'),
      html_class='feedback',
      form=form,
    )


################################################################################
# User Stuff
################################################################################
@app.route('/_s/user/', endpoint='user_list_service')
@app.route('/user/')
@auth.admin_required
def user_list():
  user_dbs, more_cursor = util.retrieve_dbs(
      model.User.query(),
      limit=util.param('limit', int),
      cursor=util.param('cursor'),
      order=util.param('order') or '-created',
      name=util.param('name'),
      admin=util.param('admin', bool),
    )

  if flask.request.path.startswith('/_s/'):
    return util.jsonify_model_dbs(user_dbs, more_cursor)

  return flask.render_template(
      'user_list.html',
      html_class='user',
      title=_('User List'),
      user_dbs=user_dbs,
      more_url=util.generate_more_url(more_cursor),
      has_json=True,
    )


################################################################################
# Error Handling
################################################################################
@app.errorhandler(400)  # Bad Request
@app.errorhandler(401)  # Unauthorized
@app.errorhandler(403)  # Forbidden
@app.errorhandler(404)  # Not Found
@app.errorhandler(405)  # Method Not Allowed
@app.errorhandler(410)  # Gone
@app.errorhandler(418)  # I'm a Teapot
@app.errorhandler(500)  # Internal Server Error
def error_handler(e):
  try:
    e.code
  except AttributeError as e:
    e.code = 500
    e.name = 'Internal Server Error'

  if flask.request.path.startswith('/_s/'):
    return util.jsonpify({
        'status': 'error',
        'error_code': e.code,
        'error_name': e.name.lower().replace(' ', '_'),
        'error_message': e.name,
      }), e.code

  return flask.render_template(
      'error.html',
      title='Error %d (%s)!!1' % (e.code, e.name),
      html_class='error-page',
      error=e,
    ), e.code
