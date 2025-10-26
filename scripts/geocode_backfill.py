#!/usr/bin/env python3
"""Backfill origin/destination coordinates for existing pools.

Usage: run from repository root with activated virtualenv or python in path.
"""
import os
from app import create_app, db
from sqlalchemy import text
from app.models import Pool
from app.geo import geocode_any


def add_column_if_missing(engine, table, column, coltype):
    # For sqlite, ALTER TABLE ADD COLUMN is supported; ignore if exists
    try:
        # Use a transaction/connection execute to avoid deprecated Engine.execute
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))
    except Exception:
        # ignore any errors (column exists or not supported)
        pass


def main():
    app = create_app()
    with app.app_context():
        # Use the current engine - avoid deprecated get_engine()
        engine = db.engine
        # Best-effort add columns for older databases
        add_column_if_missing(engine, 'pool', 'origin_lat', 'FLOAT')
        add_column_if_missing(engine, 'pool', 'origin_lng', 'FLOAT')
        add_column_if_missing(engine, 'pool', 'dest_lat', 'FLOAT')
        add_column_if_missing(engine, 'pool', 'dest_lng', 'FLOAT')

        pools = Pool.query.all()
        for p in pools:
            updated = False
            # Origin
            if (p.origin_lat is None or p.origin_lng is None) and p.origin:
                lat, lng, provider = geocode_any(p.origin)
                if lat and lng:
                    p.origin_lat = lat
                    p.origin_lng = lng
                    updated = True
                    print(f'Pool {p.id}: origin geocoded via {provider} -> {lat},{lng}')
                else:
                    print(f'Pool {p.id}: origin geocode FAILED for "{p.origin}"')

            # Destination
            if (p.dest_lat is None or p.dest_lng is None) and p.destination:
                dlat, dlng, dprovider = geocode_any(p.destination)
                if dlat and dlng:
                    p.dest_lat = dlat
                    p.dest_lng = dlng
                    updated = True
                    print(f'Pool {p.id}: destination geocoded via {dprovider} -> {dlat},{dlng}')
                else:
                    print(f'Pool {p.id}: destination geocode FAILED for "{p.destination}"')

            if updated:
                db.session.add(p)

        db.session.commit()


if __name__ == '__main__':
    main()
