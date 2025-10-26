from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from .forms import PoolForm, JoinRequestForm
from .models import Pool, JoinRequest, Ride, User
from .geo import geocode_mapbox, haversine_miles, route_any, estimate_duration_seconds_from_meters
from sqlalchemy.exc import OperationalError
from . import db
from datetime import datetime, timedelta

# If a computed/persisted ETA exceeds this (seconds) we'll flag it as suspicious in the UI
ETA_FLAG_THRESHOLD_SECONDS = 6 * 3600  # 6 hours
# (no direct 'or_' usage in this module)

# Hard-coded example gas cost assumptions (example values)
# You can later make these configurable via settings or per-user preferences
GAS_PRICE_PER_GALLON = 3.50  # USD per gallon (example)
VEHICLE_MPG = 30.0  # average miles per gallon (example)

"""
Primary application routes were removed to leave a structural scaffold. Add
views and route handlers here when implementing the application logic.
"""
main_bp = Blueprint('main', __name__, template_folder='templates')

__all__ = []

@main_bp.route('/')
@main_bp.route('/listings')
def listings():
    """Serve the listings page at both / and /listings."""
    q = request.args.get('q', type=str)
    try:
        if q:
            # simple case-insensitive search on destination
            term = f"%{q}%"
            pools = Pool.query.filter(Pool.cancelled == False, Pool.destination.ilike(term)).order_by(Pool.depart_time.asc().nullsfirst()).all()
        else:
            pools = Pool.query.filter_by(cancelled=False).order_by(Pool.depart_time.asc().nullsfirst()).all()
    except OperationalError:
        # If the DB doesn't have the 'cancelled' column (older schema), fall back to not filtering
        if q:
            term = f"%{q}%"
            pools = Pool.query.filter(Pool.destination.ilike(term)).order_by(Pool.depart_time.asc().nullsfirst()).all()
        else:
            pools = Pool.query.order_by(Pool.depart_time.asc().nullsfirst()).all()

    # Attempt to compute ETA (duration) for pools that have origin/destination coordinates.
    # This will call Mapbox Directions for each pool with coords when MAPBOX_TOKEN is set.
    # Pre-geocode the current user's pickup address once (if available)
    user_pickup_lat = None
    user_pickup_lng = None
    try:
        if current_user.is_authenticated and getattr(current_user, 'pickup_address', None):
            upl, uplng = geocode_mapbox(current_user.pickup_address)
            if upl and uplng:
                user_pickup_lat = upl
                user_pickup_lng = uplng
    except Exception:
        user_pickup_lat = None
        user_pickup_lng = None

    # simple pagination so the listings page doesn't try to render an enormous list at once
    page = request.args.get('page', default=1, type=int) or 1
    per_page = 12
    total_pools = len(pools)
    start = (page - 1) * per_page
    end = start + per_page
    paged_pools = pools[start:end]

    for p in paged_pools:
        # default: no eta
        p.eta_seconds = None
        p.eta_human = None
        p.eta_arrival = None
        # Ensure cost/display attributes exist to avoid template undefined errors
        p.travel_distance_miles = None
        p.cost_total = None
        p.cost_per_rider = None

        # If a persisted ETA exists on the pool, prefer that (useful for listings created earlier)
        if hasattr(p, 'eta_seconds') and p.eta_seconds is not None:
            try:
                dur = int(p.eta_seconds)
                p.eta_seconds = dur
                hours, rem = divmod(dur, 3600)
                mins = rem // 60
                p.eta_human = f"{hours}h {mins}m" if hours else f"{mins}m"
                if p.depart_time:
                    try:
                        p.eta_arrival = p.depart_time + timedelta(seconds=dur)
                    except Exception:
                        p.eta_arrival = None
            except Exception:
                p.eta_seconds = None
                p.eta_human = None
                p.eta_arrival = None
        else:
            # compute ETA for origin -> destination using road routing when available
            try:
                if hasattr(p, 'origin_lat') and p.origin_lat and p.origin_lng and p.dest_lat and p.dest_lng:
                    route = route_any([(p.origin_lng, p.origin_lat), (p.dest_lng, p.dest_lat)])
                    if route and route.get('duration_seconds'):
                        # sanity-check route result; fall back to haversine estimate if unreasonable
                        from .geo import route_result_is_reasonable
                        if not route_result_is_reasonable(route, p.origin_lat, p.origin_lng, p.dest_lat, p.dest_lng):
                            # suspicious routing result (very long or far off); fallback
                            miles = haversine_miles(p.origin_lat, p.origin_lng, p.dest_lat, p.dest_lng)
                            if miles is not None:
                                meters = miles * 1609.344
                                dur = estimate_duration_seconds_from_meters(meters)
                            else:
                                dur = None
                        else:
                            dur = int(round(route.get('duration_seconds')))
                    else:
                        # fallback: estimate from haversine distance between origin and destination
                        miles = haversine_miles(p.origin_lat, p.origin_lng, p.dest_lat, p.dest_lng)
                        if miles is not None:
                            meters = miles * 1609.344
                            dur = estimate_duration_seconds_from_meters(meters)
                        else:
                            dur = None

                    if dur:
                        p.eta_seconds = dur
                        hours, rem = divmod(dur, 3600)
                        mins = rem // 60
                        p.eta_human = f"{hours}h {mins}m" if hours else f"{mins}m"
                        if p.depart_time:
                            try:
                                p.eta_arrival = p.depart_time + timedelta(seconds=dur)
                            except Exception:
                                p.eta_arrival = None
                    # compute route distance (miles) for cost estimation
                    p.travel_distance_miles = None
                    if route and route.get('distance_meters'):
                        try:
                            p.travel_distance_miles = float(route.get('distance_meters')) / 1609.344
                        except Exception:
                            p.travel_distance_miles = None
                    else:
                        try:
                            miles = haversine_miles(p.origin_lat, p.origin_lng, p.dest_lat, p.dest_lng)
                            p.travel_distance_miles = miles
                        except Exception:
                            p.travel_distance_miles = None
                    # estimate gas cost (hard-coded example): total cost = (distance / mpg) * gas_price
                    p.cost_total = None
                    p.cost_per_rider = None
                    try:
                        if p.travel_distance_miles:
                            total_gallons = float(p.travel_distance_miles) / float(VEHICLE_MPG)
                            total_cost = total_gallons * float(GAS_PRICE_PER_GALLON)
                            p.cost_total = round(total_cost, 2)
                            # Split cost by the number of seats originally listed for the pool.
                            # If seats is not set or invalid, fall back to 1 to avoid division by zero.
                            try:
                                seats = int(p.seats) if (hasattr(p, 'seats') and p.seats and int(p.seats) > 0) else 1
                            except Exception:
                                seats = 1
                            p.cost_per_rider = round(total_cost / float(seats), 2)
                    except Exception:
                        p.cost_total = None
                        p.cost_per_rider = None
                    # compute a display ETA that is capped/adjusted when route seems unreasonable
                    p.eta_seconds_display = p.eta_seconds
                    p.eta_human_display = p.eta_human
                    p.eta_arrival_display = p.eta_arrival
                    try:
                        # if coords exist compute straight-line estimate
                        if hasattr(p, 'origin_lat') and p.origin_lat and p.origin_lng and p.dest_lat and p.dest_lng:
                            miles = haversine_miles(p.origin_lat, p.origin_lng, p.dest_lat, p.dest_lng)
                            if miles is not None:
                                est = estimate_duration_seconds_from_meters(miles * 1609.344)
                            else:
                                est = None
                            # If route duration is massively larger than straight-line estimate and the straight-line
                            # distance is small (likely ambiguous geocode), prefer an adjusted estimate.
                            if p.eta_seconds and est and p.eta_seconds > (4 * 3600) and p.eta_seconds > (est * 5) and miles < 10:
                                adj = int(max(60, round(est * 1.2)))
                                p.eta_seconds_display = adj
                                ph, prem = divmod(adj, 3600)
                                p.eta_human_display = f"{ph}h {prem//60}m" if ph else f"{prem//60}m"
                                if p.depart_time:
                                    try:
                                        p.eta_arrival_display = p.depart_time + timedelta(seconds=adj)
                                    except Exception:
                                        p.eta_arrival_display = None
                                p.eta_flagged = True
                    except Exception:
                        pass
                    # flag suspiciously large ETAs for UI
                    p.eta_flagged = True if (hasattr(p, 'eta_seconds') and p.eta_seconds and p.eta_seconds > ETA_FLAG_THRESHOLD_SECONDS) else False
            except Exception:
                p.eta_seconds = None
                p.eta_human = None
                p.eta_arrival = None

            # Ensure cost is computed for pools with coords even if ETA was persisted
            try:
                if hasattr(p, 'origin_lat') and p.origin_lat and p.origin_lng and p.dest_lat and p.dest_lng:
                    # prefer routing distance when available
                    try:
                        r = route_any([(p.origin_lng, p.origin_lat), (p.dest_lng, p.dest_lat)])
                    except Exception:
                        r = None
                    if r and r.get('distance_meters'):
                        try:
                            p.travel_distance_miles = float(r.get('distance_meters')) / 1609.344
                        except Exception:
                            p.travel_distance_miles = None
                    else:
                        try:
                            p.travel_distance_miles = haversine_miles(p.origin_lat, p.origin_lng, p.dest_lat, p.dest_lng)
                        except Exception:
                            p.travel_distance_miles = None

                    if p.travel_distance_miles:
                        try:
                            total_gallons = float(p.travel_distance_miles) / float(VEHICLE_MPG)
                            total_cost = total_gallons * float(GAS_PRICE_PER_GALLON)
                            p.cost_total = round(total_cost, 2)
                            # split by originally listed seats (fallback to 1)
                            try:
                                seats = int(p.seats) if (hasattr(p, 'seats') and p.seats and int(p.seats) > 0) else 1
                            except Exception:
                                seats = 1
                            p.cost_per_rider = round(total_cost / float(seats), 2)
                        except Exception:
                            p.cost_total = None
                            p.cost_per_rider = None
            except Exception:
                # don't let cost computation break listings rendering
                p.travel_distance_miles = None
                p.cost_total = None
                p.cost_per_rider = None

    # pickup-specific timings for the current user
        p.pickup_travel_seconds = None
        p.pickup_travel_human = None
        p.pickup_leave_by = None
        try:
            if user_pickup_lat and user_pickup_lng and hasattr(p, 'origin_lat') and p.origin_lat and p.origin_lng:
                proute = route_any([(user_pickup_lng, user_pickup_lat), (p.origin_lng, p.origin_lat)])
                if proute and proute.get('duration_seconds'):
                    pdur = int(round(proute.get('duration_seconds')))
                else:
                    miles = haversine_miles(user_pickup_lat, user_pickup_lng, p.origin_lat, p.origin_lng)
                    if miles is not None:
                        meters = miles * 1609.344
                        pdur = estimate_duration_seconds_from_meters(meters)
                    else:
                        pdur = None

                if pdur:
                    p.pickup_travel_seconds = pdur
                    phours, prem = divmod(pdur, 3600)
                    pmins = prem // 60
                    p.pickup_travel_human = f"{phours}h {pmins}m" if phours else f"{pmins}m"
                    if p.depart_time:
                        try:
                            p.pickup_leave_by = p.depart_time - timedelta(seconds=pdur)
                        except Exception:
                            p.pickup_leave_by = None
        except Exception:
            p.pickup_travel_seconds = None
            p.pickup_travel_human = None
            p.pickup_leave_by = None
        # ensure eta_flagged exists even if no eta computed
        if not hasattr(p, 'eta_flagged'):
            p.eta_flagged = False
    # build next page url if needed
    has_next = end < total_pools
    next_page = page + 1 if has_next else None
    return render_template('listings.html', pools=paged_pools, q=q, page=page, next_page=next_page)


@main_bp.route('/pool/create', methods=['GET', 'POST'])
@login_required
def create_pool():
    form = PoolForm()
    if form.validate_on_submit():
        pool = Pool(title=form.title.data, origin=form.origin.data, destination=form.destination.data,
                    depart_time=form.depart_time.data, seats=form.seats.data, description=form.description.data,
                    owner=current_user)
        # attempt to geocode origin and destination (no-op if MAPBOX_TOKEN missing)
        try:
            lat, lng = geocode_mapbox(form.origin.data)
            if lat and lng:
                pool.origin_lat = lat
                pool.origin_lng = lng
        except Exception:
            pass
        try:
            dlat, dlng = geocode_mapbox(form.destination.data)
            if dlat and dlng:
                pool.dest_lat = dlat
                pool.dest_lng = dlng
        except Exception:
            pass
        # Compute and persist ETA (origin -> destination) at creation time when coords available
        try:
            if hasattr(pool, 'origin_lat') and pool.origin_lat and pool.origin_lng and pool.dest_lat and pool.dest_lng:
                route = route_any([(pool.origin_lng, pool.origin_lat), (pool.dest_lng, pool.dest_lat)])
                if route and route.get('duration_seconds'):
                    pool.eta_seconds = int(round(route.get('duration_seconds')))
                    pool.eta_updated_at = datetime.utcnow()
                else:
                    miles = haversine_miles(pool.origin_lat, pool.origin_lng, pool.dest_lat, pool.dest_lng)
                    if miles is not None:
                        meters = miles * 1609.344
                        est = estimate_duration_seconds_from_meters(meters)
                        if est:
                            pool.eta_seconds = int(est)
                            pool.eta_updated_at = datetime.utcnow()
        except Exception:
            # fail silently; ETA will be computed on-demand in listings
            pass
        db.session.add(pool)
        db.session.commit()
        flash('Pool created.', 'success')
        return redirect(url_for('main.pool_detail', pool_id=pool.id))
    return render_template('create_pool.html', form=form)


@main_bp.route('/pool/<int:pool_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_pool(pool_id):
    pool = Pool.query.get_or_404(pool_id)
    # only owner can edit
    if pool.owner_id != current_user.id:
        flash('Unauthorized', 'danger')
        return redirect(url_for('main.manage'))
    form = PoolForm(obj=pool)
    if form.validate_on_submit():
        # update fields
        pool.title = form.title.data
        pool.origin = form.origin.data
        pool.destination = form.destination.data
        pool.depart_time = form.depart_time.data
        pool.seats = form.seats.data
        pool.description = form.description.data

        # attempt to geocode origin/destination if changed
        try:
            lat, lng = geocode_mapbox(pool.origin)
            if lat and lng:
                pool.origin_lat = lat
                pool.origin_lng = lng
        except Exception:
            pass
        try:
            dlat, dlng = geocode_mapbox(pool.destination)
            if dlat and dlng:
                pool.dest_lat = dlat
                pool.dest_lng = dlng
        except Exception:
            pass

        # recompute and persist ETA if coords available
        try:
            if hasattr(pool, 'origin_lat') and pool.origin_lat and pool.origin_lng and pool.dest_lat and pool.dest_lng:
                route = route_any([(pool.origin_lng, pool.origin_lat), (pool.dest_lng, pool.dest_lat)])
                if route and route.get('duration_seconds'):
                    pool.eta_seconds = int(round(route.get('duration_seconds')))
                    pool.eta_updated_at = datetime.utcnow()
                else:
                    miles = haversine_miles(pool.origin_lat, pool.origin_lng, pool.dest_lat, pool.dest_lng)
                    if miles is not None:
                        meters = miles * 1609.344
                        est = estimate_duration_seconds_from_meters(meters)
                        if est:
                            pool.eta_seconds = int(est)
                            pool.eta_updated_at = datetime.utcnow()
        except Exception:
            pass

        db.session.commit()
        flash('Pool updated.', 'success')
        return redirect(url_for('main.manage'))
    return render_template('create_pool.html', form=form)


@main_bp.route('/pool/<int:pool_id>', methods=['GET', 'POST'])
def pool_detail(pool_id):
    pool = Pool.query.get_or_404(pool_id)
    # check if current user already has a ride on this pool
    user_ride = None
    if current_user.is_authenticated:
        user_ride = Ride.query.filter_by(pool_id=pool.id, user_id=current_user.id).first()
    form = JoinRequestForm()
    if form.validate_on_submit():
        if not current_user.is_authenticated:
            flash('You must be logged in to request joining.', 'warning')
            return redirect(url_for('auth.login'))
        # Prevent pool owner from requesting to join their own pool
        if pool.owner_id == current_user.id:
            flash('You are the owner of this pool and cannot request to join it.', 'warning')
            return redirect(url_for('main.pool_detail', pool_id=pool.id))
        # Prevent duplicate pending requests or if user already has a ride on this pool
        existing_jr = JoinRequest.query.filter_by(user_id=current_user.id, pool_id=pool.id, status='pending').first()
        if existing_jr:
            flash('You already have a pending request for this pool.', 'info')
            return redirect(url_for('main.pool_detail', pool_id=pool.id))
        existing_ride_for_user = Ride.query.filter_by(pool_id=pool.id, user_id=current_user.id).first()
        if existing_ride_for_user:
            flash('You are already a rider on this pool.', 'info')
            return redirect(url_for('main.pool_detail', pool_id=pool.id))
        # Prevent joining a full pool
        if hasattr(pool, 'seats') and (pool.seats is not None) and pool.seats <= 0:
            flash('This pool has no seats available.', 'warning')
            return redirect(url_for('main.pool_detail', pool_id=pool.id))
        jr = JoinRequest(user_id=current_user.id, pool_id=pool.id, message=form.message.data)
        db.session.add(jr)
        db.session.commit()
        flash('Join request sent.', 'success')
        return redirect(url_for('main.pool_detail', pool_id=pool.id))
    is_owner = current_user.is_authenticated and (pool.owner_id == current_user.id)
    is_rider = user_ride is not None
    seats_available = None
    is_full = False
    if hasattr(pool, 'seats'):
        seats_available = pool.seats
        is_full = (seats_available is not None) and (seats_available <= 0)
    return render_template('pool_detail.html', pool=pool, form=form, is_owner=is_owner, is_rider=is_rider, seats_available=seats_available, is_full=is_full)


@main_bp.route('/manage')
@login_required
def manage():
    # show pools owned by user and join requests for those pools
    # Exclude cancelled pools from the owner's list
    try:
        owned_pools = Pool.query.filter_by(owner_id=current_user.id, cancelled=False).all()
    except Exception:
        # If the DB doesn't have the column, fall back to showing all owned pools
        owned_pools = Pool.query.filter_by(owner_id=current_user.id).all()

    # Get the user's active rides (pools they're participating in as a rider, not as owner)
    my_rides = Ride.query.filter_by(user_id=current_user.id).join(Pool).filter(Pool.owner_id != current_user.id).all()
    # Filter out cancelled pools if the column exists
    if my_rides:
        filtered_rides = []
        for ride in my_rides:
            if hasattr(ride.pool, 'cancelled') and ride.pool.cancelled:
                continue
            if ride.status == 'cancelled':
                continue
            filtered_rides.append(ride)
        my_rides = filtered_rides

    # Show the user's join requests, but hide those where the pool is cancelled or where
    # the user already has a ride on that pool which is cancelled.
    # Show the user's join requests (only pending ones), but hide those where the pool is cancelled
    raw_requests = JoinRequest.query.filter_by(user_id=current_user.id, status='pending').all()
    my_requests = []
    for jr in raw_requests:
        pool = jr.pool
        # skip if pool is cancelled (if that attribute exists)
        if hasattr(pool, 'cancelled') and pool.cancelled:
            continue
        # skip if there is a cancelled ride for this user on that pool
        cancelled_ride = Ride.query.filter_by(pool_id=jr.pool_id, user_id=current_user.id, status='cancelled').first()
        if cancelled_ride:
            continue
        my_requests.append(jr)

    # Collect pending join requests for pools owned by the current user (owners review only pending requests)
    owner_raw_requests = JoinRequest.query.join(Pool).filter(Pool.owner_id == current_user.id, JoinRequest.status == 'pending').all()
    owner_requests = []
    for jr in owner_raw_requests:
        pool = jr.pool
        if hasattr(pool, 'cancelled') and pool.cancelled:
            continue
        owner_requests.append(jr)

    # Build owner pools info: riders and pending requests grouped per pool
    owner_pools_info = []
    for p in owned_pools:
        # current riders
        rides = Ride.query.filter_by(pool_id=p.id).all()
        riders = []
        for r in rides:
            u = User.query.get(r.user_id)
            if u:
                riders.append({'user': u, 'ride': r})

        # pending/other requests for this pool
        reqs = [jr for jr in owner_requests if jr.pool_id == p.id]

        owner_pools_info.append({'pool': p, 'riders': riders, 'requests': reqs})

    # Compute added time to route for each pending request (for owners to review)
    # Attach jr.added_seconds and jr.added_human when computable.
    for jr in owner_requests:
        try:
            jr.added_seconds = None
            jr.added_human = None
            pool = jr.pool
            # Need pool coords and requester pickup address
            if (hasattr(pool, 'origin_lat') and pool.origin_lat and pool.origin_lng and pool.dest_lat and pool.dest_lng) and getattr(jr.requester, 'pickup_address', None):
                # Geocode requester pickup address (use geocode_any which prefers ORS/Mapbox/Nominatim)
                from .geo import geocode_any
                plat, plong, provider = geocode_any(jr.requester.pickup_address)
                if plat and plong:
                    # Compute base duration (origin -> destination)
                    base_route = route_any([(pool.origin_lng, pool.origin_lat), (pool.dest_lng, pool.dest_lat)])
                    if base_route and base_route.get('duration_seconds'):
                        base_dur = int(round(base_route.get('duration_seconds')))
                    else:
                        miles = haversine_miles(pool.origin_lat, pool.origin_lng, pool.dest_lat, pool.dest_lng)
                        base_dur = estimate_duration_seconds_from_meters(miles * 1609.344) if miles is not None else None

                    # Compute detour: origin -> pickup -> destination
                    detour_route = route_any([(pool.origin_lng, pool.origin_lat), (plong, plat), (pool.dest_lng, pool.dest_lat)])
                    if detour_route and detour_route.get('duration_seconds'):
                        detour_dur = int(round(detour_route.get('duration_seconds')))
                    else:
                        # Estimate by summing legs via haversine
                        legs_miles = None
                        try:
                            m1 = haversine_miles(pool.origin_lat, pool.origin_lng, plat, plong)
                            m2 = haversine_miles(plat, plong, pool.dest_lat, pool.dest_lng)
                            if m1 is not None and m2 is not None:
                                meters = (m1 + m2) * 1609.344
                                detour_dur = estimate_duration_seconds_from_meters(meters)
                            else:
                                detour_dur = None
                        except Exception:
                            detour_dur = None

                    if base_dur is not None and detour_dur is not None:
                        added = detour_dur - base_dur
                        if added < 0:
                            added = 0
                        jr.added_seconds = added
                        hours, rem = divmod(added, 3600)
                        mins = rem // 60
                        jr.added_human = f"{hours}h {mins}m" if hours else f"{mins}m"
        except Exception:
            jr.added_seconds = None
            jr.added_human = None

    return render_template('manage.html', owned_pools=owned_pools, my_requests=my_requests, my_rides=my_rides, owner_requests=owner_requests, owner_pools_info=owner_pools_info)


@main_bp.route('/pool/<int:pool_id>/cancel', methods=['POST'])
@login_required
def cancel_pool(pool_id):
    pool = Pool.query.get_or_404(pool_id)
    if pool.owner_id != current_user.id:
        flash('Unauthorized', 'danger')
        return redirect(url_for('main.pool_detail', pool_id=pool.id))
    # Prevent cancelling a pool that already has riders
    existing_ride = Ride.query.filter_by(pool_id=pool.id).first()
    if existing_ride:
        flash('Cannot cancel a pool with riders. Remove riders first.', 'warning')
        return redirect(url_for('main.manage'))
    try:
        pool.cancelled = True
        db.session.commit()
        flash('Pool cancelled.', 'info')
    except OperationalError:
        # DB doesn't have cancelled column: fallback to deleting the pool record
        db.session.rollback()
        db.session.delete(pool)
        db.session.commit()
        flash('Pool deleted (old database schema).', 'info')
    return redirect(url_for('main.listings'))


@main_bp.route('/pool/<int:pool_id>/leave', methods=['POST'])
@login_required
def leave_pool(pool_id):
    pool = Pool.query.get_or_404(pool_id)
    # find Ride for current user
    ride = Ride.query.filter_by(pool_id=pool.id, user_id=current_user.id).first()
    if not ride:
        flash('You are not a rider on this pool.', 'warning')
        return redirect(url_for('main.pool_detail', pool_id=pool.id))
    # remove the ride record (user leaves pool)
    db.session.delete(ride)
    # restore a seat when a rider leaves (if seats column exists)
    if hasattr(pool, 'seats') and (pool.seats is not None):
        try:
            pool.seats = pool.seats + 1
        except Exception:
            # fallback: ignore if seats can't be updated
            pass
    db.session.commit()
    flash('You have left the pool.', 'info')
    return redirect(url_for('main.listings'))


@main_bp.route('/pool/<int:pool_id>/add_rider', methods=['POST'])
@login_required
def add_rider(pool_id):
    pool = Pool.query.get_or_404(pool_id)
    if pool.owner_id != current_user.id:
        flash('Unauthorized', 'danger')
        return redirect(url_for('main.manage'))
    identifier = request.form.get('identifier', '').strip()
    if not identifier:
        flash('Please provide a username or email to add.', 'warning')
        return redirect(url_for('main.manage'))
    # find user by username or email
    user = User.query.filter((User.username == identifier) | (User.email == identifier)).first()
    if not user:
        flash('No user found with that username or email.', 'warning')
        return redirect(url_for('main.manage'))
    if user.id == pool.owner_id:
        flash('Owner is automatically part of the pool.', 'warning')
        return redirect(url_for('main.manage'))
    existing = Ride.query.filter_by(pool_id=pool.id, user_id=user.id).first()
    if existing:
        flash('That user is already a rider on this pool.', 'info')
        return redirect(url_for('main.manage'))
    # ensure seats available before adding
    if hasattr(pool, 'seats') and (pool.seats is not None):
        if pool.seats <= 0:
            flash('No seats available to add this rider.', 'warning')
            return redirect(url_for('main.manage'))
        pool.seats = pool.seats - 1
    ride = Ride(pool_id=pool.id, user_id=user.id, status='scheduled')
    db.session.add(ride)
    db.session.commit()
    flash(f'{user.username} has been added to the pool.', 'success')
    return redirect(url_for('main.manage'))


@main_bp.route('/pool/<int:pool_id>/remove_rider/<int:user_id>', methods=['POST'])
@login_required
def remove_rider(pool_id, user_id):
    pool = Pool.query.get_or_404(pool_id)
    if pool.owner_id != current_user.id:
        flash('Unauthorized', 'danger')
        return redirect(url_for('main.manage'))
    # prevent removing the owner
    if pool.owner_id == user_id:
        flash('Cannot remove the owner from the pool.', 'warning')
        return redirect(url_for('main.manage'))
    ride = Ride.query.filter_by(pool_id=pool.id, user_id=user_id).first()
    if not ride:
        flash('Rider not found.', 'warning')
        return redirect(url_for('main.manage'))
    db.session.delete(ride)
    # restore a seat when a rider is removed by owner
    if hasattr(pool, 'seats') and (pool.seats is not None):
        try:
            pool.seats = pool.seats + 1
        except Exception:
            pass
    db.session.commit()
    flash('Rider removed from the pool.', 'info')
    return redirect(url_for('main.manage'))


@main_bp.route('/request/<int:req_id>/action/<string:action>')
@login_required
def handle_request(req_id, action):
    jr = JoinRequest.query.get_or_404(req_id)
    pool = jr.pool
    # only pool owner can accept/reject
    if pool.owner_id != current_user.id:
        flash('Unauthorized', 'danger')
        return redirect(url_for('main.manage'))
    if action == 'accept':
        # ensure there are seats available
        if hasattr(pool, 'seats') and (pool.seats is not None):
            if pool.seats <= 0:
                flash('No seats available to accept this request.', 'warning')
                return redirect(url_for('main.manage'))
            pool.seats = pool.seats - 1
        jr.status = 'accepted'
        # create a Ride as basic assignment
        ride = Ride(pool_id=pool.id, user_id=jr.user_id, status='scheduled')
        db.session.add(ride)
    elif action == 'reject':
        jr.status = 'rejected'
    db.session.commit()
    flash('Request updated', 'info')
    return redirect(url_for('main.manage'))


@main_bp.route('/request/<int:req_id>/cancel', methods=['POST'])
@login_required
def cancel_request(req_id):
    """Allow a requester to cancel/withdraw their pending join request."""
    jr = JoinRequest.query.get_or_404(req_id)
    # only the requester can cancel their own request
    if jr.user_id != current_user.id:
        flash('Unauthorized', 'danger')
        return redirect(url_for('main.manage'))
    if jr.status != 'pending':
        flash('Request cannot be cancelled (already processed).', 'info')
        return redirect(url_for('main.manage'))
    jr.status = 'withdrawn'
    db.session.commit()
    flash('Join request cancelled.', 'info')
    return redirect(url_for('main.manage'))


@main_bp.route('/api/listings')
def api_listings():
    """Return JSON list of pools sorted by distance to a provided lat/lng.

    Query params: lat, lng, max (optional, default 50), include_eta (optional, true/false)
    """
    try:
        user_lat = request.args.get('lat', type=float)
        user_lng = request.args.get('lng', type=float)
    except Exception:
        user_lat = None
        user_lng = None
    max_results = request.args.get('max', default=50, type=int)
    include_eta = request.args.get('include_eta', default='false').lower() in ('1', 'true', 'yes')

    pools = Pool.query.filter_by(cancelled=False).all()
    results = []
    for p in pools:
        distance = None
        if user_lat is not None and user_lng is not None and p.origin_lat is not None and p.origin_lng is not None:
            distance = haversine_miles(user_lat, user_lng, p.origin_lat, p.origin_lng)
        results.append({'pool': p, 'distance_miles': distance})

    # sort pools - those without distance go to the end
    results = sorted(results, key=lambda r: (r['distance_miles'] is None, r['distance_miles'] if r['distance_miles'] is not None else 1e9))

    output = []
    # Optionally include ETA using Mapbox for top N results
    to_check = results[: min(len(results), max_results)]
    for item in to_check:
        p = item['pool']
        row = p.serialize()
        row['distance_miles'] = item['distance_miles']
        if include_eta:
            # only attempt ETA if we have both origin and destination coords
            if p.origin_lng and p.origin_lat and p.dest_lng and p.dest_lat:
                # prefer persisted ETA when present
                if hasattr(p, 'eta_seconds') and p.eta_seconds:
                    row['eta_seconds'] = p.eta_seconds
                    row['eta_source'] = 'persisted'
                else:
                    route = route_any([(p.origin_lng, p.origin_lat), (p.dest_lng, p.dest_lat)])
                    if route and route.get('duration_seconds'):
                        row['eta_seconds'] = route.get('duration_seconds')
                        row['route_distance_meters'] = route.get('distance_meters')
                        row['eta_source'] = 'routing'
                    else:
                        # fallback: estimate using haversine distance
                        miles = haversine_miles(p.origin_lat, p.origin_lng, p.dest_lat, p.dest_lng)
                        if miles is not None:
                            meters = miles * 1609.344
                            est = estimate_duration_seconds_from_meters(meters)
                            row['eta_seconds'] = est
                            row['eta_source'] = 'estimate'
        output.append(row)

    return {'count': len(output), 'results': output}