#!/bin/bash

# Script to run test_dynamic_updates.py with all required services

echo "================================================"
echo "Running Dynamic Updates Test"
echo "================================================"
echo ""
echo "This will start all required services and run the test"
echo ""

# Load environment variables from .env if it exists
if [ -f .env ]; then
    echo "Loading environment variables from .env..."
    export $(cat .env | grep -v '^#' | xargs)
else
    echo "ERROR: .env file not found!"
    echo ""
    echo "Please create .env file with your credentials:"
    echo "  cp .env.example .env"
    echo "  # Edit .env with your credentials"
    echo ""
    echo "Required variables:"
    echo "  QUEUE_TYPE=file|storage"
    echo "  DB_SERVER, DB_DATABASE, DB_USERNAME, DB_PASSWORD"
    echo "  (Plus AZURE_STORAGE_ACCOUNT_NAME if using storage queue)"
    exit 1
fi

# Verify queue configuration
QUEUE_TYPE=${QUEUE_TYPE:-file}
echo "Using queue type: $QUEUE_TYPE"

if [ "$QUEUE_TYPE" == "storage" ]; then
    if [ -z "$AZURE_STORAGE_ACCOUNT_NAME" ]; then
        echo "ERROR: AZURE_STORAGE_ACCOUNT_NAME not set for storage queue!"
        exit 1
    fi
    echo "  Storage account: $AZURE_STORAGE_ACCOUNT_NAME"
    echo "  Queue name: ${AZURE_STORAGE_QUEUE_NAME:-crawler-jobs}"
elif [ "$QUEUE_TYPE" == "file" ]; then
    echo "  Queue directory: ${QUEUE_DIR:-queue}"
else
    echo "ERROR: Unknown QUEUE_TYPE: $QUEUE_TYPE"
    echo "Supported types: file, storage"
    exit 1
fi
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "Stopping all services..."

    # Kill all background processes
    jobs -p | xargs -I {} kill {} 2>/dev/null

    # Give processes time to shut down
    sleep 2

    # Force kill if still running
    jobs -p | xargs -I {} kill -9 {} 2>/dev/null

    echo "All services stopped"
}

# Set trap to cleanup on exit
trap cleanup EXIT INT TERM

# Verify test data exists
if [ ! -d "data/backcountry_com" ]; then
    echo "ERROR: Test data not found in data/backcountry_com"
    echo "Please ensure test data is available"
    exit 1
fi

# Kill any existing processes on required ports
echo "Checking for existing processes on required ports..."
for port in 8000 5001; do
    PID=$(lsof -ti :$port 2>/dev/null)
    if [ ! -z "$PID" ]; then
        echo "  Killing process on port $port (PID: $PID)"
        kill -9 $PID 2>/dev/null
        sleep 1
    fi
done

# Clear queue and database
echo "Clearing queue and database..."
python3 -c "
import sys
sys.path.insert(0, 'code/core')
import config
import os

queue_type = os.getenv('QUEUE_TYPE', 'file').lower()
print(f'Queue type: {queue_type}')

if queue_type == 'file':
    import shutil
    queue_dir = os.getenv('QUEUE_DIR', 'queue')
    if os.path.exists(queue_dir):
        shutil.rmtree(queue_dir)
        os.makedirs(queue_dir)
        print(f'Cleared file queue directory: {queue_dir}')
    else:
        os.makedirs(queue_dir)
        print(f'Created file queue directory: {queue_dir}')

elif queue_type == 'storage':
    try:
        from azure.storage.queue import QueueServiceClient
        from azure.identity import DefaultAzureCredential

        storage_account = os.getenv('AZURE_STORAGE_ACCOUNT_NAME')
        queue_name = os.getenv('AZURE_STORAGE_QUEUE_NAME', 'crawler-jobs')

        account_url = f'https://{storage_account}.queue.core.windows.net'
        credential = DefaultAzureCredential()
        service_client = QueueServiceClient(account_url=account_url, credential=credential)
        queue_client = service_client.get_queue_client(queue_name)

        queue_client.clear_messages()
        print(f'Cleared storage queue: {queue_name}')
    except Exception as e:
        print(f'Warning: Could not clear storage queue: {e}')

# Clear database
print('Clearing database...')
import db
conn = db.get_connection()
db.clear_all_data(conn)
conn.close()
print('Database cleared')
"

echo ""
echo "Starting services..."
echo ""

# Start test data server in background
echo "Starting test data server on port 8000..."
python3 test_data_server.py &
DATA_SERVER_PID=$!
sleep 2

# Start master service (API + scheduler) in background
echo "Starting master service (API + scheduler) on port 5001..."
python3 code/core/api.py &
MASTER_PID=$!
sleep 3

# Start worker in background
echo "Starting worker service..."
python3 code/core/worker.py &
WORKER_PID=$!
sleep 2

echo ""
echo "All services started!"
echo "  Test data server: PID $DATA_SERVER_PID"
echo "  Master service: PID $MASTER_PID"
echo "  Worker service: PID $WORKER_PID"
echo ""

# Wait a bit for services to fully initialize
echo "Waiting for services to initialize..."
sleep 5

# Check if API is responding
echo "Checking API health..."
curl -s http://localhost:5001/api/status > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "ERROR: API is not responding!"
    echo "Check the logs above for errors"
    exit 1
fi

echo ""
echo "================================================"
echo "Running test..."
echo "================================================"
echo ""

# Run the test
python3 test_dynamic_updates.py

# Test exit code
TEST_RESULT=$?

if [ $TEST_RESULT -eq 0 ]; then
    echo ""
    echo "✅ Test completed successfully!"
else
    echo ""
    echo "❌ Test failed!"
fi

echo ""
echo "Services will be stopped automatically..."
exit $TEST_RESULT
