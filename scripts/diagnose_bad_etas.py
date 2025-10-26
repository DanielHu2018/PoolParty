#!/usr/bin/env python3
"""Diagnose pools with large ETAs: print stored coords and provider geocode/router outputs.

Run from repo root with the project's venv activated or by setting PYTHONPATH to repo root.
"""
import os
from app import create_app, db
from app.models import Pool
from app.geo import geocode_any, geocode_mapbox, geocode_nominatim, geocode_ors, route_any

THRESH = int(os.environ.get('ETA_FLAG_THRESHOLD_SECONDS', 6 * 3600))


def main():
    app = create_app()
    with app.app_context():
        pools = Pool.query.filter(Pool.eta_seconds != None).all()
        bad = [p for p in pools if p.eta_seconds and p.eta_seconds > THRESH]
        if not bad:
            print('No pools with eta_seconds >', THRESH)
            return
        for p in bad:
            print('\n---')
            print(f'Pool {p.id}: {p.title}')
            print(' origin:', p.origin)
            print(' origin_lat,lng:', p.origin_lat, p.origin_lng)
            print(' dest:', p.destination)
            print(' dest_lat,lng:', p.dest_lat, p.dest_lng)
            print(' stored eta_seconds:', p.eta_seconds)
            # Try geocoding the origin/destination with each provider to compare
            try:
                mlat, mlng = geocode_mapbox(p.origin)
            except Exception as e:
                mlat = mlng = None
                print('mapbox origin error:', e)
            try:
                nlat, nlng = geocode_nominatim(p.origin)
            except Exception as e:
                nlat = nlng = None
                print('nominatim origin error:', e)
            try:
                olat, olng = geocode_ors(p.origin)
            except Exception as e:
                olat = olng = None
                print('ors origin error:', e)
            print(' geocode_mapbox(origin):', mlat, mlng)
            print(' geocode_nominatim(origin):', nlat, nlng)
            print(' geocode_ors(origin):', olat, olng)

            # destination
            try:
                mlatd, mlngd = geocode_mapbox(p.destination)
            except Exception:
                mlatd = mlngd = None
            try:
                nlatd, nlngd = geocode_nominatim(p.destination)
            except Exception:
                nlatd = nlngd = None
            try:
                olatd, olngd = geocode_ors(p.destination)
            except Exception:
                olatd = olngd = None
            print(' geocode_mapbox(dest):', mlatd, mlngd)
            print(' geocode_nominatim(dest):', nlatd, nlngd)
            print(' geocode_ors(dest):', olatd, olngd)

            # route comparisons
            try:
                stored_route = route_any([(p.origin_lng, p.origin_lat), (p.dest_lng, p.dest_lat)])
            except Exception as e:
                stored_route = None
                print('route_any(stored coords) error:', e)
            print(' route_any(stored coords):', stored_route)
            # try route using mapbox geocodes if available
            if mlat and mlng and mlatd and mlngd:
                try:
                    r2 = route_any([(mlng, mlat), (mlngd, mlatd)])
                except Exception as e:
                    r2 = None
                    print('route_any(mapbox geocodes) error:', e)
                print(' route_any(mapbox geocodes):', r2)

            # try ORS geocodes
            if olat and olng and olatd and olngd:
                try:
                    r3 = route_any([(olng, olat), (olngd, olatd)])
                except Exception as e:
                    r3 = None
                    print('route_any(ors geocodes) error:', e)
                print(' route_any(ors geocodes):', r3)

if __name__ == '__main__':
    main()
