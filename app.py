import random
import string
import redis
from flask import Flask, request, jsonify, redirect
from flask_sqlalchemy import SQLAlchemy
from config import Config
from models import db, URL, ClickAnalytics

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)
r = redis.Redis.from_url(app.config["REDIS_URL"])

def generate_short_url():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=7))

@app.route('/shorten', methods=['POST'])
def shorten_url():
    data = request.json
    original_url = data.get('url')
    if not original_url:
        return jsonify({'error': 'URL is required'}), 400

    short_url = generate_short_url()
    while URL.query.filter_by(short_url=short_url).first():
        short_url = generate_short_url()

    new_url = URL(original_url=original_url, short_url=short_url)
    db.session.add(new_url)
    db.session.commit()

    r.set(short_url, original_url)  # Cache the mapping

    return jsonify({'short_url': request.host_url + short_url})

@app.route('/<short_url>')
def redirect_url(short_url):
    cached_url = r.get(short_url)
    
    if cached_url:
        original_url = cached_url.decode()
    else:
        url_entry = URL.query.filter_by(short_url=short_url).first()
        if not url_entry:
            return jsonify({'error': 'URL not found'}), 404
        original_url = url_entry.original_url
        r.set(short_url, original_url)  # Cache for future use

    # Track analytics
    click = ClickAnalytics(short_url=short_url, ip_address=request.remote_addr)
    db.session.add(click)
    db.session.commit()

    # Update click count
    URL.query.filter_by(short_url=short_url).update({'click_count': URL.click_count + 1})
    db.session.commit()

    return redirect(original_url)

@app.route('/analytics/<short_url>', methods=['GET'])
def get_analytics(short_url):
    url_entry = URL.query.filter_by(short_url=short_url).first()
    if not url_entry:
        return jsonify({'error': 'Short URL not found'}), 404

    analytics_data = ClickAnalytics.query.filter_by(short_url=short_url).all()
    analytics_list = [{
        'ip_address': click.ip_address,
        'timestamp': click.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    } for click in analytics_data]

    return jsonify({
        'short_url': request.host_url + short_url,
        'original_url': url_entry.original_url,
        'click_count': url_entry.click_count,
        'click_details': analytics_list
    })
