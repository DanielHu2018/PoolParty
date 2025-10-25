from werkzeug.security import generate_password_hash
from app import create_app, db
from app.models import User, Pool

app = create_app()

with app.app_context():
    # reset DB for smoke test
    try:
        db.drop_all()
    except Exception:
        pass
    db.create_all()

    user = User(username='smokeuser', email='smoke@example.com', password=generate_password_hash('password'))
    db.session.add(user)
    db.session.commit()

    pool = Pool(title='Morning Commute', origin='Home', destination='Office', seats=3, owner=user)
    db.session.add(pool)
    db.session.commit()

    print('SMOKE_TEST_OK', user.id, pool.id)
