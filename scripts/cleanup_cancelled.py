#!/usr/bin/env python3
"""Cleanup script to permanently remove cancelled pools and cancelled rides from the database.

Usage:
  python scripts/cleanup_cancelled.py [--yes]

By default the script prints counts and asks for confirmation. Use --yes to run non-interactively.
"""
import argparse
from app import create_app, db
from app.models import Pool, Ride, JoinRequest


def main(auto_yes=False):
    app = create_app()
    with app.app_context():
        cancelled_rides_q = Ride.query.filter(Ride.status == 'cancelled')
        num_cancelled_rides = cancelled_rides_q.count()

        cancelled_pools_q = Pool.query.filter(Pool.cancelled == True)
        num_cancelled_pools = cancelled_pools_q.count()

        print(f"Found {num_cancelled_rides} cancelled ride(s) and {num_cancelled_pools} cancelled pool(s).")
        if not auto_yes:
            resp = input('Proceed to permanently delete these records? (y/N): ').strip().lower()
            if resp not in ('y', 'yes'):
                print('Aborting. No changes made.')
                return

        # Delete cancelled rides
        if num_cancelled_rides:
            print('Deleting cancelled rides...')
            cancelled_rides_q.delete(synchronize_session=False)

        # For cancelled pools, delete related join requests and rides, then the pools
        if num_cancelled_pools:
            print('Deleting related join requests and rides for cancelled pools...')
            cancelled_pools = cancelled_pools_q.all()
            pool_ids = [p.id for p in cancelled_pools]
            if pool_ids:
                JoinRequest.query.filter(JoinRequest.pool_id.in_(pool_ids)).delete(synchronize_session=False)
                Ride.query.filter(Ride.pool_id.in_(pool_ids)).delete(synchronize_session=False)
                print(f'Deleting {len(pool_ids)} cancelled pools...')
                cancelled_pools_q.delete(synchronize_session=False)

        db.session.commit()
        print('Cleanup complete.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Cleanup cancelled pools and rides from DB')
    parser.add_argument('--yes', action='store_true', help='Do not prompt for confirmation')
    args = parser.parse_args()
    main(auto_yes=args.yes)
