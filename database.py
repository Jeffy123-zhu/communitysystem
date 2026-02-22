import sqlite3
import os
from datetime import datetime

# database location - use /data for cloud, otherwise local
if os.path.exists('/data'):
    DATABASE = '/data/community.db'
else:
    DATABASE = 'community.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    # create tables if they don't exist
    conn = get_db()
    cursor = conn.cursor()
    
    # event types table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS event_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT
        )
    ''')
    
    # Table: organizations
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS organizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT,
            size TEXT,
            contact_name TEXT,
            contact_phone TEXT,
            contact_email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Table: volunteers (individual donation accounts)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS volunteers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            address TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Table: cost_types (labor, facility, in-kind, donations, food, supply, other)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cost_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            default_rate REAL DEFAULT 0,
            description TEXT
        )
    ''')
    
    # Table: event_profiles
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS event_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_name TEXT NOT NULL,
            event_date DATE NOT NULL,
            event_type_id INTEGER,
            lens_category_id INTEGER,
            lens_subcategory_id INTEGER,
            location TEXT,
            description TEXT,
            organization_id INTEGER,
            coordinator_name TEXT,
            coordinator_phone TEXT,
            coordinator_email TEXT,
            expected_participants INTEGER DEFAULT 0,
            actual_participants INTEGER DEFAULT 0,
            total_income REAL DEFAULT 0,
            total_expense REAL DEFAULT 0,
            net_profit REAL DEFAULT 0,
            notes TEXT,
            status TEXT DEFAULT 'In Progress',
            entry_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            quarter TEXT,
            year INTEGER,
            FOREIGN KEY (event_type_id) REFERENCES event_types(id),
            FOREIGN KEY (organization_id) REFERENCES organizations(id),
            FOREIGN KEY (lens_category_id) REFERENCES lens_categories(id),
            FOREIGN KEY (lens_subcategory_id) REFERENCES lens_subcategories(id)
        )
    ''')
    
    # Table: cost_entries (each cost item is a single record)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cost_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            cost_type_id INTEGER,
            cost_type_name TEXT,
            description TEXT,
            hours REAL DEFAULT 0,
            rate_per_hour REAL DEFAULT 0,
            amount REAL DEFAULT 0,
            volunteer_id INTEGER,
            volunteer_name TEXT,
            volunteer_contact TEXT,
            is_income INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (event_id) REFERENCES event_profiles(id) ON DELETE CASCADE,
            FOREIGN KEY (cost_type_id) REFERENCES cost_types(id),
            FOREIGN KEY (volunteer_id) REFERENCES volunteers(id)
        )
    ''')
    
    # Table: profit_distributions (where profits go)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS profit_distributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            target_type TEXT NOT NULL,
            target_name TEXT,
            target_organization_id INTEGER,
            percentage REAL DEFAULT 0,
            amount REAL DEFAULT 0,
            notes TEXT,
            FOREIGN KEY (event_id) REFERENCES event_profiles(id) ON DELETE CASCADE,
            FOREIGN KEY (target_organization_id) REFERENCES organizations(id)
        )
    ''')
    
    # Table: lens_categories (main categories)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lens_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            sort_order INTEGER DEFAULT 0
        )
    ''')
    
    # Table: lens_subcategories (subcategories under main categories)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lens_subcategories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            sort_order INTEGER DEFAULT 0,
            FOREIGN KEY (category_id) REFERENCES lens_categories(id) ON DELETE CASCADE
        )
    ''')
    
    # Insert default event types
    default_types = [('School', 'School related activities'), ('Church', 'Church related activities'), 
                     ('Community', 'Community related activities'), ('Other', 'Other activities')]
    for name, desc in default_types:
        cursor.execute('INSERT OR IGNORE INTO event_types (name, description) VALUES (?, ?)', (name, desc))
    
    # Insert default cost types with rates
    default_costs = [
        ('Labor', 15.00, 'Volunteer labor hours'),
        ('Facility', 25.00, 'Facility rental/usage'),
        ('In-Kind', 0, 'In-kind donations'),
        ('Donations', 0, 'Cash donations received'),
        ('Food', 0, 'Food costs'),
        ('Supply', 0, 'Supply costs'),
        ('Other', 0, 'Other costs')
    ]
    for name, rate, desc in default_costs:
        cursor.execute('INSERT OR IGNORE INTO cost_types (name, default_rate, description) VALUES (?, ?, ?)', (name, rate, desc))
    
    # Insert LENS categories and subcategories
    lens_data = [
        ('CALENDAR', ['Event', 'Event - Heartness', 'School']),
        ('ACCOUNTABILITY', ['Observation Budget', 'Issues - Community', 'Education', 'Land Use / Development', 'Environment', 'Judiciary', 'Safety', 'Taxes', 'Public Policy']),
        ('COMMUNICATIONS', ['Application - Medical', 'Application - Dental', 'Effectiveness', 'Lens Stats', 'Content']),
        ('FELLOWSHIP', ['Advocacy', 'Announcements', 'Entertainment', 'Events', 'Recognition', 'Statistics']),
        ('SERVICE', ['Community Needs (Religion)', 'Social Programs', 'Statistics', 'Celebrations', 'Lectures', 'Meetings', 'Sports hosting fishing too', 'Calendar']),
        ('LEADERSHIP', ['Contacts', 'Neighborhoods', 'Education', 'Licensing', 'Permits', 'Zoning', 'Landscaping', 'AI', 'Broadband', 'Elections / neighborhood', 'Public Engagement', 'Regional Policies / Initiatives']),
        ('VIABILITY', ['Qshere', 'e-Commerce', 'Real Estate', 'Employment', 'Apprenticeships', 'Internships', 'Gig Work', 'History', 'Workforce', 'Wearing / Animal Audit', 'Community Coordinating System', 'Organizational Chart'])
    ]
    
    for category_name, subcategories in lens_data:
        cursor.execute('INSERT OR IGNORE INTO lens_categories (name) VALUES (?)', (category_name,))
        cursor.execute('SELECT id FROM lens_categories WHERE name = ?', (category_name,))
        cat_result = cursor.fetchone()
        if cat_result:
            cat_id = cat_result[0]
            for subcat in subcategories:
                # Check if subcategory already exists for this category
                cursor.execute('SELECT id FROM lens_subcategories WHERE category_id = ? AND name = ?', 
                             (cat_id, subcat))
                if not cursor.fetchone():
                    cursor.execute('INSERT INTO lens_subcategories (category_id, name) VALUES (?, ?)', 
                                 (cat_id, subcat))
    
    conn.commit()
    conn.close()

def calculate_quarter(date_str):
    """Calculate quarter from date"""
    date = datetime.strptime(date_str, '%Y-%m-%d')
    quarter = (date.month - 1) // 3 + 1
    return f"{date.year}Q{quarter}", date.year, quarter

if __name__ == '__main__':
    init_db()
    print("Database initialized!")
