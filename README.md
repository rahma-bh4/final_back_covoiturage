# Django Car Rental Backend

## Overview
A Django backend project for a car rental/co-voiturage application. This project provides a RESTful API for managing car rentals, user authentication, and route tracking.



## Getting Started

### Prerequisites
- Python 3.x
- Git

### Installation

1. Clone the repository
```bash
git clone https://github.com/username/repository-name.git
cd repository-name
```

2. Set up a virtual environment
```bash
# Create virtual environment
python -m venv venv

# Activate the virtual environment
# For Windows:
venv\Scripts\activate.bat
# For PowerShell:
venv\Scripts\Activate
# For macOS/Linux:
source venv/bin/activate
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Apply migrations
```bash
python manage.py migrate
```

5. Run the server
```bash
python manage.py runserver
```

The server will be available at http://127.0.0.1:8000/

## Common Commands

```bash
# Create a superuser to access the admin panel
python manage.py createsuperuser

# Make migrations after model changes
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Run tests
python manage.py test

# Collect static files
python manage.py collectstatic

# Shell access
python manage.py shell
```

## Features
- User authentication
- Car management
- Route/trajectory tracking
- RESTful API

## Technologies
- Django
- Django REST Framework
- SQLite (development)
- Supabase (storage and authentication)

## License
[MIT](https://choosealicense.com/licenses/mit/)

## Contact
Your Name - email@example.com

Project Link: [https://github.com/username/repository-name](https://github.com/username/repository-name)