from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from .forms import PoolForm, JoinRequestForm
from .models import Pool, JoinRequest, Ride, User
from sqlalchemy.exc import OperationalError
from . import db
from datetime import datetime
from sqlalchemy import or_

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
    return render_template('listings.html', pools=pools, q=q)


@main_bp.route('/pool/create', methods=['GET', 'POST'])
@login_required
def create_pool():
    form = PoolForm()
    if form.validate_on_submit():
        pool = Pool(title=form.title.data, origin=form.origin.data, destination=form.destination.data,
                    depart_time=form.depart_time.data, seats=form.seats.data, description=form.description.data,
                    owner=current_user)
        db.session.add(pool)
        db.session.commit()
        flash('Pool created.', 'success')
        return redirect(url_for('main.pool_detail', pool_id=pool.id))
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