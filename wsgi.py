"""WSGI entry point for Alwaysdata/uWSGI."""

from app import app

# Some Alwaysdata/uWSGI configurations use ``application`` as the default
# callable name. Keep both names available.
application = app

