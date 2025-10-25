"""
Run placeholder.

This file was previously a tiny runner that imported the application factory.
Because the application implementation has been removed to leave only the
project structure, this runner is now a placeholder describing how to start
the app after you re-add the implementation.

To restore a runnable app, re-create an application factory in `app/__init__.py`
and then replace this file's contents with something like:

    from app import create_app
    app = create_app()
    if __name__ == '__main__':
        app.run(debug=True)

"""

__all__ = []
