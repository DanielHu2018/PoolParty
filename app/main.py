"""
Main blueprint placeholder.

Primary application routes were removed to leave a structural scaffold. Add
views and route handlers here when implementing the application logic.
"""

__all__ = []

@main_bp.route('/listings')
def listings():
    pools = Pool.query.order_by(Pool.depart_time.asc().nullsfirst()).all()
    return render_template('listings.html', pools=pools)


@main_bp.route('/manage')
@login_required
def manage():
    # show pools owned by user and join requests for those pools
    owned_pools = Pool.query.filter_by(owner_id=current_user.id).all()
    my_requests = JoinRequest.query.filter_by(user_id=current_user.id).all()
    return render_template('manage.html', owned_pools=owned_pools, my_requests=my_requests)