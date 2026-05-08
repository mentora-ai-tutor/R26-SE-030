# Mentora Full System Setup Guide

This guide explains how to run the full Mentora system after pulling the relevant frontend and backend branches.

## Repositories And Branches

Pull or clone both repositories into the same parent folder.

Expected branches:

```text
mentora-frontend  -> feature/kalana
R26-SE-030        -> knowledge-analysis/kalana
```

Recommended folder structure:

```text
Mentora/
  docker-compose.yml
  mentora-frontend/
  R26-SE-030/
```

The `docker-compose.yml` file must be in the parent `Mentora/` folder, beside both repositories.

## Required Tools

For the Docker setup:

```text
Docker Desktop
Git
MongoDB Compass, optional but useful for checking DB records
```

For the manual no-Docker setup:

```text
Node.js 20+
npm
Python 3.11+
MongoDB local or MongoDB Atlas
```

## Required Private Files

Do not commit these files to Git.

```text
R26-SE-030/services/user service/.env

add these -

# Server Configuration
PORT=3001
NODE_ENV=development
SERVICE_NAME=user-service

# Database
MONGODB_URI=mongodb://localhost:27017/mentora_users

# JWT Configuration
JWT_SECRET=your-super-secret-jwt-key-minimum-32-characters
JWT_EXPIRES_IN=1h
JWT_REFRESH_SECRET=your-super-secret-refresh-key-different-from-jwt
JWT_REFRESH_EXPIRES_IN=7d

# Security
BCRYPT_SALT_ROUNDS=12
INTERNAL_SERVICE_KEY=your-internal-service-api-key

# CORS
CORS_ORIGIN=http://localhost:3000,http://localhost:5173

# Optional Features
ENABLE_EMAIL_VERIFICATION=false
ENABLE_ACCOUNT_LOCKOUT=true
ENABLE_AUDIT_LOGGING=true

# GitHub OAuth
GH_CLIENT_ID=0v23liAAsRI9g14OHHcK

GH_CLIENT_SECRET=56d3456956a516e2002aab53764ca0ad4da23a75
GH_OAUTH_SCOPE=repo
GH_OAUTH_CALLBACK_URL=http://localhost:3001/api/github/oauth/callback

# Optional Redis (for caching & rate limiting)
# REDIS_URL=redis://localhost:6379




R26-SE-030/services/knowledge-analysis/secrets/gcp-sa.json


GOOGLE_APPLICATION_CREDENTIALS=/Users/idea8/Documents/SLIIT Work/R26-SE-030/services/knowledge-analysis/secrets/gcp-sa.json
GCP_PROJECT=chapmanvoice
GCP_LOCATION=us-central1
LLM_PROVIDER=gemini
GEMINI_MODEL_PRIMARY=gemini-3.1-pro-preview
GEMINI_MODEL_TOOLS=gemini-3.1-pro-preview-customtools
GEMINI_MODEL_GA=gemini-2.5-pro
GEMINI_MODEL_FAST=gemini-2.5-flash



mentora-frontend/.env.local
```

The GCP JSON key is only required if the Gemini/Vertex AI knowledge review flow must work.

## Setup With Docker

Use this path when Docker Desktop is installed.

### 1. Pull Both Branches

From the parent folder:

```bash
git clone -b feature/kalana <frontend-repo-url> mentora-frontend
git clone -b knowledge-analysis/kalana <backend-repo-url> R26-SE-030
```

If the repositories are already cloned:

```bash
cd mentora-frontend
git checkout feature/kalana
git pull

cd ../R26-SE-030
git checkout knowledge-analysis/kalana
git pull
```

Return to the parent folder:

```bash
cd ..
```

### 2. Create User Service Environment File

From the parent `Mentora/` folder:

```bash
cp "R26-SE-030/services/user service/.env.example" "R26-SE-030/services/user service/.env"
```

Open:

```text
R26-SE-030/services/user service/.env
```

Make sure these values are not empty:

```env
GH_CLIENT_ID=dummy-or-real-github-client-id
GH_CLIENT_SECRET=dummy-or-real-github-client-secret
GH_OAUTH_SCOPE=repo
GH_OAUTH_CALLBACK_URL=http://localhost:3001/api/github/oauth/callback
```

Use real GitHub OAuth credentials if GitHub account linking and repository review must work. For a basic signup/login demo, dummy non-empty values are enough.

### 3. Add GCP JSON Key

Create the secrets folder:

```bash
mkdir -p "R26-SE-030/services/knowledge-analysis/secrets"
```

Place the service account JSON key here:

```text
R26-SE-030/services/knowledge-analysis/secrets/gcp-sa.json
```

Do not rename it unless `docker-compose.yml` is also updated.

### 4. Start The Full System

From the parent `Mentora/` folder:

```bash
docker compose up --build
```

This starts:

```text
MongoDB             -> localhost:27017
User service        -> http://localhost:3001
Knowledge service   -> http://localhost:5007
Frontend            -> http://localhost:3002
```

### 5. Open The Application

Open the frontend in the browser:

```text
http://localhost:3002
```

Health checks:

```text
User service:
http://localhost:3001/health

Knowledge service:
http://localhost:5007/health

Knowledge API docs:
http://localhost:5007/docs
```

### 6. Check The Database

Open MongoDB Compass and connect to:

```text
mongodb://localhost:27017
```

Expected databases:

```text
mentora_users
knowledge_analysis
```

After a user signs up or logs in, user records should appear in `mentora_users`.

### 7. Demo Flow

Use this order to verify the full system:

```text
1. Open http://localhost:3002
2. Sign up as a new student
3. Login
4. Open the dashboard
5. Check MongoDB Compass for the created user
6. Test GitHub linking only if real GitHub OAuth credentials are configured
7. Test repository review only if GitHub OAuth and the GCP JSON key are configured
```

### 8. Stop The System

Stop containers:

```bash
docker compose down
```

Stop containers and delete MongoDB volume data:

```bash
docker compose down -v
```

Use `down -v` only when you intentionally want to clear local database data.

## Manual Setup Without Docker

Use this path only when Docker is not available.

Run the services in this exact order:

```text
1. MongoDB
2. User service
3. Knowledge service
4. Frontend
```

### 1. Start MongoDB

Local MongoDB URI:

```text
mongodb://localhost:27017
```

If using MongoDB Atlas, use the Atlas connection string instead.

### 2. Run User Service

Create:

```text
R26-SE-030/services/user service/.env
```

Use this local configuration:

```env
PORT=3001
NODE_ENV=development
SERVICE_NAME=user-service
MONGODB_URI=mongodb://localhost:27017/mentora_users

JWT_SECRET=change-this-dev-jwt-secret-minimum-32-chars
JWT_EXPIRES_IN=1h
JWT_REFRESH_SECRET=change-this-dev-refresh-secret-minimum-32-chars
JWT_REFRESH_EXPIRES_IN=7d
INTERNAL_SERVICE_KEY=change-this-internal-service-key

CORS_ORIGIN=http://localhost:3000
BCRYPT_SALT_ROUNDS=12
ENABLE_EMAIL_VERIFICATION=false
ENABLE_ACCOUNT_LOCKOUT=true
ENABLE_AUDIT_LOGGING=true

GH_CLIENT_ID=dummy-or-real-github-client-id
GH_CLIENT_SECRET=dummy-or-real-github-client-secret
GH_OAUTH_SCOPE=repo
GH_OAUTH_CALLBACK_URL=http://localhost:3001/api/github/oauth/callback
FRONTEND_ORIGIN=http://localhost:3000
```

Run:

```bash
cd "R26-SE-030/services/user service"
npm install
npm run dev
```

Check:

```text
http://localhost:3001/health
```

### 3. Run Knowledge Service

Create:

```text
R26-SE-030/services/knowledge-analysis/.env
```

Use this local configuration:

```env
APP_NAME=KAA - Knowledge Analysis Agent
APP_VERSION=1.0.0
CORS_ORIGINS=http://localhost:3000

MONGODB_URL=mongodb://localhost:27017
MONGODB_DB=knowledge_analysis

USER_SERVICE_INTERNAL_URL=http://localhost:3001
INTERNAL_SERVICE_KEY=change-this-internal-service-key

LLM_PROVIDER=gemini
GCP_PROJECT=chapmanvoice
GCP_LOCATION=us-central1
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/R26-SE-030/services/knowledge-analysis/secrets/gcp-sa.json

OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3
GITHUB_PAT=
```

Place the GCP key here:

```text
R26-SE-030/services/knowledge-analysis/secrets/gcp-sa.json
```

Run:

```bash
cd R26-SE-030/services/knowledge-analysis
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 5007
```

Check:

```text
http://localhost:5007/health
http://localhost:5007/docs
```

### 4. Run Frontend

Create:

```text
mentora-frontend/.env.local
```

Use:

```env
NEXT_PUBLIC_API_URL=http://localhost:3001
NEXT_PUBLIC_KNOWLEDGE_API_URL=http://localhost:5007
```

Run:

```bash
cd mentora-frontend
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

## Common Problems

### User Service Stops Immediately

Check that these values are present and not empty in `R26-SE-030/services/user service/.env`:

```text
GH_CLIENT_ID
GH_CLIENT_SECRET
GH_OAUTH_SCOPE
GH_OAUTH_CALLBACK_URL
```

The user service treats them as required environment variables.

### Frontend Shows Network Error

Check that the user service is running:

```text
http://localhost:3001/health
```

For Docker, frontend should use:

```text
http://localhost:3002
```

For manual setup, frontend should use:

```text
http://localhost:3000
```

### Knowledge Review Fails

Check:

```text
1. GCP JSON key exists
2. GOOGLE_APPLICATION_CREDENTIALS points to the correct file
3. The service account has the required Vertex AI access
4. GitHub OAuth is configured if repository review is being tested
```

### MongoDB Has No Data

First create a user from the browser signup flow, then check:

```text
mongodb://localhost:27017
```

Expected database:

```text
mentora_users
```

## What To Commit

Commit setup documentation and safe templates only:

```text
docs/FULL_SYSTEM_SETUP.md
.env.example files
.env.local.example files
```

Do not commit:

```text
.env
.env.local
gcp-sa.json
node_modules/
.next/
.venv/
__pycache__/
```
