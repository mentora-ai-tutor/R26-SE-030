# MENTORA User Service API

Base URL: `http://localhost:3001`

## Public Endpoints

### POST /api/auth/register
Register a new student.

**Request:**
```json
{
  "name": "Kaweesha Nethmina",
  "email": "kaweesha@example.com",
  "password": "password123",
  "country": "Sri Lanka"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Registration successful",
  "data": {
    "student": { ... },
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "expires_in": "7d"
  }
}
```

### POST /api/auth/login
Login with email and password.

**Request:**
```json
{
  "email": "kaweesha@example.com",
  "password": "password123"
}
```

### POST /api/auth/refresh
Refresh access token.

**Request:**
```json
{
  "refresh_token": "eyJ..."
}
```

### POST /api/auth/logout
Logout (requires Authorization header).

---

## Protected Endpoints (Require Bearer Token)

### GET /api/students/me
Get current user profile.

### PUT /api/students/me
Update profile.

**Request:**
```json
{
  "name": "Updated Name",
  "profile": {
    "java_level": "intermediate",
    "country": "Sri Lanka"
  }
}
```

### PUT /api/students/me/password
Change password.

**Request:**
```json
{
  "current_password": "password123",
  "new_password": "newpassword123"
}
```

### PATCH /api/students/me/stats
Update stats (called by LMG Service).

**Request:**
```json
{
  "overall_mastery_score": 75,
  "total_materials_generated_increment": 5
}
```

### GET /api/students/me/summary
Get lightweight summary for dashboard.

---

## Internal Endpoints (Service-to-Service)

**Header Required:** `X-Internal-Key: your_internal_service_secret_key_here`

### POST /internal/auth/verify
Verify JWT token from another service.

**Request:**
```json
{
  "token": "eyJ..."
}
```

### GET /internal/students/:studentId
Get student by student_id.

### PATCH /internal/students/:studentId/stats
Update student stats.

---

## Admin Endpoints (Admin Role Only)

### GET /api/admin/users
Search users with filters.

### GET /api/admin/users/:userId
Get user by ID.

### PATCH /api/admin/users/:userId/deactivate
Deactivate user.

### GET /api/admin/stats
System statistics.

---

## Health Check

### GET /health
```json
{
  "service": "user-service",
  "status": "ok",
  "timestamp": "2026-04-22T..."
}
```