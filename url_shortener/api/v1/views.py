from flask import current_app, Blueprint, request, redirect, jsonify
from urllib.parse import urlparse

from url_shortener.models import db, Redirect, MobileRedirect, TabletRedirect, \
    DesktopRedirect
from url_shortener.utils import elapsed_time_in_seconds_since, \
    get_device_model_from_device_string, get_device_model_from_request
from url_shortener.api.v1.error_messages import *

API_VERSION = 'v1'
api_v1 = Blueprint(
    'api',
    __name__,
    url_prefix="/{}".format(API_VERSION)
)


@api_v1.route('/', methods=['GET'], defaults={'hashed_id': None})
@api_v1.route('/<string:hashed_id>', methods=['GET'])
def redirect_to_long_url(hashed_id):
    if not hashed_id:
        return jsonify({}), 404
    device_model = get_device_model_from_request(request)
    redirect_instance = device_model.query.filter_by(
        hashed_id=hashed_id
    ).first()
    if not redirect_instance or not redirect_instance.long_url:
        error_message = NO_REDIRECT_ERROR_MSG.format(
            hashed_id
        )
        return jsonify({"error": error_message}), 404
    redirect_instance.redirect_count += 1
    db.session.commit()
    return redirect(redirect_instance.long_url)


@api_v1.route('/redirects', methods=['POST'])
def create_redirect():
    if request.json is None:
        return jsonify({"error": NO_LONG_URL_ERROR_MSG}), 400
    long_url = request.json['longUrl']
    mobile_redirect = MobileRedirect(long_url=long_url)
    db.session.add(mobile_redirect)
    db.session.commit()
    id = mobile_redirect.id
    hashed_id = current_app.hasher.encode(id)
    mobile_redirect.hashed_id = hashed_id
    db.session.add_all([
        TabletRedirect(hashed_id=hashed_id, long_url=long_url),
        DesktopRedirect(hashed_id=hashed_id, long_url=long_url)
    ])
    db.session.commit()
    short_url = get_short_url(hashed_id)
    return jsonify(shortUrl=short_url), 200


@api_v1.route('/redirects', methods=['GET'])
def get_all_redirects():
    redirects = Redirect.query.all()
    redirects_dict = {}
    for redirect in redirects:
        if redirect.hashed_id not in redirects_dict:
            redirects_dict[redirect.hashed_id] = []
        since_creation = elapsed_time_in_seconds_since(redirect.created_at)
        redirect_dict = {
            'type': redirect.type,
            'longUrl': redirect.long_url,
            'redirectCount': redirect.redirect_count,
            'sinceCreation': since_creation
        }
        redirects_dict[redirect.hashed_id].append(redirect_dict)
    return jsonify(redirects_dict), 200


@api_v1.route('/redirects/<string:hashed_id>', methods=['PATCH'])
def update_long_url_mapped_for_device_to(hashed_id):
    data = request.json
    if not data:
        return jsonify({"error": NO_CONFIG_ERROR_MSG}), 400
    normalized_data = {k.lower(): v for k, v in data.items()}
    redirect_instance = Redirect.query.filter_by(hashed_id=hashed_id).first()
    if redirect_instance is None:
        error_message = NO_REDIRECT_WONT_CONFIGURE_ERROR_MSG.format(hashed_id)
        return jsonify({"error": error_message}), 404
    for type_string in normalized_data:
        device_model = get_device_model_from_device_string(type_string)
        if device_model is None:
            # TODO: This following line should be logged properly
            print('url_shortener.api.v1.views: No model associated to type string {}'.format(type_string))
            continue
        redirect_instance = device_model.query.filter_by(
            hashed_id=hashed_id
        ).first()
        redirect_instance.long_url = normalized_data[type_string]
    db.session.commit()
    return jsonify({}), 200


def get_short_url(hashed_id):
    host = current_app.config['APP_HOST']
    port = current_app.config['APP_PORT']
    return "http://{}:{}/{}/{}".format(host, port, API_VERSION, hashed_id)
