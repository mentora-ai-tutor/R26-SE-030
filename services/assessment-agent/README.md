# Mentora Assessment & Mastery Evaluation (AME) Agent

The AME Agent is a core microservice of the Mentora platform designed to manage AI-driven assessment sessions and evaluate learner mastery in real-time.

## Project Overview

The Mentora Assessment Agent acts as the bridge between the learner frontend and the agentic n8n workflows. It manages the lifecycle of an assessment session, including:
- Initializing sessions based on learner mastery profiles and identified knowledge gaps.
- Handling answer submissions and routing them to LLM-based evaluation engines.
- Tracking real-time mastery updates and remediation loops.
- Providing detailed analytics on cohort performance and common misconceptions.

## Repository Structure

```
assessment-agent/
├── src/
│   ├── config/             # Database connection logic
│   ├── controllers/        # Request handling logic (AssessmentController)
│   ├── middleware/         # Auth (JWT) and Error Handling
│   ├── routes/             # API Endpoint definitions
│   ├── services/           # Core business logic (Mongo & n8n integrations)
│   └── app.js              # Express application configuration
├── .env.example            # Template for environment variables
├── implementation.md       # Detailed breakdown of algorithms and progress
├── package.json            # Node.js dependencies and scripts
└── server.js               # Entry point for the service
```

## Development Workflow

1. **Local Development**: The project uses `nodemon` for automatic restarts during development.
2. **Integration**: The service communicates with n8n workflows via webhooks. Ensure the n8n instance is accessible.
3. **Database**: MongoDB is used for storing session states, questions, and feedback reports.
4. **Security**: All routes (except health checks) are protected by JWT authentication.

## How to Run or Set Up the Project

### Prerequisites
- Node.js (v18 or higher)
- MongoDB instance
- n8n instance with AME workflows deployed

### Setup Steps

1. **Install Dependencies**:
   ```bash
   npm install
   ```

2. **Configure Environment**:
   Copy `.env.example` to `.env` and fill in the required values:
   ```bash
   PORT=5002
   MONGODB_URI=your_mongodb_connection_string
   JWT_SECRET=your_jwt_secret
   N8N_BASE_URL=your_n8n_instance_url
   N8N_WEBHOOK_PATH=/webhook/your-path
   FRONTEND_URL=your_frontend_url
   ```

3. **Start the Service**:
   - For development:
     ```bash
     npm run dev
     ```
   - For production:
     ```bash
     npm start
     ```

4. **Health Check**:
   Verify the service is running by visiting:
   `http://localhost:3001/health`
