const express = require('express');
const router = express.Router();
const authController = require('../controllers/auth.controller');
const {
  validate,
  registerSchema,
  loginSchema,
  refreshTokenSchema,
  forgotPasswordSchema,
  resetPasswordSchema,
  verifyEmailSchema,
  resendVerificationSchema,
} = require('../middleware/validate.middleware');
const { protect } = require('../middleware/auth.middleware');

router.post('/register', validate(registerSchema), authController.register);

router.post('/login', validate(loginSchema), authController.login);

router.post('/refresh', validate(refreshTokenSchema), authController.refresh);

router.post('/logout', protect, authController.logout);

// Password Reset
router.post('/forgot-password', validate(forgotPasswordSchema), authController.forgotPassword);

router.post('/reset-password', validate(resetPasswordSchema), authController.resetPassword);

// Email Verification
router.post('/verify-email', validate(verifyEmailSchema), authController.verifyEmail);

router.post('/resend-verification', validate(resendVerificationSchema), authController.resendVerification);

// Session Management
router.get('/sessions', protect, authController.getSessions);

router.delete('/sessions/:sessionId', protect, authController.revokeSession);

module.exports = router;
