#!/bin/bash

set -eo pipefail

# Configuration
PROFILE="ai-sandbox01"
VERSION="v1.0"
ECR_REPOSITORY_NAME="demo"
AWS_REGION="us-east-1"
ACCOUNT_ID="$(aws --profile $PROFILE sts get-caller-identity --query "Account" --output text)"
IMAGE_NAME="duploctl"
ECR_URI="$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
PLATFORM="linux/arm64"


# Set local container image name using USERNAME
LOCAL_CONTAINER_IMAGE="$ECR_URI/$ECR_REPOSITORY_NAME:$IMAGE_NAME-$VERSION"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting build and ECR push process...${NC}"

# Build the image with platform detection
echo "Building image '$LOCAL_CONTAINER_IMAGE' for platform '$PLATFORM'..."
docker build -t $LOCAL_CONTAINER_IMAGE .

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to build image '$LOCAL_CONTAINER_IMAGE'.${NC}"
    exit 1
fi

echo -e "${GREEN}Image built successfully.${NC}"

# Authenticate with ECR
echo "Authenticating with ECR..."
aws --profile $PROFILE ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_URI

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to authenticate with ECR.${NC}"
    exit 1
fi

echo -e "${GREEN}Authentication successful.${NC}"

# Push the image
echo "Pushing image to ECR..."
docker push $LOCAL_CONTAINER_IMAGE

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Image pushed successfully!${NC}"
    echo "Image URI: $LOCAL_CONTAINER_IMAGE"
else
    echo -e "${RED}Error: Failed to push image.${NC}"
    exit 1
fi