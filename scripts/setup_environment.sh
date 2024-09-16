#!/bin/bash

# Check and install required dependencies
echo "Checking and installing required dependencies..."
if ! command -v python3 &> /dev/null; then
    echo "Python3 not found. Installing..."
    sudo apt-get update
    sudo apt-get install -y python3
fi

if ! command -v node &> /dev/null; then
    echo "Node.js not found. Installing..."
    curl -sL https://deb.nodesource.com/setup_14.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi

if ! command -v npm &> /dev/null; then
    echo "npm not found. Installing..."
    sudo apt-get install -y npm
fi

# Set up virtual environment for Python
echo "Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies from requirements.txt
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Set up Node.js environment and install npm packages
echo "Setting up Node.js environment and installing npm packages..."
npm install

# Configure environment variables
echo "Configuring environment variables..."
cp .env.example .env
# HUMAN ASSISTANCE NEEDED
# Please update the .env file with appropriate values for your local environment

# Initialize local development database
echo "Initializing local development database..."
# HUMAN ASSISTANCE NEEDED
# Please provide the specific command to initialize your database
# For example, if using Django:
# python manage.py migrate

echo "Environment setup complete!"