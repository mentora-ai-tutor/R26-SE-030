const { Student, AuditLog, UserSession } = require('../models');
const { sendSuccess, sendError } = require('../utils/apiResponse');
const logger = require('../utils/logger');
const { logAuth } = require('../utils/auditLogger');

// Search Users
const searchUsers = async (req, res, next) => {
  try {
    const {
      query,
      role,
      is_active,
      is_verified,
      java_level,
      sort_by = 'createdAt',
      sort_order = 'desc',
      page = 1,
      limit = 20,
    } = req.query;

    const filter = { is_deleted: false };

    // Text search
    if (query) {
      filter.$or = [
        { name: { $regex: query, $options: 'i' } },
        { email: { $regex: query, $options: 'i' } },
        { student_id: { $regex: query, $options: 'i' } },
      ];
    }

    // Filters
    if (role) filter.role = role;
    if (is_active !== undefined) filter.is_active = is_active === 'true';
    if (is_verified !== undefined) filter.is_verified = is_verified === 'true';
    if (java_level) filter['profile.java_level'] = java_level;

    // Sorting
    const sort = {};
    sort[sort_by] = sort_order === 'asc' ? 1 : -1;

    // Pagination
    const skip = (parseInt(page) - 1) * parseInt(limit);

    // Execute query
    const [users, total] = await Promise.all([
      Student.find(filter)
        .sort(sort)
        .skip(skip)
        .limit(parseInt(limit))
        .select('-password -refresh_token')
        .lean(),
      Student.countDocuments(filter),
    ]);

    return sendSuccess(res, {
      users,
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total,
        pages: Math.ceil(total / parseInt(limit)),
      },
    });
  } catch (error) {
    next(error);
  }
};

// Get User by ID
const getUserById = async (req, res, next) => {
  try {
    const { userId } = req.params;

    const user = await Student.findOne({ _id: userId, is_deleted: false })
      .select('-password -refresh_token');

    if (!user) {
      return sendError(res, 'User not found', 404, 'USER_NOT_FOUND');
    }

    // Get recent audit logs
    const auditLogs = await AuditLog.find({ student: userId })
      .sort({ createdAt: -1 })
      .limit(20)
      .lean();

    // Get active sessions
    const sessions = await UserSession.find({
      student: userId,
      is_active: true,
      expires_at: { $gt: Date.now() },
    })
      .select('-refresh_token -session_token')
      .lean();

    return sendSuccess(res, {
      user: user.toSafeObject(),
      audit_logs: auditLogs,
      active_sessions: sessions.length,
      sessions: sessions,
    });
  } catch (error) {
    next(error);
  }
};

// Update User
const updateUser = async (req, res, next) => {
  try {
    const { userId } = req.params;
    const updateData = req.body;
    const adminId = req.student._id;

    const user = await Student.findOne({ _id: userId, is_deleted: false });

    if (!user) {
      return sendError(res, 'User not found', 404, 'USER_NOT_FOUND');
    }

    // Build update object
    const updates = {};
    if (updateData.name) updates.name = updateData.name;
    if (updateData.email) updates.email = updateData.email.toLowerCase();
    if (updateData.role) updates.role = updateData.role;
    if (updateData.is_active !== undefined) updates.is_active = updateData.is_active;
    if (updateData.is_verified !== undefined) updates.is_verified = updateData.is_verified;
    if (updateData.profile?.java_level) {
      updates['profile.java_level'] = updateData.profile.java_level;
    }

    const updatedUser = await Student.findByIdAndUpdate(
      userId,
      { $set: updates },
      { new: true, runValidators: true }
    );

    await logAuth.adminAction(userId, req, req.requestId, 'User updated by admin', {
      updated_by: adminId,
      changes: Object.keys(updates),
    });

    logger.info(`Admin ${adminId} updated user ${userId}`);

    return sendSuccess(res, updatedUser.toSafeObject(), 'User updated successfully');
  } catch (error) {
    next(error);
  }
};

// Activate User
const activateUser = async (req, res, next) => {
  try {
    const { userId } = req.params;
    const adminId = req.student._id;

    const user = await Student.findOne({ _id: userId, is_deleted: false });

    if (!user) {
      return sendError(res, 'User not found', 404, 'USER_NOT_FOUND');
    }

    if (user.is_active) {
      return sendSuccess(res, null, 'User is already active');
    }

    user.is_active = true;
    await user.save();

    await logAuth.accountUnlocked(userId, req, req.requestId);
    await logAuth.adminAction(userId, req, req.requestId, 'User activated', { by: adminId });

    logger.info(`Admin ${adminId} activated user ${userId}`);

    return sendSuccess(res, null, 'User activated successfully');
  } catch (error) {
    next(error);
  }
};

// Deactivate User
const deactivateUser = async (req, res, next) => {
  try {
    const { userId } = req.params;
    const { reason } = req.body;
    const adminId = req.student._id;

    const user = await Student.findOne({ _id: userId, is_deleted: false });

    if (!user) {
      return sendError(res, 'User not found', 404, 'USER_NOT_FOUND');
    }

    if (user._id.toString() === adminId.toString()) {
      return sendError(res, 'Cannot deactivate your own account', 400, 'INVALID_ACTION');
    }

    if (!user.is_active) {
      return sendSuccess(res, null, 'User is already inactive');
    }

    user.is_active = false;
    await user.save();

    // Revoke all sessions
    await UserSession.updateMany(
      { student: userId, is_active: true },
      { $set: { is_active: false, is_revoked: true, revoked_at: new Date(), revoked_reason: 'account_deactivated' } }
    );

    await logAuth.adminAction(userId, req, req.requestId, 'User deactivated', { by: adminId, reason });

    logger.info(`Admin ${adminId} deactivated user ${userId}`);

    return sendSuccess(res, null, 'User deactivated successfully');
  } catch (error) {
    next(error);
  }
};

// Delete User (Soft Delete)
const deleteUser = async (req, res, next) => {
  try {
    const { userId } = req.params;
    const { permanent } = req.body;
    const adminId = req.student._id;

    const user = await Student.findOne({ _id: userId });

    if (!user) {
      return sendError(res, 'User not found', 404, 'USER_NOT_FOUND');
    }

    if (user._id.toString() === adminId.toString()) {
      return sendError(res, 'Cannot delete your own account', 400, 'INVALID_ACTION');
    }

    if (permanent) {
      // Hard delete - remove from database
      await Student.findByIdAndDelete(userId);
      await logAuth.adminAction(null, req, req.requestId, 'User permanently deleted', { user_id: userId, by: adminId });
      logger.info(`Admin ${adminId} permanently deleted user ${userId}`);
    } else {
      // Soft delete
      await user.softDelete(adminId);

      // Revoke all sessions
      await UserSession.updateMany(
        { student: userId, is_active: true },
        { $set: { is_active: false, is_revoked: true, revoked_at: new Date(), revoked_reason: 'account_deleted' } }
      );

      await logAuth.adminAction(userId, req, req.requestId, 'User soft deleted', { by: adminId });
      logger.info(`Admin ${adminId} soft deleted user ${userId}`);
    }

    return sendSuccess(res, null, 'User deleted successfully');
  } catch (error) {
    next(error);
  }
};

// Restore User
const restoreUser = async (req, res, next) => {
  try {
    const { userId } = req.params;
    const adminId = req.student._id;

    const user = await Student.findOne({ _id: userId, is_deleted: true });

    if (!user) {
      return sendError(res, 'User not found or not deleted', 404, 'USER_NOT_FOUND');
    }

    await user.restore();

    await logAuth.adminAction(userId, req, req.requestId, 'User restored', { by: adminId });
    logger.info(`Admin ${adminId} restored user ${userId}`);

    return sendSuccess(res, user.toSafeObject(), 'User restored successfully');
  } catch (error) {
    next(error);
  }
};

// Bulk Action
const bulkAction = async (req, res, next) => {
  try {
    const { action, user_ids } = req.body;
    const adminId = req.student._id;

    const results = {
      success: [],
      failed: [],
    };

    for (const userId of user_ids) {
      try {
        const user = await Student.findOne({ _id: userId, is_deleted: false });

        if (!user) {
          results.failed.push({ user_id: userId, reason: 'User not found' });
          continue;
        }

        if (user._id.toString() === adminId.toString()) {
          results.failed.push({ user_id: userId, reason: 'Cannot modify your own account' });
          continue;
        }

        switch (action) {
          case 'activate':
            user.is_active = true;
            await user.save();
            await logAuth.accountUnlocked(userId, req, req.requestId);
            break;
          case 'deactivate':
            user.is_active = false;
            await user.save();
            await UserSession.updateMany(
              { student: userId, is_active: true },
              { $set: { is_active: false, is_revoked: true, revoked_at: new Date(), revoked_reason: 'bulk_deactivate' } }
            );
            break;
          case 'verify':
            user.is_verified = true;
            user.email_verified_at = new Date();
            await user.save();
            break;
          case 'delete':
            await user.softDelete(adminId);
            await UserSession.updateMany(
              { student: userId, is_active: true },
              { $set: { is_active: false, is_revoked: true, revoked_at: new Date(), revoked_reason: 'bulk_delete' } }
            );
            break;
        }

        results.success.push(userId);

        await logAuth.adminAction(userId, req, req.requestId, `Bulk ${action} executed`, { by: adminId });
      } catch (error) {
        results.failed.push({ user_id: userId, reason: error.message });
      }
    }

    logger.info(`Admin ${adminId} executed bulk ${action} on ${results.success.length} users`);

    return sendSuccess(res, results, `Bulk ${action} completed`);
  } catch (error) {
    next(error);
  }
};

// Get User Audit History
const getUserAuditHistory = async (req, res, next) => {
  try {
    const { userId } = req.params;
    const { page = 1, limit = 50 } = req.query;

    const skip = (parseInt(page) - 1) * parseInt(limit);

    const [logs, total] = await Promise.all([
      AuditLog.find({ student: userId })
        .sort({ createdAt: -1 })
        .skip(skip)
        .limit(parseInt(limit))
        .lean(),
      AuditLog.countDocuments({ student: userId }),
    ]);

    return sendSuccess(res, {
      logs,
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total,
        pages: Math.ceil(total / parseInt(limit)),
      },
    });
  } catch (error) {
    next(error);
  }
};

// Get System Stats
const getSystemStats = async (req, res, next) => {
  try {
    const now = new Date();
    const dayAgo = new Date(now - 24 * 60 * 60 * 1000);
    const weekAgo = new Date(now - 7 * 24 * 60 * 60 * 1000);
    const monthAgo = new Date(now - 30 * 24 * 60 * 60 * 1000);

    const [
      totalUsers,
      activeUsers,
      verifiedUsers,
      newUsersToday,
      newUsersThisWeek,
      newUsersThisMonth,
      usersByRole,
      usersByJavaLevel,
      deletedUsers,
    ] = await Promise.all([
      Student.countDocuments({ is_deleted: false }),
      Student.countDocuments({ is_deleted: false, is_active: true }),
      Student.countDocuments({ is_deleted: false, is_verified: true }),
      Student.countDocuments({ is_deleted: false, createdAt: { $gte: dayAgo } }),
      Student.countDocuments({ is_deleted: false, createdAt: { $gte: weekAgo } }),
      Student.countDocuments({ is_deleted: false, createdAt: { $gte: monthAgo } }),
      Student.aggregate([
        { $match: { is_deleted: false } },
        { $group: { _id: '$role', count: { $sum: 1 } } },
      ]),
      Student.aggregate([
        { $match: { is_deleted: false } },
        { $group: { _id: '$profile.java_level', count: { $sum: 1 } } },
      ]),
      Student.countDocuments({ is_deleted: true }),
    ]);

    const stats = {
      users: {
        total: totalUsers,
        active: activeUsers,
        verified: verifiedUsers,
        deleted: deletedUsers,
      },
      new_users: {
        today: newUsersToday,
        this_week: newUsersThisWeek,
        this_month: newUsersThisMonth,
      },
      by_role: usersByRole.reduce((acc, item) => {
        acc[item._id] = item.count;
        return acc;
      }, {}),
      by_java_level: usersByJavaLevel.reduce((acc, item) => {
        acc[item._id || 'not_set'] = item.count;
        return acc;
      }, {}),
    };

    return sendSuccess(res, stats);
  } catch (error) {
    next(error);
  }
};

// Export Users
const exportUsers = async (req, res, next) => {
  try {
    const { format = 'json', filters = {} } = req.body;

    const query = { is_deleted: false };
    if (filters.role) query.role = filters.role;
    if (filters.is_active !== undefined) query.is_active = filters.is_active;
    if (filters.is_verified !== undefined) query.is_verified = filters.is_verified;

    const users = await Student.find(query)
      .select('-password -refresh_token -__v')
      .lean();

    if (format === 'csv') {
      // Convert to CSV
      const headers = [
        'student_id', 'name', 'email', 'role', 'java_level', 'is_active',
        'is_verified', 'enrolled_at', 'last_active', 'country', 'institution',
      ];

      const rows = users.map(u => [
        u.student_id,
        u.name,
        u.email,
        u.role,
        u.profile?.java_level || '',
        u.is_active,
        u.is_verified,
        u.enrolled_at,
        u.last_active,
        u.profile?.country || '',
        u.profile?.institution || '',
      ]);

      const csv = [headers.join(','), ...rows.map(r => r.map(v => `"${v}"`).join(','))].join('\n');

      res.setHeader('Content-Type', 'text/csv');
      res.setHeader('Content-Disposition', 'attachment; filename="users.csv"');
      return res.send(csv);
    }

    // Default JSON
    res.setHeader('Content-Type', 'application/json');
    res.setHeader('Content-Disposition', 'attachment; filename="users.json"');
    return res.send(JSON.stringify(users, null, 2));
  } catch (error) {
    next(error);
  }
};

module.exports = {
  searchUsers,
  getUserById,
  updateUser,
  activateUser,
  deactivateUser,
  deleteUser,
  restoreUser,
  bulkAction,
  getUserAuditHistory,
  getSystemStats,
  exportUsers,
};
