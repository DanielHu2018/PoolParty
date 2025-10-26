#!/usr/bin/env python3
"""Re-geocode pools with suspiciously large ETAs using Mapbox (preferred) and update coords + ETA.

Run with PYTHONPATH set to repo root and MAPBOX_TOKEN available if you want Mapbox geocoding.
This will only update pools whose stored ETA exceeds the threshold to avoid touching every row.
"""
import os
from math import radians, cos, sin, asin, sqrt
from app import create_app, db
from app.models import Pool
from app.geo import geocode_mapbox, route_any, haversine_miles, estimate_duration_seconds_from_meters, route_result_is_reasonable

ETA_THRESH = int(os.environ.get('ETA_FLAG_THRESHOLD_SECONDS', 6 * 3600))
DIST_DIFF_METERS = int(os.environ.get('REGEOCODE_DIFF_METERS', 5000))


def meters_between(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    # reuse haversine_miles
    miles = haversine_miles(lat1, lon1, lat2, lon2)
    if miles is None:
        return None
    return miles * 1609.344


def main():
    app = create_app()
    with app.app_context():
        pools = Pool.query.filter(Pool.eta_seconds != None).all()
        candidates = [p for p in pools if p.eta_seconds and p.eta_seconds > ETA_THRESH]
        if not candidates:
            print('No candidate pools with ETA >', ETA_THRESH)
            return
        print('Found', len(candidates), 'candidate pools')
        for p in candidates:
            print('\n---')
            print(f'Pool {p.id}: {p.title} (stored eta {p.eta_seconds}s)')
            print('Stored origin coords:', p.origin_lat, p.origin_lng)
            print('Stored dest coords:  ', p.dest_lat, p.dest_lng)
            # try mapbox geocode for origin and destination
            nlat, nlng = None, None
            dlat, dlng = None, None
            try:
                nlat, nlng = geocode_mapbox(p.origin)
            except Exception as e:
                print('mapbox origin error:', e)
            try:
                dlat, dlng = geocode_mapbox(p.destination)
            except Exception as e:
                print('mapbox dest error:', e)
            print('Mapbox geocode origin:', nlat, nlng)
            print('Mapbox geocode dest:  ', dlat, dlng)

            changed = False
            # if mapbox found coords and they differ substantially from stored, update
            if nlat and nlng and p.origin_lat is not None and p.origin_lng is not None:
                diff = meters_between(p.origin_lat, p.origin_lng, nlat, nlng)
            else:
                diff = None
            if diff is None or (diff and diff > DIST_DIFF_METERS):
                if nlat and nlng:
                    print(f' Updating origin coords (diff {diff} m)')
                    p.origin_lat = nlat
                    p.origin_lng = nlng
                    changed = True
            if dlat and dlng and p.dest_lat is not None and p.dest_lng is not None:
                ddiff = meters_between(p.dest_lat, p.dest_lng, dlat, dlng)
            else:
                ddiff = None
            if ddiff is None or (ddiff and ddiff > DIST_DIFF_METERS):
                if dlat and dlng:
                    print(f' Updating destination coords (diff {ddiff} m)')
                    p.dest_lat = dlat
                    p.dest_lng = dlng
                    changed = True

            if changed:
                # recompute ETA
                try:
                    if p.origin_lat and p.origin_lng and p.dest_lat and p.dest_lng:
                        route = route_any([(p.origin_lng, p.origin_lat), (p.dest_lng, p.dest_lat)])
                        if route and route.get('duration_seconds') and route_result_is_reasonable(route, p.origin_lat, p.origin_lng, p.dest_lat, p.dest_lng):
                            p.eta_seconds = int(round(route.get('duration_seconds')))
                            print(' New ETA from routing:', p.eta_seconds)
                        else:
                            miles = haversine_miles(p.origin_lat, p.origin_lng, p.dest_lat, p.dest_lng)
                            if miles is not None:
                                est = estimate_duration_seconds_from_meters(miles * 1609.344)
                                if est:
                                    p.eta_seconds = int(est)
                                    print(' New ETA from estimate:', p.eta_seconds)
                        p.eta_updated_at = __import__('datetime').datetime.utcnow()
                        db.session.add(p)
                        db.session.commit()
                        print(' Pool updated')
                except Exception as e:
                    print(' Error recomputing ETA:', e)
            else:
                print(' No significant geocode change; skipping')

if __name__ == '__main__':
    main()
