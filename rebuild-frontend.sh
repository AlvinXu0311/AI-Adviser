#!/bin/bash

echo "Stopping containers..."
sudo docker-compose stop frontend backend

echo "Removing old containers..."
sudo docker-compose rm -f frontend backend

echo "Rebuilding images with updated configuration..."
sudo docker-compose build --no-cache frontend backend

echo "Starting containers..."
sudo docker-compose up -d

echo ""
echo "Services rebuilt and restarted successfully!"
echo ""
echo "Frontend: http://localhost:8080"
echo "Backend API: http://localhost:8000/api/status"
echo ""
echo "Checking container status..."
sudo docker-compose ps
echo ""
echo "Waiting 5 seconds for services to stabilize..."
sleep 5
echo ""
echo "Recent logs:"
sudo docker-compose logs --tail=20 frontend backend
