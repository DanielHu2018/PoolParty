"""
Main blueprint placeholder.

Primary application routes were removed to leave a structural scaffold. Add
views and route handlers here when implementing the application logic.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from .forms import PoolForm, JoinRequestForm
from .models import Pool, JoinRequest, Ride, User
from . import db
from datetime import datetime

main_bp = Blueprint('main', __name__, template_folder='templates')


@main_bp.route('/')
def index():
    pools = Pool.query.order_by(Pool.created_at.desc()).limit(50).all()
    return render_template('index.html', pools=pools)

@main_bp.route('/listings')
def listings():
    pools = Pool.query.order_by(Pool.depart_time.asc().nullsfirst()).all()
    return render_template('listings.html', pools=pools)

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
    form = JoinRequestForm()
    if form.validate_on_submit():
        if not current_user.is_authenticated:
            flash('You must be logged in to request joining.', 'warning')
            return redirect(url_for('auth.login'))
        jr = JoinRequest(user_id=current_user.id, pool_id=pool.id, message=form.message.data)
        db.session.add(jr)
        db.session.commit()
        flash('Join request sent.', 'success')
        return redirect(url_for('main.pool_detail', pool_id=pool.id))
    return render_template('pool_detail.html', pool=pool, form=form)

@main_bp.route('/manage')
@login_required
def manage():
    # show pools owned by user and join requests for those pools
    owned_pools = Pool.query.filter_by(owner_id=current_user.id).all()
    my_requests = JoinRequest.query.filter_by(user_id=current_user.id).all()
    return render_template('manage.html', owned_pools=owned_pools, my_requests=my_requests)


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
        jr.status = 'accepted'
        # create a Ride as basic assignment
        ride = Ride(pool_id=pool.id, user_id=jr.user_id, status='scheduled')
        db.session.add(ride)
    elif action == 'reject':
        jr.status = 'rejected'
    db.session.commit()
    flash('Request updated', 'info')
    return redirect(url_for('main.manage'))