const express = require('express');
const router = express.Router();
const adminController = require('../controllers/admin.controller');
const { validate, validateQuery, userSearchSchema, bulkActionSchema, adminUpdateUserSchema, paginationSchema } = require('../middleware/validate.middleware');
const { protect, requireRole } = require('../middleware/auth.middleware');

// All routes require admin role
router.use(protect);
router.use(requireRole('admin'));

// User Management
router.get('/users', validateQuery(userSearchSchema), adminController.searchUsers);
router.get('/users/:userId', adminController.getUserById);
router.put('/users/:userId', validate(adminUpdateUserSchema), adminController.updateUser);
router.patch('/users/:userId/activate', adminController.activateUser);
router.patch('/users/:userId/deactivate', adminController.deactivateUser);
router.delete('/users/:userId', adminController.deleteUser);
router.patch('/users/:userId/restore', adminController.restoreUser);

// Bulk Actions
router.post('/users/bulk', validate(bulkActionSchema), adminController.bulkAction);

// User History
router.get('/users/:userId/audit-logs', validateQuery(paginationSchema), adminController.getUserAuditHistory);

// System Stats
router.get('/stats', adminController.getSystemStats);

// Export
router.post('/export', adminController.exportUsers);

module.exports = router;
