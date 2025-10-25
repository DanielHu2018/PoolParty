"""Clear all data from database tables while preserving schema."""
from app import create_app, db
from app.models import User, Pool, JoinRequest, Ride

app = create_app()

with app.app_context():
    # Delete all records from each table
    Ride.query.delete()
    JoinRequest.query.delete()
    Pool.query.delete()
    User.query.delete()
    
    db.session.commit()
    print("All data cleared from database.")
