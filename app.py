from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from database import get_db, init_db, calculate_quarter
from datetime import datetime, date, timedelta
import calendar

app = Flask(__name__)
app.secret_key = 'community_system_secret_key'
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['TEMPLATES_AUTO_RELOAD'] = True

def get_date_range(period, year=None, quarter=None):
    # get date range for filtering
    today = date.today()
    
    if period == 'quarterly':
        if not year or not quarter:
            year = today.year
            quarter = (today.month - 1) // 3 + 1
        start = date(year, (quarter - 1) * 3 + 1, 1)
        if quarter == 4:
            end = date(year, 12, 31)
        else:
            next_month = quarter * 3 + 1
            end = date(year, next_month, 1) - timedelta(days=1)
    elif period == 'annual':
        if not year:
            year = today.year
        start = date(year, 1, 1)
        end = date(year, 12, 31)
    else:  # to_date - show everything
        start = date(2000, 1, 1)
        end = today
    
    return start, end

@app.route('/')
def index():
    # dashboard with filters
    period = request.args.get('period', 'to_date')
    year = request.args.get('year', type=int)
    quarter = request.args.get('quarter', type=int)
    org_id = request.args.get('org_id', type=int)
    
    start_date, end_date = get_date_range(period, year, quarter)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # build query filters
    where_clauses = ['ep.event_date BETWEEN ? AND ?']
    params = [start_date, end_date]
    
    if org_id:
        where_clauses.append('ep.organization_id = ?')
        params.append(org_id)
    
    where_sql = ' AND '.join(where_clauses)
    
    # Statistics
    cursor.execute(f'SELECT COUNT(*) FROM event_profiles ep WHERE {where_sql}', params)
    total_events = cursor.fetchone()[0]
    
    cursor.execute(f'''
        SELECT COALESCE(SUM(hours * rate_per_hour), 0) 
        FROM cost_entries ce 
        JOIN event_profiles ep ON ce.event_id = ep.id 
        WHERE {where_sql} AND ce.cost_type_name = "Labor"
    ''', params)
    total_labor_value = cursor.fetchone()[0]
    
    cursor.execute(f'''
        SELECT COALESCE(SUM(amount), 0) 
        FROM cost_entries ce 
        JOIN event_profiles ep ON ce.event_id = ep.id 
        WHERE {where_sql} AND ce.is_income = 1
    ''', params)
    total_income = cursor.fetchone()[0]
    
    cursor.execute(f'''
        SELECT COALESCE(SUM(amount), 0) 
        FROM cost_entries ce 
        JOIN event_profiles ep ON ce.event_id = ep.id 
        WHERE {where_sql} AND ce.is_income = 0
    ''', params)
    total_expense = cursor.fetchone()[0]
    
    # Recent events
    cursor.execute(f'''
        SELECT ep.*, et.name as event_type_name, o.name as org_name
        FROM event_profiles ep 
        LEFT JOIN event_types et ON ep.event_type_id = et.id 
        LEFT JOIN organizations o ON ep.organization_id = o.id
        WHERE {where_sql}
        ORDER BY ep.event_date DESC LIMIT 5
    ''', params)
    recent_events = cursor.fetchall()
    
    # Get organizations for filter
    cursor.execute('SELECT * FROM organizations ORDER BY name')
    organizations = cursor.fetchall()
    
    # Get available years
    cursor.execute('SELECT DISTINCT year FROM event_profiles WHERE year IS NOT NULL ORDER BY year DESC')
    years = [row['year'] for row in cursor.fetchall()]
    
    conn.close()
    
    return render_template('index.html',
                         period=period, year=year, quarter=quarter, org_id=org_id,
                         total_events=total_events,
                         total_labor_value=total_labor_value,
                         total_income=total_income,
                         total_expense=total_expense,
                         net_profit=total_income - total_expense,
                         recent_events=recent_events,
                         organizations=organizations,
                         years=years)


@app.route('/events')
def event_list():
    # Show all events
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT ep.*, et.name as event_type_name, o.name as org_name
        FROM event_profiles ep 
        LEFT JOIN event_types et ON ep.event_type_id = et.id 
        LEFT JOIN organizations o ON ep.organization_id = o.id
        ORDER BY ep.event_date DESC
    ''')
    events = cursor.fetchall()
    conn.close()
    return render_template('event_list.html', events=events)

@app.route('/events/add', methods=['GET', 'POST'])
def add_event():
    """Add event"""
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        event_date = request.form['event_date']
        quarter_str, year, quarter = calculate_quarter(event_date)
        
        cursor.execute('''
            INSERT INTO event_profiles 
            (event_name, event_date, event_type_id, lens_category_id, lens_subcategory_id, location, description,
             organization_id, coordinator_name, coordinator_phone, coordinator_email,
             expected_participants, actual_participants, notes, status, quarter, year)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            request.form['event_name'],
            event_date,
            request.form.get('event_type_id') or None,
            request.form.get('lens_category_id') or None,
            request.form.get('lens_subcategory_id') or None,
            request.form.get('location'),
            request.form.get('description'),
            request.form.get('organization_id') or None,
            request.form.get('coordinator_name'),
            request.form.get('coordinator_phone'),
            request.form.get('coordinator_email'),
            request.form.get('expected_participants') or 0,
            request.form.get('actual_participants') or 0,
            request.form.get('notes'),
            request.form.get('status', 'In Progress'),
            quarter_str,
            year
        ))
        event_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        flash('Event added successfully!', 'success')
        return redirect(url_for('edit_event', event_id=event_id))
    
    cursor.execute('SELECT * FROM event_types')
    event_types = cursor.fetchall()
    cursor.execute('SELECT * FROM organizations ORDER BY name')
    organizations = cursor.fetchall()
    cursor.execute('SELECT * FROM lens_categories ORDER BY name')
    lens_categories = cursor.fetchall()
    
    # Build lens data for JavaScript
    lens_data = {}
    for cat in lens_categories:
        cursor.execute('SELECT id, name FROM lens_subcategories WHERE category_id = ? ORDER BY name', (cat['id'],))
        subcats = cursor.fetchall()
        lens_data[str(cat['id'])] = [{'id': s['id'], 'name': s['name']} for s in subcats]
    
    conn.close()
    
    return render_template('add_event.html', event_types=event_types, organizations=organizations, 
                         lens_categories=lens_categories, lens_data=lens_data)

@app.route('/events/<int:event_id>')
def view_event(event_id):
    """View event details"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT ep.*, et.name as event_type_name, o.name as org_name
        FROM event_profiles ep 
        LEFT JOIN event_types et ON ep.event_type_id = et.id 
        LEFT JOIN organizations o ON ep.organization_id = o.id
        WHERE ep.id = ?
    ''', (event_id,))
    event = cursor.fetchone()
    
    if not event:
        flash('Event not found', 'error')
        return redirect(url_for('event_list'))
    
    # Get cost entries grouped by type
    cursor.execute('''
        SELECT cost_type_name, SUM(amount) as total, SUM(hours) as total_hours
        FROM cost_entries WHERE event_id = ? AND is_income = 0
        GROUP BY cost_type_name
    ''', (event_id,))
    expenses = cursor.fetchall()
    
    cursor.execute('''
        SELECT cost_type_name, SUM(amount) as total
        FROM cost_entries WHERE event_id = ? AND is_income = 1
        GROUP BY cost_type_name
    ''', (event_id,))
    income = cursor.fetchall()
    
    # Get profit distributions
    cursor.execute('SELECT * FROM profit_distributions WHERE event_id = ?', (event_id,))
    distributions = cursor.fetchall()
    
    conn.close()
    return render_template('view_event.html', event=event, expenses=expenses, income=income, distributions=distributions)


@app.route('/events/<int:event_id>/edit', methods=['GET', 'POST'])
def edit_event(event_id):
    """Edit event with cost tracking"""
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        event_date = request.form['event_date']
        quarter_str, year, quarter = calculate_quarter(event_date)
        
        cursor.execute('''
            UPDATE event_profiles SET
            event_name=?, event_date=?, event_type_id=?, location=?, description=?,
            organization_id=?, coordinator_name=?, coordinator_phone=?, coordinator_email=?,
            expected_participants=?, actual_participants=?, notes=?, status=?, quarter=?, year=?
            WHERE id=?
        ''', (
            request.form['event_name'], event_date,
            request.form.get('event_type_id') or None,
            request.form.get('location'), request.form.get('description'),
            request.form.get('organization_id') or None,
            request.form.get('coordinator_name'),
            request.form.get('coordinator_phone'),
            request.form.get('coordinator_email'),
            request.form.get('expected_participants') or 0,
            request.form.get('actual_participants') or 0,
            request.form.get('notes'),
            request.form.get('status', 'In Progress'),
            quarter_str, year, event_id
        ))
        conn.commit()
        flash('Event updated successfully!', 'success')
    
    cursor.execute('SELECT * FROM event_profiles WHERE id = ?', (event_id,))
    event = cursor.fetchone()
    cursor.execute('SELECT * FROM event_types')
    event_types = cursor.fetchall()
    cursor.execute('SELECT * FROM organizations ORDER BY name')
    organizations = cursor.fetchall()
    cursor.execute('SELECT * FROM cost_types ORDER BY name')
    cost_types = cursor.fetchall()
    cursor.execute('SELECT * FROM cost_entries WHERE event_id = ? ORDER BY created_at DESC', (event_id,))
    cost_entries = cursor.fetchall()
    cursor.execute('SELECT * FROM profit_distributions WHERE event_id = ?', (event_id,))
    distributions = cursor.fetchall()
    cursor.execute('SELECT * FROM volunteers ORDER BY name')
    volunteers = cursor.fetchall()
    
    # Calculate totals
    cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM cost_entries WHERE event_id = ? AND is_income = 1', (event_id,))
    total_income = cursor.fetchone()[0]
    cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM cost_entries WHERE event_id = ? AND is_income = 0', (event_id,))
    total_expense = cursor.fetchone()[0]
    
    # Update event totals
    cursor.execute('''
        UPDATE event_profiles SET total_income = ?, total_expense = ?, net_profit = ?
        WHERE id = ?
    ''', (total_income, total_expense, total_income - total_expense, event_id))
    conn.commit()
    
    conn.close()
    return render_template('edit_event.html', event=event, event_types=event_types,
                         organizations=organizations, cost_types=cost_types,
                         cost_entries=cost_entries, distributions=distributions,
                         volunteers=volunteers, total_income=total_income,
                         total_expense=total_expense, net_profit=total_income - total_expense)

@app.route('/events/<int:event_id>/costs/add', methods=['POST'])
def add_cost_entry(event_id):
    """Add cost entry"""
    conn = get_db()
    cursor = conn.cursor()
    
    cost_type_id = request.form.get('cost_type_id')
    cursor.execute('SELECT name, default_rate FROM cost_types WHERE id = ?', (cost_type_id,))
    cost_type = cursor.fetchone()
    
    hours = float(request.form.get('hours') or 0)
    rate = float(request.form.get('rate_per_hour') or cost_type['default_rate'] if cost_type else 0)
    amount = float(request.form.get('amount') or 0)
    
    if hours > 0 and rate > 0:
        amount = hours * rate
    
    cursor.execute('''
        INSERT INTO cost_entries 
        (event_id, cost_type_id, cost_type_name, description, hours, rate_per_hour, amount, 
         volunteer_id, volunteer_name, volunteer_contact, is_income)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        event_id, cost_type_id, cost_type['name'] if cost_type else 'Other',
        request.form.get('description'),
        hours, rate, amount,
        request.form.get('volunteer_id') or None,
        request.form.get('volunteer_name'),
        request.form.get('volunteer_contact'),
        1 if request.form.get('is_income') == 'yes' else 0
    ))
    conn.commit()
    conn.close()
    flash('Cost entry added!', 'success')
    return redirect(url_for('edit_event', event_id=event_id))

@app.route('/costs/<int:cost_id>/delete', methods=['POST'])
def delete_cost_entry(cost_id):
    """Delete cost entry"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT event_id FROM cost_entries WHERE id = ?', (cost_id,))
    result = cursor.fetchone()
    event_id = result['event_id'] if result else None
    cursor.execute('DELETE FROM cost_entries WHERE id = ?', (cost_id,))
    conn.commit()
    conn.close()
    flash('Cost entry deleted', 'success')
    return redirect(url_for('edit_event', event_id=event_id))

@app.route('/events/<int:event_id>/distribution/add', methods=['POST'])
def add_distribution(event_id):
    """Add profit distribution"""
    conn = get_db()
    cursor = conn.cursor()
    
    percentage = float(request.form.get('percentage') or 0)
    
    # Get net profit
    cursor.execute('SELECT net_profit FROM event_profiles WHERE id = ?', (event_id,))
    event = cursor.fetchone()
    amount = (event['net_profit'] * percentage / 100) if event else 0
    
    cursor.execute('''
        INSERT INTO profit_distributions 
        (event_id, target_type, target_name, target_organization_id, percentage, amount, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        event_id,
        request.form.get('target_type'),
        request.form.get('target_name'),
        request.form.get('target_organization_id') or None,
        percentage, amount,
        request.form.get('notes')
    ))
    conn.commit()
    conn.close()
    flash('Distribution added!', 'success')
    return redirect(url_for('edit_event', event_id=event_id))

@app.route('/distribution/<int:dist_id>/delete', methods=['POST'])
def delete_distribution(dist_id):
    """Delete distribution"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT event_id FROM profit_distributions WHERE id = ?', (dist_id,))
    result = cursor.fetchone()
    event_id = result['event_id'] if result else None
    cursor.execute('DELETE FROM profit_distributions WHERE id = ?', (dist_id,))
    conn.commit()
    conn.close()
    flash('Distribution deleted', 'success')
    return redirect(url_for('edit_event', event_id=event_id))

@app.route('/events/<int:event_id>/delete', methods=['POST'])
def delete_event(event_id):
    """Delete event"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM cost_entries WHERE event_id = ?', (event_id,))
    cursor.execute('DELETE FROM profit_distributions WHERE event_id = ?', (event_id,))
    cursor.execute('DELETE FROM event_profiles WHERE id = ?', (event_id,))
    conn.commit()
    conn.close()
    flash('Event deleted', 'success')
    return redirect(url_for('event_list'))


# ========== Volunteers ==========
@app.route('/volunteers')
def volunteer_list():
    """Volunteer list"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT v.*, 
               COALESCE(SUM(ce.hours), 0) as total_hours,
               COALESCE(SUM(CASE WHEN ce.is_income = 1 THEN ce.amount ELSE 0 END), 0) as total_donations,
               COUNT(DISTINCT ce.event_id) as event_count
        FROM volunteers v
        LEFT JOIN cost_entries ce ON v.id = ce.volunteer_id
        GROUP BY v.id
        ORDER BY v.name
    ''')
    volunteers = cursor.fetchall()
    conn.close()
    return render_template('volunteers.html', volunteers=volunteers)

@app.route('/volunteers/add', methods=['POST'])
def add_volunteer():
    """Add volunteer"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO volunteers (name, phone, email, address, notes)
        VALUES (?, ?, ?, ?, ?)
    ''', (
        request.form['name'],
        request.form.get('phone'),
        request.form.get('email'),
        request.form.get('address'),
        request.form.get('notes')
    ))
    conn.commit()
    conn.close()
    flash('Volunteer added successfully!', 'success')
    return redirect(url_for('volunteer_list'))

@app.route('/volunteers/<int:vol_id>')
def view_volunteer(vol_id):
    """View volunteer details"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM volunteers WHERE id = ?', (vol_id,))
    volunteer = cursor.fetchone()
    
    if not volunteer:
        flash('Volunteer not found', 'error')
        return redirect(url_for('volunteer_list'))
    
    cursor.execute('''
        SELECT ce.*, ep.event_name, ep.event_date
        FROM cost_entries ce
        JOIN event_profiles ep ON ce.event_id = ep.id
        WHERE ce.volunteer_id = ?
        ORDER BY ep.event_date DESC
    ''', (vol_id,))
    entries = cursor.fetchall()
    
    cursor.execute('''
        SELECT COALESCE(SUM(hours), 0) as total_hours,
               COALESCE(SUM(CASE WHEN is_income = 1 THEN amount ELSE 0 END), 0) as total_donations
        FROM cost_entries WHERE volunteer_id = ?
    ''', (vol_id,))
    totals = cursor.fetchone()
    
    conn.close()
    return render_template('view_volunteer.html', volunteer=volunteer, entries=entries, totals=totals)

@app.route('/volunteers/<int:vol_id>/delete', methods=['POST'])
def delete_volunteer(vol_id):
    """Delete volunteer"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE cost_entries SET volunteer_id = NULL WHERE volunteer_id = ?', (vol_id,))
    cursor.execute('DELETE FROM volunteers WHERE id = ?', (vol_id,))
    conn.commit()
    conn.close()
    flash('Volunteer deleted', 'success')
    return redirect(url_for('volunteer_list'))

# ========== Organizations ==========
@app.route('/organizations')
def organization_list():
    """Organization list"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM organizations ORDER BY name')
    organizations = cursor.fetchall()
    conn.close()
    return render_template('organizations.html', organizations=organizations)

@app.route('/organizations/add', methods=['POST'])
def add_organization():
    """Add organization"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO organizations (name, type, size, contact_name, contact_phone, contact_email)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        request.form['name'],
        request.form.get('type'),
        request.form.get('size'),
        request.form.get('contact_name'),
        request.form.get('contact_phone'),
        request.form.get('contact_email')
    ))
    conn.commit()
    conn.close()
    flash('Organization added successfully!', 'success')
    return redirect(url_for('organization_list'))

@app.route('/organizations/<int:org_id>/delete', methods=['POST'])
def delete_organization(org_id):
    """Delete organization"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM organizations WHERE id = ?', (org_id,))
    conn.commit()
    conn.close()
    flash('Organization deleted', 'success')
    return redirect(url_for('organization_list'))

# ========== Event Types ==========
@app.route('/event-types')
def event_type_list():
    """Event type list"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM event_types ORDER BY name')
    event_types = cursor.fetchall()
    conn.close()
    return render_template('event_types.html', event_types=event_types)

@app.route('/event-types/add', methods=['POST'])
def add_event_type():
    """Add event type"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO event_types (name, description) VALUES (?, ?)',
                      (request.form['name'], request.form.get('description')))
        conn.commit()
        flash('Event type added successfully!', 'success')
    except:
        flash('This type already exists', 'error')
    conn.close()
    return redirect(url_for('event_type_list'))

@app.route('/event-types/<int:type_id>/delete', methods=['POST'])
def delete_event_type(type_id):
    """Delete event type"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM event_types WHERE id = ?', (type_id,))
    conn.commit()
    conn.close()
    flash('Event type deleted', 'success')
    return redirect(url_for('event_type_list'))

# ========== Cost Types ==========
@app.route('/cost-types')
def cost_type_list():
    """Cost type list"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM cost_types ORDER BY name')
    cost_types = cursor.fetchall()
    conn.close()
    return render_template('cost_types.html', cost_types=cost_types)

@app.route('/cost-types/add', methods=['POST'])
def add_cost_type():
    """Add cost type"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO cost_types (name, default_rate, description) VALUES (?, ?, ?)',
                      (request.form['name'], request.form.get('default_rate') or 0, request.form.get('description')))
        conn.commit()
        flash('Cost type added successfully!', 'success')
    except:
        flash('This type already exists', 'error')
    conn.close()
    return redirect(url_for('cost_type_list'))

@app.route('/cost-types/<int:type_id>/delete', methods=['POST'])
def delete_cost_type(type_id):
    """Delete cost type"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM cost_types WHERE id = ?', (type_id,))
    conn.commit()
    conn.close()
    flash('Cost type deleted', 'success')
    return redirect(url_for('cost_type_list'))


# ========== LENS Categories ==========
@app.route('/lens-categories')
def lens_category_list():
    """LENS category list"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM lens_categories ORDER BY sort_order, name')
    categories = cursor.fetchall()
    
    # Get subcategories for each category
    categories_with_subs = []
    for cat in categories:
        cursor.execute('SELECT * FROM lens_subcategories WHERE category_id = ? ORDER BY sort_order, name', (cat['id'],))
        subcats = cursor.fetchall()
        cat_dict = dict(cat)
        cat_dict['subcategories'] = subcats
        cat_dict['subcat_count'] = len(subcats)
        categories_with_subs.append(cat_dict)
    
    conn.close()
    return render_template('lens_categories.html', categories=categories_with_subs)

@app.route('/lens-categories/add', methods=['POST'])
def add_lens_category():
    """Add LENS category"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO lens_categories (name, description) VALUES (?, ?)',
                      (request.form['name'], request.form.get('description')))
        conn.commit()
        flash('Category added successfully!', 'success')
    except:
        flash('This category already exists', 'error')
    conn.close()
    return redirect(url_for('lens_category_list'))

@app.route('/lens-categories/<int:cat_id>/delete', methods=['POST'])
def delete_lens_category(cat_id):
    """Delete LENS category"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM lens_categories WHERE id = ?', (cat_id,))
    conn.commit()
    conn.close()
    flash('Category deleted', 'success')
    return redirect(url_for('lens_category_list'))

@app.route('/lens-subcategories/add', methods=['POST'])
def add_lens_subcategory():
    """Add LENS subcategory"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO lens_subcategories (category_id, name) VALUES (?, ?)',
                      (request.form['category_id'], request.form['name']))
        conn.commit()
        flash('Subcategory added successfully!', 'success')
    except:
        flash('Error adding subcategory', 'error')
    conn.close()
    return redirect(url_for('lens_category_list'))

@app.route('/lens-subcategories/<int:subcat_id>/delete', methods=['POST'])
def delete_lens_subcategory(subcat_id):
    """Delete LENS subcategory"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM lens_subcategories WHERE id = ?', (subcat_id,))
    conn.commit()
    conn.close()
    flash('Subcategory deleted', 'success')
    return redirect(url_for('lens_category_list'))

@app.route('/lens-demo')
def lens_demo():
    """LENS demo page"""
    return render_template('lens_demo.html')

@app.route('/lens-application-list')
def lens_application_list():
    """LENS application list page"""
    return render_template('lens_application_list.html')

@app.route('/community/<category>')
@app.route('/community/<category>/<subcategory>')
@app.route('/community/<category>/<subcategory>/<detail>')
def community_menu(category, subcategory=None, detail=None):
    """Community engagement menu pages"""
    return render_template('community_page.html', 
                         category=category, 
                         subcategory=subcategory, 
                         detail=detail)


# ========== Reports ==========
@app.route('/reports')
def reports():
    """Reports page"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT quarter FROM event_profiles WHERE quarter IS NOT NULL ORDER BY quarter DESC')
    quarters = [row['quarter'] for row in cursor.fetchall()]
    cursor.execute('SELECT DISTINCT year FROM event_profiles WHERE year IS NOT NULL ORDER BY year DESC')
    years = [row['year'] for row in cursor.fetchall()]
    conn.close()
    return render_template('reports.html', quarters=quarters, years=years)

@app.route('/reports/generate', methods=['POST'])
def generate_report():
    """Generate report"""
    report_type = request.form.get('report_type', 'quarterly')
    quarter = request.form.get('quarter')
    year = request.form.get('year', type=int)
    
    conn = get_db()
    cursor = conn.cursor()
    
    if report_type == 'quarterly' and quarter:
        where_clause = 'ep.quarter = ?'
        params = [quarter]
        title = f"{quarter} Report"
    elif report_type == 'annual' and year:
        where_clause = 'ep.year = ?'
        params = [year]
        title = f"{year} Annual Report"
    else:
        where_clause = '1=1'
        params = []
        title = "All Time Report"
    
    # Get events
    cursor.execute(f'''
        SELECT ep.*, et.name as event_type_name
        FROM event_profiles ep
        LEFT JOIN event_types et ON ep.event_type_id = et.id
        WHERE {where_clause}
        ORDER BY ep.event_date
    ''', params)
    events = cursor.fetchall()
    
    # Statistics
    cursor.execute(f'SELECT COUNT(*) FROM event_profiles ep WHERE {where_clause}', params)
    total_events = cursor.fetchone()[0]
    
    cursor.execute(f'''
        SELECT COALESCE(SUM(ep.total_income), 0), COALESCE(SUM(ep.total_expense), 0), COALESCE(SUM(ep.net_profit), 0)
        FROM event_profiles ep WHERE {where_clause}
    ''', params)
    totals = cursor.fetchone()
    
    cursor.execute(f'SELECT COALESCE(SUM(ep.actual_participants), 0) FROM event_profiles ep WHERE {where_clause}', params)
    total_participants = cursor.fetchone()[0]
    
    # By type
    cursor.execute(f'''
        SELECT et.name, COUNT(*) as count, COALESCE(SUM(ep.actual_participants), 0) as participants,
               COALESCE(SUM(ep.net_profit), 0) as profit
        FROM event_profiles ep
        LEFT JOIN event_types et ON ep.event_type_id = et.id
        WHERE {where_clause}
        GROUP BY et.name
    ''', params)
    by_type = cursor.fetchall()
    
    # Cost breakdown
    cursor.execute(f'''
        SELECT ce.cost_type_name, SUM(ce.amount) as total, SUM(ce.hours) as total_hours
        FROM cost_entries ce
        JOIN event_profiles ep ON ce.event_id = ep.id
        WHERE {where_clause} AND ce.is_income = 0
        GROUP BY ce.cost_type_name
    ''', params)
    cost_breakdown = cursor.fetchall()
    
    conn.close()
    
    return render_template('report_result.html',
                         title=title, events=events,
                         total_events=total_events,
                         total_income=totals[0],
                         total_expense=totals[1],
                         net_profit=totals[2],
                         total_participants=total_participants,
                         by_type=by_type,
                         cost_breakdown=cost_breakdown)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
