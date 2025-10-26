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

            # If coords are present now, try to compute and persist ETA (origin -> destination)
            try:
                if p.origin_lat and p.origin_lng and p.dest_lat and p.dest_lng and (p.eta_seconds is None):
                    from app.geo import route_any, haversine_miles, estimate_duration_seconds_from_meters
                    route = route_any([(p.origin_lng, p.origin_lat), (p.dest_lng, p.dest_lat)])
                    if route and route.get('duration_seconds'):
                        # Sanity-check route result to avoid absurd cross-continent routes
                        from app.geo import route_result_is_reasonable
                        if route_result_is_reasonable(route, p.origin_lat, p.origin_lng, p.dest_lat, p.dest_lng):
                            p.eta_seconds = int(round(route.get('duration_seconds')))
                            p.eta_updated_at = __import__('datetime').datetime.utcnow()
                            db.session.add(p)
                            print(f'Pool {p.id}: ETA set -> {p.eta_seconds}s via routing')
                        else:
                            # fallback to straight-line estimate
                            miles = haversine_miles(p.origin_lat, p.origin_lng, p.dest_lat, p.dest_lng)
                            if miles is not None:
                                meters = miles * 1609.344
                                est = estimate_duration_seconds_from_meters(meters)
                                if est:
                                    p.eta_seconds = int(est)
                                    p.eta_updated_at = __import__('datetime').datetime.utcnow()
                                    db.session.add(p)
                                    print(f'Pool {p.id}: ETA estimated -> {p.eta_seconds}s (routing result rejected)')
                    else:
                        miles = haversine_miles(p.origin_lat, p.origin_lng, p.dest_lat, p.dest_lng)
                        if miles is not None:
                            meters = miles * 1609.344
                            est = estimate_duration_seconds_from_meters(meters)
                            if est:
                                p.eta_seconds = int(est)
                                p.eta_updated_at = __import__('datetime').datetime.utcnow()
                                db.session.add(p)
                                print(f'Pool {p.id}: ETA estimated -> {p.eta_seconds}s')
            except Exception:
                pass

        db.session.commit()


if __name__ == '__main__':
    main()
