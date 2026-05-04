const getDashboardStats = async (db) => {
  const totalSessions = await db.collection('ame_sessions').countDocuments();
  const activeSessions = await db.collection('ame_sessions').countDocuments({ session_status: 'active' });
  const completedSessions = await db.collection('ame_feedback_reports').countDocuments();

  const learnersResult = await db.collection('ame_sessions').distinct('learner_id');
  const totalLearners = learnersResult.length;

  const totalQuestions = await db.collection('ame_questions').countDocuments();

  const masteryUpdates = await db.collection('ame_session_updates').find({}, { projection: { current_topic_mastery: 1 } }).toArray();
  const masteryValues = masteryUpdates
    .map((u) => u.current_topic_mastery)
    .filter((v) => v != null && typeof v === 'number');
  const averageMastery = masteryValues.length > 0
    ? masteryValues.reduce((a, b) => a + b, 0) / masteryValues.length
    : 0;

  return {
    total_sessions: totalSessions,
    active_sessions: activeSessions,
    completed_sessions: completedSessions,
    total_learners: totalLearners,
    total_questions_generated: totalQuestions,
    average_mastery: Math.round(averageMastery * 100) / 100,
  };
};

const getLiveActivity = async (db, limit = 20) => {
  const updates = await db.collection('ame_session_updates')
    .find({}, {
      projection: {
        learner_id: 1,
        session_id: 1,
        topic_mastered: 1,
        session_complete: 1,
        current_topic_mastery: 1,
        remediation_mode: 1,
        remediation_entered: 1,
        remediation_exited: 1,
        update_timestamp: 1,
      },
    })
    .sort({ update_timestamp: -1 })
    .limit(limit)
    .toArray();

  return updates;
};

const getMasteryDistribution = async (db) => {
  const updates = await db.collection('ame_session_updates')
    .find({ current_topic_mastery: { $exists: true, $ne: null } }, { projection: { current_topic_mastery: 1 } })
    .toArray();

  const distribution = {
    '0-20': 0,
    '21-40': 0,
    '41-60': 0,
    '61-84': 0,
    '85-100': 0,
  };

  updates.forEach((u) => {
    const m = u.current_topic_mastery;
    if (m <= 20) distribution['0-20']++;
    else if (m <= 40) distribution['21-40']++;
    else if (m <= 60) distribution['41-60']++;
    else if (m <= 84) distribution['61-84']++;
    else distribution['85-100']++;
  });

  return distribution;
};

const getTopicPerformance = async (db) => {
  const updates = await db.collection('ame_session_updates')
    .find({ 'updated_session.topic_scores': { $exists: true } })
    .toArray();

  const topicMap = {};

  updates.forEach((u) => {
    const scores = u.updated_session && u.updated_session.topic_scores ? u.updated_session.topic_scores : {};
    Object.keys(scores).forEach((topic) => {
      if (!topicMap[topic]) {
        topicMap[topic] = { total_learners: 0, mastery_sum: 0, mastered_count: 0, questions_sum: 0, remediation_count: 0 };
      }
      topicMap[topic].total_learners++;
      topicMap[topic].mastery_sum += scores[topic] || 0;
      if ((scores[topic] || 0) >= 85) topicMap[topic].mastered_count++;
      topicMap[topic].questions_sum += (u.updated_session && u.updated_session.total_questions_asked) || 0;
      if (u.remediation_mode) topicMap[topic].remediation_count++;
    });
  });

  return Object.keys(topicMap).map((topic) => ({
    topic,
    total_learners: topicMap[topic].total_learners,
    avg_mastery: Math.round((topicMap[topic].mastery_sum / topicMap[topic].total_learners) * 100) / 100,
    mastery_rate: Math.round((topicMap[topic].mastered_count / topicMap[topic].total_learners) * 100),
    avg_questions_needed: Math.round(topicMap[topic].questions_sum / topicMap[topic].total_learners),
    remediation_count: topicMap[topic].remediation_count,
  }));
};

const getAllLearners = async (db, filters = {}, page = 1, limit = 20) => {
  const query = {};
  if (filters.skill_level) query.selected_skill_level = filters.skill_level;
  if (filters.session_status) query.session_status = filters.session_status;

  const total = await db.collection('ame_sessions').countDocuments(query);
  const sessions = await db.collection('ame_sessions')
    .find(query)
    .sort({ session_started_at: -1 })
    .skip((page - 1) * limit)
    .limit(limit)
    .toArray();

  const learnerMap = {};

  for (const session of sessions) {
    const learnerId = session.learner_id;
    if (!learnerMap[learnerId]) {
      const latestUpdate = await db.collection('ame_session_updates')
        .find({ learner_id: learnerId })
        .sort({ update_timestamp: -1 })
        .limit(1)
        .toArray();

      const totalSessionsCount = await db.collection('ame_sessions').countDocuments({ learner_id: learnerId });
      const latestSession = await db.collection('ame_sessions')
        .find({ learner_id: learnerId })
        .sort({ session_started_at: -1 })
        .limit(1)
        .toArray();

      const hasRemediation = await db.collection('ame_session_updates').countDocuments({
        learner_id: learnerId,
        remediation_entered: true,
      });

      const skillLevel = session.selected_skill_level || (session.mastery_profile && session.mastery_profile.overall_skill_level) || 'unknown';
      const topicsCount = (session.all_topics && session.all_topics.length) || 0;

      const masteryValues = [];
      for (const u of latestUpdate) {
        if (u.current_topic_mastery != null) masteryValues.push(u.current_topic_mastery);
      }
      const overallMastery = masteryValues.length > 0 ? Math.round(masteryValues.reduce((a, b) => a + b, 0) / masteryValues.length) : 0;

      const topicsMastered = latestUpdate.length > 0 && latestUpdate[0].topic_mastered ? 1 : 0;

      learnerMap[learnerId] = {
        learner_id: learnerId,
        skill_level: skillLevel,
        topics_count: topicsCount,
        session_count: totalSessionsCount,
        last_session: latestSession.length > 0 ? latestSession[0].session_id : null,
        overall_mastery: overallMastery,
        topics_mastered: topicsMastered,
        has_remediation: hasRemediation > 0,
        status: (latestSession.length > 0 ? latestSession[0].session_status : 'unknown') || 'unknown',
      };
    }
  }

  const learners = Object.values(learnerMap);

  if (filters.mastery_min != null) {
    learners.filter((l) => l.overall_mastery >= filters.mastery_min);
  }
  if (filters.mastery_max != null) {
    learners.filter((l) => l.overall_mastery <= filters.mastery_max);
  }

  return {
    learners,
    pagination: {
      page,
      limit,
      total,
      pages: Math.ceil(total / limit),
    },
  };
};

const getLearnerProfile = async (db, learnerId) => {
  const sessions = await db.collection('ame_sessions').find({ learner_id: learnerId }).toArray();
  const questions = await db.collection('ame_questions').find({ learner_id: learnerId }).toArray();
  const answers = await db.collection('ame_answers').find({ learner_id: learnerId }).toArray();
  const sessionUpdates = await db.collection('ame_session_updates').find({ learner_id: learnerId }).sort({ update_timestamp: -1 }).toArray();
  const feedbackReports = await db.collection('ame_feedback_reports').find({ learner_id: learnerId }).toArray();

  return {
    sessions,
    questions,
    answers,
    session_updates: sessionUpdates,
    feedback_reports: feedbackReports,
  };
};

const getLearnerMasteryTrend = async (db, learnerId) => {
  const updates = await db.collection('ame_session_updates')
    .find({ learner_id: learnerId }, {
      projection: {
        update_timestamp: 1,
        current_topic_mastery: 1,
        'updated_session.topic': 1,
        'updated_session.current_difficulty': 1,
      },
    })
    .sort({ update_timestamp: 1 })
    .toArray();

  return updates.map((u) => ({
    timestamp: u.update_timestamp,
    current_topic_mastery: u.current_topic_mastery,
    topic: u.updated_session ? u.updated_session.topic : null,
    difficulty: u.updated_session ? u.updated_session.current_difficulty : null,
  }));
};

const getAllSessions = async (db, filters = {}, page = 1, limit = 20) => {
  const query = {};
  if (filters.status) query.session_status = filters.status;
  if (filters.topic) query.selected_topic = filters.topic;
  if (filters.date_from || filters.date_to) {
    query.session_started_at = {};
    if (filters.date_from) query.session_started_at.$gte = new Date(filters.date_from);
    if (filters.date_to) query.session_started_at.$lte = new Date(filters.date_to);
  }

  const total = await db.collection('ame_sessions').countDocuments(query);
  const sessions = await db.collection('ame_sessions')
    .find(query)
    .sort({ session_started_at: -1 })
    .skip((page - 1) * limit)
    .limit(limit)
    .toArray();

  const sessionsWithDetails = await Promise.all(
    sessions.map(async (session) => {
      const latestUpdate = await db.collection('ame_session_updates')
        .findOne({ session_id: session.session_id }, { sort: { update_timestamp: -1 } });
      const feedbackReport = await db.collection('ame_feedback_reports')
        .findOne({ session_id: session.session_id });

      return {
        ...session,
        latest_mastery: latestUpdate ? latestUpdate.current_topic_mastery : null,
        has_feedback_report: !!feedbackReport,
      };
    })
  );

  return {
    sessions: sessionsWithDetails,
    pagination: {
      page,
      limit,
      total,
      pages: Math.ceil(total / limit),
    },
  };
};

const getSessionDetail = async (db, sessionId) => {
  const session = await db.collection('ame_sessions').findOne({ session_id: sessionId });
  const questions = await db.collection('ame_questions').find({ session_id: sessionId }).toArray();
  const answers = await db.collection('ame_answers').find({ session_id: sessionId }).toArray();
  const updates = await db.collection('ame_session_updates').find({ session_id: sessionId }).sort({ update_timestamp: 1 }).toArray();
  const feedbackReport = await db.collection('ame_feedback_reports').findOne({ session_id: sessionId });

  return {
    session,
    questions,
    answers,
    updates,
    feedback_report: feedbackReport,
  };
};

const getQuestionBank = async (db, filters = {}, page = 1, limit = 20) => {
  const query = {};
  if (filters.topic) query['current_question.topic'] = filters.topic;
  if (filters.difficulty) query.current_difficulty = filters.difficulty;
  if (filters.question_type) query['current_question.question_type'] = filters.question_type;
  if (filters.blooms_level) query['current_question.blooms_level'] = filters.blooms_level;
  if (filters.search) {
    query['current_question.question_text'] = { $regex: filters.search, $options: 'i' };
  }

  const total = await db.collection('ame_questions').countDocuments(query);
  const questions = await db.collection('ame_questions')
    .find(query)
    .sort({ question_generated_at: -1 })
    .skip((page - 1) * limit)
    .limit(limit)
    .toArray();

  return {
    questions,
    pagination: {
      page,
      limit,
      total,
      pages: Math.ceil(total / limit),
    },
  };
};

const getQuestionStats = async (db) => {
  const total = await db.collection('ame_questions').countDocuments();

  const byType = await db.collection('ame_questions').aggregate([
    { $group: { _id: '$current_question.question_type', count: { $sum: 1 } } },
  ]).toArray();

  const byDifficulty = await db.collection('ame_questions').aggregate([
    { $group: { _id: '$current_difficulty', count: { $sum: 1 } } },
  ]).toArray();

  const mostAssessedTopic = await db.collection('ame_questions').aggregate([
    { $group: { _id: '$current_question.topic', count: { $sum: 1 } } },
    { $sort: { count: -1 } },
    { $limit: 1 },
  ]).toArray();

  const typeMap = {};
  byType.forEach((t) => { typeMap[t._id || 'unknown'] = t.count; });

  const difficultyMap = {};
  byDifficulty.forEach((d) => { difficultyMap[d._id || 'unknown'] = d.count; });

  return {
    total,
    by_type: typeMap,
    by_difficulty: difficultyMap,
    most_assessed_topic: mostAssessedTopic.length > 0 ? mostAssessedTopic[0]._id : null,
  };
};

const getMasteryAnalytics = async (db, topic = null) => {
  const updates = await db.collection('ame_session_updates').toArray();

  const filteredUpdates = topic
    ? updates.filter((u) => u.updated_session && u.updated_session.topic === topic)
    : updates;

  const topicScores = {};
  const topicDistribution = {};
  const difficultyProgression = {};
  const bloomsDistribution = {};

  filteredUpdates.forEach((u) => {
    const session = u.updated_session || {};
    const scores = session.topic_scores || {};

    Object.keys(scores).forEach((t) => {
      if (!topicScores[t]) topicScores[t] = [];
      topicScores[t].push(scores[t]);
    });

    const sTopic = session.topic;
    if (sTopic) {
      topicDistribution[sTopic] = (topicDistribution[sTopic] || 0) + 1;
    }

    const diff = session.current_difficulty;
    if (diff) {
      difficultyProgression[diff] = (difficultyProgression[diff] || 0) + 1;
    }
  });

  const questions = await db.collection('ame_questions').find({}, { projection: { 'current_question.blooms_level': 1 } }).toArray();
  questions.forEach((q) => {
    const blooms = q.current_question && q.current_question.blooms_level;
    if (blooms) {
      bloomsDistribution[blooms] = (bloomsDistribution[blooms] || 0) + 1;
    }
  });

  const cohortHeatmap = {};
  Object.keys(topicScores).forEach((t) => {
    const vals = topicScores[t];
    cohortHeatmap[t] = vals.length > 0
      ? Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 100) / 100
      : 0;
  });

  return {
    cohort_mastery_heatmap: cohortHeatmap,
    topic_distribution: topicDistribution,
    difficulty_progression: difficultyProgression,
    blooms_distribution: bloomsDistribution,
  };
};

const getRemediationSummary = async (db) => {
  const remediationEntries = await db.collection('ame_session_updates')
    .find({ remediation_entered: true })
    .toArray();

  const totalActivations = remediationEntries.length;
  const currentlyActive = remediationEntries.filter((r) => r.remediation_mode).length;

  let successCount = 0;
  let totalQuestions = 0;
  const episodes = [];

  const sessionIds = [...new Set(remediationEntries.map((r) => r.session_id))];

  for (const sessionId of sessionIds) {
    const sessionEntries = remediationEntries.filter((r) => r.session_id === sessionId);
    const latest = sessionEntries[sessionEntries.length - 1];

    let questionsInRemediation = 0;
    sessionEntries.forEach((e) => {
      if (e.updated_session && e.updated_session.remeditation_questions != null) {
        questionsInRemediation = Math.max(questionsInRemediation, e.updated_session.remeditation_questions);
      }
    });
    if (latest && latest.updated_session && latest.updated_session.remediation_questions != null) {
      questionsInRemediation = latest.updated_session.remediation_questions;
    }

    const exited = sessionEntries.some((e) => e.remediation_exited);
    if (exited) successCount++;

    totalQuestions += questionsInRemediation;

    episodes.push({
      session_id: sessionId,
      learner_id: latest ? latest.learner_id : null,
      entered_at: sessionEntries.length > 0 ? sessionEntries[0].update_timestamp : null,
      exited: exited,
      questions_in_remediation: questionsInRemediation,
      topic: latest && latest.updated_session ? latest.updated_session.topic : null,
    });
  }

  const avgQuestions = episodes.length > 0 ? Math.round(totalQuestions / episodes.length) : 0;
  const successRate = episodes.length > 0 ? Math.round((successCount / episodes.length) * 100) : 0;

  return {
    total_activations: totalActivations,
    success_rate: successRate,
    currently_active: currentlyActive,
    avg_questions_in_remediation: avgQuestions,
    episodes,
  };
};

const getRemediationByTopic = async (db) => {
  const remediationEntries = await db.collection('ame_session_updates')
    .find({ remediation_entered: true })
    .toArray();

  const topicMap = {};

  remediationEntries.forEach((r) => {
    const topic = r.updated_session ? r.updated_session.topic : null;
    if (!topic) return;

    if (!topicMap[topic]) {
      topicMap[topic] = { entries: [], masteryBefore: [], masteryAfter: [] };
    }

    topicMap[topic].entries.push(r);
    if (r.mastery_calculation) {
      if (r.mastery_calculation.previous_mastery != null) {
        topicMap[topic].masteryBefore.push(r.mastery_calculation.previous_mastery);
      }
      if (r.mastery_calculation.current_mastery != null) {
        topicMap[topic].masteryAfter.push(r.mastery_calculation.current_mastery);
      }
    }
  });

  return Object.keys(topicMap)
    .map((topic) => {
      const data = topicMap[topic];
      const avgBefore = data.masteryBefore.length > 0 ? data.masteryBefore.reduce((a, b) => a + b, 0) / data.masteryBefore.length : 0;
      const avgAfter = data.masteryAfter.length > 0 ? data.masteryAfter.reduce((a, b) => a + b, 0) / data.masteryAfter.length : 0;
      return {
        topic,
        total_episodes: data.entries.length,
        avg_mastery_before: Math.round(avgBefore * 100) / 100,
        avg_mastery_after: Math.round(avgAfter * 100) / 100,
        avg_mastery_improvement: Math.round((avgAfter - avgBefore) * 100) / 100,
      };
    })
    .sort((a, b) => b.total_episodes - a.total_episodes);
};

const getAllFeedbackReports = async (db, filters = {}, page = 1, limit = 20) => {
  const query = {};
  if (filters.grade) query['feedback_report.overall_grade'] = filters.grade;
  if (filters.learner_id) query.learner_id = filters.learner_id;
  if (filters.date_from || filters.date_to) {
    query.generated_at = {};
    if (filters.date_from) query.generated_at.$gte = new Date(filters.date_from);
    if (filters.date_to) query.generated_at.$lte = new Date(filters.date_to);
  }

  const total = await db.collection('ame_feedback_reports').countDocuments(query);
  const reports = await db.collection('ame_feedback_reports')
    .find(query)
    .sort({ generated_at: -1 })
    .skip((page - 1) * limit)
    .limit(limit)
    .toArray();

  const reportsSummary = reports.map((r) => {
    const report = r.feedback_report || {};
    const summary = r.session_summary || {};
    const qaReview = r.full_qa_review || [];

    return {
      session_id: r.session_id,
      learner_id: r.learner_id,
      generated_at: r.generated_at,
      overall_grade: report.overall_grade || null,
      overall_mastery_percentage: report.overall_mastery_percentage || null,
      overall_accuracy_percentage: report.overall_accuracy_percentage || null,
      total_questions: qaReview.length,
      topics_covered: (report.topics_covered && report.topics_covered.length) || (summary.topics_covered && summary.topics_covered.length) || 0,
      session_duration_minutes: summary.session_duration_minutes || null,
    };
  });

  return {
    reports: reportsSummary,
    pagination: {
      page,
      limit,
      total,
      pages: Math.ceil(total / limit),
    },
  };
};

const getFeedbackReport = async (db, sessionId) => {
  const report = await db.collection('ame_feedback_reports').findOne({ session_id: sessionId });
  return report;
};

const getGradeDistribution = async (db) => {
  const distribution = {
    Excellent: 0,
    Good: 0,
    Satisfactory: 0,
    'Needs Improvement': 0,
    Poor: 0,
  };

  const reports = await db.collection('ame_feedback_reports')
    .find({ 'feedback_report.overall_grade': { $exists: true } })
    .toArray();

  reports.forEach((r) => {
    const grade = r.feedback_report.overall_grade;
    if (distribution[grade] != null) {
      distribution[grade]++;
    }
  });

  return distribution;
};

const getCommonMisconceptions = async (db, limit = 20) => {
  const reports = await db.collection('ame_feedback_reports')
    .find({ 'feedback_report.misconceptions_to_address': { $exists: true, $ne: null } })
    .toArray();

  const misconceptionCount = {};

  reports.forEach((r) => {
    const misconceptions = r.feedback_report.misconceptions_to_address || [];
    misconceptions.forEach((m) => {
      if (typeof m === 'string') {
        misconceptionCount[m] = (misconceptionCount[m] || 0) + 1;
      }
    });
  });

  return Object.keys(misconceptionCount)
    .map((misconception) => ({ misconception, count: misconceptionCount[misconception] }))
    .sort((a, b) => b.count - a.count)
    .slice(0, limit);
};

module.exports = {
  getDashboardStats,
  getLiveActivity,
  getMasteryDistribution,
  getTopicPerformance,
  getAllLearners,
  getLearnerProfile,
  getLearnerMasteryTrend,
  getAllSessions,
  getSessionDetail,
  getQuestionBank,
  getQuestionStats,
  getMasteryAnalytics,
  getRemediationSummary,
  getRemediationByTopic,
  getAllFeedbackReports,
  getFeedbackReport,
  getGradeDistribution,
  getCommonMisconceptions,
};
