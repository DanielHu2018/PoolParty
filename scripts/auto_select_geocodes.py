#!/usr/bin/env python3
"""For pools with suspicious ETAs, try geocoding origin/destination with multiple providers
and pick the pair that gives the smallest reasonable route. Update pool coords+ETA.

Run from repo root: set PYTHONPATH and optionally MAPBOX_TOKEN/ORS_API_KEY.
"""
import os
from itertools import product
from app import create_app, db
from app.models import Pool
from app.geo import geocode_mapbox, geocode_nominatim, geocode_ors, route_any, route_result_is_reasonable, haversine_miles, estimate_duration_seconds_from_meters

THRESH = int(os.environ.get('ETA_FLAG_THRESHOLD_SECONDS', 6 * 3600))
PROVIDERS = [('ors', geocode_ors), ('mapbox', geocode_mapbox), ('nominatim', geocode_nominatim)]


def gather_candidates(geocode_fn, address):
    try:
        lat, lng = geocode_fn(address)
        if lat is not None and lng is not None:
            return [(lat, lng, geocode_fn.__name__)]
    except Exception:
        pass
    return []


def main():
    app = create_app()
    with app.app_context():
        pools = Pool.query.filter(Pool.eta_seconds != None).all()
        candidates = [p for p in pools if p.eta_seconds and p.eta_seconds > THRESH]
        if not candidates:
            print('No candidate pools')
            return
        print('Checking', len(candidates), 'pools')
        for p in candidates:
            print('\n---')
            print(f'Pool {p.id}: {p.title} (stored eta {p.eta_seconds}s)')
            orig_candidates = []
            dest_candidates = []
            for name, fn in PROVIDERS:
                try:
                    latlng = fn(p.origin)
                except Exception:
                    latlng = (None, None)
                if latlng and latlng[0] is not None:
                    orig_candidates.append((latlng[0], latlng[1], name))
                try:
                    latlng = fn(p.destination)
                except Exception:
                    latlng = (None, None)
                if latlng and latlng[0] is not None:
                    dest_candidates.append((latlng[0], latlng[1], name))
            # also include stored coords as candidate
            if p.origin_lat and p.origin_lng:
                orig_candidates.append((p.origin_lat, p.origin_lng, 'stored'))
            if p.dest_lat and p.dest_lng:
                dest_candidates.append((p.dest_lat, p.dest_lng, 'stored'))

            print(' origin candidates:', orig_candidates)
            print(' dest candidates:  ', dest_candidates)

            best = None
            best_pair = None
            for o in orig_candidates:
                for d in dest_candidates:
                    olat, olng, on = o
                    dlat, dlng, dn = d
                    try:
                        route = route_any([(olng, olat), (dlng, dlat)])
                    except Exception:
                        route = None
                    # if route missing, estimate from haversine
                    if route and route.get('duration_seconds') and route_result_is_reasonable(route, olat, olng, dlat, dlng):
                        dur = int(round(route.get('duration_seconds')))
                    else:
                        miles = haversine_miles(olat, olng, dlat, dlng)
                        if miles is None:
                            dur = None
                        else:
                            dur = estimate_duration_seconds_from_meters(miles * 1609.344)
                    if dur is None:
                        continue
                    if best is None or dur < best:
                        best = dur
                        best_pair = (o, d, route)
            if best and best_pair:
                (olat, olng, on), (dlat, dlng, dn), route = best_pair
                print(' Best candidate:', on, '->', dn, 'ETA(s):', best)
                # update only if change significant (e.g., ETA reduction or coords changed)
                update = False
                if p.origin_lat != olat or p.origin_lng != olng:
                    p.origin_lat = olat
                    p.origin_lng = olng
                    update = True
                if p.dest_lat != dlat or p.dest_lng != dlng:
                    p.dest_lat = dlat
                    p.dest_lng = dlng
                    update = True
                if p.eta_seconds != best:
                    p.eta_seconds = int(best)
                    update = True
                if update:
                    p.eta_updated_at = __import__('datetime').datetime.utcnow()
                    db.session.add(p)
                    db.session.commit()
                    print(' Pool updated with best candidate')
                else:
                    print(' No update needed')
            else:
                print(' No feasible candidate route found')

if __name__ == '__main__':
    main()
