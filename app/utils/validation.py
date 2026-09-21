from flask import request

from .errors import ApiError


def payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Request body must be a JSON object.")
    return data


def get_str(data, key, required=False, max_length=None, default=None):
    value = data.get(key, default)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ApiError("%s is required." % _label(key), field=key)
        return default
    value = str(value).strip()
    if max_length and len(value) > max_length:
        raise ApiError(
            "%s must be %d characters or fewer." % (_label(key), max_length), field=key
        )
    return value


def get_int(data, key, required=False, default=None, minimum=None, maximum=None):
    value = data.get(key, default)
    if value is None or value == "":
        if required:
            raise ApiError("%s is required." % _label(key), field=key)
        return default
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ApiError("%s must be a whole number." % _label(key), field=key)
    if minimum is not None and value < minimum:
        raise ApiError("%s cannot be less than %d." % (_label(key), minimum), field=key)
    if maximum is not None and value > maximum:
        raise ApiError(
            "%s cannot be greater than %d." % (_label(key), maximum), field=key
        )
    return value


def arg_int(key, default=None):
    """Whole-number query string filter; a bad value is a 400, not a crash."""
    return get_int(request.args, key, default=default)


def get_bool(data, key, default=None):
    value = data.get(key, default)
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def get_choice(data, key, choices, required=False, default=None):
    value = get_str(data, key, required=required, default=default)
    if value is None:
        return None
    if value not in choices:
        raise ApiError(
            "%s must be one of: %s." % (_label(key), ", ".join(choices)), field=key
        )
    return value


def _label(key):
    return key.replace("_", " ").capitalize()
