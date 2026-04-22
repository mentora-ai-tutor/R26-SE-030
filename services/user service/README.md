# MENTORA User Service

A comprehensive authentication and user management microservice with advanced security features, audit logging, and admin capabilities.

## Features

### Core Features
- JWT-based authentication with refresh tokens
- Protected routes with Bearer token middleware
- Role-based access control (student, instructor, admin)
- Rate limiting on authentication endpoints

### Security Features
- **Account Lockout**: Automatically locks accounts after 5 failed login attempts (15-minute lockout)
- **Password Reset**: Secure token-based password reset via email (1-hour expiry)
- **Email Verification**: Verify email addresses before activation (24-hour token expiry)
- **Session Management**: Multi-device session tracking with device info
- **Audit Logging**: Comprehensive logging of all authentication events
- **Soft Delete**: Users are marked as deleted rather than hard-deleted

### Admin Features
- User search with filters (role, status, java_level)
- User management (activate/deactivate/delete/restore)
- Bulk actions on multiple users
- Export users (JSON/CSV)
- System statistics and analytics
- Audit history viewing

### Analytics & Monitoring
- Request metrics (response times, error rates)
- Health check endpoint with detailed status
- Activity logging (login, logout, profile updates)
- Daily/weekly/monthly user statistics

## API Endpoints

### Health & Metrics
| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/health` | Service health check | No |
| GET | `/metrics` | Request metrics | No |
| GET | `/analytics` | Usage analytics | Yes (Admin) |

### Authentication
| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/api/auth/register` | Register new user | No |
| POST | `/api/auth/login` | Login | No |
| POST | `/api/auth/refresh` | Refresh access token | No |
| POST | `/api/auth/logout` | Logout | Yes |
| POST | `/api/auth/forgot-password` | Request password reset | No |
| POST | `/api/auth/reset-password` | Reset password with token | No |
| POST | `/api/auth/verify-email` | Verify email | No |
| POST | `/api/auth/resend-verification` | Resend verification email | No |
| GET | `/api/auth/sessions` | List active sessions | Yes |
| DELETE | `/api/auth/sessions/:sessionId` | Revoke specific session | Yes |

### Student Profile (Protected)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/students/me` | Get full profile |
| PUT | `/api/students/me` | Update profile |
| PUT | `/api/students/me/password` | Change password |
| PATCH | `/api/students/me/stats` | Update stats |
| GET | `/api/students/me/summary` | Get summary |
| GET | `/api/students/me/preferences` | Get preferences |
| PUT | `/api/students/me/preferences` | Update preferences |
| DELETE | `/api/students/me` | Delete account |

### Admin Endpoints (Admin only)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/admin/users` | Search/filter users |
| GET | `/api/admin/users/:userId` | Get user details |
| PUT | `/api/admin/users/:userId` | Update user |
| PATCH | `/api/admin/users/:userId/activate` | Activate user |
| PATCH | `/api/admin/users/:userId/deactivate` | Deactivate user |
| DELETE | `/api/admin/users/:userId` | Delete user |
| PATCH | `/api/admin/users/:userId/restore` | Restore deleted user |
| POST | `/api/admin/users/bulk` | Bulk actions |
| GET | `/api/admin/users/:userId/audit-logs` | User audit history |
| GET | `/api/admin/stats` | System statistics |
| POST | `/api/admin/export` | Export users |

### Internal Service
| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/internal/auth/verify` | Verify JWT token | Internal Key |
| GET | `/internal/students/:studentId` | Get student by ID | Internal Key |
| PATCH | `/internal/students/:studentId/stats` | Update stats | Internal Key |

## Environment Variables

```bash
# Required
PORT=3001
NODE_ENV=development
SERVICE_NAME=user-service
MONGODB_URI=mongodb://localhost:27017/mentora_users
JWT_SECRET=your-super-secret-jwt-key-minimum-32-characters
JWT_EXPIRES_IN=1h
JWT_REFRESH_SECRET=your-super-secret-refresh-key
JWT_REFRESH_EXPIRES_IN=7d
INTERNAL_SERVICE_KEY=your-internal-service-api-key
CORS_ORIGIN=http://localhost:3000

# Optional
BCRYPT_SALT_ROUNDS=12
ENABLE_EMAIL_VERIFICATION=false
ENABLE_ACCOUNT_LOCKOUT=true
ENABLE_AUDIT_LOGGING=true
REDIS_URL=redis://localhost:6379
```

## Installation

```bash
npm install
```

## Running

```bash
# Development
npm run dev

# Production
npm start
```

## Student ID Format

Student IDs are auto-generated in sequential format:
- Format: `STD-XXXXX` (e.g., `STD-00001`, `STD-00042`)
- Sequential increment from last registered student
- 5-digit padding with leading zeros

## Rate Limits

- Authentication endpoints: 20 requests per 15 minutes
- API endpoints: 100 requests per 15 minutes
- Health/metrics: No rate limit

## Security Features

### Account Lockout
- After 5 failed login attempts, account is locked for 15 minutes
- Failed attempts reset on successful login
- Admin can manually unlock accounts

### Password Reset
- Token expires after 1 hour
- Previous tokens are invalidated when new one is requested
- All sessions revoked after password reset

### Session Management
- Sessions tracked per device
- Sessions expire after 7 days of inactivity
- Users can revoke specific sessions
- "Logout all devices" functionality available

### Audit Logging
Tracks:
- Login/Logout events
- Password changes
- Email verifications
- Profile updates
- Admin actions
- Failed authentication attempts

## Testing

See the Postman collection at the project root for complete API testing.
